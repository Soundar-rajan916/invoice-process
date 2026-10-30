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
    GROQ_MAX_TOKENS: int = Field(default=8192)

    # Safety Net & Second Opinion (R2)
    SECOND_OPINION_ENABLED: bool = Field(default=False)
    GROQ_SECOND_MODEL: str = Field(default="llama-3.2-90b-vision-preview")
    NATIVE_PDF_EXTRACTOR_URL: str = Field(default="")
    NATIVE_PDF_EXTRACTOR_KEY: str = Field(default="")

    # Preprocessing & Image Quality Thresholds (R1)
    MAX_IMAGE_LONG_SIDE: int = Field(default=1600)
    MIN_TEXT_CHARS: int = Field(default=80)
    BLUR_REJECT_THRESHOLD: float = Field(default=50.0)
    PREPROCESS_MIN_BRIGHTNESS: float = Field(default=30.0)
    PREPROCESS_MAX_BRIGHTNESS: float = Field(default=240.0)
    PREPROCESS_MIN_CONTRAST: float = Field(default=15.0)
    MAX_UPLOAD_MB: int = Field(default=20)

    # Business Validation Constants (R2, R3)
    BUYER_GSTIN: str = Field(default="33AAAAA0000A1Z5")
    BUYER_STATE_CODE: str = Field(default="33")
    AMOUNT_TOLERANCE: Decimal = Field(default=Decimal("0.01"))
    TOTAL_ROUNDING_TOLERANCE: Decimal = Field(default=Decimal("0.00"))
    LOW_CONFIDENCE_THRESHOLD: float = Field(default=0.7)

    # Email Intake Configuration (4.1)
    EMAIL_INTAKE_ENABLED: bool = Field(default=False)
    EMAIL_IMAP_HOST: str = Field(default="imap.example.com")
    EMAIL_IMAP_PORT: int = Field(default=993)
    EMAIL_IMAP_USER: str = Field(default="")
    EMAIL_IMAP_PASSWORD: str = Field(default="")
    EMAIL_FOLDER: str = Field(default="INBOX")
    EMAIL_PROCESSED_FOLDER: str = Field(default="Processed")
    EMAIL_FAILED_FOLDER: str = Field(default="Failed")
    EMAIL_POLL_INTERVAL_SECONDS: int = Field(default=60)
    EMAIL_MIN_ATTACHMENT_BYTES: int = Field(default=5000)
    EMAIL_MIN_IMAGE_PIXELS: int = Field(default=100)
    EMAIL_MAX_ATTACHMENT_BYTES: int = Field(default=20 * 1024 * 1024)
    EMAIL_MAX_ATTACHMENTS_PER_MESSAGE: int = Field(default=10)
    EMAIL_MAX_PDF_PAGES: int = Field(default=50)
    EMAIL_ALLOWED_SENDER_DOMAINS: list[str] | str = Field(default=[])

    # Outbox & Notifications (4.3)
    EMAIL_SMTP_HOST: str = Field(default="smtp.example.com")
    EMAIL_SMTP_PORT: int = Field(default=587)
    EMAIL_SMTP_USER: str = Field(default="")
    EMAIL_SMTP_PASSWORD: str = Field(default="")
    EMAIL_FROM_ADDRESS: str = Field(default="invoices@invoiceflow.local")
    RESEND_MAX_PER_SENDER_PER_DAY: int = Field(default=5)

    # WhatsApp Intake Configuration (4.2)
    WHATSAPP_PHONE_NUMBER_ID: str = Field(default="100000000000001")
    WHATSAPP_API_TOKEN: str = Field(default="")
    WHATSAPP_APP_SECRET: str = Field(default="dev-whatsapp-app-secret")
    WHATSAPP_VERIFY_TOKEN: str = Field(default="invoiceflow-verify-token")
    WHATSAPP_GROUP_WINDOW_SECONDS: int = Field(default=90)
    WHATSAPP_RESEND_TEMPLATE: str = Field(default="invoice_resend_request")

    # Antivirus (4.5)
    ANTIVIRUS_ENABLED: bool = Field(default=False)
    CLAMAV_HOST: str = Field(default="clamav")
    CLAMAV_PORT: int = Field(default=3310)

    # Phase 5 Fallback & Resiliency
    FALLBACK_LLM_BASE_URL: str = Field(default="")
    FALLBACK_LLM_API_KEY: str = Field(default="")
    FALLBACK_LLM_MODEL: str = Field(default="")
    REVIEW_CLAIM_TIMEOUT_MINUTES: int = Field(default=5)

    # Retention & Data Handling (6.1)
    RETENTION_DAYS: int = Field(default=0)  # 0 = disabled

    # Observability & Tracing (6.2)
    OTEL_EXPORTER_OTLP_ENDPOINT: str = Field(default="")
    SENTRY_DSN: str = Field(default="")

    # Shadow Mode (6.5)
    SHADOW_MODE: bool = Field(default=False)

    # Accounting Push API
    ACCOUNTING_API_URL: str = Field(default="http://localhost:8001")
    ACCOUNTING_API_KEY: str = Field(default="accounting-secret-token")
    PUSH_MAX_ATTEMPTS: int = Field(default=3)

    # CORS
    CORS_ORIGINS: list[str] | str = Field(
        default=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"]
    )

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def parse_cors_origins(cls, v: list[str] | str) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("[") and v.endswith("]"):
                import json

                try:
                    loaded = json.loads(v)
                    if isinstance(loaded, list):
                        return [str(x).strip() for x in loaded if str(x).strip()]
                except Exception:
                    pass
            return [x.strip() for x in v.split(",") if x.strip()]
        return v

    @field_validator("EMAIL_ALLOWED_SENDER_DOMAINS", mode="after")
    @classmethod
    def parse_allowed_domains(cls, v: list[str] | str) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return []
            return [x.strip().lower() for x in v.split(",") if x.strip()]
        return [str(x).strip().lower() for x in v if str(x).strip()]

    @field_validator("EXTRACTOR")
    @classmethod
    def validate_extractor(cls, v: str) -> str:
        if v not in ("groq", "mock"):
            raise ValueError(f"Invalid EXTRACTOR: {v}. Must be 'groq' or 'mock'")
        return v


settings = Settings()
