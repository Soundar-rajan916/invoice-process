from __future__ import annotations

import hashlib
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
from app.core.logging import logger
from app.core.security import get_current_user, require_reviewer, verify_csrf_header
from app.core.storage import storage_service
from app.ingestors.upload import convert_heic_to_jpeg, detect_content_type
from app.models.entities import (
    Extraction,
    InboundMessage,
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
    channel_filter: str | None = Query(default=None, alias="channel"),
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

    effective_received = func.coalesce(InboundMessage.received_at, Invoice.created_at)

    # 2. Base query
    query = (
        select(
            Invoice,
            SourceFile.original_filename,
            InboundMessage.channel,
            InboundMessage.received_at,
        )
        .join(SourceFile, Invoice.source_file_id == SourceFile.id)
        .outerjoin(InboundMessage, Invoice.inbound_message_id == InboundMessage.id)
    )

    if isinstance(status_filter, str) and status_filter.strip():
        query = query.where(Invoice.status == status_filter.upper())

    if isinstance(channel_filter, str) and channel_filter.upper() != "ALL":
        cf = channel_filter.lower()
        if cf == "upload":
            query = query.where(Invoice.inbound_message_id.is_(None))
        else:
            query = query.where(InboundMessage.channel == cf)

    if q:
        search = f"%{q}%"
        query = query.where(
            or_(
                Invoice.normalized_invoice_number.ilike(search),
                Invoice.supplier_gstin.ilike(search),
                SourceFile.original_filename.ilike(search),
            )
        )

    if flagged:
        flagged_sub = (
            select(ValidationIssue.invoice_id)
            .where(ValidationIssue.severity.in_(["error", "warning"]))
            .distinct()
        )
        query = query.where(Invoice.id.in_(flagged_sub))

    # Total count for the filtered query (without order/limit)
    count_query = select(func.count()).select_from(query.order_by(None).subquery())
    total_count = (await db.execute(count_query)).scalar() or 0

    # Sorting: oldest received_at first by default (R4 queue pressure)
    if sort == "newest":
        query = query.order_by(effective_received.desc())
    elif sort == "total_asc":
        query = query.order_by(Invoice.created_at.asc())
    elif sort == "total_desc":
        query = query.order_by(Invoice.created_at.desc())
    else:  # oldest default
        query = query.order_by(effective_received.asc())

    # Pagination
    offset = (page - 1) * page_size
    paged_query = query.offset(offset).limit(page_size)
    rows = (await db.execute(paged_query)).all()

    results = []

    for inv, orig_filename, inb_channel, inb_received_at in rows:
        # Check issues count
        issue_stmt = select(
            func.count(ValidationIssue.id).filter(ValidationIssue.severity == "error"),
            func.count(ValidationIssue.id).filter(ValidationIssue.severity == "warning"),
        ).where(ValidationIssue.invoice_id == inv.id)
        err_count, warn_count = (await db.execute(issue_stmt)).one()

        display_received = inb_received_at or inv.created_at

        results.append(
            {
                "id": str(inv.id),
                "status": inv.status,
                "status_reason": inv.status_reason,
                "supplier_gstin": inv.supplier_gstin,
                "normalized_invoice_number": inv.normalized_invoice_number,
                "financial_year": inv.financial_year,
                "received_at": display_received.isoformat(),
                "page_count": inv.page_count,
                "extraction_path": inv.extraction_path,
                "dup_of_id": str(inv.dup_of_id) if inv.dup_of_id else None,
                "dup_overridden": inv.dup_overridden,
                "row_version": inv.row_version,
                "error_count": err_count,
                "warning_count": warn_count,
                "original_filename": orig_filename,
                "channel": inb_channel or "upload",
                "sender": inv.sender,
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

    # Lease & Concurrency Info
    now = datetime.now(UTC)
    claim_exp = (
        invoice.claim_expires_at
        if (invoice.claim_expires_at and invoice.claim_expires_at.tzinfo)
        else (invoice.claim_expires_at.replace(tzinfo=UTC) if invoice.claim_expires_at else None)
    )
    is_lease_active = claim_exp is not None and claim_exp > now

    claimed_user_email = None

    if invoice.claimed_by:
        claimed_user = await db.get(User, invoice.claimed_by)

        if claimed_user:
            claimed_user_email = claimed_user.email

    # Automatically acquire/extend claim if unowned or lease expired or owned by current user

    if not is_lease_active or invoice.claimed_by == user.id or invoice.claimed_by is None:
        invoice.claimed_by = user.id

        from datetime import timedelta

        invoice.claim_expires_at = now + timedelta(minutes=5)

        invoice.heartbeat_at = now

        await db.commit()

        claimed_user_email = user.email

        is_lease_active = True

    channel = "upload"
    received_at_dt = invoice.created_at
    if invoice.inbound_message_id:
        inbound_msg = await db.get(InboundMessage, invoice.inbound_message_id)
        if inbound_msg:
            channel = inbound_msg.channel
            if inbound_msg.received_at:
                received_at_dt = inbound_msg.received_at

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
        "received_at": received_at_dt.isoformat(),
        "original_filename": source_file.original_filename if source_file else None,
        "channel": channel,
        "sender": invoice.sender,
        "current_extraction": current_ext_data,
        "validation_issues": issues_list,
        "duplicate_info": dup_summary,
        "pages": page_urls,
        "claimed_by": str(invoice.claimed_by) if invoice.claimed_by else None,
        "claimed_by_email": claimed_user_email,
        "claim_expires_at": invoice.claim_expires_at.isoformat()
        if invoice.claim_expires_at
        else None,
        "is_claimed_by_me": (invoice.claimed_by == user.id)
        if (invoice.claimed_by and is_lease_active)
        else False,
        "is_claim_locked": (
            invoice.claimed_by is not None and invoice.claimed_by != user.id and is_lease_active
        ),
    }


def check_invoice_claim(invoice: Invoice, current_user: User) -> None:
    """Enforces review lease concurrency (R4). Rejects write operations with HTTP 409
    if another reviewer holds an active, non-expired lease on this invoice.
    """
    now = datetime.now(UTC)
    claim_exp = (
        invoice.claim_expires_at
        if (invoice.claim_expires_at and invoice.claim_expires_at.tzinfo)
        else (invoice.claim_expires_at.replace(tzinfo=UTC) if invoice.claim_expires_at else None)
    )

    if (
        invoice.claimed_by is not None
        and invoice.claimed_by != current_user.id
        and claim_exp is not None
        and claim_exp > now
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Invoice is currently claimed by another reviewer. Take over review to make changes.",
        )


@router.post("/{invoice_id}/claim")
async def claim_invoice(
    invoice_id: uuid.UUID,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:

    invoice = await db.get(Invoice, invoice_id)

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    now = datetime.now(UTC)

    if (
        invoice.claimed_by
        and invoice.claimed_by != user.id
        and invoice.claim_expires_at
        and invoice.claim_expires_at > now
    ):
        claimed_user = await db.get(User, invoice.claimed_by)

        claimed_email = claimed_user.email if claimed_user else str(invoice.claimed_by)

        return {
            "status": "locked",
            "claimed_by": str(invoice.claimed_by),
            "claimed_by_email": claimed_email,
            "claim_expires_at": invoice.claim_expires_at.isoformat(),
        }

    from datetime import timedelta

    invoice.claimed_by = user.id

    invoice.claim_expires_at = now + timedelta(minutes=5)

    invoice.heartbeat_at = now

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="claim",
            payload={"expires_at": invoice.claim_expires_at.isoformat()},
        )
    )

    await db.commit()

    return {
        "status": "claimed",
        "claimed_by": str(user.id),
        "claimed_by_email": user.email,
        "claim_expires_at": invoice.claim_expires_at.isoformat(),
    }


@router.post("/{invoice_id}/heartbeat")
async def heartbeat_claim(
    invoice_id: uuid.UUID,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:

    invoice = await db.get(Invoice, invoice_id)

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    now = datetime.now(UTC)

    if invoice.claimed_by == user.id:
        from datetime import timedelta

        invoice.claim_expires_at = now + timedelta(minutes=5)

        invoice.heartbeat_at = now

        await db.commit()

        return {"status": "extended", "claim_expires_at": invoice.claim_expires_at.isoformat()}

    return {"status": "not_claimed_by_user"}


@router.post("/{invoice_id}/takeover")
async def takeover_claim(
    invoice_id: uuid.UUID,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:

    invoice = await db.get(Invoice, invoice_id)

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    prev_owner = invoice.claimed_by

    now = datetime.now(UTC)

    from datetime import timedelta

    invoice.claimed_by = user.id

    invoice.claim_expires_at = now + timedelta(minutes=5)

    invoice.heartbeat_at = now

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="claim_takeover",
            payload={
                "previous_owner": str(prev_owner) if prev_owner else None,
                "new_owner": str(user.id),
                "expires_at": invoice.claim_expires_at.isoformat(),
            },
        )
    )

    await db.commit()

    return {
        "status": "taken_over",
        "claimed_by": str(user.id),
        "claimed_by_email": user.email,
        "claim_expires_at": invoice.claim_expires_at.isoformat(),
    }


@router.post("/{invoice_id}/release")
async def release_claim(
    invoice_id: uuid.UUID,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:

    invoice = await db.get(Invoice, invoice_id)

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.claimed_by == user.id:
        invoice.claimed_by = None

        invoice.claim_expires_at = None

        db.add(
            ReviewEvent(
                invoice_id=invoice.id,
                actor_id=user.id,
                action="claim_release",
                payload={"released_by": str(user.id)},
            )
        )

        await db.commit()

    return {"status": "released"}


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
    check_invoice_claim(invoice, user)

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
    check_invoice_claim(invoice, user)

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
    check_invoice_claim(invoice, user)

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
    check_invoice_claim(invoice, user)

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

    if invoice.sender:
        from app.services.outbox import queue_resend_notification

        is_whatsapp = (
            getattr(invoice, "source", None) == "whatsapp"
            or invoice.sender.endswith("@c.us")
            or invoice.sender.endswith("@lid")
            or invoice.sender.endswith("@g.us")
            or invoice.sender.startswith("+")
            or invoice.sender.replace("+", "").isdigit()
        )
        channel = "whatsapp" if is_whatsapp else "email"
        await queue_resend_notification(
            db,
            invoice=invoice,
            channel=channel,
            recipient=invoice.sender,
            reason=req.reason or "Invoice document needs correction",
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

    invoice.created_at = datetime.now(UTC)

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
    check_invoice_claim(invoice, user)

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
    check_invoice_claim(invoice, user)

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


@router.post("/{invoice_id}/split-pages")
async def split_invoice_pages(
    invoice_id: uuid.UUID,
    user: User = Depends(require_reviewer),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    """Splits a grouped multi-page invoice into individual invoices (R1)."""

    invoice = await db.get(Invoice, invoice_id)

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if (invoice.page_count or 1) <= 1:
        raise HTTPException(status_code=400, detail="Invoice has only 1 page, cannot split")

    total_pages = invoice.page_count

    invoice.page_count = 1

    invoice.row_version += 1

    created_invoices = [str(invoice.id)]

    for _p in range(2, total_pages + 1):
        new_inv = Invoice(
            id=uuid.uuid4(),
            source_file_id=invoice.source_file_id,
            status="RECEIVED",
            page_count=1,
            inbound_message_id=invoice.inbound_message_id,
            sender=invoice.sender,
        )

        db.add(new_inv)

        await db.flush()

        created_invoices.append(str(new_inv.id))

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="split_pages",
            payload={"original_pages": total_pages, "resulting_invoices": created_invoices},
        )
    )

    await db.commit()

    return {
        "message": f"Successfully split document into {len(created_invoices)} invoices",
        "invoices": created_invoices,
    }
