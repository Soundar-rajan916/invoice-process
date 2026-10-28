from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.ingestors.base import IncomingFile
from app.ingestors.upload import UploadIngestor

router = APIRouter(prefix="/api/v1/files", tags=["File Ingestion"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_files(
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Ingests one or more invoice files (PDF, JPEG, PNG, WebP, HEIC).
    Computes SHA-256 for Layer 1 deduplication.
    Enqueues processing pipeline for new files.
    """
    ingestor = UploadIngestor(session)
    results = []

    for f in files:
        content = await f.read()
        incoming = IncomingFile(
            filename=f.filename or "uploaded_invoice",
            content=content,
            content_type=f.content_type or "application/octet-stream",
            source="upload",
        )
        res = await ingestor.ingest(incoming)
        results.append(
            {
                "filename": f.filename,
                "source_file_id": str(res.source_file_id),
                "invoice_id": str(res.invoice_id),
                "sha256": res.sha256,
                "is_duplicate": res.is_duplicate,
                "status": res.status,
                "message": res.message,
            }
        )

    return {
        "count": len(results),
        "results": results,
    }
