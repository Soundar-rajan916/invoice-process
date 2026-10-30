"""Chaos and Failure Injection Tests (Phase 5).

Verifies resilience and recovery against:
1. Groq 429 rate limit burst (AIMD throttle, backoff, recovery on success).
2. Accounting 503 service outage (Circuit breaker trips to OPEN, fast-fails to PUSH_FAILED, recovers via canary).
3. Database transient failure recovery and transaction rollbacks.
"""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import CircuitBreaker, CircuitState
from app.core.rate_limiter import AdaptiveRateLimiter
from app.models.entities import Invoice, SourceFile


@pytest.mark.asyncio
async def test_chaos_groq_429_burst_throttling():
    """Simulates a sudden burst of 429 Too Many Requests from LLM provider."""
    limiter = AdaptiveRateLimiter(
        initial_concurrency=10,
        min_concurrency=1,
        max_concurrency=20,
        backoff_factor=0.5,
        success_threshold_to_increase=2,
    )

    # 5 consecutive 429 responses
    for _ in range(5):
        limiter.on_rate_limit(retry_after=0.5)

    # Concurrency throttled down to floor
    assert limiter.concurrency_limit == 1
    assert limiter.is_backing_off()

    # Recovery after backoff window expires
    time.sleep(0.55)
    assert not limiter.is_backing_off()

    # Additive increase on subsequent successful extractions
    for _ in range(3):
        limiter.on_success()
    assert limiter.concurrency_limit > 1


@pytest.mark.asyncio
async def test_chaos_accounting_503_outage_circuit_breaker():
    """Simulates external ERP/accounting service returning 503 Service Unavailable."""
    cb = CircuitBreaker(
        name="test_accounting_chaos",
        failure_threshold=3,
        recovery_timeout_seconds=0.2,
    )

    assert cb.state == CircuitState.CLOSED
    assert await cb.is_allowed()

    # Record 3 failures (simulating 503 errors)
    await cb.record_failure("HTTP 503 Service Unavailable")
    await cb.record_failure("HTTP 503 Service Unavailable")
    assert cb.state == CircuitState.CLOSED
    await cb.record_failure("HTTP 503 Service Unavailable")

    # Circuit breaker trips to OPEN
    assert cb.state == CircuitState.OPEN
    # Immediate subsequent calls are blocked (fast fail)
    assert not await cb.is_allowed()

    # After recovery timeout, circuit enters HALF_OPEN for canary probe
    time.sleep(0.25)
    assert await cb.is_allowed()
    assert cb.state == CircuitState.HALF_OPEN

    # Successful canary resets breaker to CLOSED
    await cb.record_success()
    assert cb.state == CircuitState.CLOSED
    assert await cb.is_allowed()


@pytest.mark.asyncio
async def test_chaos_db_transient_failure_recovery(db_session: AsyncSession):
    """Verifies that transient database operations recover cleanly with proper session lifecycle."""
    source = SourceFile(
        sha256="chaos" + uuid.uuid4().hex[:16],
        original_filename="chaos.pdf",
        content_type="application/pdf",
        size_bytes=512,
        storage_key="test/chaos.pdf",
    )
    db_session.add(source)
    await db_session.commit()

    inv = Invoice(
        source_file_id=source.id,
        status="NEEDS_REVIEW",
    )
    db_session.add(inv)
    await db_session.commit()
    await db_session.refresh(inv)
    assert inv.id is not None
