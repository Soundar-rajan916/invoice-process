from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from groq import RateLimitError

from app.core.model_check import check_groq_models_at_startup
from app.extraction.base import ExtractionResult, PageInput
from app.extraction.groq_extractor import GroqExtractor
from app.schemas.extraction import InvoiceExtraction, LineItem


@pytest.fixture
def dummy_page() -> PageInput:
    return PageInput(
        page_number=1,
        text="TAX INVOICE\nInvoice No: INV-100\nDate: 01/04/2026\nTotal: 1500.00",
        image_bytes=b"dummy_jpeg_bytes",
        is_digital=True,
        storage_key="pages/test/1.jpg",
        original_filename="inv.pdf",
    )


@pytest.mark.asyncio
async def test_groq_extractor_json_repair_retry(dummy_page: PageInput):
    extractor = GroqExtractor()

    invalid_msg = MagicMock()
    invalid_msg.content = "INVALID NON-JSON OUTPUT {"
    choice1 = MagicMock()
    choice1.message = invalid_msg
    resp1 = MagicMock(
        choices=[choice1], usage=MagicMock(prompt_tokens=10, completion_tokens=10, total_tokens=20)
    )

    valid_json = {
        "invoice_number": "INV-100",
        "invoice_date": "2026-04-01",
        "supplier_name": "Acme Supplier",
        "supplier_gstin": "33AAAAA0000A1Z5",
        "line_items": [{"description": "Item A", "quantity": 1, "rate": 1500, "amount": 1500}],
        "taxable_value": 1500,
        "cgst": 0,
        "sgst": 0,
        "igst": 0,
        "total": 1500,
        "field_confidence": {},
        "unreadable_fields": [],
    }
    valid_msg = MagicMock()
    valid_msg.content = json.dumps(valid_json)
    choice2 = MagicMock()
    choice2.message = valid_msg
    resp2 = MagicMock(
        choices=[choice2], usage=MagicMock(prompt_tokens=10, completion_tokens=10, total_tokens=20)
    )

    mock_create = AsyncMock(side_effect=[resp1, resp2])

    with patch("groq.resources.chat.completions.AsyncCompletions.create", mock_create):
        res = await extractor.extract([dummy_page])
        assert res.retries_used == 1
        assert res.extraction.invoice_number == "INV-100"
        assert res.extraction.total == 1500


@pytest.mark.asyncio
async def test_groq_extractor_rate_limit_backoff(dummy_page: PageInput):
    extractor = GroqExtractor()

    # Create dummy httpx response with retry-after header
    mock_http_resp = httpx.Response(
        status_code=429,
        headers={"retry-after": "0.1"},
        request=httpx.Request("POST", "https://api.groq.com"),
    )
    rate_limit_err = RateLimitError("Rate limit exceeded", response=mock_http_resp, body=None)

    valid_json = {
        "invoice_number": "INV-200",
        "total": 500,
        "line_items": [],
    }
    choice = MagicMock(message=MagicMock(content=json.dumps(valid_json)))
    success_resp = MagicMock(choices=[choice], usage=None)

    mock_create = AsyncMock(side_effect=[rate_limit_err, success_resp])

    with patch("groq.resources.chat.completions.AsyncCompletions.create", mock_create):
        res = await extractor.extract([dummy_page])
        assert res.extraction.invoice_number == "INV-200"


def test_batch_merge_preserves_order_and_totals():
    # Batch 1: Header + Line items 1 & 2
    ext1 = InvoiceExtraction(
        invoice_number="INV-BATCH-01",
        invoice_date="2026-04-01",
        supplier_name="Batch Supplier",
        supplier_gstin="33AAAAA0000A1Z5",
        line_items=[
            LineItem(description="Line 1", amount=100),
            LineItem(description="Line 2", amount=200),
        ],
        total=None,
    )
    res1 = ExtractionResult(
        extraction=ext1,
        extraction_path="vision",
        model_id="test-vision",
        prompt_version="v1",
        raw_response={},
        token_usage={"prompt_tokens": 100, "completion_tokens": 50},
        latency_ms=500,
    )

    # Batch 2: Line items 3 & 4 + Totals
    ext2 = InvoiceExtraction(
        invoice_number=None,
        line_items=[
            LineItem(description="Line 3", amount=300),
            LineItem(description="Line 4", amount=400),
        ],
        taxable_value=1000,
        total=1180,
    )
    res2 = ExtractionResult(
        extraction=ext2,
        extraction_path="vision",
        model_id="test-vision",
        prompt_version="v1",
        raw_response={},
        token_usage={"prompt_tokens": 100, "completion_tokens": 50},
        latency_ms=600,
    )

    merged = GroqExtractor.merge_batch_extractions([res1, res2])
    assert merged.extraction.invoice_number == "INV-BATCH-01"
    assert len(merged.extraction.line_items) == 4
    assert [i.description for i in merged.extraction.line_items] == [
        "Line 1",
        "Line 2",
        "Line 3",
        "Line 4",
    ]
    assert merged.extraction.total == 1180
    assert merged.token_usage["total_tokens"] == 300


@pytest.mark.asyncio
async def test_startup_model_check_missing_model():
    with (
        patch("app.core.config.settings.EXTRACTOR", "groq"),
        patch("app.core.config.settings.GROQ_API_KEY", "dummy_key"),
        patch("app.core.config.settings.GROQ_TEXT_MODEL", "missing-model-id"),
    ):
        mock_models = MagicMock()
        mock_models.data = [MagicMock(id="model-a"), MagicMock(id="model-b")]

        with patch("groq.resources.models.AsyncModels.list", AsyncMock(return_value=mock_models)):
            with pytest.raises(RuntimeError) as exc_info:
                await check_groq_models_at_startup()
            assert "missing-model-id" in str(exc_info.value)
            assert "Available models are" in str(exc_info.value)
