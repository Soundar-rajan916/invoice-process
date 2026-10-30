from __future__ import annotations

import hashlib
import hmac
import io
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

import fitz  # PyMuPDF
import httpx
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestors.base import IncomingFile
from app.ingestors.upload import UploadIngestor, detect_content_type
from app.models.entities import InboundMessage, Invoice


class WhatsAppClient(Protocol):
    async def get_media_url(self, media_id: str) -> str: ...
    async def download_media(self, media_url: str) -> bytes: ...


class CloudWhatsAppClient:
    """Official Meta WhatsApp Business Cloud API client."""

    def __init__(self) -> None:
        self.token = settings.WHATSAPP_API_TOKEN

    async def get_media_url(self, media_id: str) -> str:
        url = f"https://graph.facebook.com/v20.0/{media_id}"
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            return resp.json()["url"]

    async def download_media(self, media_url: str) -> bytes:
        headers = {"Authorization": f"Bearer {self.token}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(media_url, headers=headers)
            resp.raise_for_status()
            return resp.content


class FakeWhatsAppClient:
    """In-memory test double for WhatsApp media downloading."""

    def __init__(self) -> None:
        self.media_store: dict[str, tuple[str, bytes]] = {}  # media_id -> (url, bytes)

    def register_media(self, media_id: str, content: bytes, url: str | None = None) -> None:
        self.media_store[media_id] = (url or f"https://lookaside.fbsbx.com/whatsapp/{media_id}", content)

    async def get_media_url(self, media_id: str) -> str:
        if media_id in self.media_store:
            return self.media_store[media_id][0]
        return f"https://lookaside.fbsbx.com/whatsapp/{media_id}"

    async def download_media(self, media_url: str) -> bytes:
        for _mid, (url, data) in self.media_store.items():
            if url == media_url:
                return data
        # Return a minimal 1x1 png or pdf for testing
        return b"%PDF-1.4\n%fake-pdf-content-for-whatsapp-tests\n%%EOF"


active_whatsapp_client: WhatsAppClient = FakeWhatsAppClient()


def get_whatsapp_client() -> WhatsAppClient:
    global active_whatsapp_client
    if settings.ENVIRONMENT == "test":
        return active_whatsapp_client
    if settings.WHATSAPP_API_TOKEN:
        return CloudWhatsAppClient()
    return active_whatsapp_client


def verify_webhook_signature(payload_bytes: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Verifies X-Hub-Signature-256 HMAC header using constant-time comparison."""
    if not signature_header or not app_secret:
        return False
    if not signature_header.startswith("sha256="):
        return False

    received_sig = signature_header[7:]
    expected_sig = hmac.new(
        app_secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(received_sig, expected_sig)


def stitch_images_to_pdf(images_bytes: list[bytes]) -> bytes:
    """Combines multiple image pages into a single multi-page PDF document (R1 multi-page)."""
    doc = fitz.open()
    try:
        for _idx, img_b in enumerate(images_bytes):
            img = Image.open(io.BytesIO(img_b))
            rgb_img = img.convert("RGB") if img.mode != "RGB" else img
            buf = io.BytesIO()
            rgb_img.save(buf, format="JPEG", quality=90)
            jpeg_bytes = buf.getvalue()

            img_doc = fitz.open(stream=jpeg_bytes, filetype="jpeg")
            rect = img_doc[0].rect
            page = doc.new_page(width=rect.width, height=rect.height)
            page.insert_image(rect, stream=jpeg_bytes)
            img_doc.close()

        pdf_bytes = doc.tobytes(garbage=3, deflate=True)
        return pdf_bytes
    finally:
        doc.close()


class WhatsAppIngestor:
    """Handles intake of invoices from WhatsApp Business Cloud API."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.upload_ingestor = UploadIngestor(session)
        self.client = get_whatsapp_client()

    async def handle_media_message(
        self,
        message_id: str,
        sender: str,
        media_id: str,
        media_type: str,  # 'image' or 'document'
        filename: str | None = None,
        mime_type: str | None = None,
        raw_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Downloads media, verifies magic bytes, and ingests into pipeline."""
        # 1. Idempotency check on external_id
        stmt = select(InboundMessage).where(
            InboundMessage.channel == "whatsapp",
            InboundMessage.external_id == message_id,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            return {"status": "skipped", "reason": "Already processed", "message_id": message_id}

        # 2. Download media
        media_url = await self.client.get_media_url(media_id)
        content_bytes = await self.client.download_media(media_url)

        # 3. Validate content type by magic bytes
        real_type = detect_content_type(content_bytes, mime_type or "application/octet-stream")

        ext = ".pdf" if real_type == "application/pdf" else ".jpg"
        final_filename = filename or f"whatsapp_{message_id}{ext}"

        # 4. Record inbound_messages
        inbound_rec = InboundMessage(
            id=uuid.uuid4(),
            channel="whatsapp",
            external_id=message_id,
            sender=sender,
            subject=None,
            received_at=datetime.now(UTC),
            status="ingested",
            source_file_ids=[],
            raw_meta=raw_meta or {},
        )
        self.session.add(inbound_rec)
        await self.session.flush()

        # 5. Ingest file
        incoming = IncomingFile(
            filename=final_filename,
            content=content_bytes,
            content_type=real_type,
            source="whatsapp",
        )
        res = await self.upload_ingestor.ingest(incoming)

        # 6. Set invoice inbound metadata
        inv = await self.session.get(Invoice, res.invoice_id)
        if inv:
            inv.inbound_message_id = inbound_rec.id
            inv.sender = sender

        inbound_rec.source_file_ids = [str(res.source_file_id)]
        await self.session.commit()

        return {
            "status": "ingested",
            "message_id": message_id,
            "invoice_id": str(res.invoice_id),
            "source_file_id": str(res.source_file_id),
        }
