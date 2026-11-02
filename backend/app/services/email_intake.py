from __future__ import annotations

import email
import email.utils
import imaplib
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.header import decode_header
from typing import Any, Protocol

import fitz  # PyMuPDF
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.ingestors.base import IncomingFile
from app.ingestors.upload import UploadIngestor, detect_content_type
from app.models.entities import InboundMessage, Invoice, ReviewEvent


@dataclass
class MailAttachment:
    filename: str
    content: bytes
    content_type: str
    is_inline: bool = False
    size_bytes: int = 0
    content_id: str | None = None


@dataclass
class MailMessage:
    message_id: str
    sender: str
    subject: str | None
    received_at: datetime
    headers: dict[str, str] = field(default_factory=dict)
    attachments: list[MailAttachment] = field(default_factory=list)
    raw_meta: dict[str, Any] = field(default_factory=dict)


class MailboxClient(Protocol):
    def connect(self) -> None: ...
    def fetch_unseen_messages(self, folder: str = "INBOX") -> list[MailMessage]: ...
    def move_message(self, message_id: str, from_folder: str, to_folder: str) -> None: ...
    def disconnect(self) -> None: ...


def _decode_mime_header(header_value: str | None) -> str:
    if not header_value:
        return ""
    decoded_fragments = decode_header(header_value)
    result = []
    for fragment, charset in decoded_fragments:
        if isinstance(fragment, bytes):
            try:
                result.append(fragment.decode(charset or "utf-8", errors="replace"))
            except Exception:
                result.append(fragment.decode("latin-1", errors="replace"))
        else:
            result.append(str(fragment))
    return "".join(result)


class ImapMailboxClient:
    """TLS-only IMAP mailbox client for email invoice intake."""

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self.host = host or settings.EMAIL_IMAP_HOST
        self.port = port or settings.EMAIL_IMAP_PORT
        self.username = username or settings.EMAIL_IMAP_USER
        self.password = password or settings.EMAIL_IMAP_PASSWORD
        self._conn: imaplib.IMAP4_SSL | None = None

    def connect(self) -> None:
        # TLS only: IMAP4_SSL verifies encryption in transit
        self._conn = imaplib.IMAP4_SSL(self.host, self.port)
        if self.username and self.password:
            self._conn.login(self.username, self.password)

    def fetch_unseen_messages(self, folder: str = "INBOX") -> list[MailMessage]:
        if not self._conn:
            self.connect()
        assert self._conn is not None

        self._conn.select(folder)
        # In a dedicated label like 'invoices', check ALL messages since user may have previewed/opened it; in INBOX only check UNSEEN
        criteria = "UNSEEN" if folder.strip().upper() == "INBOX" else "ALL"
        status, data = self._conn.search(None, criteria)
        if status != "OK" or not data or not data[0]:
            return []

        messages: list[MailMessage] = []
        all_ids = data[0].split()
        # Cap batch to latest 20 messages to prevent latency spikes with large mailboxes
        msg_ids = all_ids[-20:]

        for msg_id in msg_ids:
            res_status, msg_data = self._conn.fetch(msg_id, "(RFC822)")
            if res_status != "OK" or not msg_data:
                continue

            raw_part = msg_data[0]
            if not isinstance(raw_part, tuple) or len(raw_part) < 2:
                continue
            raw_bytes = raw_part[1]
            if not isinstance(raw_bytes, (bytes, bytearray)):
                continue
            parsed = self.parse_rfc822(bytes(raw_bytes))
            if parsed:
                messages.append(parsed)

        return messages

    def parse_rfc822(self, raw_bytes: bytes) -> MailMessage | None:
        msg = email.message_from_bytes(raw_bytes)
        message_id = msg.get("Message-ID", "").strip()
        if not message_id:
            message_id = f"<generated-{uuid.uuid4()}@invoiceflow.local>"

        sender = _decode_mime_header(msg.get("From", "unknown@sender.local"))
        subject = _decode_mime_header(msg.get("Subject", ""))
        date_str = msg.get("Date")
        received_at = datetime.now(UTC)
        if date_str:
            try:
                parsed_date = email.utils.parsedate_to_datetime(date_str)
                if parsed_date.tzinfo is None:
                    parsed_date = parsed_date.replace(tzinfo=UTC)
                received_at = parsed_date
            except Exception:
                pass

        headers = {k: _decode_mime_header(v) for k, v in msg.items()}
        attachments: list[MailAttachment] = []

        for part in msg.walk():
            content_disposition = str(part.get("Content-Disposition", ""))
            content_type = part.get_content_type()
            filename = part.get_filename()

            if filename:
                filename = _decode_mime_header(filename)

            payload = part.get_payload(decode=True)
            if not payload or not isinstance(payload, bytes):
                continue

            is_inline = "inline" in content_disposition.lower()
            content_id = part.get("Content-ID")

            attachments.append(
                MailAttachment(
                    filename=filename or f"attachment_{len(attachments) + 1}",
                    content=payload,
                    content_type=content_type,
                    is_inline=is_inline,
                    size_bytes=len(payload),
                    content_id=content_id,
                )
            )

        return MailMessage(
            message_id=message_id,
            sender=sender,
            subject=subject,
            received_at=received_at,
            headers=headers,
            attachments=attachments,
            raw_meta={"message_id": message_id, "subject": subject, "sender": sender},
        )

    def move_message(self, message_id: str, from_folder: str, to_folder: str) -> None:
        if not self._conn:
            return
        try:
            self._conn.select(from_folder)
            status, data = self._conn.search(None, f'HEADER Message-ID "{message_id}"')
            if status == "OK" and data and data[0]:
                for uid in data[0].split():
                    self._conn.copy(uid, to_folder)
                    self._conn.store(uid, "+FLAGS", "\\Deleted")
                self._conn.expunge()
        except Exception as e:
            logger.warning("Could not move IMAP message", message_id=message_id, error=str(e))

    def disconnect(self) -> None:
        if self._conn:
            try:
                self._conn.close()
                self._conn.logout()
            except Exception:
                pass
            self._conn = None


class FakeMailboxClient:
    """In-memory test double for MailboxClient with reproducible message queueing."""

    def __init__(self) -> None:
        self.folders: dict[str, list[MailMessage]] = {
            "INBOX": [],
            "Processed": [],
            "Failed": [],
        }
        self.connected = False

    def add_message(self, message: MailMessage, folder: str = "INBOX") -> None:
        if folder not in self.folders:
            self.folders[folder] = []
        self.folders[folder].append(message)

    def connect(self) -> None:
        self.connected = True

    def fetch_unseen_messages(self, folder: str = "INBOX") -> list[MailMessage]:
        return list(self.folders.get(folder, []))

    def move_message(self, message_id: str, from_folder: str, to_folder: str) -> None:
        from_list = self.folders.get(from_folder, [])
        if to_folder not in self.folders:
            self.folders[to_folder] = []
        for msg in list(from_list):
            if msg.message_id == message_id:
                from_list.remove(msg)
                self.folders[to_folder].append(msg)

    def disconnect(self) -> None:
        self.connected = False


# Signature / logo heuristics regex
LOGO_PATTERN = re.compile(r"^(image\d{3}|logo|sig|signature|banner|icon).*", re.IGNORECASE)


def is_usable_attachment(att: MailAttachment) -> tuple[bool, str]:
    """Applies strict filtering to separate real invoice documents from signature logos."""
    # 1. Size filter: tiny inline attachments (< EMAIL_MIN_ATTACHMENT_BYTES)
    if att.size_bytes < settings.EMAIL_MIN_ATTACHMENT_BYTES and att.is_inline:
        return (
            False,
            f"Inline image below minimum size ({att.size_bytes}B < {settings.EMAIL_MIN_ATTACHMENT_BYTES}B)",
        )

    # 2. Filename pattern check for inline images
    if att.is_inline and LOGO_PATTERN.match(att.filename):
        return False, f"Inline signature logo filename pattern match: {att.filename}"

    # 3. Content type magic bytes check
    try:
        real_type = detect_content_type(att.content, att.content_type)
    except Exception as e:
        return False, f"Unsupported file type: {e}"

    # 4. Check image dimensions if it's an image
    if real_type.startswith("image/"):
        try:
            with Image.open(io.BytesIO(att.content)) as im:
                w, h = im.size
                if w < settings.EMAIL_MIN_IMAGE_PIXELS or h < settings.EMAIL_MIN_IMAGE_PIXELS:
                    return (
                        False,
                        f"Image dimensions too small ({w}x{h} < {settings.EMAIL_MIN_IMAGE_PIXELS}px)",
                    )
        except Exception as e:
            return False, f"Corrupt image file: {e}"

    # 5. Over-limit size check
    if att.size_bytes > settings.EMAIL_MAX_ATTACHMENT_BYTES:
        return (
            False,
            f"Attachment exceeds max size limit ({att.size_bytes} > {settings.EMAIL_MAX_ATTACHMENT_BYTES})",
        )

    return True, "Usable invoice attachment"


def check_pdf_safety(pdf_bytes: bytes) -> tuple[bool, str | None, int]:
    """Inspects PDF for encryption, corruption, and page limits.
    Returns: (is_safe, failure_reason_if_any, page_count)
    """
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return False, f"Corrupt or unreadable PDF: {e}", 0

    try:
        if doc.is_encrypted:
            return False, "Password-protected PDF. Please submit an unencrypted invoice.", 0

        page_count = len(doc)
        if page_count > settings.EMAIL_MAX_PDF_PAGES:
            return (
                False,
                f"PDF exceeds page limit ({page_count} > {settings.EMAIL_MAX_PDF_PAGES} pages)",
                page_count,
            )
        return True, None, page_count
    finally:
        doc.close()


class EmailIngestor:
    """Ingests incoming invoices from email messages using Ingestor patterns (R1, R3)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.upload_ingestor = UploadIngestor(session)

    async def process_message(self, msg: MailMessage) -> dict[str, Any]:
        """Processes a single email message idempotently by Message-ID."""
        # 1. Idempotency check: inbound_messages keyed by Message-ID
        stmt = select(InboundMessage).where(
            InboundMessage.channel == "email",
            InboundMessage.external_id == msg.message_id,
        )
        existing = (await self.session.execute(stmt)).scalar_one_or_none()
        if existing:
            logger.info(
                "Email message already recorded, skipping re-poll", message_id=msg.message_id
            )
            return {
                "status": "skipped",
                "reason": "Already processed",
                "message_id": msg.message_id,
            }

        # 2. Check sender domain allowlist
        sender_email = msg.sender
        if "<" in sender_email and ">" in sender_email:
            sender_email = sender_email.split("<")[1].split(">")[0].strip()

        if settings.EMAIL_ALLOWED_SENDER_DOMAINS:
            domain = sender_email.split("@")[-1].lower() if "@" in sender_email else ""
            allowed = [
                d.strip().lower() for d in settings.EMAIL_ALLOWED_SENDER_DOMAINS if d.strip()
            ]
            if domain not in allowed:
                inbound_rec = InboundMessage(
                    id=uuid.uuid4(),
                    channel="email",
                    external_id=msg.message_id,
                    sender=sender_email,
                    subject=msg.subject,
                    received_at=msg.received_at,
                    status="ignored",
                    status_reason=f"Sender domain '{domain}' not in allowlist",
                    source_file_ids=[],
                    raw_meta=msg.raw_meta,
                )
                self.session.add(inbound_rec)
                await self.session.commit()
                return {
                    "status": "ignored",
                    "reason": "Domain not in allowlist",
                    "message_id": msg.message_id,
                }

        # 3. Filter attachments
        kept_attachments: list[MailAttachment] = []
        ignored_reasons: list[str] = []

        if len(msg.attachments) > settings.EMAIL_MAX_ATTACHMENTS_PER_MESSAGE:
            inbound_rec = InboundMessage(
                id=uuid.uuid4(),
                channel="email",
                external_id=msg.message_id,
                sender=sender_email,
                subject=msg.subject,
                received_at=msg.received_at,
                status="ignored",
                status_reason=f"Exceeded max attachments limit ({len(msg.attachments)} > {settings.EMAIL_MAX_ATTACHMENTS_PER_MESSAGE})",
                source_file_ids=[],
                raw_meta=msg.raw_meta,
            )
            self.session.add(inbound_rec)
            await self.session.commit()
            return {
                "status": "ignored",
                "reason": "Too many attachments",
                "message_id": msg.message_id,
            }

        for att in msg.attachments:
            usable, reason = is_usable_attachment(att)
            if usable:
                kept_attachments.append(att)
            else:
                ignored_reasons.append(f"{att.filename}: {reason}")

        if not kept_attachments:
            inbound_rec = InboundMessage(
                id=uuid.uuid4(),
                channel="email",
                external_id=msg.message_id,
                sender=sender_email,
                subject=msg.subject,
                received_at=msg.received_at,
                status="ignored",
                status_reason="No usable invoice attachment found. "
                + "; ".join(ignored_reasons[:3]),
                source_file_ids=[],
                raw_meta=msg.raw_meta,
            )
            self.session.add(inbound_rec)
            await self.session.commit()
            return {
                "status": "ignored",
                "reason": "No usable attachments",
                "message_id": msg.message_id,
            }

        # 4. Ingest valid attachments
        created_file_ids: list[str] = []
        created_invoice_ids: list[str] = []

        inbound_rec = InboundMessage(
            id=uuid.uuid4(),
            channel="email",
            external_id=msg.message_id,
            sender=sender_email,
            subject=msg.subject,
            received_at=msg.received_at,
            status="ingested",
            source_file_ids=[],
            raw_meta=msg.raw_meta,
        )
        self.session.add(inbound_rec)
        await self.session.flush()

        for att in kept_attachments:
            # Check for corrupt or password-protected PDF
            content_type = detect_content_type(att.content, att.content_type)
            if content_type == "application/pdf":
                is_safe, fail_reason, pages = check_pdf_safety(att.content)
                if not is_safe:
                    # Ingest file, but move directly to RESEND_REQUESTED!
                    incoming = IncomingFile(
                        filename=att.filename,
                        content=att.content,
                        content_type=content_type,
                        source="email",
                    )
                    res = await self.upload_ingestor.ingest(incoming)
                    created_file_ids.append(str(res.source_file_id))
                    created_invoice_ids.append(str(res.invoice_id))

                    inv = await self.session.get(Invoice, res.invoice_id)
                    if inv:
                        inv.inbound_message_id = inbound_rec.id
                        inv.sender = sender_email
                        inv.status = "RESEND_REQUESTED"
                        inv.status_reason = fail_reason
                        # Insert transactional outbox message for resend
                        from app.services.outbox import queue_resend_notification

                        await queue_resend_notification(
                            self.session,
                            invoice=inv,
                            channel="email",
                            recipient=sender_email,
                            reason=fail_reason or "Unreadable document",
                        )
                        self.session.add(
                            ReviewEvent(
                                invoice_id=inv.id,
                                action="request_resend",
                                payload={"reason": fail_reason, "source": "email_intake"},
                            )
                        )
                        await self.session.commit()
                    continue

            # Standard ingestion
            incoming = IncomingFile(
                filename=att.filename,
                content=att.content,
                content_type=content_type,
                source="email",
            )
            res = await self.upload_ingestor.ingest(incoming)
            created_file_ids.append(str(res.source_file_id))
            created_invoice_ids.append(str(res.invoice_id))

            inv = await self.session.get(Invoice, res.invoice_id)
            if inv:
                inv.inbound_message_id = inbound_rec.id
                inv.sender = sender_email
                await self.session.commit()

        inbound_rec.source_file_ids = created_file_ids
        await self.session.commit()

        return {
            "status": "ingested",
            "message_id": msg.message_id,
            "invoices": created_invoice_ids,
            "files": created_file_ids,
        }
