from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from app.core.config import settings
from app.core.logging import logger


class AdaptiveRateLimiter:
    """Additive Increase / Multiplicative Decrease (AIMD) dynamic rate limiter (R4).
    Replaces static concurrency semaphore by dynamically scaling active requests
    based on real-time provider feedback (HTTP 429s vs sustained 200s).
    """

    def __init__(
        self,
        initial_concurrency: int = 5,
        min_concurrency: int = 1,
        max_concurrency: int = 20,
        increase_step: int = 1,
        success_threshold_to_increase: int = 5,
        backoff_factor: float = 0.5,
    ) -> None:
        self.min_concurrency = min_concurrency
        self.max_concurrency = max_concurrency
        self.current_concurrency = min(max(initial_concurrency, min_concurrency), max_concurrency)
        self.increase_step = increase_step
        self.success_threshold = success_threshold_to_increase
        self.backoff_factor = backoff_factor

        self._consecutive_successes = 0
        self._active_requests = 0
        self._sync_lock = threading.Lock()
        self._semaphore = asyncio.Semaphore(self.current_concurrency)
        self._last_scale_down = 0.0
        self.backoff_until = 0.0

    @property
    def concurrency_limit(self) -> int:
        return self.current_concurrency

    def is_backing_off(self) -> bool:
        return time.monotonic() < self.backoff_until

    async def acquire(self) -> None:
        """Acquires a concurrency slot under current adaptive limit."""
        await self._semaphore.acquire()
        with self._sync_lock:
            self._active_requests += 1

    def release(self) -> None:
        """Releases the slot."""
        with self._sync_lock:
            self._active_requests = max(0, self._active_requests - 1)
        self._semaphore.release()

    async def __aenter__(self) -> AdaptiveRateLimiter:
        await self.acquire()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()

    def on_success(self) -> None:
        """Notified on HTTP 200: Additive increase on sustained successes."""
        with self._sync_lock:
            self._consecutive_successes += 1
            if self._consecutive_successes >= self.success_threshold:
                self._consecutive_successes = 0
                if self.current_concurrency < self.max_concurrency:
                    old_c = self.current_concurrency
                    self.current_concurrency = min(
                        self.max_concurrency, self.current_concurrency + self.increase_step
                    )
                    # Expand semaphore capacity
                    self._semaphore.release()
                    logger.info(
                        "AIMD: Concurrency increased",
                        old=old_c,
                        new=self.current_concurrency,
                        active=self._active_requests,
                    )

    def on_rate_limit(self, retry_after: float | None = None) -> None:
        """Notified on HTTP 429: Multiplicative decrease and backoff."""
        now = time.monotonic()
        with self._sync_lock:
            self._consecutive_successes = 0
            if retry_after and retry_after > 0:
                self.backoff_until = now + retry_after
            else:
                self.backoff_until = now + 1.0

            old_c = self.current_concurrency
            self.current_concurrency = max(
                self.min_concurrency, int(self.current_concurrency * self.backoff_factor)
            )
            self._last_scale_down = now

            logger.warning(
                "AIMD: Rate limit 429 hit. Concurrency decreased",
                old=old_c,
                new=self.current_concurrency,
                retry_after=retry_after,
            )


# Global instance for Groq API extraction
llm_rate_limiter = AdaptiveRateLimiter(
    initial_concurrency=settings.GROQ_MAX_CONCURRENCY or 5,
    min_concurrency=1,
    max_concurrency=max(settings.GROQ_MAX_CONCURRENCY * 2, 10),
)
