from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Invoice, SourceFile, User


@pytest.mark.asyncio
async def test_r2_check_constraint_rejects_unapproved_push(db_session: AsyncSession):
    source_file = SourceFile(
        sha256="test_sha_check_constraint",
        original_filename="inv.pdf",
        content_type="application/pdf",
        size_bytes=1000,
        storage_key="test_storage",
    )
    db_session.add(source_file)
    await db_session.flush()

    # Attempting to save an invoice in PUSHING or PUSHED status without approved_by and approved_extraction_id
    invalid_invoice = Invoice(
        source_file_id=source_file.id,
        status="PUSHING",
        approved_by=None,
        approved_extraction_id=None,
    )
    db_session.add(invalid_invoice)

    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_r2_check_constraint_allows_approved_push(db_session: AsyncSession):
    reviewer = User(
        email="rev@example.com",
        password_hash="argon2fake",
        role="reviewer",
    )
    source_file = SourceFile(
        sha256="test_sha_check_constraint_valid",
        original_filename="inv.pdf",
        content_type="application/pdf",
        size_bytes=1000,
        storage_key="test_storage",
    )
    db_session.add_all([reviewer, source_file])
    await db_session.flush()

    extraction_id = uuid.uuid4()

    valid_invoice = Invoice(
        source_file_id=source_file.id,
        status="PUSHING",
        approved_by=reviewer.id,
        approved_extraction_id=extraction_id,
    )
    db_session.add(valid_invoice)
    await db_session.flush()
    assert valid_invoice.status == "PUSHING"
