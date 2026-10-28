import asyncio
import uuid
from typing import Any

from celery import shared_task

from app.core.database import async_session_maker
from app.core.logging import logger
from app.services.pipeline import process_invoice_pipeline


@shared_task(
    bind=True,
    name="app.workers.tasks.process_invoice",
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    acks_late=True,
)
def process_invoice(self: Any, invoice_id_str: str) -> dict[str, str]:
    """Celery task executing the invoice processing pipeline."""
    invoice_id = uuid.UUID(invoice_id_str)

    async def _run() -> str:
        async with async_session_maker() as session:
            inv = await process_invoice_pipeline(session, invoice_id)
            return inv.status if inv else "SKIPPED"

    try:
        status = asyncio.run(_run())
        return {"invoice_id": invoice_id_str, "status": status}
    except Exception as exc:
        err_msg = str(exc)
        logger.exception(
            "Error executing process_invoice Celery task", invoice_id=invoice_id_str, error=err_msg
        )
        if self.request.retries >= self.max_retries:
            # Mark FAILED on exhausted retries
            async def _mark_failed() -> None:
                async with async_session_maker() as session:
                    from app.models.entities import Invoice

                    inv = await session.get(Invoice, invoice_id)
                    if inv:
                        inv.status = "FAILED"
                        inv.status_reason = f"Exhausted worker retries: {err_msg}"
                        await session.commit()

            asyncio.run(_mark_failed())
        raise self.retry(exc=exc) from exc


@shared_task(
    bind=True,
    name="app.workers.tasks.push_invoice_task",
    max_retries=3,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_jitter=True,
    acks_late=True,
)
def push_invoice_task(self: Any, invoice_id_str: str) -> dict[str, str]:
    """Celery task executing idempotent push of approved invoice to accounting API."""
    import uuid

    from app.services.push import push_invoice

    invoice_id = uuid.UUID(invoice_id_str)

    async def _run() -> str:
        async with async_session_maker() as session:
            inv = await push_invoice(session, invoice_id)
            return inv.status if inv else "SKIPPED"

    try:
        status = asyncio.run(_run())
        return {"invoice_id": invoice_id_str, "status": status}
    except Exception as exc:
        logger.exception(
            "Error executing push_invoice_task", invoice_id=invoice_id_str, error=str(exc)
        )
        raise self.retry(exc=exc) from exc
