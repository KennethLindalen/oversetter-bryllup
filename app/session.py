import random
import string
from dataclasses import dataclass, field
from fastapi import WebSocket
import json


@dataclass
class Session:
    code: str
    admin_ws: WebSocket | None = None
    clients: dict[str, WebSocket] = field(default_factory=dict)
    client_langs: dict[str, str] = field(default_factory=dict)  # client_id → lang
    active: bool = True

    def needed_langs(self) -> set[str]:
        return set(self.client_langs.values()) or {"en", "no", "ru"}


class SessionStore:
    def __init__(self):
        self._sessions: dict[str, Session] = {}

    def create(self) -> Session:
        code = self._generate_code()
        session = Session(code=code)
        self._sessions[code] = session
        return session

    def get(self, code: str) -> Session | None:
        return self._sessions.get(code.upper())

    def remove(self, code: str):
        self._sessions.pop(code.upper(), None)

    async def broadcast(self, code: str, message: dict):
        session = self.get(code)
        if not session:
            return
        data = json.dumps(message)
        dead = []
        for client_id, ws in session.clients.items():
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(client_id)
        for client_id in dead:
            session.clients.pop(client_id, None)

    async def broadcast_all(self, code: str, message: dict):
        """Broadcast to admin + all clients."""
        session = self.get(code)
        if not session:
            return
        data = json.dumps(message)
        if session.admin_ws:
            try:
                await session.admin_ws.send_text(data)
            except Exception:
                session.admin_ws = None
        await self.broadcast(code, message)

    def user_count(self, code: str) -> int:
        session = self.get(code)
        return len(session.clients) if session else 0

    def _generate_code(self) -> str:
        chars = string.ascii_uppercase + string.digits
        while True:
            code = "".join(random.choices(chars, k=4))
            if code not in self._sessions:
                return code


store = SessionStore()
