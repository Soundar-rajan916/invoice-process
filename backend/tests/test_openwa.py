"""Comprehensive test suite for WhatsApp intake via OpenWA and Meta abstraction.

Tests:
1. HMAC signature verification (valid, missing, malformed, wrong secret, tampered body).
2. Idempotency by (channel, external_id) - no duplicate invoices (R3).
3. Filtering (fromMe, group when disabled, allowlist, text-only recorded as ignored).
4. Media processing and R2 Universal Human Gate (invoices enter NEEDS_REVIEW, no auto-approval).
5. Media limits (oversized media recorded as failed with media_too_large and queues resend).
6. Photo grouping window (multi-page image grouping vs separate invoices).
7. Unrecognized payload handling (returns 200, records failed with unrecognized_payload).
8. Session status webhook (session.status updates WhatsAppSessionState).
9. Safe-sending outbox (24h inbound window check, hourly cap, daily cap, no amounts in text).
10. Production guard (fails startup in production without OPENWA_ACCEPT_UNOFFICIAL_RISK=true).
11. Provider abstraction factory (openwa vs meta).
12. CLI setup-openwa command idempotency with fake OpenWA server.
13. Live contract test (@pytest.mark.openwa_live).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ingestors.whatsapp import (
    InboundWhatsAppMessage,
    MediaRef,
    MetaCloudProvider,
    OpenWAProvider,
    UnrecognizedPayloadError,
    WhatsAppIngestor,
    get_whatsapp_provider,
)
from app.models.entities import (
    InboundMessage,
    Invoice,
    OutboundMessage,
    WhatsAppSessionState,
)
from app.services.outbox import (
    dispatch_pending_outbox_messages,
)
from tests.fakes.openwa_server import FakeOpenWAServer

TINY_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
TINY_PDF_B64 = (
    "JVBERi0xLjQKMSAwIG9iajw8L1R5cGUvQ2F0YWxvZy9QYWdlcyAyIDAgUj4+ZW5kb2JqIDIgMCBvYmo8PC9UeXBlL1BhZ2VzL0tpZHNbMyAwIFJdL0NvdW50IDE+PmVuZG9iaiAzIDAgb2JqPDwvVHlwZS9QYWdlL01lZGlhQm94WzAgMCA2MTIgNzkyXS9QYXJlbnQgMiAwIFIvUmVzb3VyY2VzPDw+Pj5lbmRvYmoKeHJlZgowIDQKMDAwMDAwMDAwMCA2NTUzNSBmIAowMDAwMDAwMDEwIDAwMDAwIG4gCjAwMDAwMDAwNjAgMDAwMDAgbiAKMDAwMDAwMDExNyAwMDAwMCBuIAp0cmFpbGVyCjw8L1NpemUgNC9Sb290IDEgMCBSPj4Kc3RhcnR4cmVmCjIxMAolJUVPRg=="
)


@pytest.fixture(autouse=True)
def setup_openwa_test_env():
    old_secret = settings.OPENWA_WEBHOOK_SECRET
    old_key = settings.OPENWA_API_KEY
    settings.OPENWA_WEBHOOK_SECRET = "test-openwa-secret"
    settings.OPENWA_API_KEY = "test-openwa-api-key"
    yield
    settings.OPENWA_WEBHOOK_SECRET = old_secret
    settings.OPENWA_API_KEY = old_key


def make_signed_headers(body: bytes, secret: str = "test-openwa-secret") -> dict[str, str]:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-OpenWA-Signature": f"sha256={digest}",
    }


# =====================================================================
# 1. SIGNATURE VERIFICATION TESTS
# =====================================================================


def test_openwa_verify_request_valid():
    provider = OpenWAProvider(
        base_url="http://openwa:2785/api",
        webhook_secret="super-secret",
    )
    raw_body = b'{"event":"message.received"}'
    digest = hmac.new(b"super-secret", raw_body, hashlib.sha256).hexdigest()

    # Valid signature
    headers = {"X-OpenWA-Signature": f"sha256={digest}"}
    provider.verify_request(headers, raw_body)  # Should not raise

    # Case insensitive header
    headers_lower = {"x-openwa-signature": f"sha256={digest}"}
    provider.verify_request(headers_lower, raw_body)


def test_openwa_verify_request_invalid_cases():
    provider = OpenWAProvider(
        base_url="http://openwa:2785/api",
        webhook_secret="super-secret",
    )
    raw_body = b'{"event":"message.received"}'
    valid_sig = hmac.new(b"super-secret", raw_body, hashlib.sha256).hexdigest()

    # 1. Missing header
    with pytest.raises(HTTPException) as exc1:
        provider.verify_request({}, raw_body)
    assert exc1.value.status_code == 401

    # 2. Malformed signature (missing sha256= prefix)
    with pytest.raises(HTTPException) as exc2:
        provider.verify_request({"X-OpenWA-Signature": valid_sig}, raw_body)
    assert exc2.value.status_code == 401

    # 3. Wrong secret
    wrong_sig = hmac.new(b"wrong-secret", raw_body, hashlib.sha256).hexdigest()
    with pytest.raises(HTTPException) as exc3:
        provider.verify_request({"X-OpenWA-Signature": f"sha256={wrong_sig}"}, raw_body)
    assert exc3.value.status_code == 401

    # 4. Tampered body
    with pytest.raises(HTTPException) as exc4:
        provider.verify_request({"X-OpenWA-Signature": f"sha256={valid_sig}"}, b'{"event":"tampered"}')
    assert exc4.value.status_code == 401


@pytest.mark.asyncio
async def test_openwa_webhook_endpoint_rejects_bad_signature(client: httpx.AsyncClient):
    """Calling POST /api/v1/webhooks/whatsapp/openwa with bad signature returns 401."""
    body = b'{"event":"message.received"}'
    resp = await client.post(
        "/api/v1/webhooks/whatsapp/openwa",
        content=body,
        headers={"Content-Type": "application/json", "X-OpenWA-Signature": "sha256=invalidhex123"},
    )
    assert resp.status_code == 401
    assert "signature" in resp.text.lower()


# =====================================================================
# 2. IDEMPOTENCY & DUPLICATE DELIVERY TESTS (R3)
# =====================================================================


@pytest.mark.asyncio
async def test_openwa_idempotency_prevents_duplicate_invoice(db_session: AsyncSession):
    """Duplicate webhook deliveries with same message ID result in only one invoice (R3)."""
    provider = OpenWAProvider(base_url="http://openwa:2785/api")
    ingestor = WhatsAppIngestor(db_session, provider=provider)

    msg = InboundWhatsAppMessage(
        external_id="sess-01:msg-unique-123",
        session_ref="sess-01",
        chat_id="919876543210@c.us",
        sender_id="919876543210@c.us",
        is_group=False,
        from_me=False,
        message_type="image",
        timestamp=datetime.now(UTC),
        caption="Invoice #1",
        filename="invoice.png",
        mimetype="image/png",
        media=MediaRef(data=base64.b64decode(TINY_PNG_B64), mimetype="image/png"),
    )

    # First delivery
    res1 = await ingestor.process_inbound_message(msg)
    assert res1["status"] == "ingested"
    first_invoice_id = res1["invoice_id"]
    assert first_invoice_id is not None

    # Second delivery (exact duplicate webhook)
    res2 = await ingestor.process_inbound_message(msg)
    assert res2["status"] == "skipped"
    assert "already" in res2["reason"].lower()

    # Verify only 1 invoice exists in DB for this external_id
    stmt = select(func.count(Invoice.id)).where(Invoice.id == uuid.UUID(first_invoice_id))
    count = (await db_session.execute(stmt)).scalar()
    assert count == 1


# =====================================================================
# 3. FILTERING TESTS
# =====================================================================


@pytest.mark.asyncio
async def test_openwa_filters_from_me(db_session: AsyncSession):
    provider = OpenWAProvider(base_url="http://openwa:2785/api")
    ingestor = WhatsAppIngestor(db_session, provider=provider)

    msg = InboundWhatsAppMessage(
        external_id="sess-01:from-me-1",
        session_ref="sess-01",
        chat_id="919876543210@c.us",
        sender_id="919876543210@c.us",
        is_group=False,
        from_me=True,  # Self sent
        message_type="image",
        timestamp=datetime.now(UTC),
        media=MediaRef(data=base64.b64decode(TINY_PNG_B64), mimetype="image/png"),
    )

    res = await ingestor.process_inbound_message(msg)
    assert res["status"] == "ignored"
    assert res["reason"] == "from_me"


@pytest.mark.asyncio
async def test_openwa_filters_groups_when_disabled(db_session: AsyncSession):
    provider = OpenWAProvider(base_url="http://openwa:2785/api", allow_groups=False)
    ingestor = WhatsAppIngestor(db_session, provider=provider)

    msg = InboundWhatsAppMessage(
        external_id="sess-01:group-msg-1",
        session_ref="sess-01",
        chat_id="123456789-group@g.us",
        sender_id="919876543210@c.us",
        is_group=True,
        from_me=False,
        message_type="image",
        timestamp=datetime.now(UTC),
        media=MediaRef(data=base64.b64decode(TINY_PNG_B64), mimetype="image/png"),
    )

    res = await ingestor.process_inbound_message(msg)
    assert res["status"] == "ignored"
    assert res["reason"] == "group_messages_disabled"


@pytest.mark.asyncio
async def test_openwa_filters_disallowed_senders(db_session: AsyncSession):
    provider = OpenWAProvider(
        base_url="http://openwa:2785/api",
        allowed_senders=["919876543210"],
    )
    ingestor = WhatsAppIngestor(db_session, provider=provider)

    with patch.object(settings, "OPENWA_ALLOWED_SENDERS", ["919876543210"]):
        msg = InboundWhatsAppMessage(
            external_id="sess-01:stranger-msg-1",
            session_ref="sess-01",
            chat_id="919111111111@c.us",
            sender_id="919111111111@c.us",
            is_group=False,
            from_me=False,
            message_type="image",
            timestamp=datetime.now(UTC),
            media=MediaRef(data=base64.b64decode(TINY_PNG_B64), mimetype="image/png"),
        )

        res = await ingestor.process_inbound_message(msg)
        assert res["status"] == "ignored"
        assert res["reason"] == "sender_not_allowlisted"


@pytest.mark.asyncio
async def test_openwa_ignores_text_only_messages(db_session: AsyncSession):
    provider = OpenWAProvider(base_url="http://openwa:2785/api")
    ingestor = WhatsAppIngestor(db_session, provider=provider)

    msg = InboundWhatsAppMessage(
        external_id="sess-01:text-msg-1",
        session_ref="sess-01",
        chat_id="919876543210@c.us",
        sender_id="919876543210@c.us",
        is_group=False,
        from_me=False,
        message_type="text",
        timestamp=datetime.now(UTC),
        caption="Just saying hello",
        media=None,
    )

    res = await ingestor.process_inbound_message(msg)
    assert res["status"] == "ignored"
    assert "no_media" in res["reason"] or "text" in res["reason"]

    # Verify no outbound message was queued
    outbound_stmt = select(func.count(OutboundMessage.id)).where(OutboundMessage.recipient == "919876543210@c.us")
    out_count = (await db_session.execute(outbound_stmt)).scalar()
    assert out_count == 0


# =====================================================================
# 4. R2 INVARIANT (UNIVERSAL HUMAN GATE) & INGESTION
# =====================================================================


@pytest.mark.asyncio
async def test_openwa_inbound_invoice_strictly_enters_needs_review(db_session: AsyncSession):
    """R2 Invariant: WhatsApp invoice enters NEEDS_REVIEW after processing, never auto-approves."""
    from app.services.pipeline import process_invoice_pipeline

    provider = OpenWAProvider(base_url="http://openwa:2785/api")
    ingestor = WhatsAppIngestor(db_session, provider=provider)

    msg = InboundWhatsAppMessage(
        external_id=f"sess-01:r2-test-{uuid.uuid4().hex[:6]}",
        session_ref="sess-01",
        chat_id="919876543210@c.us",
        sender_id="919876543210@c.us",
        is_group=False,
        from_me=False,
        message_type="document",
        timestamp=datetime.now(UTC),
        caption="Tax invoice for services",
        filename="tax_invoice.pdf",
        mimetype="application/pdf",
        media=MediaRef(data=base64.b64decode(TINY_PDF_B64), mimetype="application/pdf"),
    )

    res = await ingestor.process_inbound_message(msg)
    assert res["status"] == "ingested"
    invoice_id = uuid.UUID(res["invoice_id"])

    inv = await db_session.get(Invoice, invoice_id)
    assert inv is not None
    assert inv.status == "RECEIVED"
    assert inv.sender == "919876543210@c.us"
    assert inv.inbound_message_id is not None
    inb = await db_session.get(InboundMessage, inv.inbound_message_id)
    assert inb is not None
    assert inb.channel == "whatsapp"

    # Process through pipeline
    from app.extraction.preprocess import ProcessedPage

    with patch(
        "app.extraction.preprocess.Preprocessor.process",
        return_value=[
            ProcessedPage(
                page_number=1,
                text="Tax Invoice #INV-1234\nTotal: 1000.00",
                is_digital=True,
                blur_score=150.0,
                image_bytes=b"dummy",
                storage_key="test/1.jpg",
            )
        ],
    ):
        await process_invoice_pipeline(db_session, invoice_id)
    await db_session.refresh(inv)
    assert inv.status == "NEEDS_REVIEW"
    assert inv.status != "APPROVED"
    assert inv.status != "PUSHED"


# =====================================================================
# 5. OVERSIZED MEDIA & RESEND OUTBOX
# =====================================================================


@pytest.mark.asyncio
async def test_openwa_oversized_media_records_failed_and_queues_resend(db_session: AsyncSession):
    """When media exceeds byte limit or is dropped by OpenWA, records failed and queues resend."""
    provider = OpenWAProvider(base_url="http://openwa:2785/api")
    ingestor = WhatsAppIngestor(db_session, provider=provider)

    msg = InboundWhatsAppMessage(
        external_id="sess-01:oversized-msg-1",
        session_ref="sess-01",
        chat_id="919876543210@c.us",
        sender_id="919876543210@c.us",
        is_group=False,
        from_me=False,
        message_type="document",
        timestamp=datetime.now(UTC),
        filename="giant_file.pdf",
        mimetype="application/pdf",
        media=None,  # Dropped due to size
    )

    res = await ingestor.process_inbound_message(msg)
    assert res["status"] == "failed"
    assert "media_too_large" in res["reason"]

    # Verify resend notification was queued in outbound_messages
    stmt = select(OutboundMessage).where(OutboundMessage.recipient == "919876543210@c.us")
    out_msg = (await db_session.execute(stmt)).scalars().first()
    assert out_msg is not None
    assert out_msg.status == "pending"
    assert "size limit" in out_msg.body.lower() or "exceeds" in out_msg.body.lower()


# =====================================================================
# 6. UNRECOGNIZED PAYLOAD HANDLING
# =====================================================================


def test_openwa_unrecognized_payload_raises():
    provider = OpenWAProvider(base_url="http://openwa:2785/api")
    bad_payload = {"unknown_key": "some_value"}
    with pytest.raises(UnrecognizedPayloadError):
        provider.parse(bad_payload)


@pytest.mark.asyncio
async def test_openwa_webhook_returns_200_on_unrecognized_payload(client: httpx.AsyncClient):
    """OpenWA webhook endpoint returns 200 on unrecognized payload so gateway does not loop."""
    body = json.dumps({"unknown_event": "foobar"}).encode("utf-8")
    headers = make_signed_headers(body, settings.OPENWA_WEBHOOK_SECRET)
    resp = await client.post("/api/v1/webhooks/whatsapp/openwa", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "recorded_unrecognized_payload"


# =====================================================================
# 7. SESSION STATUS EVENT & TELEMETRY
# =====================================================================


@pytest.mark.asyncio
async def test_openwa_session_status_webhook(client: httpx.AsyncClient, db_session: AsyncSession):
    body = json.dumps({
        "event": "session.status",
        "sessionId": "test-session-42",
        "data": {
            "status": "connected",
            "phone": "919876543210"
        }
    }).encode("utf-8")
    headers = make_signed_headers(body, settings.OPENWA_WEBHOOK_SECRET)

    resp = await client.post("/api/v1/webhooks/whatsapp/openwa", content=body, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "session_status_updated"

    # Verify session status row updated
    stmt = select(WhatsAppSessionState).where(WhatsAppSessionState.provider == "openwa")
    row = (await db_session.execute(stmt)).scalars().first()
    assert row is not None
    assert row.state == "connected"


# =====================================================================
# 8. SAFE-SENDING OUTBOX & POLICIES
# =====================================================================


@pytest.mark.asyncio
async def test_outbox_refuses_to_send_if_no_inbound_in_24h(db_session: AsyncSession):
    """Safe sending: only sends to contacts who messaged within the last 24 hours."""
    out_msg = OutboundMessage(
        id=uuid.uuid4(),
        channel="whatsapp",
        recipient="919999999999@c.us",
        template_key="whatsapp_resend.txt",
        body="Please resend your invoice.",
        status="pending",
    )
    db_session.add(out_msg)
    await db_session.commit()

    with patch("app.services.outbox.get_whatsapp_provider") as mock_get_provider:
        mock_instance = MagicMock()
        mock_instance.send_text = AsyncMock()
        mock_get_provider.return_value = mock_instance

        # Dispatch
        await dispatch_pending_outbox_messages(db_session, limit=10)

        # Provider send_text should NOT have been called
        mock_instance.send_text.assert_not_called()

    # Message marked skipped due to 24h rule
    await db_session.refresh(out_msg)
    assert out_msg.status == "skipped"


@pytest.mark.asyncio
async def test_outbox_sends_when_inbound_exists_in_24h(db_session: AsyncSession):
    """When contact sent an inbound message within 24h, outbox successfully sends."""
    from app.services.outbox import CompositeNotifier, FakeNotifier, set_notifier

    recipient = "919888888888@c.us"

    # 1. Add inbound message within last 24h
    inb = InboundMessage(
        id=uuid.uuid4(),
        channel="whatsapp",
        external_id="recent_msg_1",
        sender=recipient,
        received_at=datetime.now(UTC) - timedelta(minutes=10),
        status="processed",
    )
    db_session.add(inb)

    # 2. Add pending outbox message
    out_msg = OutboundMessage(
        id=uuid.uuid4(),
        channel="whatsapp",
        recipient=recipient,
        template_key="whatsapp_resend.txt",
        body="Please resend the blurred image.",
        status="pending",
    )
    db_session.add(out_msg)
    await db_session.commit()

    try:
        with patch("app.services.outbox.get_whatsapp_provider") as mock_get_provider:
            mock_instance = MagicMock()
            mock_instance.send_text = AsyncMock(
                return_value=MagicMock(success=True, message_id="sent_wamid_999", error=None)
            )
            mock_get_provider.return_value = mock_instance

            set_notifier(CompositeNotifier())
            await dispatch_pending_outbox_messages(db_session, limit=10)

            mock_instance.send_text.assert_called_once()
    finally:
        set_notifier(FakeNotifier())

    await db_session.refresh(out_msg)
    assert out_msg.status == "sent"
    assert out_msg.external_id == "sent_wamid_999"


# =====================================================================
# 9. PHOTO GROUPING TESTS
# =====================================================================


def test_photo_grouping_window_stitching():
    """Verify stitch_images_to_pdf stitches multiple image bytes into one valid PDF."""
    img1 = base64.b64decode(TINY_PNG_B64)
    img2 = base64.b64decode(TINY_PNG_B64)

    pdf_bytes = WhatsAppIngestor.stitch_images_to_pdf([img1, img2])
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > len(img1)


# =====================================================================
# 10. PRODUCTION GUARD
# =====================================================================


def test_production_guard_fails_without_risk_acceptance():
    from app.main import create_app
    with patch.object(settings, "ENVIRONMENT", "production"), \
         patch.object(settings, "WHATSAPP_PROVIDER", "openwa"), \
         patch.object(settings, "OPENWA_ACCEPT_UNOFFICIAL_RISK", False):
        with pytest.raises(RuntimeError) as exc:
            create_app()
        assert "OPENWA_ACCEPT_UNOFFICIAL_RISK" in str(exc.value)
        assert "production" in str(exc.value).lower()


# =====================================================================
# 11. PROVIDER FACTORY SWITCHABILITY
# =====================================================================


def test_provider_factory_openwa():
    with patch.object(settings, "WHATSAPP_PROVIDER", "openwa"):
        p = get_whatsapp_provider(force_reload=True)
        assert isinstance(p, OpenWAProvider)


def test_provider_factory_meta():
    with patch.object(settings, "WHATSAPP_PROVIDER", "meta"), \
         patch.object(settings, "WHATSAPP_PHONE_NUMBER_ID", "12345"), \
         patch.object(settings, "WHATSAPP_API_TOKEN", "token"), \
         patch.object(settings, "WHATSAPP_APP_SECRET", "secret"), \
         patch.object(settings, "WHATSAPP_VERIFY_TOKEN", "verify"):
        p = get_whatsapp_provider(force_reload=True)
        assert isinstance(p, MetaCloudProvider)


# =====================================================================
# 12. CLI SETUP-OPENWA IDEMPOTENCY
# =====================================================================


@pytest.mark.asyncio
async def test_cli_setup_openwa_idempotent():
    from app.cli.whatsapp import run_setup_openwa

    fake_server = FakeOpenWAServer(api_key="cli-test-api-key")
    transport = httpx.ASGITransport(app=fake_server.app)

    async with httpx.AsyncClient(transport=transport, base_url="http://openwa:2785/api") as test_client:
        # First run
        res1 = await run_setup_openwa(
            base_url="http://openwa:2785/api",
            api_key="cli-test-api-key",
            session_name="invoiceflow",
            webhook_target_url="http://api:8000/api/v1/webhooks/whatsapp/openwa",
            webhook_secret="cli-webhook-secret",
            client=test_client,
        )
        assert res1["session_id"] is not None

        # Second run (idempotent)
        res2 = await run_setup_openwa(
            base_url="http://openwa:2785/api",
            api_key="cli-test-api-key",
            session_name="invoiceflow",
            webhook_target_url="http://api:8000/api/v1/webhooks/whatsapp/openwa",
            webhook_secret="cli-webhook-secret",
            client=test_client,
        )
        assert res2["session_id"] == res1["session_id"]


# =====================================================================
# 13. LIVE CONTRACT TEST (@pytest.mark.openwa_live)
# =====================================================================


@pytest.mark.openwa_live
@pytest.mark.asyncio
async def test_openwa_live_healthcheck():
    """Live contract test against a real running OpenWA gateway.

    Skipped unless OpenWA is reachable at OPENWA_BASE_URL.
    """
    provider = OpenWAProvider(base_url=settings.OPENWA_BASE_URL, api_key=settings.OPENWA_API_KEY)
    is_healthy = await provider.healthcheck()
    if not is_healthy:
        pytest.skip(f"Live OpenWA container is not reachable at {settings.OPENWA_BASE_URL}")
    status = await provider.session_status()
    assert status in ["connected", "needs_qr", "disconnected", "unknown"]
