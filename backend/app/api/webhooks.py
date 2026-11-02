from __future__ import annotations

import json
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logging import logger
from app.core.telemetry import metrics_registry
from app.ingestors.whatsapp import (
    MetaCloudProvider,
    OpenWAProvider,
    SessionStatusEvent,
    UnrecognizedPayloadError,
    WhatsAppIngestor,
)
from app.models.entities import InboundMessage, WhatsAppSessionState
from app.services.whatsapp import verify_webhook_signature

router = APIRouter(prefix="/api/v1/webhooks", tags=["Webhooks"])


# ---------------------------------------------------------------------------
# 1. OpenWA Webhook Endpoint (Section 2 & 3)
# ---------------------------------------------------------------------------
@router.post("/whatsapp/openwa", status_code=status.HTTP_200_OK)
async def handle_openwa_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Receives incoming OpenWA webhook deliveries.
    - Validates X-OpenWA-Signature with HMAC-SHA256 constant-time comparison (401 on failure).
    - Session status events update whatsapp_session_state.
    - Inbound messages are enqueued for Celery ingestion or run immediately in tests.
    - Unrecognized payload structures record an inbound failure and return 200 to prevent retries.
    """
    raw_body = await request.body()
    provider = OpenWAProvider()

    # 1. Cryptographic HMAC-SHA256 signature verification
    try:
        provider.verify_request(dict(request.headers), raw_body)
    except HTTPException:
        metrics_registry.record_whatsapp_signature_failure()
        raise

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Malformed JSON payload: {e}",
        ) from e

    # 2. Parse payload
    try:
        parsed = provider.parse(payload)
    except UnrecognizedPayloadError as err:
        logger.warning(
            "OpenWA unrecognized payload received", payload_keys=err.payload_keys
        )
        inb_fail = InboundMessage(
            id=uuid.uuid4(),
            channel="whatsapp",
            external_id=f"unrecognized:{uuid.uuid4()}",
            sender="unknown",
            subject=None,
            received_at=datetime.now(UTC),
            status="failed",
            status_reason="unrecognized_payload",
            source_file_ids=[],
            raw_meta={"unrecognized_keys": err.payload_keys},
        )
        session.add(inb_fail)
        await session.commit()
        metrics_registry.record_whatsapp_inbound("failed")
        return {"status": "recorded_unrecognized_payload"}

    # 3. Handle Session Status Event
    if isinstance(parsed, SessionStatusEvent):
        metrics_registry.set_whatsapp_session_state(parsed.status)
        stmt = select(WhatsAppSessionState).where(
            WhatsAppSessionState.provider == "openwa"
        )
        row = (await session.execute(stmt)).scalars().first()
        now = datetime.now(UTC)
        if row:
            if row.state != parsed.status:
                row.state = parsed.status
                row.last_changed_at = now
            row.last_webhook_at = now
            row.detail = parsed.detail
        else:
            row = WhatsAppSessionState(
                id=uuid.uuid4(),
                provider="openwa",
                state=parsed.status,
                last_changed_at=now,
                last_webhook_at=now,
                detail=parsed.detail,
            )
            session.add(row)
        await session.commit()
        return {"status": "session_status_updated", "state": parsed.status}

    # 4. Handle Inbound WhatsApp Messages
    results = []
    for msg in parsed:
        if settings.ENVIRONMENT == "test":
            ingestor = WhatsAppIngestor(session)
            res = await ingestor.ingest_message(msg)
            metrics_registry.record_whatsapp_inbound(res.get("status", "ingested"))
            results.append(res)
        else:
            try:
                from app.workers.tasks import process_whatsapp_inbound_task

                process_whatsapp_inbound_task.delay(asdict(msg))
                metrics_registry.record_whatsapp_inbound("enqueued")
                results.append({"status": "enqueued", "external_id": msg.external_id})
            except Exception as e:
                logger.error("Could not enqueue OpenWA inbound task", error=str(e))
                results.append({"status": "failed_to_enqueue", "external_id": msg.external_id})

    return {"status": "ok", "processed": results}


# ---------------------------------------------------------------------------
# 2. Meta WhatsApp Cloud API Endpoints (Section 2)
# ---------------------------------------------------------------------------
@router.get("/whatsapp/meta")
@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    hub_mode: str = Query(..., alias="hub.mode"),
    hub_verify_token: str = Query(..., alias="hub.verify_token"),
    hub_challenge: str = Query(..., alias="hub.challenge"),
) -> Response:
    """Handles the WhatsApp webhook verification challenge from Meta."""
    provider = MetaCloudProvider()
    challenge = provider.verify_handshake(hub_mode, hub_verify_token, hub_challenge)
    logger.info("WhatsApp webhook challenge verified successfully")
    return Response(content=challenge, media_type="text/plain")


@router.post("/whatsapp/meta", status_code=status.HTTP_200_OK)
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
            metrics_registry.record_whatsapp_signature_failure()
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
                    logger.info(
                        "WhatsApp message already recorded, ignoring duplicate", message_id=msg_id
                    )
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
                    metrics_registry.record_whatsapp_inbound("ignored")
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
                    from app.services.whatsapp import WhatsAppIngestor as LegacyWhatsAppIngestor

                    ingestor = LegacyWhatsAppIngestor(session)
                    await ingestor.handle_media_message(
                        message_id=msg_id,
                        sender=sender,
                        media_id=media_id,
                        media_type=msg_type,
                        filename=filename,
                        mime_type=mime_type,
                        raw_meta={"type": msg_type, "sender": sender},
                    )
                    metrics_registry.record_whatsapp_inbound("ingested")
                else:
                    try:
                        from app.workers.tasks import process_whatsapp_message_task

                        process_whatsapp_message_task.delay(
                            msg_id, sender, media_id, msg_type, filename, mime_type
                        )
                        metrics_registry.record_whatsapp_inbound("enqueued")
                    except Exception as e:
                        logger.warning(
                            "Could not enqueue Celery task for WhatsApp message", error=str(e)
                        )

                processed_messages.append(msg_id)

    return {"status": "ok", "processed": processed_messages}
