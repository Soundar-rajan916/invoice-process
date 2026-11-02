from __future__ import annotations

from celery import Celery
from kombu import Queue

from app.core.config import settings

celery_app = Celery(
    "invoiceflow",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.workers.tasks"],
)
celery_app.set_default()

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=180,  # 3 minutes soft limit
    task_time_limit=240,  # 4 minutes hard limit
    task_default_retry_delay=5,
    task_max_retries=3,
    broker_connection_retry_on_startup=True,
    task_queues=[
        Queue("ingest", routing_key="ingest.#"),
        Queue("extract", routing_key="extract.#"),
        Queue("push", routing_key="push.#"),
        Queue("notify", routing_key="notify.#"),
        Queue("maintenance", routing_key="maintenance.#"),
    ],
    task_default_queue="extract",
    task_routes={
        "app.workers.tasks.process_whatsapp_message_task": {"queue": "ingest"},
        "app.workers.tasks.process_whatsapp_inbound_task": {"queue": "ingest"},
        "app.workers.tasks.process_invoice_task": {"queue": "extract"},
        "app.workers.tasks.push_invoice_task": {"queue": "push"},
        "app.workers.tasks.dispatch_outbox_task": {"queue": "notify"},
        "app.workers.tasks.poll_mailbox_task": {"queue": "maintenance"},
        "app.workers.tasks.poll_whatsapp_session_task": {"queue": "maintenance"},
        "app.workers.tasks.watchdog_stuck_invoices_task": {"queue": "maintenance"},
        "app.workers.tasks.reconcile_accounting_task": {"queue": "maintenance"},
        "app.workers.tasks.verify_invariants_task": {"queue": "maintenance"},
        "app.workers.tasks.purge_expired_files_task": {"queue": "maintenance"},
    },
    beat_schedule={
        "poll-mailbox-every-interval": {
            "task": "app.workers.tasks.poll_mailbox_task",
            "schedule": float(settings.EMAIL_POLL_INTERVAL_SECONDS),
        },
        "poll-whatsapp-session-every-60s": {
            "task": "app.workers.tasks.poll_whatsapp_session_task",
            "schedule": 60.0,
        },
        "dispatch-outbox-every-30s": {
            "task": "app.workers.tasks.dispatch_outbox_task",
            "schedule": 30.0,
        },
        "watchdog-stuck-invoices-every-60s": {
            "task": "app.workers.tasks.watchdog_stuck_invoices_task",
            "schedule": 60.0,
        },
        "reconcile-accounting-daily": {
            "task": "app.workers.tasks.reconcile_accounting_task",
            "schedule": 86400.0,  # Run daily
        },
        "purge-expired-retention-files-daily": {
            "task": "app.workers.tasks.purge_expired_files_task",
            "schedule": 86400.0,
        },
    },
)
