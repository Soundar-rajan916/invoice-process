from __future__ import annotations

import hashlib
import io
import uuid

from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import DomainError
from app.core.logging import logger
from app.core.storage import storage_service
from app.ingestors.base import IncomingFile, IngestResult
from app.models.entities import Invoice, ReviewEvent, SourceFile


def detect_content_type(data: bytes, reported_type: str) -> str:
    """Validate the real content type by magic bytes, not just the header."""
    if data.startswith(b"%PDF"):
        return "application/pdf"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    if (
        len(data) >= 12
        and data[4:8] == b"ftyp"
        and data[8:12] in (b"heic", b"mif1", b"msf1", b"heix")
    ):
        return "image/heic"

    # Fallback to reported type if it starts with valid prefix
    if reported_type in ("application/pdf", "image/jpeg", "image/png", "image/webp"):
        return reported_type

    raise DomainError(
        title="Unsupported File Type",
        detail="Detected unsupported file magic bytes. Allowed formats: PDF, JPEG, PNG, WebP, HEIC.",
        status_code=415,
    )


def convert_heic_to_jpeg(data: bytes) -> tuple[bytes, str]:
    try:
        image = Image.open(io.BytesIO(data))
        out = io.BytesIO()
        image.convert("RGB").save(out, format="JPEG", quality=95)
        return out.getvalue(), "image/jpeg"
    except Exception as e:
        raise DomainError(
            title="HEIC Conversion Failed",
            detail=f"Could not convert HEIC file to JPEG: {e}. Please upload JPEG, PNG, or PDF directly.",
            status_code=422,
        ) from e


class UploadIngestor:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(self, raw: IncomingFile) -> IngestResult:
        # 1. Size validation
        max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
        if len(raw.content) > max_bytes:
            raise DomainError(
                title="File Too Large",
                detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_MB} MB",
                status_code=413,
            )

        # 2. Magic byte content-type detection
        real_type = detect_content_type(raw.content, raw.content_type)
        content_bytes = raw.content

        # Handle HEIC conversion
        if real_type == "image/heic":
            content_bytes, real_type = convert_heic_to_jpeg(content_bytes)

        # 3. Compute SHA-256 (R3 Layer 1)
        file_hash = hashlib.sha256(content_bytes).hexdigest()

        # Check existing source_files
        stmt = select(SourceFile).where(SourceFile.sha256 == file_hash)
        existing_file = (await self.session.execute(stmt)).scalar_one_or_none()

        if existing_file:
            inv_stmt = select(Invoice).where(Invoice.source_file_id == existing_file.id)
            existing_invoice = (await self.session.execute(inv_stmt)).scalars().first()
            inv_id = existing_invoice.id if existing_invoice else existing_file.id

            # If the invoice was waiting for a resend, fulfill the request and re-process!
            if existing_invoice and existing_invoice.status == "RESEND_REQUESTED":
                existing_invoice.status = "RECEIVED"
                existing_invoice.status_reason = None
                existing_invoice.row_version += 1

                event = ReviewEvent(
                    invoice_id=existing_invoice.id,
                    actor_id=raw.uploaded_by,
                    action="resend_fulfilled",
                    payload={
                        "sha256": file_hash,
                        "filename": raw.filename,
                        "source": "inbox_upload",
                        "reason": "Re-uploaded file fulfills resend request",
                    },
                )
                self.session.add(event)
                await self.session.commit()

                if settings.ENVIRONMENT != "test":
                    try:
                        from app.workers.tasks import process_invoice

                        process_invoice.delay(str(existing_invoice.id))
                    except Exception as e:
                        logger.warning(
                            "Could not dispatch Celery task for re-uploaded resend", error=str(e)
                        )
                else:
                    from app.services.pipeline import process_invoice_pipeline

                    await process_invoice_pipeline(self.session, existing_invoice.id)

                logger.info(
                    "Resend request fulfilled by re-uploaded file",
                    invoice_id=str(existing_invoice.id),
                    filename=raw.filename,
                )
                return IngestResult(
                    source_file_id=existing_file.id,
                    invoice_id=existing_invoice.id,
                    sha256=file_hash,
                    is_duplicate=False,
                    status="RECEIVED",
                    message="Replacement file accepted. Re-processing invoice pipeline...",
                )

            # Existing file: do not create new invoice. Write duplicate_file_skipped audit event
            event = ReviewEvent(
                invoice_id=inv_id,
                actor_id=raw.uploaded_by,
                action="duplicate_file_skipped",
                payload={
                    "sha256": file_hash,
                    "filename": raw.filename,
                    "existing_invoice_id": str(inv_id),
                },
            )
            self.session.add(event)
            await self.session.commit()

            logger.info(
                "Duplicate file uploaded and skipped", sha256=file_hash, filename=raw.filename
            )
            return IngestResult(
                source_file_id=existing_file.id,
                invoice_id=inv_id,
                sha256=file_hash,
                is_duplicate=True,
                status=existing_invoice.status if existing_invoice else "RECEIVED",
                message="File with identical SHA-256 content was previously uploaded.",
            )

        # 4. Store original in MinIO (immutable originals/{sha256[:2]}/{sha256})
        storage_key = f"originals/{file_hash[:2]}/{file_hash}"
        storage_service.upload_bytes(content_bytes, storage_key, content_type=real_type)

        # 5. Insert SourceFile and Invoice rows atomically in single transaction
        new_source_file = SourceFile(
            id=uuid.uuid4(),
            sha256=file_hash,
            original_filename=raw.filename,
            content_type=real_type,
            size_bytes=len(content_bytes),
            storage_key=storage_key,
            source=raw.source,
            uploaded_by=raw.uploaded_by,
        )
        self.session.add(new_source_file)
        await self.session.flush()

        new_invoice = Invoice(
            id=uuid.uuid4(),
            source_file_id=new_source_file.id,
            status="RECEIVED",
        )
        self.session.add(new_invoice)
        await self.session.commit()

        # 6. Enqueue processing task
        if settings.ENVIRONMENT != "test":
            try:
                from app.workers.tasks import process_invoice

                process_invoice.delay(str(new_invoice.id))
            except Exception as e:
                logger.warning(
                    "Could not dispatch Celery task (worker may be local/testing)", error=str(e)
                )

        return IngestResult(
            source_file_id=new_source_file.id,
            invoice_id=new_invoice.id,
            sha256=file_hash,
            is_duplicate=False,
            status="RECEIVED",
            message="File uploaded successfully and enqueued for processing.",
        )
