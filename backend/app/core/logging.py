from __future__ import annotations

import logging as std_logging
import sys
from typing import Any, MutableMapping
import structlog
from app.core.config import settings


def drop_sensitive_data(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Ensure no full invoice bodies, API keys, or presigned URLs leak into INFO+ logs."""
    for key in list(event_dict.keys()):
        lower_key = key.lower()
        if any(secret in lower_key for secret in ("key", "secret", "password", "token", "auth")):
            event_dict[key] = "[REDACTED]"
        elif "url" in lower_key and ("X-Amz-Signature" in str(event_dict[key]) or "sig=" in str(event_dict[key])):
            event_dict[key] = "[REDACTED_PRESIGNED_URL]"
    return event_dict


def setup_logging() -> None:
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        drop_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.ENVIRONMENT == "production":
        processors = shared_processors + [
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer(),
        ]
    else:
        processors = shared_processors + [
            structlog.dev.ConsoleRenderer(colors=True),
        ]

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    std_logging.basicConfig(  # type: ignore[attr-defined]
        format="%(message)s",
        stream=sys.stdout,
        level=std_logging.INFO if settings.ENVIRONMENT == "production" else std_logging.DEBUG,  # type: ignore[attr-defined]
    )


logger = structlog.get_logger("invoiceflow")
