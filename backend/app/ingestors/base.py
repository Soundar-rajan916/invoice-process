from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol


@dataclass
class IncomingFile:
    filename: str
    content: bytes
    content_type: str
    source: str = "upload"  # upload | email | whatsapp
    uploaded_by: uuid.UUID | None = None


@dataclass
class IngestResult:
    source_file_id: uuid.UUID
    invoice_id: uuid.UUID
    sha256: str
    is_duplicate: bool
    status: str
    message: str


class Ingestor(Protocol):
    async def ingest(self, raw: IncomingFile) -> IngestResult: ...
