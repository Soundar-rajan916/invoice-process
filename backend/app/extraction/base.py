from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.schemas.extraction import InvoiceExtraction


@dataclass
class PageInput:
    page_number: int
    text: str
    image_bytes: bytes
    is_digital: bool
    storage_key: str
    original_filename: str | None = None


@dataclass
class ExtractionResult:
    extraction: InvoiceExtraction
    extraction_path: str  # text | vision
    model_id: str | None
    prompt_version: str
    raw_response: dict[str, Any] | None
    token_usage: dict[str, Any] | None
    latency_ms: int
    retries_used: int = 0


class Extractor(Protocol):
    async def extract(
        self,
        pages: list[PageInput],
        validation_feedback: list[str] | None = None,
    ) -> ExtractionResult: ...
