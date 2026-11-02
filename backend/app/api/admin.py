from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logging import logger
from app.core.security import hash_password, require_admin, verify_csrf_header
from app.core.storage import storage_service
from app.models.entities import (
    Extraction,
    Invoice,
    ReviewEvent,
    ShadowRecord,
    SourceFile,
    Supplier,
    User,
)
from app.services.validation import validate_gstin_checksum, validate_gstin_format

router = APIRouter(prefix="/admin", tags=["admin"])


class SupplierCreateRequest(BaseModel):
    gstin: str = Field(min_length=15, max_length=15)
    name: str = Field(min_length=2)
    state_code: str | None = None


class SupplierUpdateRequest(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class UserCreateRequest(BaseModel):
    email: str
    password: str = Field(min_length=6)
    role: str = "reviewer"  # reviewer | admin


class UserUpdateRequest(BaseModel):
    role: str | None = None
    is_active: bool | None = None


# Suppliers CRUD
@router.get("/suppliers")
async def list_suppliers(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    stmt = select(Supplier).order_by(Supplier.name.asc())
    suppliers = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(s.id),
            "gstin": s.gstin,
            "name": s.name,
            "state_code": s.state_code,
            "is_active": s.is_active,
        }
        for s in suppliers
    ]


@router.post("/suppliers")
async def create_supplier(
    req: SupplierCreateRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    gstin_clean = req.gstin.strip().upper()
    if not validate_gstin_format(gstin_clean) or not validate_gstin_checksum(gstin_clean):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid GSTIN format or checksum: {gstin_clean}",
        )

    stmt = select(Supplier).where(Supplier.gstin == gstin_clean)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Supplier with GSTIN {gstin_clean} already exists",
        )

    supplier = Supplier(
        id=uuid.uuid4(),
        gstin=gstin_clean,
        name=req.name.strip(),
        state_code=req.state_code or gstin_clean[:2],
        is_active=True,
    )
    db.add(supplier)
    await db.commit()
    return {
        "id": str(supplier.id),
        "gstin": supplier.gstin,
        "name": supplier.name,
        "state_code": supplier.state_code,
        "is_active": supplier.is_active,
    }


@router.patch("/suppliers/{supplier_id}")
async def update_supplier(
    supplier_id: uuid.UUID,
    req: SupplierUpdateRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    target_supplier = await db.get(Supplier, supplier_id)
    if not target_supplier:
        raise HTTPException(status_code=404, detail="Supplier not found")

    if req.name is not None:
        target_supplier.name = req.name.strip()
    if req.is_active is not None:
        target_supplier.is_active = req.is_active

    await db.commit()
    return {
        "id": str(target_supplier.id),
        "gstin": target_supplier.gstin,
        "name": target_supplier.name,
        "state_code": target_supplier.state_code,
        "is_active": target_supplier.is_active,
    }


@router.post("/suppliers/import-csv")
async def import_suppliers_csv(
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    """Imports suppliers from CSV with columns 'gstin,name' and validates GSTIN checksums."""
    content = await file.read()
    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    imported = 0
    errors: list[dict[str, Any]] = []

    for row_idx, row in enumerate(reader, start=2):
        gstin = (row.get("gstin") or "").strip().upper()
        name = (row.get("name") or "").strip()

        if not gstin or not name:
            errors.append({"row": row_idx, "error": "Missing gstin or name"})
            continue

        if not validate_gstin_format(gstin) or not validate_gstin_checksum(gstin):
            errors.append(
                {"row": row_idx, "gstin": gstin, "error": "Invalid GSTIN checksum/format"}
            )
            continue

        stmt = select(Supplier).where(Supplier.gstin == gstin)
        existing = (await db.execute(stmt)).scalar_one_or_none()
        if existing:
            existing.name = name
            existing.state_code = gstin[:2]
        else:
            sup = Supplier(
                id=uuid.uuid4(), gstin=gstin, name=name, state_code=gstin[:2], is_active=True
            )
            db.add(sup)
        imported += 1

    await db.commit()
    return {"imported": imported, "errors": errors}


# Users CRUD
@router.get("/users")
async def list_users(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    stmt = select(User).order_by(User.email.asc())
    users = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(u.id),
            "email": u.email,
            "role": u.role,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat(),
        }
        for u in users
    ]


@router.post("/users")
async def create_user(
    req: UserCreateRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    email_clean = req.email.strip().lower()
    stmt = select(User).where(User.email == email_clean)
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email {email_clean} already exists",
        )

    new_user = User(
        id=uuid.uuid4(),
        email=email_clean,
        password_hash=hash_password(req.password),
        role=req.role,
        is_active=True,
    )
    db.add(new_user)
    await db.commit()
    return {
        "id": str(new_user.id),
        "email": new_user.email,
        "role": new_user.role,
        "is_active": new_user.is_active,
    }


@router.patch("/users/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    req: UserUpdateRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    target_user = await db.get(User, user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.role is not None:
        target_user.role = req.role
    if req.is_active is not None:
        target_user.is_active = req.is_active

    await db.commit()
    return {
        "id": str(target_user.id),
        "email": target_user.email,
        "role": target_user.role,
        "is_active": target_user.is_active,
    }


# Admin Retry Endpoint
@router.post("/invoices/{invoice_id}/retry")
async def retry_invoice(
    invoice_id: uuid.UUID,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, str]:
    """Retries an invoice that ended in FAILED or PUSH_FAILED."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status == "FAILED":
        # Re-run pipeline
        invoice.status = "RECEIVED"
        invoice.status_reason = "Retried by admin"
        db.add(
            ReviewEvent(
                invoice_id=invoice.id,
                actor_id=user.id,
                action="status_change",
                payload={"from_status": "FAILED", "to_status": "RECEIVED", "reason": "admin_retry"},
            )
        )
        await db.commit()

        if settings.ENVIRONMENT == "test":
            from app.services.pipeline import process_invoice_pipeline

            await process_invoice_pipeline(db, invoice.id)
        else:
            from app.workers.tasks import process_invoice

            process_invoice.delay(str(invoice.id))
        return {"message": "Pipeline processing re-triggered"}

    elif invoice.status == "PUSH_FAILED":
        # Re-run push
        invoice.status = "APPROVED"
        invoice.status_reason = "Push retried by admin"
        db.add(
            ReviewEvent(
                invoice_id=invoice.id,
                actor_id=user.id,
                action="status_change",
                payload={
                    "from_status": "PUSH_FAILED",
                    "to_status": "APPROVED",
                    "reason": "admin_retry",
                },
            )
        )
        await db.commit()

        if settings.ENVIRONMENT == "test":
            from app.services.push import push_invoice

            await push_invoice(db, invoice.id)
        else:
            from app.workers.tasks import push_invoice_task

            push_invoice_task.delay(str(invoice.id))
        return {"message": "Push to accounting re-triggered"}

    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only FAILED or PUSH_FAILED invoices can be retried (current status: {invoice.status})",
        )


# Dead-Letter Management Endpoints (Phase 5)
class DiscardRequest(BaseModel):
    reason: str = Field(min_length=3)


@router.get("/dead-letters")
async def list_dead_letters(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Lists invoices currently stuck in unrecoverable or failed states (PUSH_FAILED, FAILED)."""
    from sqlalchemy import func

    base_query = select(Invoice).where(Invoice.status.in_(["FAILED", "PUSH_FAILED"]))

    count_stmt = select(func.count(Invoice.id)).where(Invoice.status.in_(["FAILED", "PUSH_FAILED"]))
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        base_query.order_by(Invoice.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = (await db.execute(stmt)).scalars().all()

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [
            {
                "id": str(inv.id),
                "status": inv.status,
                "status_reason": inv.status_reason,
                "supplier_gstin": inv.supplier_gstin,
                "normalized_invoice_number": inv.normalized_invoice_number,
                "watchdog_requeue_count": inv.watchdog_requeue_count,
                "created_at": inv.created_at.isoformat(),
                "updated_at": inv.updated_at.isoformat(),
            }
            for inv in items
        ],
    }


@router.post("/dead-letters/{invoice_id}/retry")
async def retry_dead_letter(
    invoice_id: uuid.UUID,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, str]:
    """Retries a dead-letter invoice, resetting watchdog counters."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.status not in ("FAILED", "PUSH_FAILED"):
        raise HTTPException(status_code=404, detail="Dead-letter invoice not found")

    invoice.watchdog_requeue_count = 0
    return await retry_invoice(invoice_id, user, db, _)


@router.post("/dead-letters/{invoice_id}/discard")
async def discard_dead_letter(
    invoice_id: uuid.UUID,
    body: DiscardRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, str]:
    """Permanently discards an unrecoverable invoice with an audit explanation."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice or invoice.status not in ("FAILED", "PUSH_FAILED"):
        raise HTTPException(status_code=404, detail="Dead-letter invoice not found")

    prev_status = invoice.status
    invoice.status = "REJECTED"
    invoice.status_reason = f"Discarded from dead-letter queue: {body.reason}"
    invoice.row_version += 1

    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="status_change",
            payload={
                "from_status": prev_status,
                "to_status": "REJECTED",
                "action": "dead_letter_discard",
                "reason": body.reason,
            },
        )
    )
    await db.commit()
    return {"message": "Invoice successfully discarded from dead-letter queue"}


# Reconciliation Admin Endpoints (Phase 5)
@router.get("/reconciliation/runs")
async def list_reconciliation_runs(
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> list[dict[str, Any]]:
    from app.models.entities import ReconciliationRun

    stmt = select(ReconciliationRun).order_by(ReconciliationRun.started_at.desc()).limit(limit)
    runs = (await db.execute(stmt)).scalars().all()
    return [
        {
            "id": str(r.id),
            "started_at": r.started_at.isoformat(),
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "status": r.status,
            "total_checked": r.total_checked,
            "total_matched": r.total_matched,
            "total_discrepancies": r.total_discrepancies,
            "summary": r.summary,
        }
        for r in runs
    ]


@router.get("/reconciliation/runs/{run_id}")
async def get_reconciliation_run_detail(
    run_id: uuid.UUID,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    from app.models.entities import ReconciliationFinding, ReconciliationRun

    run = await db.get(ReconciliationRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Reconciliation run not found")

    findings_stmt = (
        select(ReconciliationFinding)
        .where(ReconciliationFinding.run_id == run.id)
        .order_by(ReconciliationFinding.created_at.desc())
    )
    findings = (await db.execute(findings_stmt)).scalars().all()

    return {
        "id": str(run.id),
        "started_at": run.started_at.isoformat(),
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "status": run.status,
        "total_checked": run.total_checked,
        "total_matched": run.total_matched,
        "total_discrepancies": run.total_discrepancies,
        "summary": run.summary,
        "findings": [
            {
                "id": str(f.id),
                "invoice_id": str(f.invoice_id) if f.invoice_id else None,
                "finding_type": f.finding_type,
                "discrepancy_type": f.finding_type,
                "severity": f.severity,
                "details": f.details,
                "accounting_id": f.details.get("accounting_id") if isinstance(f.details, dict) else None,
                "resolved": f.resolved,
                "created_at": f.created_at.isoformat(),
            }
            for f in findings
        ],
    }


@router.post("/reconciliation/trigger")
async def trigger_reconciliation(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    from datetime import UTC, datetime

    from app.services.reconciliation import run_accounting_reconciliation

    run = await run_accounting_reconciliation(db, target_date=datetime.now(UTC).date())
    return {
        "status": "triggered",
        "run_id": str(run.id),
        "total_matched": run.total_matched,
        "total_discrepancies": run.total_discrepancies,
    }


# ---------------------------------------------------------------------------
# Data Retention, Right to Erasure, and Shadow Mode Endpoints (Phase 6)
# ---------------------------------------------------------------------------
class EraseInvoiceRequest(BaseModel):
    reason: str = Field(min_length=5)


@router.post("/invoices/{invoice_id}/erase")
async def erase_invoice(
    invoice_id: uuid.UUID,
    body: EraseInvoiceRequest,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    """Erases an invoice, purging raw storage files, redacting PII, and leaving an immutable tombstone."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # 1. Purge S3 / MinIO objects
    if invoice.source_file_id:
        source = await db.get(SourceFile, invoice.source_file_id)
        if source and source.storage_key:
            try:
                storage_service.delete_object(source.storage_key)
            except Exception as e:
                logger.warning("Could not delete raw file from storage", key=source.storage_key, error=str(e))

    # 2. Redact Invoice PII fields
    invoice.is_erased = True
    invoice.erased_at = datetime.now(UTC)
    invoice.erased_by = user.id
    invoice.erased_reason = body.reason
    invoice.sender = "REDACTED"
    invoice.recipient = "REDACTED"
    invoice.status = "REJECTED"
    invoice.status_reason = f"Erased by admin: {body.reason}"
    invoice.row_version += 1

    # 3. Redact Extraction data
    ext_stmt = select(Extraction).where(Extraction.invoice_id == invoice.id)
    extractions = (await db.execute(ext_stmt)).scalars().all()
    for ext in extractions:
        ext.data = {"redacted": True, "reason": body.reason}

    # 4. Create immutable tombstone audit event
    db.add(
        ReviewEvent(
            invoice_id=invoice.id,
            actor_id=user.id,
            action="invoice_erased",
            payload={
                "reason": body.reason,
                "erased_by": str(user.id),
                "erased_at": invoice.erased_at.isoformat(),
            },
        )
    )
    await db.commit()
    return {"message": "Invoice erased successfully", "invoice_id": str(invoice.id)}


@router.post("/shadow/import")
async def import_shadow_records(
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
    _: None = Depends(verify_csrf_header),
) -> dict[str, Any]:
    """Imports historical ground-truth invoice records for shadow-mode dual run evaluation."""
    content = await file.read()
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))

    batch_id = str(uuid.uuid4())
    count = 0
    for row in reader:
        inv_num = (row.get("invoice_number") or row.get("invoice_no") or "").strip()
        gstin = (row.get("supplier_gstin") or row.get("gstin") or "").strip()
        date_str = (row.get("invoice_date") or row.get("date") or "").strip()
        total_str = (row.get("total") or row.get("amount") or "0").replace(",", "").strip()
        try:
            total_val = float(total_str)
        except ValueError:
            total_val = 0.0

        if inv_num and gstin:
            rec = ShadowRecord(
                batch_id=batch_id,
                invoice_number=inv_num,
                supplier_gstin=gstin,
                invoice_date=date_str,
                total=total_val,
                raw_data=dict(row),
            )
            db.add(rec)
            count += 1

    await db.commit()
    return {
        "batch_id": batch_id,
        "total_imported": count,
        "message": f"Successfully imported {count} shadow records",
    }


@router.get("/shadow/report")
async def get_shadow_report(
    batch_id: str | None = Query(None),
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Generates dual-run shadow mode agreement report comparing system extractions against historical records."""
    stmt = select(ShadowRecord)
    if batch_id:
        stmt = stmt.where(ShadowRecord.batch_id == batch_id)
    shadow_records = (await db.execute(stmt)).scalars().all()

    total_shadow = len(shadow_records)
    if total_shadow == 0:
        return {
            "batch_id": batch_id,
            "total_shadow_records": 0,
            "total_matched": 0,
            "perfect_matches": 0,
            "overall_agreement_pct": 100.0,
            "amount_matches": 0,
            "date_matches": 0,
            "missing_in_invoiceflow": [],
            "mismatches_by_supplier": [],
        }

    matched_count = 0
    perfect_count = 0
    amount_matches = 0
    date_matches = 0
    missing_in_invoiceflow = []
    supplier_mismatches: dict[str, int] = {}

    for s_rec in shadow_records:
        norm_num = "".join(c for c in s_rec.invoice_number if c.isalnum()).upper()
        inv_stmt = select(Invoice).where(
            Invoice.supplier_gstin == s_rec.supplier_gstin,
            Invoice.normalized_invoice_number == norm_num,
        )
        inv = (await db.execute(inv_stmt)).scalars().first()
        if not inv:
            missing_in_invoiceflow.append({
                "invoice_number": s_rec.invoice_number,
                "supplier_gstin": s_rec.supplier_gstin,
                "total": float(s_rec.total),
            })
            supplier_mismatches[s_rec.supplier_gstin] = supplier_mismatches.get(s_rec.supplier_gstin, 0) + 1
            continue

        matched_count += 1
        ext = None
        if inv.approved_extraction_id:
            ext = await db.get(Extraction, inv.approved_extraction_id)
        elif inv.current_extraction_id:
            ext = await db.get(Extraction, inv.current_extraction_id)

        amt_match = False
        dt_match = False
        if ext and ext.data:
            inv_total = ext.data.get("total")
            try:
                if inv_total is not None and abs(float(inv_total) - float(s_rec.total)) < 0.01:
                    amt_match = True
            except (ValueError, TypeError):
                pass

            inv_date = ext.data.get("invoice_date")
            if inv_date and str(inv_date) == str(s_rec.invoice_date):
                dt_match = True

        if amt_match:
            amount_matches += 1
        if dt_match:
            date_matches += 1

        if amt_match and dt_match:
            perfect_count += 1
        else:
            supplier_mismatches[s_rec.supplier_gstin] = supplier_mismatches.get(s_rec.supplier_gstin, 0) + 1

    overall_pct = round((perfect_count / total_shadow) * 100.0, 2) if total_shadow > 0 else 0.0

    mismatches_by_supplier = [
        {"supplier_gstin": gstin, "mismatches": cnt}
        for gstin, cnt in sorted(supplier_mismatches.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "batch_id": batch_id,
        "total_shadow_records": total_shadow,
        "total_matched": matched_count,
        "perfect_matches": perfect_count,
        "overall_agreement_pct": overall_pct,
        "amount_matches": amount_matches,
        "date_matches": date_matches,
        "missing_in_invoiceflow": missing_in_invoiceflow[:20],
        "mismatches_by_supplier": mismatches_by_supplier,
    }


@router.get("/whatsapp/status")
async def get_whatsapp_status(
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Returns WhatsApp gateway & session status for the Admin dashboard."""
    from app.models.entities import InboundMessage, OutboundMessage, WhatsAppSessionState

    provider_name = settings.WHATSAPP_PROVIDER

    stmt = (
        select(WhatsAppSessionState)
        .where(WhatsAppSessionState.provider == provider_name)
        .order_by(WhatsAppSessionState.last_changed_at.desc())
    )
    session_row = (await db.execute(stmt)).scalars().first()

    current_state = session_row.state if session_row else "unknown"
    last_changed_at = session_row.last_changed_at.isoformat() if session_row else None
    last_webhook_at = session_row.last_webhook_at.isoformat() if session_row and session_row.last_webhook_at else None

    last_inb_stmt = (
        select(InboundMessage.received_at)
        .where(InboundMessage.channel == "whatsapp")
        .order_by(InboundMessage.received_at.desc())
        .limit(1)
    )
    last_received_at = (await db.execute(last_inb_stmt)).scalar_one_or_none()

    one_hour_ago = datetime.now(UTC) - timedelta(hours=1)
    outbound_stmt = (
        select(func.count(OutboundMessage.id))
        .where(
            OutboundMessage.channel == "whatsapp",
            OutboundMessage.status == "sent",
            OutboundMessage.sent_at >= one_hour_ago,
        )
    )
    outbound_last_hour = (await db.execute(outbound_stmt)).scalar() or 0

    return {
        "provider": provider_name,
        "state": current_state,
        "last_changed_at": last_changed_at,
        "last_webhook_at": last_webhook_at,
        "last_received_at": last_received_at.isoformat() if last_received_at else None,
        "outbound_last_hour": outbound_last_hour,
        "outbound_cap_per_hour": settings.WHATSAPP_MAX_OUTBOUND_PER_HOUR,
        "dashboard_url": settings.OPENWA_DASHBOARD_URL if provider_name == "openwa" else None,
    }
