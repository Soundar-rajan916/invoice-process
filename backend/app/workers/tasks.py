from __future__ import annotations

import asyncio
import uuid
from typing import Any

import redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.logging import logger
from app.services.pipeline import process_invoice_pipeline
from app.workers.celery_app import celery_app


def _get_worker_session() -> tuple[async_sessionmaker[AsyncSession], Any]:
    task_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
    maker = async_sessionmaker(task_engine, class_=AsyncSession, expire_on_commit=False)
    return maker, task_engine


@celery_app.task(
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
        maker, task_engine = _get_worker_session()
        try:
            async with maker() as session:
                inv = await process_invoice_pipeline(session, invoice_id)
                return inv.status if inv else "SKIPPED"
        finally:
            await task_engine.dispose()

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
                maker, task_engine = _get_worker_session()
                try:
                    async with maker() as session:
                        from app.models.entities import Invoice

                        inv = await session.get(Invoice, invoice_id)
                        if inv:
                            inv.status = "FAILED"
                            inv.status_reason = f"Exhausted worker retries: {err_msg}"
                            await session.commit()
                finally:
                    await task_engine.dispose()

            asyncio.run(_mark_failed())
        raise self.retry(exc=exc) from exc


@celery_app.task(
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
    from app.services.push import push_invoice

    invoice_id = uuid.UUID(invoice_id_str)

    async def _run() -> str:
        maker, task_engine = _get_worker_session()
        try:
            async with maker() as session:
                inv = await push_invoice(session, invoice_id)
                return inv.status if inv else "SKIPPED"
        finally:
            await task_engine.dispose()

    try:
        status = asyncio.run(_run())
        return {"invoice_id": invoice_id_str, "status": status}
    except Exception as exc:
        logger.exception(
            "Error executing push_invoice_task", invoice_id=invoice_id_str, error=str(exc)
        )
        raise self.retry(exc=exc) from exc


@celery_app.task(
    bind=True,
    name="app.workers.tasks.poll_mailbox_task",
    max_retries=1,
    acks_late=True,
)
def poll_mailbox_task(self: Any) -> dict[str, Any]:
    """Celery beat task polling unseen messages from configured mailbox under Redis lock."""
    # 1. Distributed lock to ensure only one poller runs at a time
    try:
        r = redis.Redis.from_url(settings.REDIS_URL)
        lock = r.lock("lock:poll_mailbox", timeout=120)
        have_lock = lock.acquire(blocking=False)
        if not have_lock:
            logger.info("Another poll_mailbox task is running, skipping iteration")
            return {"status": "skipped", "reason": "lock_acquired_by_other_worker"}
    except Exception as e:
        logger.warning("Redis lock check failed, proceeding without lock", error=str(e))
        lock = None

    from app.services.email_intake import EmailIngestor, ImapMailboxClient

    client = ImapMailboxClient()

    async def _poll() -> list[dict[str, Any]]:
        maker, task_engine = _get_worker_session()
        results: list[dict[str, Any]] = []
        try:
            client.connect()
            messages = client.fetch_unseen_messages(settings.EMAIL_FOLDER)
            async with maker() as session:
                ingestor = EmailIngestor(session)
                for msg in messages:
                    res = await ingestor.process_message(msg)
                    results.append(res)
                    # Move to Processed (or Failed on error)
                    target_folder = (
                        settings.EMAIL_PROCESSED_FOLDER
                        if res.get("status") in ("ingested", "ignored", "skipped")
                        else settings.EMAIL_FAILED_FOLDER
                    )
                    client.move_message(msg.message_id, settings.EMAIL_FOLDER, target_folder)
            return results
        finally:
            client.disconnect()
            await task_engine.dispose()

    try:
        processed = asyncio.run(_poll())
        return {"status": "completed", "count": len(processed), "details": processed}
    except Exception as exc:
        logger.exception("Error executing poll_mailbox_task", error=str(exc))
        return {"status": "failed", "error": str(exc)}
    finally:
        if lock:
            try:
                lock.release()
            except Exception:
                pass


@celery_app.task(
    name="app.workers.tasks.dispatch_outbox_task",
    acks_late=True,
)
def dispatch_outbox_task() -> dict[str, Any]:
    """Celery beat task dispatching pending outbox messages."""
    from app.services.outbox import dispatch_pending_outbox_messages

    async def _dispatch() -> int:
        maker, task_engine = _get_worker_session()
        try:
            async with maker() as session:
                return await dispatch_pending_outbox_messages(session)
        finally:
            await task_engine.dispose()

    sent = asyncio.run(_dispatch())
    return {"status": "completed", "sent": sent}


@celery_app.task(
    name="app.workers.tasks.process_whatsapp_message_task",
    acks_late=True,
)
def process_whatsapp_message_task(
    message_id: str,
    sender: str,
    media_id: str,
    media_type: str,
    filename: str | None = None,
    mime_type: str | None = None,
) -> dict[str, Any]:
    """Celery task downloading WhatsApp media and running ingestion."""
    from app.services.whatsapp import WhatsAppIngestor

    async def _run() -> dict[str, Any]:
        maker, task_engine = _get_worker_session()
        try:
            async with maker() as session:
                ingestor = WhatsAppIngestor(session)
                return await ingestor.handle_media_message(
                    message_id=message_id,
                    sender=sender,
                    media_id=media_id,
                    media_type=media_type,
                    filename=filename,
                    mime_type=mime_type,
                )
        finally:
            await task_engine.dispose()

    return asyncio.run(_run())


async def _execute_watchdog_sweep_on_session(session: AsyncSession) -> dict[str, Any]:
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import or_, select

    from app.models.entities import Invoice, ReviewEvent

    requeued: list[str] = []
    escalated: list[str] = []
    now = datetime.now(UTC)
    proc_cutoff = now - timedelta(minutes=5)
    push_cutoff = now - timedelta(minutes=2)

    stmt = select(Invoice).where(
        or_(
            (Invoice.status == "PROCESSING")
            & (
                or_(
                    (Invoice.heartbeat_at.is_not(None)) & (Invoice.heartbeat_at < proc_cutoff),
                    (Invoice.heartbeat_at.is_(None)) & (Invoice.updated_at < proc_cutoff),
                )
            ),
            (Invoice.status == "PUSHING")
            & (
                or_(
                    (Invoice.heartbeat_at.is_not(None)) & (Invoice.heartbeat_at < push_cutoff),
                    (Invoice.heartbeat_at.is_(None)) & (Invoice.updated_at < push_cutoff),
                )
            ),
        )
    )
    stuck_invoices = (await session.execute(stmt)).scalars().all()

    for inv in stuck_invoices:
        prev_status = inv.status
        if inv.watchdog_requeue_count < 3:
            inv.watchdog_requeue_count += 1
            inv.heartbeat_at = now
            if inv.status == "PROCESSING":
                inv.status = "RECEIVED"
                try:
                    process_invoice.delay(str(inv.id))
                except Exception:
                    pass
            elif inv.status == "PUSHING":
                inv.status = "APPROVED"
                try:
                    from app.workers.tasks import push_invoice_task

                    push_invoice_task.delay(str(inv.id))
                except Exception:
                    pass

            session.add(
                ReviewEvent(
                    invoice_id=inv.id,
                    action="watchdog_requeue",
                    payload={
                        "previous_status": prev_status,
                        "requeue_count": inv.watchdog_requeue_count,
                        "cutoff": proc_cutoff.isoformat()
                        if prev_status == "PROCESSING"
                        else push_cutoff.isoformat(),
                    },
                )
            )
            requeued.append(str(inv.id))
        else:
            inv.status = "FAILED"
            inv.status_reason = "watchdog_timeout"
            session.add(
                ReviewEvent(
                    invoice_id=inv.id,
                    action="status_change",
                    payload={
                        "previous_status": prev_status,
                        "reason": "watchdog_timeout",
                        "requeue_count": inv.watchdog_requeue_count,
                    },
                )
            )
            escalated.append(str(inv.id))

    if stuck_invoices:
        await session.commit()
    return {"requeued": requeued, "escalated": escalated}


async def run_watchdog_sweep(session: AsyncSession | None = None) -> dict[str, Any]:
    """Sweeps for stuck PROCESSING or PUSHING invoices and requeues or escalates them."""
    if session is not None:
        return await _execute_watchdog_sweep_on_session(session)

    maker, task_engine = _get_worker_session()
    try:
        async with maker() as sess:
            return await _execute_watchdog_sweep_on_session(sess)
    finally:
        await task_engine.dispose()


@celery_app.task(
    name="app.workers.tasks.watchdog_stuck_invoices_task",
    acks_late=True,
)
def watchdog_stuck_invoices_task() -> dict[str, Any]:
    """Watchdog task (R4 scale & reliability).
    Requeues stuck PROCESSING (older than 5 min) or PUSHING (older than 2 min) invoices.
    After 3 requeues, escalates to FAILED with reason 'watchdog_timeout'.
    """
    res = asyncio.run(run_watchdog_sweep())
    logger.info(
        "Watchdog sweep finished", requeued=len(res["requeued"]), escalated=len(res["escalated"])
    )
    return res
