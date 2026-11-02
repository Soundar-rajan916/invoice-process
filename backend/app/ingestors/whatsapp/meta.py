from __future__ import annotations

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


class MetaCloudProvider(WhatsAppProvider):
    """Official Meta WhatsApp Business Cloud API Provider."""

    def __init__(self) -> None:
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.token = settings.WHATSAPP_API_TOKEN
        self.app_secret = settings.WHATSAPP_APP_SECRET
        self.verify_token = settings.WHATSAPP_VERIFY_TOKEN or "invoiceflow-verify-token"
        self.resend_template = settings.WHATSAPP_RESEND_TEMPLATE
        self.max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024

    def verify_request(self, headers: dict[str, str], raw_body: bytes) -> None:
        """Verifies X-Hub-Signature-256 HMAC header using constant-time comparison."""
        sig_header = None
        for k, v in headers.items():
            if k.lower() == "x-hub-signature-256":
                sig_header = v
                break

        if not sig_header or not self.app_secret:
            logger.warning("Meta webhook rejected: missing X-Hub-Signature-256")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

        if not sig_header.startswith("sha256="):
            logger.warning("Meta webhook rejected: malformed signature format")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

        received_sig = sig_header[7:].strip()
        expected_sig = hmac.new(
            self.app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(received_sig, expected_sig):
            logger.warning("Meta webhook rejected: signature mismatch")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    def verify_handshake(self, mode: str, token: str, challenge: str) -> str:
        """Handles Meta GET hub.challenge handshake."""
        if mode == "subscribe" and token == self.verify_token:
            return challenge
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")

    def parse(self, payload: dict[str, Any]) -> list[InboundWhatsAppMessage] | SessionStatusEvent:
        """Parses Meta Cloud API webhook envelope."""
        entry_list = payload.get("entry")
        if not isinstance(entry_list, list):
            field_names = list(payload.keys())
            logger.warning("Unrecognized Meta payload shape", payload_fields=field_names)
            raise UnrecognizedPayloadError("Meta payload missing entry list", payload_keys=field_names)

        results: list[InboundWhatsAppMessage] = []

        for entry in entry_list:
            for change in entry.get("changes", []):
                val = change.get("value", {})
                messages = val.get("messages", [])
                for msg in messages:
                    msg_id = str(msg.get("id"))
                    sender = str(msg.get("from"))
                    msg_type = str(msg.get("type", "chat"))
                    ts_raw = msg.get("timestamp")
                    try:
                        timestamp = datetime.fromtimestamp(float(ts_raw), tz=UTC) if ts_raw else datetime.now(UTC)
                    except Exception:
                        timestamp = datetime.now(UTC)

                    caption = None
                    filename = None
                    media_id = None
                    mimetype = None

                    if msg_type == "image":
                        img_data = msg.get("image", {})
                        media_id = img_data.get("id")
                        caption = img_data.get("caption")
                        mimetype = img_data.get("mime_type")
                    elif msg_type == "document":
                        doc_data = msg.get("document", {})
                        media_id = doc_data.get("id")
                        filename = doc_data.get("filename")
                        caption = doc_data.get("caption")
                        mimetype = doc_data.get("mime_type")

                    media_ref = None
                    if media_id:
                        # Meta Graph API media lookup URL
                        media_ref = MediaRef(
                            url=f"https://graph.facebook.com/v20.0/{media_id}",
                            mimetype=mimetype,
                        )

                    results.append(
                        InboundWhatsAppMessage(
                            external_id=msg_id,
                            session_ref="meta",
                            chat_id=sender,
                            sender_id=sender,
                            is_group=False,
                            from_me=False,
                            message_type=msg_type,
                            timestamp=timestamp,
                            caption=caption,
                            filename=filename,
                            mimetype=mimetype,
                            media=media_ref,
                            raw_payload=payload,
                        )
                    )

        return results

    async def fetch_media(self, msg: InboundWhatsAppMessage) -> bytes:
        """Downloads media via Meta Graph API two-step fetch."""
        if not msg.media or not msg.media.url:
            raise MediaTooLargeError("No media reference in Meta message")

        if settings.ENVIRONMENT == "test":
            from app.services.whatsapp import get_whatsapp_client

            client = get_whatsapp_client()
            return await client.download_media(msg.media.url)

        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(msg.media.url, headers=headers)
            resp.raise_for_status()
            download_url = resp.json().get("url")

        if not download_url:
            raise MediaTooLargeError("Meta Graph API returned no download URL")

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp2 = await client.get(download_url, headers=headers)
            resp2.raise_for_status()
            content_bytes = resp2.content

        if len(content_bytes) > self.max_bytes:
            raise MediaTooLargeError(
                f"Media exceeds maximum allowed size ({len(content_bytes)} > {self.max_bytes})",
                size_bytes=len(content_bytes),
            )

        real_type = detect_content_type(content_bytes, msg.mimetype or "application/octet-stream")
        if real_type not in ("application/pdf", "image/jpeg", "image/png", "image/webp", "image/heic"):
            raise ValueError(f"Unsupported media content type: {real_type}")

        return content_bytes

    async def send_text(self, chat_id: str, text: str) -> ProviderSendResult:
        """Sends WhatsApp message via Meta Cloud API."""
        if settings.ENVIRONMENT == "test":
            return ProviderSendResult(success=True, message_id=f"wamid.{datetime.now(UTC).timestamp()}")

        url = f"https://graph.facebook.com/v20.0/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": chat_id,
            "type": "text",
            "text": {"preview_url": False, "body": text},
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                messages = data.get("messages", [])
                msg_id = messages[0]["id"] if messages else f"wamid.{datetime.now(UTC).timestamp()}"
                return ProviderSendResult(success=True, message_id=msg_id)
        except Exception as e:
            logger.error("Meta send_text failed", chat_id=chat_id, error=str(e))
            return ProviderSendResult(success=False, error=str(e))

    async def session_status(self) -> SessionStatus:
        """Cloud API is always connected unless credentials missing."""
        if not self.phone_number_id or not self.token:
            return "disconnected"
        return "connected"

    async def healthcheck(self) -> bool:
        return bool(self.phone_number_id and self.token)
