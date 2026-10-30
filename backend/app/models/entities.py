from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.core.database import GUID, Base, TimestampMixin

# Use JSONB on Postgres, standard JSON on other DBs (e.g. SQLite for unit tests)
JSONType = JSONB().with_variant(JSON(), "sqlite")


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(50), default="reviewer", nullable=False
    )  # reviewer | admin
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    gstin: Mapped[str] = mapped_column(String(15), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class SourceFile(Base, TimestampMixin):
    __tablename__ = "source_files"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), default="upload", nullable=False
    )  # upload | email | whatsapp
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id"), nullable=True
    )

    invoices = relationship("Invoice", back_populates="source_file")


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    source_file_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("source_files.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(50), default="RECEIVED", index=True, nullable=False)
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    page_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    extraction_path: Mapped[str | None] = mapped_column(String(20), nullable=True)  # text | vision

    current_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("extractions.id", use_alter=True, name="fk_invoice_current_extraction"),
        nullable=True,
    )
    approved_extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID,
        ForeignKey("extractions.id", use_alter=True, name="fk_invoice_approved_extraction"),
        nullable=True,
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Business-key columns
    supplier_gstin: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    normalized_invoice_number: Mapped[str | None] = mapped_column(
        String(100), index=True, nullable=True
    )
    financial_year: Mapped[str | None] = mapped_column(String(10), index=True, nullable=True)

    dup_of_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("invoices.id"), nullable=True
    )
    dup_overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dup_override_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    accounting_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    row_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    source_file = relationship("SourceFile", back_populates="invoices")
    extractions = relationship(
        "Extraction", back_populates="invoice", foreign_keys="Extraction.invoice_id"
    )
    validation_issues = relationship("ValidationIssue", back_populates="invoice")
    review_events = relationship("ReviewEvent", back_populates="invoice")
    push_attempts = relationship("PushAttempt", back_populates="invoice")

    __table_args__ = (
        # R2 Guarantee: Never push without reviewer approval
        CheckConstraint(
            "status NOT IN ('PUSHING', 'PUSHED') OR (approved_by IS NOT NULL AND approved_extraction_id IS NOT NULL)",
            name="check_approved_before_push",
        ),
        # R3 Guarantee: Partial unique index for business key
        Index(
            "idx_invoices_business_key_unique",
            "supplier_gstin",
            "normalized_invoice_number",
            "financial_year",
            unique=True,
            postgresql_where=(
                (Column("dup_of_id").is_(None))
                & (~Column("status").in_(["REJECTED", "REJECTED_DUPLICATE", "RESEND_REQUESTED"]))
            ),
            sqlite_where=(
                (Column("dup_of_id").is_(None))
                & (~Column("status").in_(["REJECTED", "REJECTED_DUPLICATE", "RESEND_REQUESTED"]))
            ),
        ),
    )


class Extraction(Base, TimestampMixin):
    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("invoices.id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)  # model | human_edit
    data: Mapped[dict[str, Any]] = mapped_column(JSONType, nullable=False)
    confidences: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("users.id"), nullable=True
    )

    invoice = relationship("Invoice", back_populates="extractions", foreign_keys=[invoice_id])


class ValidationIssue(Base, TimestampMixin):
    __tablename__ = "validation_issues"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("invoices.id"), nullable=False, index=True
    )
    extraction_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID, ForeignKey("extractions.id"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    field: Mapped[str | None] = mapped_column(String(100), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # error | warning
    message: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_by_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    invoice = relationship("Invoice", back_populates="validation_issues")


class ReviewEvent(Base, TimestampMixin):
    __tablename__ = "review_events"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("invoices.id"), nullable=False, index=True
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(GUID, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    # actions: status_change, edit, approve, reject, request_resend, confirm_duplicate, override_duplicate, override_issue, duplicate_file_skipped
    payload: Mapped[dict[str, Any]] = mapped_column(JSONType, default=dict, nullable=False)

    invoice = relationship("Invoice", back_populates="review_events")


class PushAttempt(Base, TimestampMixin):
    __tablename__ = "push_attempts"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("invoices.id"), nullable=False, index=True
    )
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    response: Mapped[dict[str, Any] | None] = mapped_column(JSONType, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    invoice = relationship("Invoice", back_populates="push_attempts")
