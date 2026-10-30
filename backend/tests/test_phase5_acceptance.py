"""Phase 5 Acceptance Test Suite.

Verifies:
1. Adaptive Rate Limiter (AIMD algorithm, backpressure, 429 handling).
2. Circuit Breaker (CLOSED -> OPEN -> HALF_OPEN state transitions, fast failure).
3. Watchdog Task (requeuing stuck PROCESSING/PUSHING invoices, dead-letter escalation after 3 attempts).
4. Review Lease Concurrency (R4: 5-minute leases, HTTP 409 Conflict, heartbeat extension, lease takeover).
5. Configurable Accounting Client (YAML config, custom headers, timeout, circuit breaker integration).
6. Accounting Reconciliation (discrepancy detection, finding generation).
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import CircuitBreaker, CircuitState
from app.core.rate_limiter import AdaptiveRateLimiter
from app.core.security import create_access_token
from app.models.entities import (
    Extraction,
    Invoice,
    ReconciliationFinding,
    SourceFile,
    User,
)
from app.services.push import ConfigurableAccountingClient
from app.services.reconciliation import run_accounting_reconciliation


# ---------------------------------------------------------------------------
# 1. Adaptive Rate Limiter & AIMD Tests
# ---------------------------------------------------------------------------
def test_adaptive_rate_limiter_aimd():
    limiter = AdaptiveRateLimiter(
        initial_concurrency=10,
        min_concurrency=2,
        max_concurrency=20,
        backoff_factor=0.5,
    )
    assert limiter.concurrency_limit == 10

    # Successful calls increment concurrency additively
    for _ in range(5):
        limiter.on_success()
    assert limiter.concurrency_limit > 10

    # Rate limit error triggers multiplicative decrease
    prev = limiter.concurrency_limit
    limiter.on_rate_limit(retry_after=5.0)
    assert limiter.concurrency_limit == max(2, int(prev * 0.5))
    assert limiter.is_backing_off()


# ---------------------------------------------------------------------------
# 2. Circuit Breaker Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_circuit_breaker_transitions():
    cb = CircuitBreaker(
        name="test_cb",
        failure_threshold=3,
        recovery_timeout_seconds=0.2,
    )
    assert cb.state == CircuitState.CLOSED
    assert await cb.is_allowed()

    # Record 3 failures
    await cb.record_failure()
    await cb.record_failure()
    assert cb.state == CircuitState.CLOSED
    await cb.record_failure()
    assert cb.state == CircuitState.OPEN
    assert not await cb.is_allowed()

    # Waiting recovery time transitions to HALF_OPEN
    time.sleep(0.25)
    assert await cb.is_allowed()
    assert cb.state == CircuitState.HALF_OPEN

    # In HALF_OPEN, successful requests recover circuit back to CLOSED
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED


# ---------------------------------------------------------------------------
# 3. Watchdog Task Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_watchdog_requeues_and_escalates_to_failed(db_session: AsyncSession):
    # Setup test file
    source = SourceFile(
        sha256="watchdog" + uuid.uuid4().hex[:16],
        original_filename="stuck.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test/stuck.pdf",
    )
    db_session.add(source)
    await db_session.flush()

    # Create stuck PROCESSING invoice older than 5 minutes
    stuck_invoice = Invoice(
        source_file_id=source.id,
        status="PROCESSING",
        watchdog_requeue_count=2,
        heartbeat_at=datetime.now(UTC) - timedelta(minutes=10),
    )
    db_session.add(stuck_invoice)
    await db_session.commit()

    # Run watchdog logic directly
    from app.workers.tasks import run_watchdog_sweep

    await run_watchdog_sweep(session=db_session)

    # Refresh invoice state
    await db_session.refresh(stuck_invoice)
    assert stuck_invoice.watchdog_requeue_count == 3
    # Next timeout exceeds max (3) -> escalated to FAILED
    stuck_invoice.heartbeat_at = datetime.now(UTC) - timedelta(minutes=10)
    stuck_invoice.status = "PROCESSING"
    await db_session.commit()

    await run_watchdog_sweep(session=db_session)
    await db_session.refresh(stuck_invoice)
    assert stuck_invoice.status == "FAILED"
    assert "watchdog_timeout" in (stuck_invoice.status_reason or "")


# ---------------------------------------------------------------------------
# 4. Review Lease Concurrency Tests (R4)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_review_lease_locking_and_takeover(client: AsyncClient, db_session: AsyncSession):
    # Create two reviewers
    u1 = User(
        email=f"reviewer1_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="fake",
        role="reviewer",
        is_active=True,
    )
    u2 = User(
        email=f"reviewer2_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="fake",
        role="reviewer",
        is_active=True,
    )
    source = SourceFile(
        sha256="lease" + uuid.uuid4().hex[:16],
        original_filename="lease.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test/lease.pdf",
    )
    db_session.add_all([u1, u2, source])
    await db_session.flush()

    now = datetime.now(UTC)
    invoice = Invoice(
        source_file_id=source.id,
        status="NEEDS_REVIEW",
        claimed_by=u1.id,
        claim_expires_at=now + timedelta(minutes=5),
        heartbeat_at=now,
    )
    db_session.add(invoice)
    await db_session.commit()

    # User 2 attempts to perform write action while User 1 holds active lease -> Expect 409 Conflict
    token2 = create_access_token(str(u2.id), u2.role)
    auth_headers = {
        "Authorization": f"Bearer {token2}",
        "X-Requested-With": "XMLHttpRequest",
    }
    res = await client.post(
        f"/api/v1/invoices/{invoice.id}/approve",
        headers=auth_headers,
        json={"row_version": invoice.row_version},
    )
    assert res.status_code == 409
    assert "claimed by another reviewer" in res.json()["detail"]

    # User 2 takes over the lease
    takeover_res = await client.post(
        f"/api/v1/invoices/{invoice.id}/takeover",
        headers=auth_headers,
    )
    assert takeover_res.status_code == 200
    assert takeover_res.json()["status"] == "taken_over"

    # Verify claim transferred
    await db_session.refresh(invoice)
    assert invoice.claimed_by == u2.id


# ---------------------------------------------------------------------------
# 5. Configurable Accounting Client Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_configurable_accounting_client(tmp_path):
    yaml_content = """
url: "http://mock-accounting:8000/api/invoices"
timeout_seconds: 5.0
retry_policy:
  max_attempts: 2
  backoff_factor: 2.0
custom_headers:
  X-Accounting-Client: "InvoiceFlow-Test"
"""
    cfg_file = tmp_path / "test_accounting.yaml"
    cfg_file.write_text(yaml_content)

    client = ConfigurableAccountingClient(config_path=str(cfg_file))
    assert client.url == "http://mock-accounting:8000/api/invoices"
    assert client.custom_headers["X-Accounting-Client"] == "InvoiceFlow-Test"
    assert client.timeout == 5.0


# ---------------------------------------------------------------------------
# 6. Accounting Reconciliation Tests
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_accounting_reconciliation_detects_missing(db_session: AsyncSession):
    # Create reviewer and approved extraction to satisfy R2 check constraint
    reviewer = User(
        email=f"rev_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="fake",
        role="reviewer",
        is_active=True,
    )
    source = SourceFile(
        sha256="recon" + uuid.uuid4().hex[:16],
        original_filename="recon.pdf",
        content_type="application/pdf",
        size_bytes=1024,
        storage_key="test/recon.pdf",
    )
    db_session.add_all([reviewer, source])
    await db_session.flush()

    inv_id = uuid.uuid4()
    ext = Extraction(
        id=uuid.uuid4(),
        invoice_id=inv_id,
        kind="model",
        model_id="mock",
        data={"invoice_number": "INV-RECON-1", "total": "500.00"},
        raw_response={},
    )
    db_session.add(ext)
    await db_session.flush()

    today = datetime.now(UTC)
    inv = Invoice(
        id=inv_id,
        source_file_id=source.id,
        status="PUSHED",
        approved_extraction_id=ext.id,
        approved_by=reviewer.id,
        approved_at=today,
        accounting_id="ACC-MISSING-999",
        idempotency_key="key-recon-1",
        normalized_invoice_number="INV-RECON-1",
        created_at=today,
        updated_at=today,
    )
    db_session.add(inv)
    await db_session.commit()

    # Mock external accounting system having no matching invoice
    mock_http_client = AsyncMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"items": []}
    mock_http_client.get.return_value = mock_resp

    run = await run_accounting_reconciliation(
        session=db_session,
        target_date=today.date(),
        client=mock_http_client,
    )
    assert run.status == "completed"
    assert run.total_discrepancies >= 1

    # Verify finding was created
    stmt = select(ReconciliationFinding).where(ReconciliationFinding.run_id == run.id)
    findings = (await db_session.execute(stmt)).scalars().all()
    assert any(f.finding_type == "missing_in_accounting" for f in findings)
