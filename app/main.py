import os
import re
import time
import uuid
from pathlib import Path

import httpx

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, UploadFile, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from .session import store
from .translation import translate_all, close_client

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await close_client()


app = FastAPI(lifespan=lifespan)
BUILD_ID = str(int(time.time()))

BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.globals["build_id"] = BUILD_ID


class IframeHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "ALLOWALL"
        response.headers["Content-Security-Policy"] = "frame-ancestors *"
        return response


app.add_middleware(IframeHeadersMiddleware)


# ── HTTP routes ──────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return RedirectResponse(url="/join")


@app.get("/join", response_class=HTMLResponse)
async def join_page(request: Request):
    return templates.TemplateResponse(request, "join.html")


@app.get("/session/{code}", response_class=HTMLResponse)
async def session_page(request: Request, code: str, lang: str = "en"):
    session = store.get(code)
    if not session or not session.active:
        return RedirectResponse(url="/join")
    return templates.TemplateResponse(request, "session.html", {"code": code.upper(), "lang": lang})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    return templates.TemplateResponse(request, "admin.html")


# ── API routes ───────────────────────────────────────────────────────────────

@app.post("/api/auth/admin")
async def auth_admin(request: Request):
    body = await request.json()
    keyphrase = os.getenv("ADMIN_KEYPHRASE", "")
    if not keyphrase or body.get("keyphrase") != keyphrase:
        raise HTTPException(status_code=403, detail="Invalid keyphrase")
    return {"ok": True}


@app.post("/api/session/start")
async def session_start(request: Request):
    body = await request.json()
    keyphrase = os.getenv("ADMIN_KEYPHRASE", "")
    if not keyphrase or body.get("keyphrase") != keyphrase:
        raise HTTPException(status_code=403, detail="Unauthorized")
    session = store.create()
    return {"code": session.code}


@app.get("/api/session/{code}/exists")
async def session_exists(code: str):
    session = store.get(code)
    if not session or not session.active:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}


@app.post("/api/session/end")
async def session_end(request: Request):
    body = await request.json()
    keyphrase = os.getenv("ADMIN_KEYPHRASE", "")
    if not keyphrase or body.get("keyphrase") != keyphrase:
        raise HTTPException(status_code=403, detail="Unauthorized")
    code = body.get("code", "").upper()
    session = store.get(code)
    if session:
        session.active = False
        await store.broadcast_all(code, {"type": "session_end"})
        store.remove(code)
    return {"ok": True}


# ── Transcription ────────────────────────────────────────────────────────────

WHISPER_LANG = {"en": "en", "no": "no", "nb": "no", "ru": "ru"}


@app.post("/api/transcribe")
async def transcribe(
    audio: UploadFile,
    code: str = Form(...),
    keyphrase: str = Form(...),
    lang: str = Form("no"),
):
    if keyphrase != os.getenv("ADMIN_KEYPHRASE", ""):
        raise HTTPException(status_code=403, detail="Unauthorized")

    session = store.get(code.upper())
    if not session or not session.active:
        raise HTTPException(status_code=404, detail="Session not found")

    audio_bytes = await audio.read()
    if len(audio_bytes) < 1500:
        return {"ok": True, "skipped": True}

    openai_key = os.getenv("OPENAI_API_KEY", "")
    if not openai_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not set")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {openai_key}"},
            files={"file": ("audio.webm", audio_bytes, "audio/webm")},
            data={
                "model": "whisper-1",
                "language": WHISPER_LANG.get(lang, "no"),
                "response_format": "verbose_json",
            },
        )
        if resp.status_code == 429:
            raise HTTPException(status_code=429, detail="OpenAI rate limit — speak in longer chunks or wait a moment")
        resp.raise_for_status()
        body = resp.json()

    text = body.get("text", "").strip()
    if not text:
        return {"ok": True, "skipped": True}

    # Discard chunks that are almost certainly silence/noise
    segments = body.get("segments", [])
    if segments:
        avg_no_speech = sum(s.get("no_speech_prob", 0) for s in segments) / len(segments)
        if avg_no_speech > 0.7:
            return {"ok": True, "skipped": True}

    # Discard known hallucination patterns (subtitle credits, filler phrases)
    _HALLUCINATION_RE = re.compile(
        r"\bsubtitl|\btekst\w*\s+av|undertekster\s+av|\btranscribed\s+by|"
        r"ai.?media|\bcaptioned\s+by|thank\s+you\s+for\s+(watching|listening)|"
        r"takk\s+for\s+at\s+du",
        re.IGNORECASE,
    )
    if _HALLUCINATION_RE.search(text):
        return {"ok": True, "skipped": True}

    translations = await translate_all(text, source=lang, needed=session.needed_langs())

    await store.broadcast(code.upper(), {
        "type": "transcript",
        "original": text,
        "translations": translations,
        "is_final": True,
    })

    return {"ok": True, "text": text}


# ── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/{code}/{role}")
async def websocket_endpoint(websocket: WebSocket, code: str, role: str, lang: str = "en"):
    code = code.upper()
    session = store.get(code)
    if not session or not session.active:
        await websocket.close(code=4004)
        return

    await websocket.accept()
    client_id = str(uuid.uuid4())

    if role == "admin":
        session.admin_ws = websocket
    else:
        session.clients[client_id] = websocket
        session.client_langs[client_id] = lang
        await store.broadcast_all(code, {"type": "user_count", "count": store.user_count(code)})

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "set_lang" and role != "admin":
                session.client_langs[client_id] = data.get("lang", "en")

            elif msg_type == "transcript" and role == "admin":
                text = data.get("text", "").strip()
                is_final = data.get("is_final", False)
                if not text:
                    continue

                source_lang = data.get("source", "en")
                if is_final:
                    translations = await translate_all(
                        text, source=source_lang, needed=session.needed_langs()
                    )
                else:
                    translations = {"en": text, "no": text, "ru": text}

                await store.broadcast(code, {
                    "type": "transcript",
                    "original": text,
                    "translations": translations,
                    "is_final": is_final,
                })

    except WebSocketDisconnect:
        pass
    finally:
        if role == "admin":
            session.admin_ws = None
        else:
            session.clients.pop(client_id, None)
            session.client_langs.pop(client_id, None)
            if session.active:
                await store.broadcast_all(code, {"type": "user_count", "count": store.user_count(code)})
