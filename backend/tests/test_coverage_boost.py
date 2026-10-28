from __future__ import annotations

import io
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainError
from app.extraction.base import PageInput
from app.extraction.groq_extractor import GroqExtractor
from app.extraction.grouping import PageGrouper
from app.extraction.preprocess import ProcessedPage
from app.ingestors.base import IncomingFile
from app.ingestors.upload import UploadIngestor, detect_content_type
from app.models.entities import Extraction, Invoice
from app.schemas.extraction import InvoiceExtraction
from app.services.dedup import check_duplicates


@pytest.mark.asyncio
async def test_api_upload_endpoint(client: AsyncClient):
    pdf_content = b"%PDF-1.4 dummy valid pdf content for endpoint test"
    files = [("files", ("invoice.pdf", pdf_content, "application/pdf"))]
    resp = await client.post("/api/v1/files", files=files)
    assert resp.status_code == 201
    data = resp.json()
    assert data["count"] == 1
    assert data["results"][0]["filename"] == "invoice.pdf"
    assert not data["results"][0]["is_duplicate"]


def test_magic_byte_detection_and_heic():
    assert detect_content_type(b"%PDF-1.5", "") == "application/pdf"
    assert detect_content_type(b"\xff\xd8\xff\xe0", "") == "image/jpeg"
    assert detect_content_type(b"\x89PNG\r\n\x1a\n", "") == "image/png"
    assert detect_content_type(b"RIFF\x00\x00\x00\x00WEBP", "") == "image/webp"

    # Unsupported format raises DomainError
    with pytest.raises(DomainError):
        detect_content_type(b"UNKNOWN_BINARY_BYTES", "")


@pytest.mark.asyncio
async def test_groq_vision_path_and_recompression(dummy_page: PageInput):
    extractor = GroqExtractor()
    # Create large image bytes exceeding max_bytes budget
    large_img = Image.new("RGB", (2000, 2000), color="white")
    buf = io.BytesIO()
    large_img.save(buf, format="JPEG", quality=95)
    large_bytes = buf.getvalue()

    vision_page = PageInput(
        page_number=1,
        text="",
        image_bytes=large_bytes,
        is_digital=False,  # forces vision path
        storage_key="test_large.jpg",
        original_filename="large.jpg",
    )

    choice = MagicMock(
        message=MagicMock(
            content='{"invoice_number": "INV-VISION-1", "total": 1200, "line_items": []}'
        )
    )
    mock_resp = MagicMock(choices=[choice], usage=None)

    with patch(
        "groq.resources.chat.completions.AsyncCompletions.create", AsyncMock(return_value=mock_resp)
    ):
        res = await extractor.extract([vision_page])
        assert res.extraction_path == "vision"
        assert res.extraction.invoice_number == "INV-VISION-1"


@pytest.mark.asyncio
async def test_layer3_fuzzy_duplicate_detection(db_session: AsyncSession):
    import uuid
    from datetime import date
    from decimal import Decimal

    inv1_id = uuid.uuid4()
    ext1_id = uuid.uuid4()

    ext1 = Extraction(
        id=ext1_id,
        invoice_id=inv1_id,
        version=1,
        kind="model",
        data={"invoice_date": "2026-04-10", "total": "5000.00"},
        confidences={},
    )
    inv1 = Invoice(
        id=inv1_id,
        source_file_id=uuid.uuid4(),
        status="NEEDS_REVIEW",
        supplier_gstin="27AAPFU0939F1ZV",
        normalized_invoice_number="INV100",
        financial_year="2026-27",
        current_extraction_id=ext1_id,
    )
    db_session.add_all([inv1, ext1])
    await db_session.flush()

    # Second invoice with same supplier, same total, same date, but different normalized number
    inv2_id = uuid.uuid4()
    _, issues = await check_duplicates(
        session=db_session,
        invoice_id=inv2_id,
        supplier_gstin="27AAPFU0939F1ZV",
        normalized_inv_num="INV999",  # Different number
        financial_year="2026-27",
        invoice_date=date(2026, 4, 10),
        total=Decimal("5000.00"),
    )

    assert any(i["code"] == "possible_duplicate" for i in issues)


def test_page_grouper_multi_invoice_split():
    # Page 1 of Invoice 1
    p1 = ProcessedPage(
        page_number=1,
        text="Invoice No: INV-01\nPage 1 of 1",
        is_digital=True,
        blur_score=100.0,
        image_bytes=b"bytes1",
        storage_key="k1",
    )
    # Page 1 of Invoice 2
    p2 = ProcessedPage(
        page_number=2,
        text="Invoice No: INV-02\nPage 1 of 1",
        is_digital=True,
        blur_score=100.0,
        image_bytes=b"bytes2",
        storage_key="k2",
    )

    groups = PageGrouper.group_pages([p1, p2])
    assert len(groups) == 2
    assert groups[0].detected_invoice_number == "INV-01"
    assert groups[1].detected_invoice_number == "INV-02"


@pytest.mark.asyncio
async def test_error_handlers_rfc7807(client: AsyncClient):
    # Validation error 422
    resp = await client.post(
        "/api/v1/files", content=b"invalid body", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 422
    assert resp.headers["content-type"] == "application/problem+json"
    body = resp.json()
    assert body["type"] == "https://invoiceflow.local/errors/validation-error"
    assert "errors" in body["extra"]


def test_domain_error_classes():
    from app.core.errors import (
        DuplicateInvoiceError,
        OptimisticLockError,
        UnresolvedErrorsApprovalError,
    )

    e1 = OptimisticLockError(current_version=2, client_version=1)
    assert e1.status_code == 409
    assert e1.extra["current_version"] == 2

    e2 = UnresolvedErrorsApprovalError(issue_count=3)
    assert e2.status_code == 422
    assert e2.extra["issue_count"] == 3

    e3 = DuplicateInvoiceError("INV1", "GSTIN1", "ID1")
    assert e3.status_code == 409
    assert e3.extra["existing_invoice_id"] == "ID1"


def test_logging_and_sensitive_data():
    from app.core.logging import drop_sensitive_data, setup_logging

    setup_logging()
    data = {
        "api_key": "secret123",
        "user_password": "mypassword",
        "presigned_url": "https://s3.local/test?X-Amz-Signature=xyz",
        "normal_field": "ok_value",
    }
    redacted = drop_sensitive_data(None, "info", data)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["user_password"] == "[REDACTED]"
    assert redacted["presigned_url"] == "[REDACTED_PRESIGNED_URL]"
    assert redacted["normal_field"] == "ok_value"


def test_money_and_schema_parsing():
    from app.schemas.extraction import LineItem, parse_money

    assert parse_money("₹ 1,23,456.50") == 123456.50
    assert parse_money("Rs. 500") == 500.00
    assert parse_money(None) is None
    assert parse_money("") is None

    inv = InvoiceExtraction(
        total="₹ 2,500.75",
        line_items=[LineItem(description="Item", quantity=2, rate=1250, amount="2,500.00")],
    )
    serialized = inv.model_dump(mode="json")
    assert serialized["total"] == "2500.75"
    assert serialized["line_items"][0]["amount"] == "2500.00"


def test_guid_type_decorator():
    import uuid

    from app.core.database import GUID

    guid = GUID()
    u = uuid.uuid4()
    assert guid.process_bind_param(None, MagicMock()) is None
    assert guid.process_bind_param(u, MagicMock(name="sqlite")) == str(u)
    assert guid.process_result_value(str(u), MagicMock(name="sqlite")) == u
    assert guid.process_result_value(None, MagicMock()) is None


@pytest.mark.asyncio
async def test_pipeline_missing_source_file(db_session: AsyncSession):
    import uuid

    from app.models.entities import Invoice
    from app.services.pipeline import process_invoice_pipeline

    dummy_inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),  # Non-existent
        status="RECEIVED",
    )
    db_session.add(dummy_inv)
    await db_session.flush()

    res = await process_invoice_pipeline(db_session, dummy_inv.id)
    assert res is not None
    assert res.status == "FAILED"
    assert "missing" in (res.status_reason or "")


@pytest.mark.asyncio
async def test_upload_ingestor_file_too_large(db_session: AsyncSession):
    from app.core.config import settings
    from app.core.errors import DomainError

    ingestor = UploadIngestor(db_session)
    large_bytes = b"x" * (settings.MAX_UPLOAD_MB * 1024 * 1024 + 10)
    file_input = IncomingFile(
        filename="huge.pdf", content=large_bytes, content_type="application/pdf"
    )
    with pytest.raises(DomainError) as exc_info:
        await ingestor.ingest(file_input)
    assert exc_info.value.status_code == 413


@pytest.mark.asyncio
async def test_storage_service_methods():
    from app.core.storage import StorageService

    storage = StorageService()
    test_key = "test/file.txt"
    test_data = b"Hello, storage!"

    # upload
    storage.upload_bytes(test_data, test_key, "text/plain")

    # download
    retrieved = storage.download_bytes(test_key)
    assert retrieved == test_data

    # presigned url
    url = storage.generate_presigned_url(test_key)
    assert url is not None


@pytest.mark.asyncio
async def test_pipeline_cas_and_already_processed(db_session: AsyncSession):
    import uuid

    from app.models.entities import Invoice
    from app.services.pipeline import process_invoice_pipeline

    # Invoice already in PROCESSING
    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=uuid.uuid4(),
        status="PROCESSING",
    )
    db_session.add(inv)
    await db_session.flush()

    res = await process_invoice_pipeline(db_session, inv.id)
    assert res is None


@pytest.mark.asyncio
async def test_validation_edge_cases():
    from datetime import date
    from decimal import Decimal

    from app.schemas.extraction import LineItem
    from app.services.validation import validate_extraction

    # CGST != SGST
    ext = InvoiceExtraction(
        invoice_number="INV-101",
        invoice_date=date.today(),
        supplier_name="Acme Corp",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[
            LineItem(
                description="Item",
                quantity=Decimal("1"),
                rate=Decimal("100"),
                amount=Decimal("100"),
            )
        ],
        taxable_value=Decimal("100"),
        cgst=Decimal("9"),
        sgst=Decimal("10"),  # unequal
        igst=Decimal("0"),
        total=Decimal("119"),
        field_confidence={"total": 0.5},  # low confidence
        unreadable_fields=["supplier_phone"],
    )
    issues = validate_extraction(ext)
    codes = [i.code for i in issues]
    assert "cgst_sgst_unequal" in codes
    assert "low_confidence" in codes

    # Inter-state vs intra-state mismatch
    # 27 is Maharashtra. If buyer is 33 (Tamil Nadu), CGST+SGST charged instead of IGST is tax_type_mismatch
    assert "tax_type_mismatch" in codes


@pytest.mark.asyncio
async def test_pipeline_duplicate_detection(db_session: AsyncSession):
    import uuid

    import fitz

    from app.core.storage import storage_service
    from app.models.entities import Invoice, SourceFile
    from app.services.pipeline import process_invoice_pipeline

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Tax Invoice INV-100 Acme Corp 27AAPFU0939F1ZV")
    content = doc.tobytes()
    doc.close()

    sf1 = SourceFile(
        id=uuid.uuid4(),
        sha256="hash1",
        original_filename="inv1.pdf",
        content_type="application/pdf",
        size_bytes=len(content),
        storage_key="test/inv1.pdf",
        source="upload",
    )
    sf2 = SourceFile(
        id=uuid.uuid4(),
        sha256="hash2",
        original_filename="inv2.pdf",
        content_type="application/pdf",
        size_bytes=len(content),
        storage_key="test/inv2.pdf",
        source="upload",
    )
    storage_service.upload_bytes(content, "test/inv1.pdf", "application/pdf")
    storage_service.upload_bytes(content, "test/inv2.pdf", "application/pdf")

    inv1 = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf1.id,
        status="NEEDS_REVIEW",
        supplier_gstin="27AAPFU0939F1ZV",
        normalized_invoice_number="INV100",
        financial_year="2025-26",
    )
    inv2 = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf2.id,
        status="RECEIVED",
    )
    db_session.add_all([sf1, sf2, inv1, inv2])
    await db_session.flush()

    from datetime import date
    from decimal import Decimal
    from unittest.mock import AsyncMock, patch

    from app.extraction.base import ExtractionResult

    mock_result = ExtractionResult(
        extraction=InvoiceExtraction(
            invoice_number="INV-100",
            invoice_date=date(2026, 3, 1),
            supplier_name="Acme Corp",
            supplier_gstin="27AAPFU0939F1ZV",
            total=Decimal("100"),
            line_items=[],
        ),
        raw_response={},
        token_usage={},
        latency_ms=10,
        model_id="mock",
        prompt_version="v1",
        extraction_path="text",
    )

    with patch("app.services.pipeline.get_extractor") as mock_get_ext:
        mock_ext = AsyncMock()
        mock_ext.extract.return_value = mock_result
        mock_get_ext.return_value = mock_ext

        res = await process_invoice_pipeline(db_session, inv2.id)
        assert res.status == "NEEDS_REVIEW"
        assert res.dup_of_id == inv1.id


@pytest.mark.asyncio
async def test_pipeline_validation_error_repair_retry(db_session: AsyncSession):
    import uuid
    from datetime import date
    from decimal import Decimal
    from unittest.mock import AsyncMock, patch

    import fitz

    from app.core.config import settings
    from app.core.storage import storage_service
    from app.extraction.base import ExtractionResult
    from app.models.entities import Invoice, SourceFile
    from app.schemas.extraction import LineItem
    from app.services.pipeline import process_invoice_pipeline

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Tax Invoice INV-999 Acme Corp 27AAPFU0939F1ZV")
    content = doc.tobytes()
    doc.close()

    sf = SourceFile(
        id=uuid.uuid4(),
        sha256="repair_hash",
        original_filename="repair.pdf",
        content_type="application/pdf",
        size_bytes=len(content),
        storage_key="test/repair.pdf",
        source="upload",
    )
    storage_service.upload_bytes(content, "test/repair.pdf", "application/pdf")

    inv = Invoice(
        id=uuid.uuid4(),
        source_file_id=sf.id,
        status="RECEIVED",
    )
    db_session.add_all([sf, inv])
    await db_session.flush()

    # Initial result with error (missing invoice_number)
    initial_res = ExtractionResult(
        extraction=InvoiceExtraction(
            invoice_number=None,
            invoice_date=date(2026, 3, 1),
            supplier_name="Acme Corp",
            supplier_gstin="27AAPFU0939F1ZV",
            total=Decimal("100"),
            line_items=[
                LineItem(
                    description="Item",
                    quantity=Decimal("1"),
                    rate=Decimal("100"),
                    amount=Decimal("100"),
                )
            ],
        ),
        raw_response={},
        token_usage={},
        latency_ms=10,
        model_id="groq-test",
        prompt_version="v1",
        extraction_path="text",
    )

    # Repaired result with invoice_number fixed
    repaired_res = ExtractionResult(
        extraction=InvoiceExtraction(
            invoice_number="INV-999",
            invoice_date=date(2026, 3, 1),
            supplier_name="Acme Corp",
            supplier_gstin="27AAPFU0939F1ZV",
            total=Decimal("100"),
            line_items=[
                LineItem(
                    description="Item",
                    quantity=Decimal("1"),
                    rate=Decimal("100"),
                    amount=Decimal("100"),
                )
            ],
        ),
        raw_response={},
        token_usage={},
        latency_ms=10,
        model_id="groq-test",
        prompt_version="v1",
        extraction_path="text",
    )

    mock_ext = AsyncMock()
    mock_ext.extract.side_effect = [initial_res, repaired_res]

    with patch.object(settings, "EXTRACTOR", "groq"):
        with patch("app.services.pipeline.get_extractor", return_value=mock_ext):
            res = await process_invoice_pipeline(db_session, inv.id)
            assert res.status == "NEEDS_REVIEW"
            assert res.normalized_invoice_number == "INV999"
