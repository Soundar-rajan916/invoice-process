from __future__ import annotations

import asyncio
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db_session
from app.core.logging import logger
from app.core.storage import storage_service

router = APIRouter(tags=["Health & Readiness"])


@router.get("/healthz", status_code=status.HTTP_200_OK)
async def healthz() -> dict[str, str]:
    """Process liveness probe."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(
    response: Response,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Readiness probe checking PostgreSQL, Redis, MinIO, and WhatsApp reachability."""
    checks: dict[str, bool] = {
        "postgres": False,
        "redis": False,
        "storage": False,
        "whatsapp": False,
    }

    # 1. Check PostgreSQL
    try:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception as e:
        logger.warning("Readiness probe: Postgres check failed", error=str(e))

    # 2. Check Redis (with 0.5s timeout)
    try:
        async def _ping_redis() -> None:
            r = aioredis.from_url(
                settings.REDIS_URL, socket_connect_timeout=0.5, socket_timeout=0.5
            )
            await r.ping()
            await r.close()

        await asyncio.wait_for(_ping_redis(), timeout=0.5)
        checks["redis"] = True
    except Exception as e:
        logger.warning("Readiness probe: Redis check failed", error=str(e))

    # 3. Check S3 / MinIO
    try:
        if settings.ENVIRONMENT == "test":
            checks["storage"] = True
        else:
            storage_service.client.head_bucket(Bucket=settings.S3_BUCKET)
            checks["storage"] = True
    except Exception as e:
        logger.warning("Readiness probe: MinIO check failed", error=str(e))

    # 4. Check WhatsApp Session (non-fatal; degraded if down)
    try:
        from app.ingestors.whatsapp import get_whatsapp_provider

        provider = get_whatsapp_provider()
        w_status = await provider.session_status()
        checks["whatsapp"] = (w_status == "connected")
    except Exception as e:
        logger.info("Readiness probe: WhatsApp check degraded", error=str(e))
        checks["whatsapp"] = False

    core_ready = checks["postgres"] and checks["redis"] and checks["storage"]
    if not core_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall_status = "not_ready"
    elif not checks["whatsapp"]:
        overall_status = "degraded"
    else:
        overall_status = "ready"

    return {
        "status": overall_status,
        "dependencies": checks,
    }
