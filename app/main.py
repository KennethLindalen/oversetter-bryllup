import os
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from .session import store
from .translation import translate_all

load_dotenv()

app = FastAPI()
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


# ── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/{code}/{role}")
async def websocket_endpoint(websocket: WebSocket, code: str, role: str):
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
        await store.broadcast_all(code, {"type": "user_count", "count": store.user_count(code)})

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "transcript" and role == "admin":
                text = data.get("text", "").strip()
                is_final = data.get("is_final", False)
                if not text:
                    continue

                source_lang = data.get("source", "en")
                if is_final:
                    translations = await translate_all(text, source=source_lang)
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
            if session.active:
                await store.broadcast_all(code, {"type": "user_count", "count": store.user_count(code)})
