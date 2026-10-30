from __future__ import annotations

from celery import Celery

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
)
