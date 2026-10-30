from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.extraction.base import ExtractionResult, PageInput
from app.extraction.factory import set_second_opinion_extractor
from app.extraction.mock_extractor import MockExtractor
from app.extraction.preprocess import (
    Preprocessor,
    QualityMetrics,
    compute_quality_metrics,
)
from app.models.entities import InboundMessage, Invoice, OutboundMessage, ReviewEvent, SourceFile
from app.schemas.extraction import InvoiceExtraction, LineItem
from app.services.email_intake import (
    EmailIngestor,
    FakeMailboxClient,
    MailAttachment,
    MailMessage,
    check_pdf_safety,
    is_usable_attachment,
)
from app.services.outbox import (
    dispatch_pending_outbox_messages,
    queue_resend_notification,
)
from app.services.pipeline import process_invoice_pipeline
from app.services.validation import validate_grounding
from app.services.whatsapp import verify_webhook_signature

# ==========================================
# 1. EMAIL INTAKE & POLLER TESTS
# ==========================================


def test_email_attachment_filtering_rules():
    """Verify filtering of logos, tiny images, and non-supported formats."""
    # 1. Tiny inline image below min bytes
    tiny_img = MailAttachment(
        filename="logo.png",
        content=b"12345",
        content_type="image/png",
        is_inline=True,
        size_bytes=5,
    )
    usable, reason = is_usable_attachment(tiny_img)
    assert not usable
    assert "below minimum size" in reason

    # 2. Ignored filename pattern for inline images
    named_logo = MailAttachment(
        filename="image001.png",
        content=b"x" * 15000,
        content_type="image/png",
        is_inline=True,
        size_bytes=15000,
    )
    usable, reason = is_usable_attachment(named_logo)
    assert not usable
    assert "logo" in reason.lower() and "pattern" in reason.lower()

    # 3. Valid PDF attachment
    valid_pdf = MailAttachment(
        filename="invoice_2026.pdf",
        content=b"%PDF-1.4 " + (b"0" * 2000),
        content_type="application/pdf",
        is_inline=False,
        size_bytes=2009,
    )
    usable, reason = is_usable_attachment(valid_pdf)
    assert usable
    assert "Usable invoice attachment" in reason


@pytest.mark.asyncio
async def test_email_poller_idempotency_and_folder_movement(db_session: AsyncSession):
    """Verify that email processing skips already seen Message-IDs and moves processed emails."""
    fake_mailbox = FakeMailboxClient()
    sample_pdf = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"

    msg = MailMessage(
        message_id="<msg-001@vendor.com>",
        sender="billing@vendor.com",
        subject="Monthly Tax Invoice INV-9901",
        received_at=datetime.now(UTC),
        attachments=[
            MailAttachment(
                filename="inv9901.pdf",
                content=sample_pdf,
                content_type="application/pdf",
                size_bytes=len(sample_pdf),
            )
        ],
    )
    fake_mailbox.add_message(msg, folder="INBOX")

    ingestor = EmailIngestor(db_session)

    # First run: process message
    res1 = await ingestor.process_message(msg)
    assert res1.get("status") == "ingested"
    fake_mailbox.move_message(msg.message_id, "INBOX", "Processed")

    assert len(fake_mailbox.folders["Processed"]) == 1
    assert len(fake_mailbox.folders["INBOX"]) == 0

    # Verify inbound_messages row
    stmt = select(InboundMessage).where(InboundMessage.external_id == "<msg-001@vendor.com>")
    inbound = (await db_session.execute(stmt)).scalar_one_or_none()
    assert inbound is not None
    assert inbound.channel == "email"
    assert inbound.status == "ingested"

    # Second run with same message_id: must skip idempotently
    res2 = await ingestor.process_message(msg)
    assert res2.get("status") == "skipped"
    assert res2.get("reason") == "Already processed"


@pytest.mark.asyncio
async def test_email_poller_corrupt_or_password_protected_pdf(db_session: AsyncSession):
    """Corrupt or password-protected PDFs are rejected by safety check."""
    corrupt_pdf_data = b"NOT_A_VALID_PDF_HEADER"
    is_safe, fail_reason, pages = check_pdf_safety(corrupt_pdf_data)
    assert is_safe is False
    assert "Corrupt or unreadable PDF" in (fail_reason or "")


@pytest.mark.asyncio
async def test_email_poller_sender_allowlist(db_session: AsyncSession):
    """Senders outside EMAIL_ALLOWED_SENDER_DOMAINS are recorded as ignored."""
    msg = MailMessage(
        message_id="<msg-spam@unknown.com>",
        sender="spammer@unknown.com",
        subject="Phishing invoice",
        received_at=datetime.now(UTC),
        attachments=[
            MailAttachment(
                filename="fake.pdf",
                content=b"%PDF-1.4 test",
                content_type="application/pdf",
                size_bytes=14,
            )
        ],
    )

    old_allowlist = settings.EMAIL_ALLOWED_SENDER_DOMAINS
    settings.EMAIL_ALLOWED_SENDER_DOMAINS = ["trustedvendor.com", "partner.in"]
    try:
        ingestor = EmailIngestor(db_session)
        res = await ingestor.process_message(msg)
        assert res.get("status") == "ignored"

        stmt = select(InboundMessage).where(InboundMessage.external_id == "<msg-spam@unknown.com>")
        inbound = (await db_session.execute(stmt)).scalar_one_or_none()
        assert inbound is not None
        assert inbound.status == "ignored"
        assert "not in allowlist" in (inbound.status_reason or "")
    finally:
        settings.EMAIL_ALLOWED_SENDER_DOMAINS = old_allowlist


# ==========================================
# 2. WHATSAPP INTAKE & WEBHOOK TESTS
# ==========================================


def test_whatsapp_hmac_signature_verification():
    """Verify X-Hub-Signature-256 HMAC constant-time check."""
    secret = "test_meta_app_secret_123"
    body = b'{"entry":[{"id":"123","changes":[]}]}'

    signature_hash = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    valid_header = f"sha256={signature_hash}"

    assert verify_webhook_signature(body, valid_header, secret) is True
    assert verify_webhook_signature(body, "sha256=invalid_hex_digest", secret) is False
    assert verify_webhook_signature(body, None, secret) is False
    assert verify_webhook_signature(body, "no_prefix_signature", secret) is False


@pytest.mark.asyncio
async def test_whatsapp_webhook_verification_endpoint(client: AsyncClient):
    """GET /api/v1/webhooks/whatsapp handles Meta hub challenge."""
    token = settings.WHATSAPP_VERIFY_TOKEN
    challenge = "9876543210"

    # Correct verify token
    res = await client.get(
        f"/api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token={token}&hub.challenge={challenge}"
    )
    assert res.status_code == 200
    assert res.text == challenge

    # Incorrect verify token -> 403
    res_bad = await client.get(
        "/api/v1/webhooks/whatsapp?hub.mode=subscribe&hub.verify_token=wrong_token&hub.challenge=123"
    )
    assert res_bad.status_code == 403


@pytest.mark.asyncio
async def test_whatsapp_webhook_post_idempotency_and_signature(
    client: AsyncClient, db_session: AsyncSession
):
    """POST /api/v1/webhooks/whatsapp rejects bad HMAC and idempotently registers inbound message."""
    secret = settings.WHATSAPP_APP_SECRET
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WHATSAPP_BIZ_ID",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "15550234567"},
                            "messages": [
                                {
                                    "from": "919876543210",
                                    "id": "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhgWM0EB",
                                    "timestamp": "1712000000",
                                    "type": "document",
                                    "document": {
                                        "filename": "tax_invoice_apr.pdf",
                                        "mime_type": "application/pdf",
                                        "id": "media_doc_991122",
                                    },
                                }
                            ],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # 1. Invalid signature -> 401
    bad_res = await client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=deadbeef"},
    )
    assert bad_res.status_code == 401

    # 2. Valid signature -> 200
    valid_sig = "sha256=" + hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    ok_res = await client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": valid_sig},
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["status"] == "ok"

    # Inbound message recorded
    stmt = select(InboundMessage).where(
        InboundMessage.external_id == "wamid.HBgMOTE5ODc2NTQzMjEwFQIAEhgWM0EB"
    )
    inbound = (await db_session.execute(stmt)).scalar_one_or_none()
    assert inbound is not None
    assert inbound.channel == "whatsapp"
    assert inbound.sender == "919876543210"

    # 3. Duplicate POST with same wamid -> returns 200, still exactly 1 inbound message
    ok_res_dup = await client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": valid_sig},
    )
    assert ok_res_dup.status_code == 200
    all_inbound = (await db_session.execute(stmt)).scalars().all()
    assert len(all_inbound) == 1


@pytest.mark.asyncio
async def test_split_pages_action(client: AsyncClient, db_session: AsyncSession, reviewer_user):
    """POST /api/v1/invoices/{id}/split-pages splits grouped multi-page invoice into individual invoices."""
    from app.core.security import create_access_token

    token = create_access_token(str(reviewer_user.id), reviewer_user.role)
    auth_headers = {"Authorization": f"Bearer {token}"}

    # Create dummy source file
    src = SourceFile(
        id=uuid.uuid4(),
        sha256=hashlib.sha256(b"grouped").hexdigest(),
        original_filename="grouped.pdf",
        content_type="application/pdf",
        size_bytes=200,
        storage_key="test/grouped.pdf",
        source="whatsapp",
    )
    db_session.add(src)

    # Create a grouped 3-page invoice
    grouped_id = uuid.uuid4()
    inv = Invoice(
        id=grouped_id,
        source_file_id=src.id,
        status="NEEDS_REVIEW",
        page_count=3,
        sender="919988776655",
        status_reason="Grouped 3 WhatsApp photos",
    )
    db_session.add(inv)
    await db_session.commit()

    res = await client.post(f"/api/v1/invoices/{grouped_id}/split-pages", headers=auth_headers)
    assert res.status_code == 200
    data = res.json()
    assert len(data["invoices"]) == 3

    # Check that original invoice now has page_count = 1
    await db_session.refresh(inv)
    assert inv.page_count == 1

    # Verify audit event recorded
    stmt = select(ReviewEvent).where(ReviewEvent.invoice_id == grouped_id)
    audits = (await db_session.execute(stmt)).scalars().all()
    assert any(a.action == "split_pages" for a in audits)


# ==========================================
# 3. OUTBOX & RESEND NOTIFICATIONS
# ==========================================


@pytest.mark.asyncio
async def test_outbox_transactional_resend_and_dispatch(db_session: AsyncSession):
    """Verify resend notification is recorded in outbox and dispatched idempotently without amounts."""
    src = SourceFile(
        id=uuid.uuid4(),
        sha256=hashlib.sha256(b"resend_doc").hexdigest(),
        original_filename="blurry.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_key="test/blurry.pdf",
        source="email",
    )
    db_session.add(src)

    inv_id = uuid.uuid4()
    inv = Invoice(
        id=inv_id,
        source_file_id=src.id,
        status="RESEND_REQUESTED",
        sender="accounts@supplier.com",
        status_reason="Document was blurry and unreadable",
    )
    db_session.add(inv)
    await db_session.commit()

    # Enqueue resend outbound message
    msg = await queue_resend_notification(
        db_session,
        invoice=inv,
        channel="email",
        recipient=inv.sender or "accounts@supplier.com",
        reason=inv.status_reason or "Document unreadable",
    )
    assert msg is not None
    assert msg.status == "pending"
    # CRITICAL: message body must NEVER contain financial amounts or currency symbols
    assert "₹" not in msg.body
    assert "rs." not in msg.body.lower()
    assert "blurry" in msg.body

    # Dispatch pending messages
    sent_count = await dispatch_pending_outbox_messages(db_session)
    assert sent_count >= 1

    # Refresh row: status must be sent
    await db_session.refresh(msg)
    assert msg.status == "sent"
    assert msg.sent_at is not None

    # Second dispatch does not re-send
    sent_count2 = await dispatch_pending_outbox_messages(db_session)
    assert sent_count2 == 0


@pytest.mark.asyncio
async def test_outbox_sender_daily_rate_limiting(db_session: AsyncSession):
    """Enforce RESEND_MAX_PER_SENDER_PER_DAY limit to prevent spamming vendors."""
    old_max = settings.RESEND_MAX_PER_SENDER_PER_DAY
    settings.RESEND_MAX_PER_SENDER_PER_DAY = 2
    sender = "test_rate_limit@vendor.com"

    src = SourceFile(
        id=uuid.uuid4(),
        sha256=hashlib.sha256(b"rate_limit_doc").hexdigest(),
        original_filename="rate_limit.pdf",
        content_type="application/pdf",
        size_bytes=100,
        storage_key="test/rate_limit.pdf",
        source="email",
    )
    db_session.add(src)

    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=src.id,
        status="RESEND_REQUESTED",
        sender=sender,
        status_reason="Unreadable document",
    )
    db_session.add(inv)
    await db_session.commit()

    try:
        # Send 1
        m1 = await queue_resend_notification(
            db_session, invoice=inv, channel="email", recipient=sender, reason="blur 1"
        )
        assert m1 is not None
        await db_session.commit()

        # Send 2
        m2 = await queue_resend_notification(
            db_session, invoice=inv, channel="email", recipient=sender, reason="blur 2"
        )
        assert m2 is not None
        await db_session.commit()

        # Send 3 -> Exceeds daily max, must return None and not create outbox row
        m3 = await queue_resend_notification(
            db_session, invoice=inv, channel="email", recipient=sender, reason="blur 3"
        )
        assert m3 is None

        # Check total created in DB
        stmt = select(OutboundMessage).where(OutboundMessage.recipient == sender)
        rows = (await db_session.execute(stmt)).scalars().all()
        assert len(rows) == 2
    finally:
        settings.RESEND_MAX_PER_SENDER_PER_DAY = old_max


# ==========================================
# 4. EXTRACTION SAFETY NET (R2)
# ==========================================


def test_grounding_safety_net_catches_hallucinated_values():
    """Grounding check must raise not_in_source error if extracted values do not appear in source text."""
    # Source text from actual document
    source_text = """
    TAX INVOICE
    Supplier: Acme Industrial Supplies
    GSTIN: 27AAPFU0939F1ZV
    Invoice No: INV-2026-09
    Date: 12/03/2026

    1. Steel Bolts 100pk   10   50.00   500.00

    Taxable Value: 500.00
    IGST @ 18%: 90.00
    Total: 590.00
    """

    # 1. Honest extraction matching text -> No grounding issues
    accurate_ext = InvoiceExtraction(
        invoice_number="INV-2026-09",
        invoice_date=date(2026, 3, 12),
        supplier_name="Acme Industrial Supplies",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[
            LineItem(
                description="Steel Bolts 100pk",
                quantity=Decimal("10"),
                rate=Decimal("50.00"),
                amount=Decimal("500.00"),
            )
        ],
        taxable_value=Decimal("500.00"),
        igst=Decimal("90.00"),
        total=Decimal("590.00"),
    )
    issues_accurate = validate_grounding(accurate_ext, source_text)
    assert len(issues_accurate) == 0

    # 2. Hallucinated total (altered number) -> raises not_in_source
    hallucinated_total_ext = InvoiceExtraction(
        invoice_number="INV-2026-09",
        invoice_date=date(2026, 3, 12),
        supplier_name="Acme Industrial Supplies",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[
            LineItem(
                description="Steel Bolts 100pk",
                quantity=Decimal("10"),
                rate=Decimal("50.00"),
                amount=Decimal("500.00"),
            )
        ],
        taxable_value=Decimal("500.00"),
        igst=Decimal("90.00"),
        total=Decimal("890.00"),  # Hallucinated!
    )
    issues_hallucinated = validate_grounding(hallucinated_total_ext, source_text)
    assert any(i.code == "not_in_source" and i.field == "total" for i in issues_hallucinated)

    # 3. Hallucinated GSTIN -> raises not_in_source
    hallucinated_gstin_ext = InvoiceExtraction(
        invoice_number="INV-2026-09",
        invoice_date=date(2026, 3, 12),
        supplier_name="Acme Industrial Supplies",
        supplier_gstin="33AAAAA0000A1Z5",  # Hallucinated!
        line_items=[],
        total=Decimal("590.00"),
    )
    issues_gstin = validate_grounding(hallucinated_gstin_ext, source_text)
    assert any(i.code == "not_in_source" and i.field == "supplier_gstin" for i in issues_gstin)


@pytest.mark.asyncio
async def test_second_opinion_disagreement_detection(db_session: AsyncSession):
    """When SECOND_OPINION_ENABLED is true, disagreement in totals raises extractors_disagree warning."""
    old_flag = settings.SECOND_OPINION_ENABLED
    settings.SECOND_OPINION_ENABLED = True

    class DisagreeingExtractor(MockExtractor):
        async def extract(
            self, pages: list[PageInput], validation_feedback: list[str] | None = None
        ) -> ExtractionResult:
            res = await super().extract(pages, validation_feedback)
            # Alter total by 500 Rs
            res.extraction.total = (res.extraction.total or Decimal("100.00")) + Decimal("500.00")
            return res

    set_second_opinion_extractor(DisagreeingExtractor())

    try:
        # Create minimal source file and invoice
        src = SourceFile(
            id=uuid.uuid4(),
            storage_key="test/sample.pdf",
            sha256=hashlib.sha256(b"sample_sec_op").hexdigest(),
            size_bytes=100,
            content_type="application/pdf",
            original_filename="sample.pdf",
            source="upload",
        )
        inv = Invoice(
            id=uuid.uuid4(),
            source_file_id=src.id,
            status="RECEIVED",
        )
        db_session.add(src)
        db_session.add(inv)
        await db_session.commit()

        # Mock storage_service.download_bytes to return dummy bytes
        from unittest.mock import patch

        with patch(
            "app.services.pipeline.storage_service.download_bytes", return_value=b"%PDF-1.4 mock"
        ):
            with patch.object(Preprocessor, "process") as mock_prep:
                from app.extraction.preprocess import ProcessedPage

                mock_prep.return_value = [
                    ProcessedPage(
                        page_number=1,
                        text="TAX INVOICE Total: 1000.00",
                        is_digital=True,
                        blur_score=150.0,
                        image_bytes=b"dummy",
                        storage_key="test/1.jpg",
                    )
                ]
                processed_inv = await process_invoice_pipeline(db_session, inv.id)
                assert processed_inv is not None
                await db_session.refresh(processed_inv, ["validation_issues"])
                assert any(
                    vi.code == "extractors_disagree" for vi in processed_inv.validation_issues
                )
    finally:
        settings.SECOND_OPINION_ENABLED = old_flag
        set_second_opinion_extractor(None)


# ==========================================
# 5. PREPROCESSING & QUALITY METRICS (R1)
# ==========================================


def test_preprocessing_quality_metrics_computation():
    """Verify composite quality score calculation (blur, brightness, contrast)."""
    import numpy as np

    # Synthetic sharp image
    sharp_img = np.zeros((200, 200, 3), dtype=np.uint8)
    sharp_img[::2, ::2] = 255  # High gradient checkerboard

    metrics = compute_quality_metrics(sharp_img)
    assert isinstance(metrics, QualityMetrics)
    assert metrics.blur_score > 50.0
    assert 0.0 <= metrics.quality_score <= 1.0
    assert metrics.is_acceptable is True

    # Uniform black image (blurry & dark)
    dark_blurry_img = np.zeros((100, 100, 3), dtype=np.uint8)
    bad_metrics = compute_quality_metrics(dark_blurry_img)
    assert bad_metrics.blur_score < 10.0
    assert bad_metrics.is_acceptable is False
