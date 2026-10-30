"""phase6_security_and_shadow

Revision ID: 60f0e4ce9e81
Revises: 50e0e3bd8d70
Create Date: 2026-10-30

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "60f0e4ce9e81"
down_revision: str | None = "50e0e3bd8d70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. User security columns
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean(), server_default="false", nullable=False),
    )

    # 2. Invoice privacy & shadow mode columns
    op.add_column(
        "invoices",
        sa.Column("is_erased", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column("invoices", sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "invoices",
        sa.Column("erased_by", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column("invoices", sa.Column("erased_reason", sa.Text(), nullable=True))
    op.add_column(
        "invoices",
        sa.Column("is_shadow", sa.Boolean(), server_default="false", nullable=False),
    )

    # 3. Revoked tokens table
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("token_jti", sa.String(255), unique=True, index=True, nullable=False),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 4. Shadow records table for historical ground truth comparison
    op.create_table(
        "shadow_records",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("batch_id", sa.String(100), nullable=False, index=True),
        sa.Column("invoice_number", sa.String(100), nullable=False, index=True),
        sa.Column("supplier_gstin", sa.String(20), nullable=False, index=True),
        sa.Column("invoice_date", sa.String(20), nullable=False),
        sa.Column("total", sa.Numeric(15, 2), nullable=False),
        sa.Column("raw_data", JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("shadow_records")
    op.drop_table("revoked_tokens")
    op.drop_column("invoices", "is_shadow")
    op.drop_column("invoices", "erased_reason")
    op.drop_column("invoices", "erased_by")
    op.drop_column("invoices", "erased_at")
    op.drop_column("invoices", "is_erased")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
