from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_defaults():
    s = Settings(
        DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/invoiceflow",
        REDIS_URL="redis://localhost:6379/0",
        JWT_SECRET="test-jwt-secret-at-least-32-characters-long",
    )
    assert s.ENVIRONMENT == "development"
    assert s.EXTRACTOR in ("groq", "mock")
    assert s.BUYER_STATE_CODE == "33"
    from decimal import Decimal

    assert s.AMOUNT_TOLERANCE == Decimal("0.01")


def test_cors_origins_parsing():
    s = Settings(
        CORS_ORIGINS="http://localhost:3000, http://localhost:5173",
        JWT_SECRET="test-jwt-secret-at-least-32-characters-long",
    )
    assert s.CORS_ORIGINS == ["http://localhost:3000", "http://localhost:5173"]


def test_invalid_extractor():
    with pytest.raises(ValidationError):
        Settings(
            EXTRACTOR="invalid_extractor",
            JWT_SECRET="test-jwt-secret-at-least-32-characters-long",
        )
