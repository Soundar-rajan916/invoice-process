from __future__ import annotations

import io
import uuid
from typing import Any

import fitz  # PyMuPDF
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.ingestors.base import IncomingFile
from app.ingestors.upload import UploadIngestor, detect_content_type
from app.ingestors.whatsapp.factory import get_whatsapp_provider
from app.ingestors.whatsapp.models import InboundWhatsAppMessage
from app.ingestors.whatsapp.provider import MediaTooLargeError, WhatsAppProvider
from app.models.entities import InboundMessage, Invoice


def stitch_images_to_pdf(images_bytes: list[bytes]) -> bytes:
    """Combines multiple image pages into a single multi-page PDF document (R1 multi-page)."""
    doc = fitz.open()
    try:
        for img_b in images_bytes:
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

        return doc.tobytes(garbage=3, deflate=True)
    finally:
        doc.close()


class WhatsAppIngestor:
    """Provider-agnostic WhatsApp invoice intake ingestor."""

    stitch_images_to_pdf = staticmethod(stitch_images_to_pdf)

    def __init__(
        self,
        session: AsyncSession,
        provider: WhatsAppProvider | None = None,
    ) -> None:
        self.session = session
        self.upload_ingestor = UploadIngestor(session)
        self.provider = provider or get_whatsapp_provider()

    async def ingest_message(self, msg: InboundWhatsAppMessage) -> dict[str, Any]:
        """Ingests a single normalised WhatsApp message."""
        # 1. Idempotency check on (channel, external_id) (R3)
        stmt = select(InboundMessage).where(
            InboundMessage.channel == "whatsapp",
            InboundMessage.external_id == msg.external_id,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            logger.info("WhatsApp message already processed, skipping idempotently", external_id=msg.external_id)
            return {
                "status": "skipped",
                "reason": "Already processed",
                "external_id": msg.external_id,
                "inbound_id": str(existing.id),
            }

        sender_chat = msg.chat_id

        # 2. Filter: fromMe
        if msg.from_me:
            return await self._record_ignored(msg, "from_me")

        # 3. Filter: Group messages
        if msg.is_group and not settings.OPENWA_ALLOW_GROUPS:
            return await self._record_ignored(msg, "group_messages_disabled")

        # 4. Filter: Senders allowlist (if configured)
        if settings.OPENWA_ALLOWED_SENDERS:
            # Check raw sender or digits against allowlist
            clean_sender = sender_chat.replace("@c.us", "").replace("@lid", "").strip()
            allowlist = [s.strip().replace("+", "") for s in settings.OPENWA_ALLOWED_SENDERS if s.strip()]
            if clean_sender not in allowlist and sender_chat not in allowlist:
                return await self._record_ignored(msg, "sender_not_allowlisted")

        # 5. Filter: Text-only messages
        if msg.message_type in ("chat", "text") or (not msg.media and not msg.filename):
            return await self._record_ignored(msg, "text_only")

        # 6. Filter: Other unsupported message types
        if msg.message_type not in ("image", "document"):
            return await self._record_ignored(msg, f"unsupported_type_{msg.message_type}")

        # 7. Fetch and validate media
        try:
            content_bytes = await self.provider.fetch_media(msg)
        except MediaTooLargeError as e:
            logger.warning("WhatsApp media too large", external_id=msg.external_id, error=str(e))
            return await self._record_failed(msg, "media_too_large", queue_resend=True)
        except Exception as e:
            logger.error("Failed to fetch WhatsApp media", external_id=msg.external_id, error=str(e))
            return await self._record_failed(msg, f"media_fetch_error: {e}", queue_resend=False)

        real_type = detect_content_type(content_bytes, msg.mimetype or "application/octet-stream")
        if real_type not in (
            "application/pdf",
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/heic",
        ):
            return await self._record_failed(msg, f"unsupported_content_type_{real_type}", queue_resend=False)

        ext = ".pdf" if real_type == "application/pdf" else ".jpg"
        clean_ext_id = msg.external_id.replace(":", "_").replace("@", "_")
        final_filename = msg.filename or f"whatsapp_{clean_ext_id}{ext}"

        # 8. Record inbound_messages row
        inbound_rec = InboundMessage(
            id=uuid.uuid4(),
            channel="whatsapp",
            external_id=msg.external_id,
            sender=sender_chat,
            subject=msg.caption,
            received_at=msg.timestamp,
            status="ingested",
            source_file_ids=[],
            raw_meta=msg.raw_payload,
        )
        self.session.add(inbound_rec)
        await self.session.flush()

        # 9. Ingest into invoice pipeline via UploadIngestor
        incoming = IncomingFile(
            filename=final_filename,
            content=content_bytes,
            content_type=real_type,
            source="whatsapp",
        )
        res = await self.upload_ingestor.ingest(incoming)

        # 10. Link invoice metadata (source info on invoice)
        inv = await self.session.get(Invoice, res.invoice_id)
        if inv:
            inv.inbound_message_id = inbound_rec.id
            inv.sender = sender_chat
            if msg.timestamp:
                inv.created_at = msg.timestamp

        inbound_rec.source_file_ids = [str(res.source_file_id)]
        await self.session.commit()

        logger.info(
            "WhatsApp invoice ingested successfully",
            external_id=msg.external_id,
            invoice_id=str(res.invoice_id),
            source_file_id=str(res.source_file_id),
        )

        return {
            "status": "ingested",
            "external_id": msg.external_id,
            "invoice_id": str(res.invoice_id),
            "source_file_id": str(res.source_file_id),
        }

    async def ingest_grouped_images(
        self,
        messages: list[InboundWhatsAppMessage],
        images_bytes: list[bytes],
    ) -> dict[str, Any]:
        """Ingests a burst of grouped photos into a single multi-page invoice (R1 multi-page)."""
        if not messages or not images_bytes:
            return {"status": "skipped", "reason": "No messages to group"}

        sender_chat = messages[0].chat_id
        min(m.timestamp for m in messages)

        # 1. Stitch images into multi-page PDF
        pdf_bytes = stitch_images_to_pdf(images_bytes)
        combined_id = "_".join(m.external_id.split(":")[-1] for m in messages)
        filename = f"whatsapp_grouped_{combined_id[:32]}.pdf"

        # 2. Record all inbound_messages
        inbound_records: list[InboundMessage] = []
        for msg in messages:
            stmt = select(InboundMessage).where(
                InboundMessage.channel == "whatsapp",
                InboundMessage.external_id == msg.external_id,
            )
            existing = (await self.session.execute(stmt)).scalar_one_or_none()
            if not existing:
                inb = InboundMessage(
                    id=uuid.uuid4(),
                    channel="whatsapp",
                    external_id=msg.external_id,
                    sender=sender_chat,
                    subject=msg.caption,
                    received_at=msg.timestamp,
                    status="ingested",
                    source_file_ids=[],
                    raw_meta=msg.raw_payload,
                )
                self.session.add(inb)
                inbound_records.append(inb)
            else:
                inbound_records.append(existing)

        await self.session.flush()

        # 3. Ingest single multi-page PDF into pipeline
        incoming = IncomingFile(
            filename=filename,
            content=pdf_bytes,
            content_type="application/pdf",
            source="whatsapp",
        )
        res = await self.upload_ingestor.ingest(incoming)

        # 4. Link invoice metadata
        inv = await self.session.get(Invoice, res.invoice_id)
        if inv:
            inv.inbound_message_id = inbound_records[0].id
            inv.sender = sender_chat
            if inbound_records[0].received_at:
                inv.created_at = inbound_records[0].received_at

        for inb in inbound_records:
            inb.source_file_ids = [str(res.source_file_id)]

        await self.session.commit()

        logger.info(
            "Grouped WhatsApp photos ingested as single multi-page invoice",
            pages=len(images_bytes),
            invoice_id=str(res.invoice_id),
        )

        return {
            "status": "ingested",
            "invoice_id": str(res.invoice_id),
            "source_file_id": str(res.source_file_id),
            "pages": len(images_bytes),
        }

    async def _record_ignored(self, msg: InboundWhatsAppMessage, reason: str) -> dict[str, Any]:
        """Records message in inbound_messages with status 'ignored'."""
        inbound_rec = InboundMessage(
            id=uuid.uuid4(),
            channel="whatsapp",
            external_id=msg.external_id,
            sender=msg.chat_id,
            subject=msg.caption,
            received_at=msg.timestamp,
            status="ignored",
            status_reason=reason,
            source_file_ids=[],
            raw_meta=msg.raw_payload,
        )
        self.session.add(inbound_rec)
        await self.session.commit()
        logger.info("Ignored WhatsApp message", external_id=msg.external_id, reason=reason)
        return {"status": "ignored", "reason": reason, "external_id": msg.external_id}

    async def _record_failed(
        self, msg: InboundWhatsAppMessage, reason: str, queue_resend: bool = False
    ) -> dict[str, Any]:
        """Records message in inbound_messages with status 'failed' and optionally queues resend outbox."""
        inbound_rec = InboundMessage(
            id=uuid.uuid4(),
            channel="whatsapp",
            external_id=msg.external_id,
            sender=msg.chat_id,
            subject=msg.caption,
            received_at=msg.timestamp,
            status="failed",
            status_reason=reason,
            source_file_ids=[],
            raw_meta=msg.raw_payload,
        )
        self.session.add(inbound_rec)
        await self.session.flush()

        if queue_resend:
            from app.services.outbox import queue_resend_notification

            await queue_resend_notification(
                self.session,
                invoice=None,
                channel="whatsapp",
                recipient=msg.chat_id,
                reason="Document could not be processed (file exceeds size limit). Please send a standard invoice PDF or clear photo under 20MB.",
            )

        await self.session.commit()
        logger.warning("Failed WhatsApp message intake", external_id=msg.external_id, reason=reason)
        return {"status": "failed", "reason": reason, "external_id": msg.external_id}

    process_inbound_message = ingest_message
