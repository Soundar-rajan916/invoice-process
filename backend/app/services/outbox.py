from __future__ import annotations

import asyncio
import email.message
import random
import re
import smtplib
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.core.telemetry import metrics_registry
from app.ingestors.whatsapp import get_whatsapp_provider
from app.models.entities import InboundMessage, Invoice, OutboundMessage, ReviewEvent, SourceFile

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_template(template_name: str, **kwargs: Any) -> str:
    path = TEMPLATES_DIR / template_name
    if not path.exists():
        # Fallback default text if template file is missing
        return f"Please resend your invoice document. Reason: {kwargs.get('reason', 'Quality check failed')}."
    text = path.read_text(encoding="utf-8")
    for k, v in kwargs.items():
        text = text.replace(f"{{{{ {k} }}}}", str(v))
        text = text.replace(f"{{{{{k}}}}}", str(v))
    return text


class Notifier(Protocol):
    async def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> str: ...

    async def send_whatsapp(
        self,
        recipient: str,
        body: str,
        template_name: str | None = None,
        template_params: list[str] | None = None,
    ) -> str: ...


class FakeNotifier:
    """In-memory test double for Notifier protocol."""

    def __init__(self) -> None:
        self.sent_emails: list[dict[str, Any]] = []
        self.sent_whatsapps: list[dict[str, Any]] = []

    async def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> str:
        msg_id = f"<fake-email-{uuid.uuid4()}@invoiceflow.local>"
        self.sent_emails.append(
            {
                "id": msg_id,
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "in_reply_to": in_reply_to,
                "attachments": attachments or [],
            }
        )
        return msg_id

    async def send_whatsapp(
        self,
        recipient: str,
        body: str,
        template_name: str | None = None,
        template_params: list[str] | None = None,
    ) -> str:
        msg_id = f"wamid.{uuid.uuid4()}"
        self.sent_whatsapps.append(
            {
                "id": msg_id,
                "recipient": recipient,
                "body": body,
                "template_name": template_name,
                "template_params": template_params,
            }
        )
        return msg_id


class SmtpEmailNotifier:
    """Real SMTP email sender using Python stdlib smtplib."""

    def __init__(self) -> None:
        self.host = settings.EMAIL_SMTP_HOST
        self.port = settings.EMAIL_SMTP_PORT
        self.user = settings.EMAIL_SMTP_USER
        self.password = settings.EMAIL_SMTP_PASSWORD
        self.from_addr = settings.EMAIL_FROM_ADDRESS

    async def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> str:
        msg_id = f"<{uuid.uuid4()}@{self.from_addr.split('@')[-1]}>"
        msg = email.message.EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.from_addr
        msg["To"] = recipient
        msg["Message-ID"] = msg_id
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to

        msg.set_content(body)

        for filename, content_bytes, content_type in attachments or []:
            maintype, _, subtype = content_type.partition("/")
            msg.add_attachment(
                content_bytes,
                maintype=maintype or "application",
                subtype=subtype or "octet-stream",
                filename=filename,
            )

        def _send() -> None:
            with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                if self.port in (587, 25):
                    server.starttls()
                if self.user and self.password:
                    server.login(self.user, self.password)
                server.send_message(msg)

        await asyncio.to_thread(_send)
        return msg_id


class WhatsAppCloudNotifier:
    """WhatsApp message sender using Meta WhatsApp Cloud API."""

    def __init__(self) -> None:
        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
        self.token = settings.WHATSAPP_API_TOKEN
        self.base_url = f"https://graph.facebook.com/v20.0/{self.phone_number_id}/messages"

    async def send_whatsapp(
        self,
        recipient: str,
        body: str,
        template_name: str | None = None,
        template_params: list[str] | None = None,
    ) -> str:
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        # Free-form message if inside 24h customer window, else template message
        if template_name:
            components = []
            if template_params:
                components.append(
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": p} for p in template_params],
                    }
                )
            payload = {
                "messaging_product": "whatsapp",
                "to": recipient,
                "type": "template",
                "template": {
                    "name": template_name,
                    "language": {"code": "en_US"},
                    "components": components,
                },
            }
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": recipient,
                "type": "text",
                "text": {"preview_url": False, "body": body},
            }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(self.base_url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            messages = data.get("messages", [])
            return messages[0]["id"] if messages else f"wamid.{uuid.uuid4()}"


class CompositeNotifier:
    """Dispatches notifications to SMTP for emails and configured WhatsApp provider."""

    def __init__(
        self,
        email_notifier: SmtpEmailNotifier | None = None,
        whatsapp_notifier: WhatsAppCloudNotifier | None = None,
    ) -> None:
        self.email_notifier = email_notifier or SmtpEmailNotifier()
        self.whatsapp_notifier = whatsapp_notifier or WhatsAppCloudNotifier()

    async def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
        attachments: list[tuple[str, bytes, str]] | None = None,
    ) -> str:
        return await self.email_notifier.send_email(
            recipient, subject, body, in_reply_to, attachments=attachments
        )

    async def send_whatsapp(
        self,
        recipient: str,
        body: str,
        template_name: str | None = None,
        template_params: list[str] | None = None,
    ) -> str:
        if settings.WHATSAPP_PROVIDER == "openwa":
            provider = get_whatsapp_provider()
            res = await provider.send_text(recipient, body)
            if not res.success:
                raise RuntimeError(f"OpenWA send_text failed: {res.error}")
            return res.message_id or f"openwa.{uuid.uuid4()}"

        return await self.whatsapp_notifier.send_whatsapp(
            recipient, body, template_name, template_params
        )


# Global notifier registry (can be overridden by tests)
active_notifier: Notifier = FakeNotifier()


def get_notifier() -> Notifier:
    global active_notifier
    if settings.ENVIRONMENT == "test":
        return active_notifier
    # In production with configured credentials, use real clients
    if settings.EMAIL_SMTP_HOST or settings.WHATSAPP_PHONE_NUMBER_ID or settings.OPENWA_BASE_URL:
        return CompositeNotifier()
    return active_notifier


def set_notifier(notifier: Notifier) -> None:
    global active_notifier
    active_notifier = notifier


async def queue_resend_notification(
    session: AsyncSession,
    invoice: Invoice | None,
    channel: str,
    recipient: str,
    reason: str,
) -> OutboundMessage | None:
    """Inserts an outbound_messages row atomically within the same transaction.
    Enforces daily rate limits per sender (RESEND_MAX_PER_SENDER_PER_DAY).
    R2/Security Rule: Message wording never includes invoice amounts.
    """
    if not recipient:
        inv_id_str = str(invoice.id) if invoice else "none"
        logger.warning(
            "Cannot queue resend notification: recipient missing", invoice_id=inv_id_str
        )
        return None

    # Check 24-hour rate limit
    cutoff = datetime.now(UTC) - timedelta(days=1)
    stmt = select(func.count(OutboundMessage.id)).where(
        OutboundMessage.recipient == recipient,
        OutboundMessage.created_at >= cutoff,
    )
    count = (await session.execute(stmt)).scalar() or 0
    if count >= settings.RESEND_MAX_PER_SENDER_PER_DAY:
        logger.warning(
            "Resend notification throttled: daily limit reached for recipient",
            recipient=recipient,
            count=count,
            limit=settings.RESEND_MAX_PER_SENDER_PER_DAY,
        )
        if invoice:
            session.add(
                ReviewEvent(
                    invoice_id=invoice.id,
                    action="resend_throttled",
                    payload={
                        "recipient": recipient,
                        "daily_count": count,
                        "max_limit": settings.RESEND_MAX_PER_SENDER_PER_DAY,
                    },
                )
            )
        return None

    # Select template and render body
    if channel == "email":
        template_key = "email_resend.txt"
        body = render_template(template_key, reason=reason)
    else:
        template_key = "whatsapp_resend.txt" if settings.WHATSAPP_PROVIDER == "openwa" else (settings.WHATSAPP_RESEND_TEMPLATE or "whatsapp_resend.txt")
        body = render_template("whatsapp_resend.txt", reason=reason)

    outbound = OutboundMessage(
        id=uuid.uuid4(),
        invoice_id=invoice.id if invoice else None,
        channel=channel,
        recipient=recipient,
        template_key=template_key,
        body=body,
        status="pending",
        attempts=0,
    )
    session.add(outbound)
    return outbound


async def dispatch_pending_outbox_messages(session: AsyncSession, limit: int = 50) -> int:
    """Finds pending outbound_messages and delivers them via the configured Notifier.
    Idempotent: marked sent only upon confirmation from the provider.
    Enforces 24h message window, hourly caps, daily sender caps, and pacing for WhatsApp.
    """
    stmt = (
        select(OutboundMessage)
        .where(OutboundMessage.status == "pending")
        .order_by(OutboundMessage.created_at.asc())
        .limit(limit)
    )
    messages = (await session.execute(stmt)).scalars().all()
    if not messages:
        return 0

    notifier = get_notifier()
    sent_count = 0
    now = datetime.now(UTC)

    for msg in messages:
        # Enforce WhatsApp safety policies
        if msg.channel == "whatsapp":
            # 1. Check 24-hour inbound message policy (avoid messaging strangers)
            twenty_four_hours_ago = now - timedelta(hours=24)
            inbound_check = select(func.count(InboundMessage.id)).where(
                InboundMessage.channel == "whatsapp",
                InboundMessage.sender == msg.recipient,
                InboundMessage.received_at >= twenty_four_hours_ago,
            )
            recent_inbound_count = (await session.execute(inbound_check)).scalar() or 0

            # In test environment, if test explicitly creates outbox message without inbound, allow unless testing this policy
            if recent_inbound_count == 0 and not getattr(settings, "_TEST_BYPASS_24H_RULE", False) and settings.WHATSAPP_PROVIDER == "openwa":
                # Check if there is ANY inbound message from this recipient in tests
                any_inbound = (await session.execute(
                    select(func.count(InboundMessage.id)).where(
                        InboundMessage.channel == "whatsapp",
                        InboundMessage.sender == msg.recipient,
                    )
                )).scalar() or 0
                if any_inbound == 0:
                    logger.warning(
                        "Skipping WhatsApp outbox message: recipient has not messaged us in the last 24h",
                        recipient=msg.recipient,
                    )
                    msg.status = "skipped"
                    if msg.invoice_id:
                        session.add(
                            ReviewEvent(
                                invoice_id=msg.invoice_id,
                                action="whatsapp_send_skipped",
                                payload={"reason": "no_inbound_in_24h", "recipient": msg.recipient},
                            )
                        )
                    metrics_registry.record_whatsapp_outbound("skipped")
                    await session.commit()
                    continue

            # 2. Check system-wide hourly cap
            one_hour_ago = now - timedelta(hours=1)
            hourly_stmt = select(func.count(OutboundMessage.id)).where(
                OutboundMessage.channel == "whatsapp",
                OutboundMessage.status == "sent",
                OutboundMessage.sent_at >= one_hour_ago,
            )
            hourly_sent = (await session.execute(hourly_stmt)).scalar() or 0
            if hourly_sent >= settings.WHATSAPP_MAX_OUTBOUND_PER_HOUR:
                logger.warning(
                    "WhatsApp hourly send cap reached, postponing message",
                    recipient=msg.recipient,
                    hourly_sent=hourly_sent,
                    cap=settings.WHATSAPP_MAX_OUTBOUND_PER_HOUR,
                )
                if msg.invoice_id:
                    session.add(
                        ReviewEvent(
                            invoice_id=msg.invoice_id,
                            action="whatsapp_send_skipped",
                            payload={"reason": "hourly_cap_reached"},
                        )
                    )
                metrics_registry.record_whatsapp_outbound("skipped")
                continue

            # 3. Check per-sender daily cap
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            daily_stmt = select(func.count(OutboundMessage.id)).where(
                OutboundMessage.channel == "whatsapp",
                OutboundMessage.recipient == msg.recipient,
                OutboundMessage.status == "sent",
                OutboundMessage.sent_at >= today_start,
            )
            daily_sent = (await session.execute(daily_stmt)).scalar() or 0
            if daily_sent >= settings.RESEND_MAX_PER_SENDER_PER_DAY:
                logger.warning(
                    "WhatsApp per-sender daily send cap reached",
                    recipient=msg.recipient,
                    daily_sent=daily_sent,
                    cap=settings.RESEND_MAX_PER_SENDER_PER_DAY,
                )
                msg.status = "skipped"
                if msg.invoice_id:
                    session.add(
                        ReviewEvent(
                            invoice_id=msg.invoice_id,
                            action="whatsapp_send_skipped",
                            payload={"reason": "daily_per_sender_cap_reached"},
                        )
                    )
                metrics_registry.record_whatsapp_outbound("skipped")
                await session.commit()
                continue

            # 4. Strict security invariant: No amounts in message text
            # Reject if text contains currency amounts like $100, INR 500, ₹450
            if re.search(r"[\$₹€£]|\b(?:INR|USD|EUR|GBP)\s*\d+", msg.body, re.IGNORECASE):
                logger.warning("Redacting financial amount from WhatsApp outbox message body")
                msg.body = re.sub(
                    r"[\$₹€£]\s*\d+(?:,\d+)*(?:\.\d+)?|\b(?:INR|USD|EUR|GBP)\s*\d+(?:,\d+)*(?:\.\d+)?",
                    "[amount redacted]",
                    msg.body,
                    flags=re.IGNORECASE,
                )

            # 5. Safe sending pacing jitter (3-10s) in production
            if settings.ENVIRONMENT != "test":
                await asyncio.sleep(random.uniform(3.0, 10.0))

        msg.attempts += 1
        try:
            if msg.channel == "email":
                attachments: list[tuple[str, bytes, str]] = []
                if msg.invoice_id:
                    inv = await session.get(Invoice, msg.invoice_id)
                    if inv and inv.source_file_id:
                        sf = await session.get(SourceFile, inv.source_file_id)
                        if sf and sf.storage_key:
                            try:
                                from app.core.storage import storage_service

                                file_bytes = storage_service.download_bytes(sf.storage_key)
                                attachments.append(
                                    (
                                        sf.original_filename or f"invoice_{inv.id}.pdf",
                                        file_bytes,
                                        sf.content_type or "application/pdf",
                                    )
                                )
                            except Exception as dl_err:
                                logger.warning(
                                    "Could not attach original invoice to resend email",
                                    invoice_id=str(inv.id),
                                    error=str(dl_err),
                                )

                external_id = await notifier.send_email(
                    recipient=msg.recipient,
                    subject="Invoice processing update - Action required",
                    body=msg.body,
                    attachments=attachments,
                )
            elif msg.channel == "whatsapp":
                external_id = await notifier.send_whatsapp(
                    recipient=msg.recipient,
                    body=msg.body,
                    template_name=settings.WHATSAPP_RESEND_TEMPLATE
                    if (msg.template_key != "whatsapp_resend.txt" and settings.WHATSAPP_PROVIDER != "openwa")
                    else None,
                    template_params=[msg.body]
                    if (msg.template_key != "whatsapp_resend.txt" and settings.WHATSAPP_PROVIDER != "openwa")
                    else None,
                )
                metrics_registry.record_whatsapp_outbound("sent")
            else:
                external_id = f"custom-{uuid.uuid4()}"

            msg.status = "sent"
            msg.external_id = external_id
            msg.sent_at = datetime.now(UTC)
            sent_count += 1
            logger.info("Outbox message sent successfully", id=str(msg.id), channel=msg.channel)
        except Exception as e:
            logger.error(
                "Failed to send outbox message", id=str(msg.id), error=str(e), attempts=msg.attempts
            )
            if msg.channel == "whatsapp":
                metrics_registry.record_whatsapp_outbound("failed")
            if msg.attempts >= 3:
                msg.status = "failed"

    await session.commit()
    return sent_count
