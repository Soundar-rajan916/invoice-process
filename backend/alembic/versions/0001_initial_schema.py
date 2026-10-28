"""Initial schema with R2/R3 constraints and audit trigger

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-28 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="reviewer"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # 2. suppliers
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("gstin", sa.String(15), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("state_code", sa.String(2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_suppliers_gstin", "suppliers", ["gstin"])

    # 3. source_files
    op.create_table(
        "source_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False),
        sa.Column("source", sa.String(50), nullable=False, server_default="upload"),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "uploaded_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_source_files_sha256", "source_files", ["sha256"])

    # 4. extractions (pre-created so invoices can FK to it)
    op.create_table(
        "extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidences", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(50), nullable=True),
        sa.Column("raw_response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("token_usage", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # 5. invoices
    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_file_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("source_files.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(50), nullable=False, server_default="RECEIVED"),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("extraction_path", sa.String(20), nullable=True),
        sa.Column(
            "current_extraction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extractions.id"),
            nullable=True,
        ),
        sa.Column(
            "approved_extraction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extractions.id"),
            nullable=True,
        ),
        sa.Column(
            "approved_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("supplier_gstin", sa.String(15), nullable=True),
        sa.Column("normalized_invoice_number", sa.String(100), nullable=True),
        sa.Column("financial_year", sa.String(10), nullable=True),
        sa.Column(
            "dup_of_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=True
        ),
        sa.Column("dup_overridden", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("dup_override_reason", sa.Text(), nullable=True),
        sa.Column("accounting_id", sa.String(100), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("row_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # R2 CHECK constraint
        sa.CheckConstraint(
            "status NOT IN ('PUSHING', 'PUSHED') OR (approved_by IS NOT NULL AND approved_extraction_id IS NOT NULL)",
            name="check_approved_before_push",
        ),
    )
    op.create_index("ix_invoices_status", "invoices", ["status"])
    op.create_index("ix_invoices_supplier_gstin", "invoices", ["supplier_gstin"])
    op.create_index(
        "ix_invoices_normalized_invoice_number", "invoices", ["normalized_invoice_number"]
    )
    op.create_index("ix_invoices_financial_year", "invoices", ["financial_year"])

    # R3 Partial unique index on business key
    op.create_index(
        "idx_invoices_business_key_unique",
        "invoices",
        ["supplier_gstin", "normalized_invoice_number", "financial_year"],
        unique=True,
        postgresql_where=sa.text(
            "dup_of_id IS NULL AND status NOT IN ('REJECTED', 'REJECTED_DUPLICATE')"
        ),
    )

    # Now add foreign key from extractions to invoices
    op.create_foreign_key(
        "fk_extractions_invoice_id",
        "extractions",
        "invoices",
        ["invoice_id"],
        ["id"],
    )
    op.create_index("ix_extractions_invoice_id", "extractions", ["invoice_id"])

    # 6. validation_issues
    op.create_table(
        "validation_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id"),
            nullable=False,
        ),
        sa.Column(
            "extraction_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("extractions.id"),
            nullable=True,
        ),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("field", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("resolved_by_override", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_validation_issues_invoice_id", "validation_issues", ["invoice_id"])

    # 7. review_events (audit trail)
    op.create_table(
        "review_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id"),
            nullable=False,
        ),
        sa.Column(
            "actor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True
        ),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_review_events_invoice_id", "review_events", ["invoice_id"])

    # Append-only trigger for review_events (Postgres specific)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE OR REPLACE FUNCTION block_review_events_mutation()
            RETURNS TRIGGER AS $$
            BEGIN
                RAISE EXCEPTION 'review_events is append-only: updates and deletes are prohibited.';
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_review_events_append_only
            BEFORE UPDATE OR DELETE ON review_events
            FOR EACH ROW
            EXECUTE FUNCTION block_review_events_mutation();
            """
        )

    # 8. push_attempts
    op.create_table(
        "push_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "invoice_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("invoices.id"),
            nullable=False,
        ),
        sa.Column("attempt_no", sa.Integer(), nullable=False),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_push_attempts_invoice_id", "push_attempts", ["invoice_id"])


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_review_events_append_only ON review_events;")
        op.execute("DROP FUNCTION IF EXISTS block_review_events_mutation();")

    op.drop_table("push_attempts")
    op.drop_table("review_events")
    op.drop_table("validation_issues")
    op.drop_table("invoices")
    op.drop_table("extractions")
    op.drop_table("source_files")
    op.drop_table("suppliers")
    op.drop_table("users")
