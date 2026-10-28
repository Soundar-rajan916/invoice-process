from __future__ import annotations

import csv
import io
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.security import hash_password, require_admin, verify_csrf_header
from app.models.entities import Invoice, ReviewEvent, Supplier, User
from app.services.validation import validate_gstin_checksum, validate_gstin_format

router = APIRouter(prefix="/admin", tags=["admin"])


class SupplierCreateRequest(BaseModel):
    gstin: str = Field(min_length=15, max_length=15)
    name: str = Field(min_length=2)
    state_code: str | None = None


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
