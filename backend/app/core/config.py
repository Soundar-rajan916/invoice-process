from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: Literal["development", "production", "test"] = "development"

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/invoiceflow",
        description="Async PostgreSQL connection URL",
    )
    DATABASE_URL_SYNC: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/invoiceflow",
        description="Synchronous PostgreSQL connection URL for Alembic",
    )

    # Redis broker for Celery
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL for Celery broker",
    )

    # S3 / MinIO Object Storage
    S3_ENDPOINT: str = Field(default="http://localhost:9000")
    S3_ACCESS_KEY: str = Field(default="minioadmin")
    S3_SECRET_KEY: str = Field(default="minioadmin")
    S3_BUCKET: str = Field(default="invoices")
    S3_REGION: str = Field(default="us-east-1")

    # Security & Auth
    JWT_SECRET: str = Field(
        default="development-insecure-secret-key-32-chars-minimum-length-req",
        description="Secret key for JWT generation",
    )
    ACCESS_TOKEN_TTL_MINUTES: int = Field(default=60)
    ADMIN_EMAIL: str = Field(default="admin@invoiceflow.local")
    ADMIN_PASSWORD: str = Field(default="AdminPassword123!")

    # Extractor
    EXTRACTOR: Literal["groq", "mock"] = Field(
        default="mock",
        description="Extractor backend choice: groq or mock",
    )
    MOCK_MANIFEST_PATH: str = Field(
        default="data/synthetic/manifest.jsonl",
        description="Path to mock ground truth manifest",
    )

    # Groq Settings
    GROQ_API_KEY: str = Field(default="")
    GROQ_TEXT_MODEL: str = Field(default="llama-3.3-70b-versatile")
    GROQ_VISION_MODEL: str = Field(default="llama-3.2-11b-vision-preview")
    GROQ_MAX_CONCURRENCY: int = Field(default=4)
    GROQ_MAX_IMAGES_PER_REQUEST: int = Field(default=5)
    GROQ_MAX_REQUEST_BYTES: int = Field(default=3500000)
    GROQ_REPAIR_RETRIES: int = Field(default=2)
    GROQ_TIMEOUT_SECONDS: float = Field(default=60.0)

    # Preprocessing & Image Quality Thresholds (R1)
    MAX_IMAGE_LONG_SIDE: int = Field(default=1600)
    MIN_TEXT_CHARS: int = Field(default=80)
    BLUR_REJECT_THRESHOLD: float = Field(default=50.0)
    MAX_UPLOAD_MB: int = Field(default=20)

    # Business Validation Constants (R2, R3)
    BUYER_GSTIN: str = Field(default="33AAAAA0000A1Z5")
    BUYER_STATE_CODE: str = Field(default="33")
    AMOUNT_TOLERANCE: Decimal = Field(default=Decimal("0.01"))
    TOTAL_ROUNDING_TOLERANCE: Decimal = Field(default=Decimal("1.00"))
    LOW_CONFIDENCE_THRESHOLD: float = Field(default=0.7)

    # Accounting Push API
    ACCOUNTING_API_URL: str = Field(default="http://localhost:8001")
    ACCOUNTING_API_KEY: str = Field(default="accounting-secret-token")
    PUSH_MAX_ATTEMPTS: int = Field(default=3)

    # CORS
    CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[str]:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("EXTRACTOR")
    @classmethod
    def validate_extractor(cls, v: str) -> str:
        if v not in ("groq", "mock"):
            raise ValueError(f"EXTRACTOR must be 'groq' or 'mock', got '{v}'")
        return v


settings = Settings()
