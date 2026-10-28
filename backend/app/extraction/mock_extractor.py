from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logging import logger
from app.extraction.base import ExtractionResult, PageInput
from app.schemas.extraction import InvoiceExtraction, LineItem


class MockExtractor:
    """Mock extractor for CI, unit testing, and local development without Groq API keys.
    Reads ground truth records from MOCK_MANIFEST_PATH matching the filename.
    """

    def __init__(self, manifest_path: str | None = None) -> None:
        self.manifest_path = Path(manifest_path or settings.MOCK_MANIFEST_PATH)
        self._manifest_cache: dict[str, dict[str, Any]] | None = None

    def _load_manifest(self) -> dict[str, dict[str, Any]]:
        if self._manifest_cache is not None:
            return self._manifest_cache

        cache: dict[str, dict[str, Any]] = {}
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        record = json.loads(line)
                        file_key = record.get("file", "")
                        if file_key:
                            cache[file_key] = record
                            # Also index without .pdf extension
                            stem = Path(file_key).stem
                            cache[stem] = record
            except Exception as e:
                logger.warning(
                    "Could not parse mock manifest file", path=str(self.manifest_path), error=str(e)
                )

        self._manifest_cache = cache
        return self._manifest_cache

    async def extract(
        self,
        pages: list[PageInput],
        validation_feedback: list[str] | None = None,
    ) -> ExtractionResult:
        start_time = time.perf_counter()
        manifest = self._load_manifest()

        filename = pages[0].original_filename if pages and pages[0].original_filename else ""
        stem = Path(filename).stem if filename else ""

        record = manifest.get(filename) or manifest.get(stem) or manifest.get(f"{stem}.pdf")

        if record:
            line_items = [
                LineItem(
                    description=item.get("description"),
                    quantity=item.get("quantity"),
                    rate=item.get("rate"),
                    amount=item.get("amount"),
                )
                for item in record.get("line_items", [])
            ]
            extraction = InvoiceExtraction(
                invoice_number=record.get("invoice_number"),
                invoice_date=record.get("invoice_date"),
                supplier_name=record.get("supplier_name"),
                supplier_gstin=record.get("supplier_gstin"),
                line_items=line_items,
                taxable_value=record.get("taxable_value"),
                cgst=record.get("cgst"),
                sgst=record.get("sgst"),
                igst=record.get("igst"),
                total=record.get("total"),
                field_confidence={
                    "invoice_number": 1.0,
                    "invoice_date": 1.0,
                    "supplier_name": 1.0,
                    "supplier_gstin": 1.0,
                    "total": 1.0,
                },
                unreadable_fields=[],
            )
        else:
            # Fallback mock extraction
            extraction = InvoiceExtraction(
                invoice_number="INV-2026-0001",
                invoice_date="2026-04-10",
                supplier_name="Default Mock Supplier Ltd",
                supplier_gstin="33AAAAA0000A1Z5",
                line_items=[
                    LineItem(description="Item 1", quantity=10, rate=100, amount=1000),
                    LineItem(description="Item 2", quantity=5, rate=200, amount=1000),
                ],
                taxable_value=2000,
                cgst=180,
                sgst=180,
                igst=0,
                total=2360,
                field_confidence={
                    "invoice_number": 1.0,
                    "invoice_date": 1.0,
                    "supplier_name": 1.0,
                    "supplier_gstin": 1.0,
                    "total": 1.0,
                },
                unreadable_fields=[],
            )

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        extraction_path = "text" if all(p.is_digital for p in pages) else "vision"

        return ExtractionResult(
            extraction=extraction,
            extraction_path=extraction_path,
            model_id="mock-model-v1",
            prompt_version="v1.0",
            raw_response={"mock": True, "record_found": bool(record)},
            token_usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            latency_ms=duration_ms,
            retries_used=0,
        )
