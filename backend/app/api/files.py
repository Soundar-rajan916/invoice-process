from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.storage import storage_service
from app.ingestors.base import IncomingFile
from app.ingestors.upload import UploadIngestor

router = APIRouter(prefix="/api/v1/files", tags=["File Ingestion"])


@router.get("/raw/{file_path:path}")
async def get_raw_file(file_path: str) -> Response:
    """Serves stored file or page images directly (for local/fallback storage)."""
    try:
        content = storage_service.download_bytes(file_path)
        media_type = "image/jpeg"
        if file_path.endswith(".png"):
            media_type = "image/png"
        elif file_path.endswith(".pdf"):
            media_type = "application/pdf"
        elif file_path.endswith(".webp"):
            media_type = "image/webp"
        return Response(content=content, media_type=media_type)
    except FileNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"File '{file_path}' not found"
        )


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
        status_label = "duplicate_skipped" if res.is_duplicate else "created"
        results.append(
            {
                "file_name": f.filename,
                "filename": f.filename,
                "source_file_id": str(res.source_file_id),
                "invoice_id": str(res.invoice_id),
                "sha256": res.sha256,
                "is_duplicate": res.is_duplicate,
                "status": status_label,
                "invoice_status": res.status,
                "message": res.message,
            }
        )

    return {
        "count": len(results),
        "results": results,
    }


@router.get("/raw/{file_path:path}")
async def get_raw_file(file_path: str) -> Response:
    """Serves raw files (e.g. rendered page images or original documents) from storage."""
    from app.core.storage import storage_service

    try:
        data = storage_service.download_bytes(file_path)
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    content_type = "application/octet-stream"
    lower_path = file_path.lower()
    if lower_path.endswith(".jpg") or lower_path.endswith(".jpeg"):
        content_type = "image/jpeg"
    elif lower_path.endswith(".png"):
        content_type = "image/png"
    elif lower_path.endswith(".pdf"):
        content_type = "application/pdf"
    elif lower_path.endswith(".webp"):
        content_type = "image/webp"

    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
