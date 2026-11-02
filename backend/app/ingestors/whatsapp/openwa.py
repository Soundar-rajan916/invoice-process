from __future__ import annotations

import base64
import hashlib
import hmac
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.logging import logger
from app.ingestors.upload import detect_content_type
from app.ingestors.whatsapp.models import (
    InboundWhatsAppMessage,
    MediaRef,
    ProviderSendResult,
    SessionStatus,
    SessionStatusEvent,
)
from app.ingestors.whatsapp.provider import (
    MediaTooLargeError,
    UnrecognizedPayloadError,
    WhatsAppProvider,
)


class OpenWAProvider(WhatsAppProvider):
    """WhatsApp Provider implementing OpenWA Gateway (whatsapp-web.js / Baileys)."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        session_id: str | None = None,
        webhook_secret: str | None = None,
        allow_groups: bool | None = None,
        allowed_senders: list[str] | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OPENWA_BASE_URL).rstrip("/")
        self.api_key = api_key if api_key is not None else settings.OPENWA_API_KEY
        self.session_id = (
            session_id
            if session_id is not None
            else (settings.OPENWA_SESSION_ID or settings.OPENWA_SESSION_NAME)
        )
        self.webhook_secret = (
            webhook_secret if webhook_secret is not None else settings.OPENWA_WEBHOOK_SECRET
        )
        self.allow_groups = (
            allow_groups if allow_groups is not None else settings.OPENWA_ALLOW_GROUPS
        )
        self.allowed_senders = (
            allowed_senders if allowed_senders is not None else settings.OPENWA_ALLOWED_SENDERS
        )
        self.max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    def verify_request(self, headers: dict[str, str], raw_body: bytes) -> None:
        """Verifies the X-OpenWA-Signature HMAC-SHA256 header.

        Header format: sha256=<hex_digest>
        Must use constant-time comparison. Missing, malformed or invalid signature returns 401.
        """
        # Look up header case-insensitively
        sig_header = None
        for k, v in headers.items():
            if k.lower() == "x-openwa-signature":
                sig_header = v
                break

        if not sig_header or not self.webhook_secret:
            logger.warning("OpenWA signature verification rejected: missing header or secret")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing webhook signature or secret unconfigured",
            )

        if not sig_header.startswith("sha256="):
            logger.warning("OpenWA signature verification rejected: malformed signature format")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid signature header format",
            )

        received_sig = sig_header[7:].strip()
        expected_sig = hmac.new(
            self.webhook_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(received_sig, expected_sig):
            logger.warning("OpenWA signature verification rejected: hash mismatch")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    def parse(self, payload: dict[str, Any]) -> list[InboundWhatsAppMessage] | SessionStatusEvent:
        """Parses an OpenWA webhook JSON payload."""
        event_type = payload.get("event") or payload.get("type")
        if not event_type:
            # Fallback inspection
            if "data" in payload and "id" in payload.get("data", {}):
                event_type = "message.received"
            elif "state" in payload or "status" in payload:
                event_type = "session.status"
            else:
                field_names = list(payload.keys())
                logger.warning("Unrecognized OpenWA payload shape", payload_fields=field_names)
                raise UnrecognizedPayloadError("Unknown payload structure", payload_keys=field_names)

        session_ref = str(payload.get("sessionId") or self.session_id)

        # 1. Session Status Events
        if event_type in ("session.status", "session.state.changed"):
            raw_state = str(
                payload.get("data", {}).get("state")
                or payload.get("data", {}).get("status")
                or payload.get("status")
                or payload.get("state")
                or "unknown"
            ).upper()

            normalized_status: SessionStatus = "unknown"
            if raw_state in ("CONNECTED", "WORKING", "READY", "ONLINE"):
                normalized_status = "connected"
            elif raw_state in ("QR", "SCAN_QR_CODE", "NEEDS_QR", "UNPAIRED"):
                normalized_status = "needs_qr"
            elif raw_state in ("DISCONNECTED", "STOPPED", "CONFLICT", "UNLAUNCHED", "OFFLINE"):
                normalized_status = "disconnected"

            return SessionStatusEvent(
                session_id=session_ref,
                status=normalized_status,
                timestamp=datetime.now(UTC),
                detail=payload.get("data") or payload,
            )

        # 2. Inbound Message Received Events
        if event_type == "message.received":
            data = payload.get("data")
            if not isinstance(data, dict):
                field_names = list(payload.keys())
                logger.warning("message.received missing 'data' dict", payload_fields=field_names)
                raise UnrecognizedPayloadError("message.received missing data", payload_keys=field_names)

            msg_id = str(data.get("id") or "")
            if not msg_id:
                field_names = list(data.keys())
                logger.warning("message.received missing message 'id'", data_fields=field_names)
                raise UnrecognizedPayloadError("Message missing id", payload_keys=field_names)

            chat_id = str(data.get("from") or data.get("chatId") or "")
            sender_id = str(data.get("sender") or data.get("author") or chat_id)
            is_group = bool(data.get("isGroup") or chat_id.endswith("@g.us"))
            from_me = bool(data.get("fromMe", False))
            msg_type = str(data.get("type") or "chat").lower()
            caption = data.get("caption") or data.get("body") if msg_type in ("image", "document") else None
            filename = data.get("filename")

            # Parse timestamp
            ts_val = data.get("timestamp")
            if isinstance(ts_val, (int, float)):
                # Could be epoch seconds or ms
                epoch_sec = ts_val if ts_val < 10_000_000_000 else ts_val / 1000.0
                msg_time = datetime.fromtimestamp(epoch_sec, tz=UTC)
            elif isinstance(ts_val, str) and ts_val:
                try:
                    msg_time = datetime.fromisoformat(ts_val.replace("Z", "+00:00"))
                except Exception:
                    msg_time = datetime.now(UTC)
            else:
                msg_time = datetime.now(UTC)

            # Idempotency key: {session_id}:{message_id}
            external_id = f"{session_ref}:{msg_id}"

            # Parse media reference
            media_ref: MediaRef | None = None
            media_obj = data.get("media") or data.get("mediaData")
            mimetype = data.get("mimetype")

            if isinstance(media_obj, dict):
                mimetype = media_obj.get("mimetype") or mimetype
                filename = media_obj.get("filename") or filename
                size_bytes = int(media_obj.get("sizeBytes") or media_obj.get("size") or 0)
                is_oversized = bool(media_obj.get("omitted", False) or media_obj.get("isOversized", False))

                raw_b64 = media_obj.get("data") or media_obj.get("base64")
                inline_bytes = None
                if raw_b64 and isinstance(raw_b64, str):
                    try:
                        clean_b64 = raw_b64.split(",")[-1] if "," in raw_b64 else raw_b64
                        inline_bytes = base64.b64decode(clean_b64)
                        size_bytes = len(inline_bytes)
                    except Exception as err:
                        logger.warning("Failed to decode base64 media", error=str(err))

                media_ref = MediaRef(
                    data=inline_bytes,
                    url=media_obj.get("url"),
                    size_bytes=size_bytes,
                    mimetype=mimetype,
                    is_oversized=is_oversized,
                )
            elif data.get("base64"):
                try:
                    raw_b64 = data["base64"]
                    clean_b64 = raw_b64.split(",")[-1] if "," in raw_b64 else raw_b64
                    inline_bytes = base64.b64decode(clean_b64)
                    media_ref = MediaRef(
                        data=inline_bytes,
                        url=None,
                        size_bytes=len(inline_bytes),
                        mimetype=mimetype,
                        is_oversized=False,
                    )
                except Exception as err:
                    logger.warning("Failed to decode inline base64 media", error=str(err))
            elif data.get("mediaUrl") or data.get("url"):
                media_ref = MediaRef(
                    data=None,
                    url=data.get("mediaUrl") or data.get("url"),
                    size_bytes=int(data.get("sizeBytes") or 0),
                    mimetype=mimetype,
                    is_oversized=bool(data.get("omitted", False)),
                )
            elif msg_type in ("image", "document"):
                # Media message without media payload (e.g. dropped by gateway or omitted)
                is_oversized = bool(data.get("isOversized") or data.get("omitted"))
                media_ref = MediaRef(
                    data=None,
                    url=None,
                    size_bytes=int(data.get("sizeBytes") or 0),
                    mimetype=mimetype,
                    is_oversized=is_oversized or True,  # If type is media but data is missing
                )

            norm_msg = InboundWhatsAppMessage(
                external_id=external_id,
                session_ref=session_ref,
                chat_id=chat_id,
                sender_id=sender_id,
                is_group=is_group,
                from_me=from_me,
                message_type=msg_type,
                timestamp=msg_time,
                caption=caption,
                filename=filename,
                mimetype=mimetype,
                media=media_ref,
                raw_payload=payload,
            )
            return [norm_msg]

        # Ignore or log other events
        logger.info("Ignored non-intake OpenWA webhook event", event=event_type)
        return []

    async def fetch_media(self, msg: InboundWhatsAppMessage) -> bytes:
        """Decodes inline media or downloads authenticated URL."""
        if not msg.media:
            raise MediaTooLargeError("No media attached to message", size_bytes=0)

        if msg.media.is_oversized:
            raise MediaTooLargeError("Media omitted by gateway as oversized", size_bytes=msg.media.size_bytes)

        # 1. Inline bytes
        if msg.media.data:
            content_bytes = msg.media.data
            if len(content_bytes) > self.max_bytes:
                raise MediaTooLargeError(
                    f"Media exceeds maximum allowed size ({len(content_bytes)} > {self.max_bytes})",
                    size_bytes=len(content_bytes),
                )
            real_type = detect_content_type(content_bytes, msg.mimetype or "application/octet-stream")
            if real_type not in (
                "application/pdf",
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
            ):
                raise ValueError(f"Unsupported media content type: {real_type}")
            return content_bytes

        # 2. Authenticated URL
        if msg.media.url:
            headers = {"X-API-Key": self.api_key} if self.api_key else {}
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
                resp = await client.get(msg.media.url, headers=headers)
                resp.raise_for_status()
                content_bytes = resp.content

            if len(content_bytes) > self.max_bytes:
                raise MediaTooLargeError(
                    f"Downloaded media exceeds maximum allowed size ({len(content_bytes)} > {self.max_bytes})",
                    size_bytes=len(content_bytes),
                )
            real_type = detect_content_type(content_bytes, msg.mimetype or "application/octet-stream")
            if real_type not in (
                "application/pdf",
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
            ):
                raise ValueError(f"Unsupported media content type: {real_type}")
            return content_bytes

        raise MediaTooLargeError("Media data unavailable", size_bytes=0)

    async def send_text(self, chat_id: str, text: str) -> ProviderSendResult:
        """Sends an outbound text message to a specific chat ID via OpenWA REST API."""
        url = f"{self.base_url}/sessions/{self.session_id}/messages/send-text"
        headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.api_key,
        }
        payload = {"chatId": chat_id, "text": text}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                msg_id = data.get("id") or data.get("messageId") or f"openwa-{datetime.now(UTC).timestamp()}"
                return ProviderSendResult(success=True, message_id=str(msg_id))
        except Exception as e:
            logger.error("OpenWA send_text failed", chat_id=chat_id, error=str(e))
            return ProviderSendResult(success=False, error=str(e))

    async def session_status(self) -> SessionStatus:
        """Fetches current session status from OpenWA."""
        url = f"{self.base_url}/sessions/{self.session_id}"
        headers = {"X-API-Key": self.api_key} if self.api_key else {}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 404:
                    return "disconnected"
                resp.raise_for_status()
                data = resp.json()
                raw_state = str(data.get("status") or data.get("state") or "unknown").upper()
                if raw_state in ("CONNECTED", "WORKING", "READY", "ONLINE"):
                    return "connected"
                elif raw_state in ("QR", "SCAN_QR_CODE", "NEEDS_QR", "UNPAIRED"):
                    return "needs_qr"
                elif raw_state in ("DISCONNECTED", "STOPPED", "CONFLICT", "OFFLINE"):
                    return "disconnected"
                return "unknown"
        except Exception as e:
            logger.warning("Could not query OpenWA session status", error=str(e))
            return "unknown"

    async def healthcheck(self) -> bool:
        """Checks if OpenWA gateway is reachable."""
        url = f"{self.base_url}/health"
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                return resp.status_code < 400
        except Exception:
            return False
