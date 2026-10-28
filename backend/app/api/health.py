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
    """Readiness probe checking PostgreSQL, Redis, and MinIO reachability."""
    checks: dict[str, bool] = {
        "postgres": False,
        "redis": False,
        "storage": False,
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
        storage_service.client.head_bucket(Bucket=settings.S3_BUCKET)
        checks["storage"] = True
    except Exception as e:
        logger.warning("Readiness probe: MinIO check failed", error=str(e))

    all_ready = all(checks.values())
    if not all_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if all_ready else "not_ready",
        "dependencies": checks,
    }
