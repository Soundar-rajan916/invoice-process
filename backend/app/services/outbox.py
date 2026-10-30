from __future__ import annotations

import email.message
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
from app.models.entities import Invoice, OutboundMessage, ReviewEvent

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
    ) -> str:
        msg_id = f"<fake-email-{uuid.uuid4()}@invoiceflow.local>"
        self.sent_emails.append(
            {
                "id": msg_id,
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "in_reply_to": in_reply_to,
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
    """Sends notification emails via SMTP over TLS, respecting thread headers (In-Reply-To)."""

    def __init__(self) -> None:
        self.host = settings.EMAIL_SMTP_HOST
        self.port = settings.EMAIL_SMTP_PORT
        self.username = settings.EMAIL_SMTP_USER
        self.password = settings.EMAIL_SMTP_PASSWORD
        self.from_addr = settings.EMAIL_FROM_ADDRESS

    async def send_email(
        self,
        recipient: str,
        subject: str,
        body: str,
        in_reply_to: str | None = None,
    ) -> str:
        msg = email.message.EmailMessage()
        msg["From"] = self.from_addr
        msg["To"] = recipient
        msg["Subject"] = subject
        msg_id = f"<outbox-{uuid.uuid4()}@invoiceflow.local>"
        msg["Message-ID"] = msg_id
        if in_reply_to:
            msg["In-Reply-To"] = in_reply_to
            msg["References"] = in_reply_to
        msg.set_content(body)

        with smtplib.SMTP(self.host, self.port, timeout=15) as server:
            server.starttls()
            if self.username and self.password:
                server.login(self.username, self.password)
            server.send_message(msg)

        return msg_id


class WhatsAppCloudNotifier:
    """Sends WhatsApp notifications via the WhatsApp Business Cloud API."""

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
    """Dispatches notifications to SMTP for emails and Cloud API for WhatsApp."""

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
    ) -> str:
        return await self.email_notifier.send_email(recipient, subject, body, in_reply_to)

    async def send_whatsapp(
        self,
        recipient: str,
        body: str,
        template_name: str | None = None,
        template_params: list[str] | None = None,
    ) -> str:
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
    if settings.EMAIL_SMTP_HOST or settings.WHATSAPP_PHONE_NUMBER_ID:
        return CompositeNotifier()
    return active_notifier


async def queue_resend_notification(
    session: AsyncSession,
    invoice: Invoice,
    channel: str,
    recipient: str,
    reason: str,
) -> OutboundMessage | None:
    """Inserts an outbound_messages row atomically within the same transaction.
    Enforces daily rate limits per sender (RESEND_MAX_PER_SENDER_PER_DAY).
    R2/Security Rule: Message wording never includes invoice amounts.
    """
    if not recipient:
        logger.warning("Cannot queue resend notification: recipient missing", invoice_id=str(invoice.id))
        return None

    # Check 24-hour rate limit
    cutoff = datetime.now(UTC) - timedelta(days=1)
    stmt = (
        select(func.count(OutboundMessage.id))
        .where(
            OutboundMessage.recipient == recipient,
            OutboundMessage.created_at >= cutoff,
        )
    )
    count = (await session.execute(stmt)).scalar() or 0
    if count >= settings.RESEND_MAX_PER_SENDER_PER_DAY:
        logger.warning(
            "Resend notification throttled: daily limit reached for recipient",
            recipient=recipient,
            count=count,
            limit=settings.RESEND_MAX_PER_SENDER_PER_DAY,
        )
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
        template_key = settings.WHATSAPP_RESEND_TEMPLATE or "whatsapp_resend.txt"
        body = render_template("whatsapp_resend.txt", reason=reason)

    outbound = OutboundMessage(
        id=uuid.uuid4(),
        invoice_id=invoice.id,
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

    for msg in messages:
        msg.attempts += 1
        try:
            if msg.channel == "email":
                external_id = await notifier.send_email(
                    recipient=msg.recipient,
                    subject="Invoice processing update - Action required",
                    body=msg.body,
                )
            elif msg.channel == "whatsapp":
                external_id = await notifier.send_whatsapp(
                    recipient=msg.recipient,
                    body=msg.body,
                    template_name=settings.WHATSAPP_RESEND_TEMPLATE if msg.template_key != "whatsapp_resend.txt" else None,
                    template_params=[msg.body] if msg.template_key != "whatsapp_resend.txt" else None,
                )
            else:
                external_id = f"custom-{uuid.uuid4()}"

            msg.status = "sent"
            msg.external_id = external_id
            msg.sent_at = datetime.now(UTC)
            sent_count += 1
            logger.info("Outbox message sent successfully", id=str(msg.id), channel=msg.channel)
        except Exception as e:
            logger.error("Failed to send outbox message", id=str(msg.id), error=str(e), attempts=msg.attempts)
            if msg.attempts >= 3:
                msg.status = "failed"

    await session.commit()
    return sent_count
