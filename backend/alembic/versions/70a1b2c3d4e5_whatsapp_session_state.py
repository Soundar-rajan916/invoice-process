"""whatsapp_session_state

Revision ID: 70a1b2c3d4e5
Revises: 60f0e4ce9e81
Create Date: 2026-11-02

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "70a1b2c3d4e5"
down_revision: str | None = "60f0e4ce9e81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    json_type = JSONB().with_variant(sa.JSON(), "sqlite")

    op.create_table(
        "whatsapp_session_state",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(50), nullable=False, server_default="openwa"),
        sa.Column("state", sa.String(50), nullable=False, server_default="unknown"),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detail", json_type, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_whatsapp_session_state_provider",
        "whatsapp_session_state",
        ["provider"],
    )


def downgrade() -> None:
    op.drop_index("ix_whatsapp_session_state_provider", table_name="whatsapp_session_state")
    op.drop_table("whatsapp_session_state")
