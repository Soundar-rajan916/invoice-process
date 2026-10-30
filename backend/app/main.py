from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging import logger, setup_logging
from app.core.middleware import RequestIdMiddleware
from app.core.model_check import check_groq_models_at_startup
from app.core.storage import storage_service


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging()
    logger.info(
        "Starting InvoiceFlow API",
        environment=settings.ENVIRONMENT,
        extractor=settings.EXTRACTOR,
    )

    # 1. Groq models check
    await check_groq_models_at_startup()

    # 2. Storage bucket check
    storage_service.ensure_bucket_exists()

    yield

    logger.info("Shutting down InvoiceFlow API")


def create_app() -> FastAPI:
    app = FastAPI(
        title="InvoiceFlow API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Middlewares
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Error Handlers (RFC 7807)
    register_error_handlers(app)

    # Routers
    app.include_router(health_router)
    from app.api.admin import router as admin_router
    from app.api.auth import router as auth_router
    from app.api.files import router as files_router
    from app.api.invoices import router as invoices_router
    from app.api.metrics import router as metrics_router
    from app.api.webhooks import router as webhooks_router

    app.include_router(files_router)
    app.include_router(webhooks_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(invoices_router, prefix="/api/v1")
    app.include_router(metrics_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")

    return app


app = create_app()
