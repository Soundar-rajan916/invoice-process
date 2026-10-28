from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidStateTransitionError
from app.models.entities import Invoice, ReviewEvent, SourceFile
from app.services.state import transition_invoice_status


@pytest.mark.asyncio
async def test_state_machine_valid_flow(db_session: AsyncSession):
    source_file = SourceFile(
        sha256="abc123sha256fake",
        original_filename="inv.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="originals/ab/abc123sha256fake",
    )
    db_session.add(source_file)
    await db_session.flush()

    invoice = Invoice(
        source_file_id=source_file.id,
        status="RECEIVED",
    )
    db_session.add(invoice)
    await db_session.flush()

    reviewer_id = uuid.uuid4()

    # RECEIVED -> PROCESSING
    await transition_invoice_status(db_session, invoice, "PROCESSING", action="start_processing")
    assert invoice.status == "PROCESSING"

    # PROCESSING -> NEEDS_REVIEW
    await transition_invoice_status(db_session, invoice, "NEEDS_REVIEW", action="extracted")
    assert invoice.status == "NEEDS_REVIEW"

    # NEEDS_REVIEW -> APPROVED (with reviewer ID)
    invoice.approved_by = reviewer_id
    invoice.approved_extraction_id = uuid.uuid4()
    await transition_invoice_status(
        db_session, invoice, "APPROVED", actor_id=reviewer_id, action="approve"
    )
    assert invoice.status == "APPROVED"

    # APPROVED -> PUSHING
    await transition_invoice_status(db_session, invoice, "PUSHING", action="push_start")
    assert invoice.status == "PUSHING"

    # PUSHING -> PUSHED
    await transition_invoice_status(db_session, invoice, "PUSHED", action="push_success")
    assert invoice.status == "PUSHED"

    # Verify review_events were created
    events = (
        (await db_session.execute(select(ReviewEvent).where(ReviewEvent.invoice_id == invoice.id)))
        .scalars()
        .all()
    )
    assert len(events) == 5
    assert events[2].action == "approve"
    assert events[2].actor_id == reviewer_id


@pytest.mark.asyncio
async def test_r2_no_auto_approval_without_actor(db_session: AsyncSession):
    source_file = SourceFile(
        sha256="fake_sha_r2_test",
        original_filename="inv.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test_key",
    )
    db_session.add(source_file)
    await db_session.flush()

    invoice = Invoice(source_file_id=source_file.id, status="NEEDS_REVIEW")
    db_session.add(invoice)
    await db_session.flush()

    # Attempting to approve without an actor_id MUST raise InvalidStateTransitionError (R2)
    with pytest.raises(InvalidStateTransitionError) as exc_info:
        await transition_invoice_status(db_session, invoice, "APPROVED", actor_id=None)
    assert "without an authenticated reviewer" in str(exc_info.value)


@pytest.mark.asyncio
async def test_illegal_state_transition(db_session: AsyncSession):
    source_file = SourceFile(
        sha256="fake_sha_illegal_test",
        original_filename="inv.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test_key",
    )
    db_session.add(source_file)
    await db_session.flush()

    invoice = Invoice(source_file_id=source_file.id, status="RECEIVED")
    db_session.add(invoice)
    await db_session.flush()

    # RECEIVED -> APPROVED directly is completely illegal
    with pytest.raises(InvalidStateTransitionError):
        await transition_invoice_status(db_session, invoice, "APPROVED", actor_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_approved_invoice_edit_reverts_to_needs_review(db_session: AsyncSession):
    source_file = SourceFile(
        sha256="fake_sha_revert_test",
        original_filename="inv.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test_key",
    )
    db_session.add(source_file)
    await db_session.flush()

    invoice = Invoice(source_file_id=source_file.id, status="APPROVED")
    db_session.add(invoice)
    await db_session.flush()

    # Editing while in APPROVED reverts to NEEDS_REVIEW (R2 guarantee)
    await transition_invoice_status(
        db_session, invoice, "NEEDS_REVIEW", action="edit", reason="Edited before push"
    )
    assert invoice.status == "NEEDS_REVIEW"
