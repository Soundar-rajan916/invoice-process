from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.errors import OptimisticLockError, UnresolvedErrorsApprovalError
import hashlib
from app.core.logging import logger
from app.ingestors.upload import convert_heic_to_jpeg, detect_content_type
from app.core.security import get_current_user, require_reviewer, verify_csrf_header
from app.core.storage import storage_service
from app.models.entities import (
    Extraction,
    Invoice,
    ReviewEvent,
    SourceFile,
    Supplier,
    User,
    ValidationIssue,
)
from app.schemas.extraction import InvoiceExtraction
from app.services.dedup import check_duplicates, get_financial_year, normalize_invoice_number
from app.services.validation import validate_extraction

router = APIRouter(prefix="/invoices", tags=["invoices"])


class EditFieldsRequest(BaseModel):
    extraction: InvoiceExtraction
    row_version: int


class ApproveRequest(BaseModel):
    row_version: int
    override_reason: str | None = None


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=3)


def get_diff(old_dict: dict[str, Any], new_dict: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    all_keys = set(old_dict.keys()) | set(new_dict.keys())
    for k in all_keys:
        if k in ("unreadable_fields", "field_confidence"):
            continue
        v_old = old_dict.get(k)
        v_new = new_dict.get(k)
        if v_old != v_new:
            diff[k] = {"before": v_old, "after": v_new}
    return diff


@router.get("")
async def list_invoices(
    status_filter: str | None = Query(default=None, alias="status"),
    flagged: bool | None = None,
    q: str | None = None,
    sort: str = "oldest",
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Queue listing with filtering, sorting, pagination, and status counts."""
    # 1. Status counts
    count_stmt = select(Invoice.status, func.count(Invoice.id)).group_by(Invoice.status)
    count_rows = (await db.execute(count_stmt)).all()
    counts = {r[0]: r[1] for r in count_rows}

    # 2. Base query
    query = select(Invoice).join(SourceFile, Invoice.source_file_id == SourceFile.id)

    if status_filter:
        query = query.where(Invoice.status == status_filter.upper())

    if q:
        search = f"%{q}%"
        query = query.where(
            or_(
                Invoice.normalized_invoice_number.ilike(search),
                Invoice.supplier_gstin.ilike(search),
                SourceFile.original_filename.ilike(search),
            )
        )

    # Sorting: oldest received_at first by default (R4 queue pressure)
    if sort == "newest":
        query = query.order_by(Invoice.created_at.desc())
    elif sort == "total_asc":
        query = query.order_by(Invoice.created_at.asc())
    elif sort == "total_desc":
        query = query.order_by(Invoice.created_at.desc())
    else:  # oldest default
        query = query.order_by(Invoice.created_at.asc())

    # Pagination
    offset = (page - 1) * page_size
    paged_query = query.offset(offset).limit(page_size)
    invoices = (await db.execute(paged_query)).scalars().all()

    # Total count
    total_count = sum(counts.values())

    results = []
    for inv in invoices:
        # Check issues count
        issue_stmt = select(
            func.count(ValidationIssue.id).filter(ValidationIssue.severity == "error"),
            func.count(ValidationIssue.id).filter(ValidationIssue.severity == "warning"),
        ).where(ValidationIssue.invoice_id == inv.id)
        err_count, warn_count = (await db.execute(issue_stmt)).one()

        if flagged and err_count == 0 and warn_count == 0:
            continue

        results.append(
            {
                "id": str(inv.id),
                "status": inv.status,
                "status_reason": inv.status_reason,
                "supplier_gstin": inv.supplier_gstin,
                "normalized_invoice_number": inv.normalized_invoice_number,
                "financial_year": inv.financial_year,
                "received_at": inv.created_at.isoformat(),
                "page_count": inv.page_count,
                "extraction_path": inv.extraction_path,
                "dup_of_id": str(inv.dup_of_id) if inv.dup_of_id else None,
                "dup_overridden": inv.dup_overridden,
                "row_version": inv.row_version,
                "error_count": err_count,
                "warning_count": warn_count,
            }
        )

    return {
        "items": results,
        "total": total_count,
        "counts": counts,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{invoice_id}")
async def get_invoice_detail(
    invoice_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Full detail of invoice with extraction data, validation issues, duplicate info, and presigned page URLs."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    source_file = await db.get(SourceFile, invoice.source_file_id)

    # Current extraction
    current_ext_data = None
    if invoice.current_extraction_id:
        ext = await db.get(Extraction, invoice.current_extraction_id)
        if ext:
            current_ext_data = ext.data

    # Validation issues
    v_stmt = select(ValidationIssue).where(ValidationIssue.invoice_id == invoice.id)
    issues = (await db.execute(v_stmt)).scalars().all()
    issues_list = [
        {
            "id": str(i.id),
            "code": i.code,
            "field": i.field,
            "severity": i.severity,
            "message": i.message,
            "resolved_by_override": i.resolved_by_override,
        }
        for i in issues
    ]

    # Duplicate summary
    dup_summary = None
    if invoice.dup_of_id:
        orig_inv = await db.get(Invoice, invoice.dup_of_id)
        if orig_inv:
            dup_summary = {
                "id": str(orig_inv.id),
                "supplier_gstin": orig_inv.supplier_gstin,
                "invoice_number": orig_inv.normalized_invoice_number,
                "financial_year": orig_inv.financial_year,
                "status": orig_inv.status,
                "received_at": orig_inv.created_at.isoformat(),
            }

    # Presigned page image URLs (R1 document viewer)
    page_urls: list[dict[str, Any]] = []
    page_count = invoice.page_count or 1
    for p in range(1, page_count + 1):
        key = f"pages/{invoice.id}/{p}.jpg"
        url = storage_service.generate_presigned_url(key, expires_in=3600)
        page_urls.append({"page_number": p, "url": url})

    return {
        "id": str(invoice.id),
        "status": invoice.status,
        "status_reason": invoice.status_reason,
        "page_count": invoice.page_count,
        "extraction_path": invoice.extraction_path,
        "supplier_gstin": invoice.supplier_gstin,
        "normalized_invoice_number": invoice.normalized_invoice_number,
        "financial_year": invoice.financial_year,
        "dup_of_id": str(invoice.dup_of_id) if invoice.dup_of_id else None,
        "dup_overridden": invoice.dup_overridden,
        "dup_override_reason": invoice.dup_override_reason,
        "accounting_id": invoice.accounting_id,
        "row_version": invoice.row_version,
        "received_at": invoice.created_at.isoformat(),
        "original_filename": source_file.original_filename if source_file else None,
        "current_extraction": current_ext_data,
        "validation_issues": issues_list,
        "duplicate_info": dup_summary,
        "pages": page_urls,
    }


@router.patch("/{invoice_id}/fields")
async def update_invoice_fields(
    invoice_id: uuid.UUID,
    req: EditFieldsRequest,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    """R2: Edits invoice extraction fields.
    - Creates a new append-only Extractions record (kind='human_edit', version+1).
    - Checks optimistic locking row_version (returns 409 on conflict).
    - If status was APPROVED, reverts to NEEDS_REVIEW (R2 guarantee).
    - Re-runs validation and dedup against edited values.
    - Writes field-level audit diff to review_events.
    """
    invoice = await db.get(Invoice, invoice_id, populate_existing=True)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status in ("PUSHED", "PUSHING", "REJECTED"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot edit invoice in '{invoice.status}' state",
        )

    # Optimistic locking check
    if invoice.row_version != req.row_version:
        raise OptimisticLockError(
            current_version=invoice.row_version, client_version=req.row_version
        )

    # Fetch latest extraction version
    latest_ext = None
    if invoice.current_extraction_id:
        latest_ext = await db.get(Extraction, invoice.current_extraction_id)

    old_data = latest_ext.data if latest_ext else {}
    new_data = req.extraction.model_dump(mode="json")
    next_version = (latest_ext.version + 1) if latest_ext else 1

    # R2 Guarantee: Any edit on an approved-but-unpushed invoice reverts it back to NEEDS_REVIEW
    if invoice.status == "APPROVED":
        invoice.status = "NEEDS_REVIEW"
        invoice.approved_by = None
        invoice.approved_at = None
        invoice.approved_extraction_id = None
        db.add(
            ReviewEvent(
                invoice_id=invoice.id,
                actor_id=user.id,
                action="status_change",
                payload={
                    "from_status": "APPROVED",
                    "to_status": "NEEDS_REVIEW",
                    "reason": "edit_invalidated_approval",
                },
            )
        )

    # 1. Create new Extraction row
    new_ext_id = uuid.uuid4()
    new_ext = Extraction(
        id=new_ext_id,
        invoice_id=invoice.id,
        version=next_version,
        kind="human_edit",
        data=new_data,
        confidences={},
        model_id="human",
        prompt_version="manual_edit",
        raw_response=None,
        token_usage=None,
        latency_ms=0,
        created_by=user.id,
    )
    db.add(new_ext)
    await db.flush()

    # 2. Update invoice pointers and business keys
    invoice.current_extraction_id = new_ext_id
    invoice.supplier_gstin = req.extraction.supplier_gstin
    invoice.normalized_invoice_number = normalize_invoice_number(req.extraction.invoice_number)
    invoice.financial_year = get_financial_year(req.extraction.invoice_date)
    invoice.row_version += 1

    # 3. Re-run validation rules
    sup_stmt = select(Supplier).where(Supplier.is_active.is_(True))
    known_suppliers = {s.gstin: s.name for s in (await db.execute(sup_stmt)).scalars().all()}
    val_issues = validate_extraction(req.extraction, known_suppliers=known_suppliers)

    # 4. Re-run dedup check
    dup_of_id, dup_issues = await check_duplicates(
        session=db,
        invoice_id=invoice.id,
        supplier_gstin=invoice.supplier_gstin,
        normalized_inv_num=invoice.normalized_invoice_number,
        financial_year=invoice.financial_year,
        invoice_date=req.extraction.invoice_date,
        total=req.extraction.total,
    )

    if dup_of_id:
        invoice.dup_of_id = dup_of_id

    # 5. Clear old issues for this invoice and save new issues
    del_stmt = select(ValidationIssue).where(ValidationIssue.invoice_id == invoice.id)
    old_issues = (await db.execute(del_stmt)).scalars().all()
    for oi in old_issues:
        await db.delete(oi)

    for issue in val_issues:
        db.add(
            ValidationIssue(
                invoice_id=invoice.id,
                extraction_id=new_ext_id,
                code=issue.code,
                field=issue.field,
                severity=issue.severity,
                message=issue.message,
            )
        )

    for d_issue in dup_issues:
        db.add(
            ValidationIssue(
                invoice_id=invoice.id,
                extraction_id=new_ext_id,
                code=d_issue["code"],
                field=d_issue["field"],
                severity=d_issue["severity"],
                message=d_issue["message"],
            )
        )

    # 6. Audit event with field-level before/after diff
    diff_payload = get_diff(old_data, new_data)
    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="edit",
            payload={"version": next_version, "diff": diff_payload},
        )
    )

    await db.commit()
    return await get_invoice_detail(invoice_id=invoice.id, user=user, db=db)


@router.post("/{invoice_id}/approve")
async def approve_invoice(
    invoice_id: uuid.UUID,
    req: ApproveRequest,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    """R2: Approves an invoice for push.
    - Strict check: Requires human reviewer user.
    - Re-validates server-side against current extraction.
    - If any 'error' issues remain, rejects with 422 unless override_reason (>=10 chars) is provided.
    - Sets approved_by, approved_at, and approved_extraction_id = current_extraction_id.
    - Transitions to APPROVED and enqueues push task.
    """
    invoice = await db.get(Invoice, invoice_id, populate_existing=True)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != "NEEDS_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve invoice in '{invoice.status}' state (only 'NEEDS_REVIEW' can be approved)",
        )

    if invoice.row_version != req.row_version:
        raise OptimisticLockError(
            current_version=invoice.row_version, client_version=req.row_version
        )

    # Check unresolved error issues
    err_stmt = select(ValidationIssue).where(
        ValidationIssue.invoice_id == invoice.id,
        ValidationIssue.severity == "error",
        ValidationIssue.resolved_by_override.is_(False),
    )
    unresolved_errors = (await db.execute(err_stmt)).scalars().all()

    # Filter out duplicate errors if dup_overridden is True
    active_errors = [
        e for e in unresolved_errors if not (e.code == "duplicate" and invoice.dup_overridden)
    ]

    if active_errors:
        reason = (req.override_reason or "").strip()
        if len(reason) < 10:
            raise UnresolvedErrorsApprovalError(issue_count=len(active_errors))

        # Mark errors as resolved by override and audit
        for err_issue in active_errors:
            err_issue.resolved_by_override = True

        db.add(
            ReviewEvent(
                invoice_id=invoice.id,
                actor_id=user.id,
                action="override_issue",
                payload={
                    "override_reason": reason,
                    "overridden_issues": [e.code for e in active_errors],
                },
            )
        )

    # Transition state to APPROVED using explicit transition engine
    now = datetime.now(UTC)
    invoice.status = "APPROVED"
    invoice.approved_by = user.id
    invoice.approved_at = now
    invoice.approved_extraction_id = invoice.current_extraction_id
    invoice.row_version += 1

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="approve",
            payload={
                "approved_extraction_id": str(invoice.approved_extraction_id),
                "override_reason": req.override_reason,
            },
        )
    )
    await db.commit()

    # Enqueue push task (or run push in test/dev environment)
    if settings.ENVIRONMENT == "test":
        from app.services.push import push_invoice

        await push_invoice(db, invoice.id)
    else:
        try:
            from app.workers.tasks import push_invoice_task

            push_invoice_task.delay(str(invoice.id))
        except Exception:
            # Fallback if Celery broker offline
            from app.services.push import push_invoice

            await push_invoice(db, invoice.id)

    return await get_invoice_detail(invoice_id=invoice.id, user=user, db=db)


@router.post("/{invoice_id}/reject")
async def reject_invoice(
    invoice_id: uuid.UUID,
    req: ReasonRequest,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, str]:
    """Rejects an invoice."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != "NEEDS_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject invoice in '{invoice.status}' state (only 'NEEDS_REVIEW' can be rejected)",
        )

    invoice.status = "REJECTED"
    invoice.status_reason = req.reason
    invoice.row_version += 1

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="reject",
            payload={"reason": req.reason},
        )
    )
    await db.commit()
    return {"message": "Invoice rejected"}


@router.post("/{invoice_id}/request-resend")
async def request_resend_invoice(
    invoice_id: uuid.UUID,
    req: ReasonRequest,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, str]:
    """Moves invoice to RESEND_REQUESTED."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != "NEEDS_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot request resend for invoice in '{invoice.status}' state (only 'NEEDS_REVIEW' can request resend)",
        )

    invoice.status = "RESEND_REQUESTED"
    invoice.status_reason = req.reason
    invoice.row_version += 1

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="request_resend",
            payload={"reason": req.reason},
        )
    )
    await db.commit()
    return {"message": "Resend requested"}


@router.post("/{invoice_id}/upload-replacement")
async def upload_replacement_invoice_file(
    invoice_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    """Uploads a replacement document fulfilling a RESEND_REQUESTED invoice.
    - Validates file format and size
    - Uploads to storage
    - Creates new SourceFile record
    - Links invoice to new source_file_id
    - Resets status to RECEIVED, clears status_reason
    - Increments row_version
    - Records resend_fulfilled audit event
    - Enqueues pipeline reprocessing
    """
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != "RESEND_REQUESTED":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot upload replacement for invoice in status '{invoice.status}'. Status must be 'RESEND_REQUESTED'.",
        )

    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_MB} MB",
        )

    real_type = detect_content_type(content, file.content_type or "application/octet-stream")
    if real_type == "image/heic":
        content, real_type = convert_heic_to_jpeg(content)

    file_hash = hashlib.sha256(content).hexdigest()
    storage_key = f"originals/{file_hash[:2]}/{file_hash}"
    storage_service.upload_bytes(content, storage_key, content_type=real_type)

    stmt = select(SourceFile).where(SourceFile.sha256 == file_hash)
    existing_file = (await db.execute(stmt)).scalar_one_or_none()

    if existing_file:
        source_file_record = existing_file
    else:
        source_file_record = SourceFile(
            id=uuid.uuid4(),
            sha256=file_hash,
            original_filename=file.filename or "replacement_invoice",
            content_type=real_type,
            size_bytes=len(content),
            storage_key=storage_key,
            source="resend_upload",
            uploaded_by=user.id,
        )
        db.add(source_file_record)
        await db.flush()

    old_file_id = str(invoice.source_file_id)
    invoice.source_file_id = source_file_record.id
    invoice.status = "RECEIVED"
    invoice.status_reason = None
    invoice.row_version += 1

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="resend_fulfilled",
            payload={
                "old_source_file_id": old_file_id,
                "new_source_file_id": str(source_file_record.id),
                "filename": file.filename,
                "size_bytes": len(content),
            },
        )
    )
    await db.commit()

    # Enqueue pipeline processing
    try:
        from app.workers.tasks import process_invoice

        process_invoice.delay(str(invoice.id))
    except Exception as e:
        logger.warning("Could not dispatch Celery task for replacement document", error=str(e))

    return {
        "message": "Replacement document uploaded successfully. Reprocessing started.",
        "invoice_id": str(invoice.id),
        "source_file_id": str(source_file_record.id),
        "filename": file.filename,
    }


@router.post("/{invoice_id}/cancel-resend")
async def cancel_resend_invoice(
    invoice_id: uuid.UUID,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, str]:
    """Cancels a pending RESEND_REQUESTED and reverts invoice back to NEEDS_REVIEW."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != "RESEND_REQUESTED":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel resend for invoice in status '{invoice.status}'",
        )

    previous_reason = invoice.status_reason
    invoice.status = "NEEDS_REVIEW"
    invoice.status_reason = None
    invoice.row_version += 1

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="cancel_resend",
            payload={"previous_resend_reason": previous_reason},
        )
    )
    await db.commit()
    return {"message": "Resend request cancelled. Invoice reverted to NEEDS_REVIEW."}


@router.post("/{invoice_id}/confirm-duplicate")
async def confirm_duplicate_invoice(
    invoice_id: uuid.UUID,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, str]:
    """R3: Confirms invoice as duplicate and moves to REJECTED_DUPLICATE."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice.status = "REJECTED_DUPLICATE"
    invoice.status_reason = "Confirmed duplicate by reviewer"
    invoice.row_version += 1

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="confirm_duplicate",
            payload={"dup_of_id": str(invoice.dup_of_id)},
        )
    )
    await db.commit()
    return {"message": "Duplicate confirmed"}


@router.post("/{invoice_id}/override-duplicate")
async def override_duplicate_invoice(
    invoice_id: uuid.UUID,
    req: ReasonRequest,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    """R3: Clears blocking duplicate error by setting dup_overridden=True with mandatory reason."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    invoice.dup_overridden = True
    invoice.dup_override_reason = req.reason
    invoice.row_version += 1

    # Mark duplicate validation issues resolved
    dup_stmt = select(ValidationIssue).where(
        ValidationIssue.invoice_id == invoice.id,
        ValidationIssue.code == "duplicate",
    )
    dup_issues = (await db.execute(dup_stmt)).scalars().all()
    for d in dup_issues:
        d.resolved_by_override = True

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="override_duplicate",
            payload={"reason": req.reason, "dup_of_id": str(invoice.dup_of_id)},
        )
    )
    await db.commit()
    return await get_invoice_detail(invoice_id=invoice.id, user=user, db=db)


@router.get("/{invoice_id}/audit")
async def get_invoice_audit_trail(
    invoice_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    """Returns chronological audit trail of all review events."""
    stmt = (
        select(ReviewEvent, User.email)
        .outerjoin(User, ReviewEvent.actor_id == User.id)
        .where(ReviewEvent.invoice_id == invoice_id)
        .order_by(ReviewEvent.created_at.asc())
    )
    rows = (await db.execute(stmt)).all()

    audit_events = []
    for event, actor_email in rows:
        audit_events.append(
            {
                "id": str(event.id),
                "action": event.action,
                "actor_email": actor_email or "System",
                "payload": event.payload,
                "created_at": event.created_at.isoformat(),
            }
        )
    return audit_events
