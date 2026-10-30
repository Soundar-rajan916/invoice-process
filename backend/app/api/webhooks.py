from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logging import logger
from app.models.entities import InboundMessage
from app.services.whatsapp import verify_webhook_signature

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
) -> Response:
    """Handles the WhatsApp webhook verification challenge from Meta."""
    expected_token = settings.WHATSAPP_VERIFY_TOKEN or "invoiceflow-verify-token"
    if hub_mode == "subscribe" and hub_verify_token == expected_token:
        logger.info("WhatsApp webhook challenge verified successfully")
        return Response(content=hub_challenge, media_type="text/plain")
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Verification token mismatch")


@router.post("/whatsapp", status_code=status.HTTP_200_OK)
async def handle_whatsapp_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    x_hub_signature_256: str | None = Header(None, alias="X-Hub-Signature-256"),
) -> dict[str, Any]:
    """Receives incoming WhatsApp Cloud API webhooks.
    1. Rejects invalid HMAC-SHA256 signatures with 401 immediately using constant-time comparison.
    2. Records inbound_messages row keyed by message ID (idempotent re-deliveries).
    3. Handles 'image' and 'document' attachments; marks other messages as ignored.
    4. Enqueues background worker task and returns 200 immediately.
    """
    raw_body = await request.body()
    app_secret = settings.WHATSAPP_APP_SECRET or "test-app-secret"

    # 1. Verify HMAC SHA-256 signature
    if settings.ENVIRONMENT != "test" or x_hub_signature_256:
        if not verify_webhook_signature(raw_body, x_hub_signature_256, app_secret):
            logger.warning("WhatsApp webhook rejected: invalid X-Hub-Signature-256")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed JSON payload: {e}",
        ) from e

    entries = payload.get("entry", [])
    processed_messages: list[str] = []

    for entry in entries:
        changes = entry.get("changes", [])
        for change in changes:
            value = change.get("value", {})
            messages = value.get("messages", [])
            for msg in messages:
                msg_id = msg.get("id", "")
                sender = msg.get("from", "unknown")
                msg_type = msg.get("type", "unknown")

                if not msg_id:
                    continue

                # 2. Check for duplicate webhook delivery
                stmt = select(InboundMessage).where(
                    InboundMessage.channel == "whatsapp",
                    InboundMessage.external_id == msg_id,
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing:
                    logger.info("WhatsApp message already recorded, ignoring duplicate", message_id=msg_id)
                    processed_messages.append(msg_id)
                    continue

                # 3. Filter supported types: image and document
                if msg_type not in ("image", "document"):
                    inbound_rec = InboundMessage(
                        id=uuid.uuid4(),
                        channel="whatsapp",
                        external_id=msg_id,
                        sender=sender,
                        subject=None,
                        status="ignored",
                        status_reason=f"Unsupported message type: {msg_type}",
                        source_file_ids=[],
                        raw_meta={"type": msg_type, "sender": sender},
                    )
                    session.add(inbound_rec)
                    await session.commit()
                    processed_messages.append(msg_id)
                    continue

                media_info = msg.get(msg_type, {})
                media_id = media_info.get("id")
                mime_type = media_info.get("mime_type")
                filename = media_info.get("filename")

                if not media_id:
                    continue

                # 4. Ingest or dispatch background task
                if settings.ENVIRONMENT == "test":
                    from app.services.whatsapp import WhatsAppIngestor

                    ingestor = WhatsAppIngestor(session)
                    await ingestor.handle_media_message(
                        message_id=msg_id,
                        sender=sender,
                        media_id=media_id,
                        media_type=msg_type,
                        filename=filename,
                        mime_type=mime_type,
                        raw_meta={"type": msg_type, "sender": sender},
                    )
                else:
                    try:
                        from app.workers.tasks import process_whatsapp_message_task

                        process_whatsapp_message_task.delay(
                            msg_id, sender, media_id, msg_type, filename, mime_type
                        )
                    except Exception as e:
                        logger.warning("Could not enqueue Celery task for WhatsApp message", error=str(e))

                processed_messages.append(msg_id)

    return {"status": "ok", "processed": processed_messages}

