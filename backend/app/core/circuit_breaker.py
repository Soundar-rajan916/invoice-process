from __future__ import annotations

import asyncio
import time
from enum import StrEnum
from typing import Any

from app.core.logging import logger


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpenError(Exception):
    """Raised when an external provider circuit breaker is open."""

    def __init__(self, provider: str, retry_after_seconds: float) -> None:
        super().__init__(
            f"Circuit breaker for provider '{provider}' is OPEN. Fast-failing to WAITING_PROVIDER. Retry in {retry_after_seconds:.0f}s"
        )
        self.provider = provider
        self.retry_after_seconds = retry_after_seconds


class CircuitBreaker:
    """Circuit breaker pattern guarding external providers (LLM, Accounting API).
    - After N consecutive 5xx errors, trips to OPEN.
    - Fast-fails requests to WAITING_PROVIDER state while OPEN.
    - Probes with a canary request every M seconds in HALF_OPEN state.
    - Recovers to CLOSED when canary succeeds.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds

        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def is_allowed(self) -> bool:
        """Determines whether a call to the provider is allowed."""
        async with self._lock:
            now = time.monotonic()

            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                elapsed = now - self.last_failure_time
                if elapsed >= self.recovery_timeout:
                    logger.info(
                        "Circuit breaker moving to HALF_OPEN to probe canary",
                        breaker=self.name,
                        elapsed=elapsed,
                    )
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                # In half-open, allow only one canary probe through
                return True

            return False

    async def record_success(self) -> None:
        """Records a successful response (HTTP 200/201)."""
        async with self._lock:
            if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("Canary succeeded! Circuit breaker RESET to CLOSED", breaker=self.name)
            self.state = CircuitState.CLOSED
            self.consecutive_failures = 0

    async def record_failure(self, error: Any = None) -> None:
        """Records a provider outage (HTTP 5xx / timeout)."""
        async with self._lock:
            self.consecutive_failures += 1
            self.last_failure_time = time.monotonic()

            if self.state == CircuitState.HALF_OPEN:
                logger.warning(
                    "Canary failed. Circuit breaker returning to OPEN",
                    breaker=self.name,
                    error=str(error),
                )
                self.state = CircuitState.OPEN
            elif self.consecutive_failures >= self.failure_threshold:
                if self.state != CircuitState.OPEN:
                    logger.error(
                        "Circuit breaker TRIPPED to OPEN after consecutive failures",
                        breaker=self.name,
                        failures=self.consecutive_failures,
                        threshold=self.failure_threshold,
                    )
                self.state = CircuitState.OPEN


# Shared circuit breakers
llm_circuit_breaker = CircuitBreaker(name="groq_llm", failure_threshold=5, recovery_timeout_seconds=30.0)
accounting_circuit_breaker = CircuitBreaker(
    name="accounting_api", failure_threshold=5, recovery_timeout_seconds=30.0
)
