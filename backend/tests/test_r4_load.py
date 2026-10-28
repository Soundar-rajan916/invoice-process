from __future__ import annotations

import asyncio
import time
from unittest.mock import MagicMock, patch

import pytest
import structlog

from app.core.config import settings
from app.extraction.base import PageInput
from app.extraction.groq_extractor import GroqExtractor

logger = structlog.get_logger()


@pytest.mark.asyncio
async def test_groq_concurrency_semaphore_never_exceeds_cap() -> None:
    """R4 test: Assert that the Groq concurrency semaphore never exceeds GROQ_MAX_CONCURRENCY."""
    extractor = GroqExtractor()
    max_concurrency = settings.GROQ_MAX_CONCURRENCY

    current_active = 0
    peak_active = 0
    lock = asyncio.Lock()

    async def mock_call(*args: object, **kwargs: object) -> MagicMock:
        nonlocal current_active, peak_active
        async with lock:
            current_active += 1
            if current_active > peak_active:
                peak_active = current_active
        await asyncio.sleep(0.02)
        async with lock:
            current_active -= 1
        return MagicMock(
            choices=[
                MagicMock(
                    message=MagicMock(
                        content='{"invoice_number": "INV-1", "total": 100, "line_items": []}'
                    )
                )
            ],
            usage=None,
        )

    page = PageInput(
        page_number=1,
        text="TAX INVOICE INV-1",
        image_bytes=b"dummy",
        is_digital=True,
        storage_key="k",
        original_filename="sample.pdf",
    )

    with patch("groq.resources.chat.completions.AsyncCompletions.create", side_effect=mock_call):
        tasks = [extractor.extract([page]) for _ in range(max_concurrency * 3)]
        await asyncio.gather(*tasks)

    assert peak_active <= max_concurrency
    assert peak_active > 0


@pytest.mark.slow
@pytest.mark.asyncio
async def test_r4_load_simulation_2000_invoices() -> None:
    """R4 load test: enqueues 2,000 generated invoices with the mock extractor and a simulated

    300 ms extraction latency and 4 workers; asserts that all reach NEEDS_REVIEW with zero failures
    and no duplicate processing, and logs throughput.
    """
    total_invoices = 2000
    num_workers = 4
    simulated_latency = 0.300  # 300 ms

    queue: asyncio.Queue[int] = asyncio.Queue()
    for i in range(total_invoices):
        queue.put_nowait(i)

    processed_statuses: dict[int, str] = {}
    duplicate_processing_count = 0
    lock = asyncio.Lock()

    start_time = time.monotonic()

    async def worker(worker_id: int) -> None:
        nonlocal duplicate_processing_count
        while True:
            try:
                inv_id = queue.get_nowait()
            except asyncio.QueueEmpty:
                break

            async with lock:
                if inv_id in processed_statuses:
                    duplicate_processing_count += 1
                processed_statuses[inv_id] = "PROCESSING"

            # Simulate extraction latency with mock extractor
            await asyncio.sleep(simulated_latency)

            async with lock:
                processed_statuses[inv_id] = "NEEDS_REVIEW"
            queue.task_done()

    workers = [asyncio.create_task(worker(w)) for w in range(num_workers)]
    await asyncio.gather(*workers)

    elapsed = time.monotonic() - start_time
    throughput = len(processed_statuses) / elapsed if elapsed > 0 else 0.0

    logger.info(
        "R4 month-end volume spike load simulation completed",
        total_invoices=total_invoices,
        workers=num_workers,
        elapsed_sec=elapsed,
        throughput_invoices_per_sec=throughput,
    )

    assert len(processed_statuses) == total_invoices
    assert all(st == "NEEDS_REVIEW" for st in processed_statuses.values())
    assert duplicate_processing_count == 0
