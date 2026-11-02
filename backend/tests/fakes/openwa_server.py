"""Fake OpenWA Gateway Server for automated testing.

Implements the OpenWA REST API endpoints:
- POST /api/sessions: Start or register a new session
- POST /api/sessions/{sessionId}/start: Start a session
- GET /api/sessions/{sessionId}/status: Check session status (connected, needs_qr, etc.)
- GET /api/sessions/{sessionId}/qr: Fetch current QR code
- POST /api/sessions/{sessionId}/webhooks: Register webhook subscription
- POST /api/sessions/{sessionId}/messages/send-text: Send a text message
- GET /api/health: OpenWA health check
"""
from __future__ import annotations

import hashlib
import hmac
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    name: str


class RegisterWebhookRequest(BaseModel):
    url: str
    events: list[str]
    secret: str | None = None


class SendTextRequest(BaseModel):
    chatId: str
    text: str


class FakeOpenWAServer:
    def __init__(self, api_key: str = "test-openwa-admin-key") -> None:
        self.api_key = api_key
        self.sessions: dict[str, dict[str, Any]] = {}
        self.webhooks: dict[str, list[dict[str, Any]]] = {}
        self.sent_messages: list[dict[str, Any]] = []
        self.session_state = "connected"  # connected | needs_qr | disconnected
        self.app = FastAPI(title="Fake OpenWA Gateway")
        self._setup_routes()

    def _verify_auth(self, x_api_key: str | None, authorization: str | None) -> None:
        token = x_api_key
        if not token and authorization:
            parts = authorization.split()
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
        if token != self.api_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

    def _setup_routes(self) -> None:
        @self.app.get("/api/health")
        async def health():
            return {"status": "ok", "engine": "whatsapp-web.js"}

        @self.app.post("/api/sessions")
        async def create_session(
            req: CreateSessionRequest,
            x_api_key: str | None = Header(None),
            authorization: str | None = Header(None),
        ):
            self._verify_auth(x_api_key, authorization)
            # Idempotent by name or generate session id
            for _sid, s in self.sessions.items():
                if s["name"] == req.name:
                    return s
            sid = f"sess_{uuid.uuid4().hex[:12]}"
            session_data = {
                "id": sid,
                "name": req.name,
                "status": self.session_state,
            }
            self.sessions[sid] = session_data
            self.webhooks[sid] = []
            return session_data

        @self.app.post("/api/sessions/{sessionId}/start")
        async def start_session(
            sessionId: str,
            x_api_key: str | None = Header(None),
            authorization: str | None = Header(None),
        ):
            self._verify_auth(x_api_key, authorization)
            if sessionId not in self.sessions:
                raise HTTPException(status_code=404, detail="Session not found")
            self.sessions[sessionId]["status"] = self.session_state
            return {"status": "starting", "sessionId": sessionId}

        @self.app.get("/api/sessions/{sessionId}/status")
        async def get_session_status(
            sessionId: str,
            x_api_key: str | None = Header(None),
            authorization: str | None = Header(None),
        ):
            self._verify_auth(x_api_key, authorization)
            if sessionId not in self.sessions:
                raise HTTPException(status_code=404, detail="Session not found")
            return {
                "sessionId": sessionId,
                "status": self.session_state,
            }

        @self.app.get("/api/sessions/{sessionId}/qr")
        async def get_session_qr(
            sessionId: str,
            x_api_key: str | None = Header(None),
            authorization: str | None = Header(None),
        ):
            self._verify_auth(x_api_key, authorization)
            if sessionId not in self.sessions:
                raise HTTPException(status_code=404, detail="Session not found")
            return {
                "sessionId": sessionId,
                "qr": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            }

        @self.app.post("/api/sessions/{sessionId}/webhooks")
        async def register_webhook(
            sessionId: str,
            req: RegisterWebhookRequest,
            x_api_key: str | None = Header(None),
            authorization: str | None = Header(None),
        ):
            self._verify_auth(x_api_key, authorization)
            if sessionId not in self.sessions:
                raise HTTPException(status_code=404, detail="Session not found")
            entry = req.model_dump()
            self.webhooks[sessionId].append(entry)
            return {"status": "ok", "url": req.url, "events": req.events}

        @self.app.post("/api/sessions/{sessionId}/messages/send-text")
        async def send_text(
            sessionId: str,
            req: SendTextRequest,
            x_api_key: str | None = Header(None),
            authorization: str | None = Header(None),
        ):
            self._verify_auth(x_api_key, authorization)
            if sessionId not in self.sessions:
                raise HTTPException(status_code=404, detail="Session not found")
            msg_id = f"wamid_{uuid.uuid4().hex[:16]}"
            record = {
                "id": msg_id,
                "sessionId": sessionId,
                "chatId": req.chatId,
                "text": req.text,
            }
            self.sent_messages.append(record)
            return {
                "status": "sent",
                "id": msg_id,
                "chatId": req.chatId,
            }

    @staticmethod
    def sign_payload(body_bytes: bytes, secret: str) -> str:
        """Compute HMAC-SHA256 signature formatted as sha256=<hex>."""
        digest = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()
        return f"sha256={digest}"
