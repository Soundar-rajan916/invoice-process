"""Phase 4: inbound_messages, outbound_messages, and invoice intake columns

Revision ID: 0002_phase4_intake_and_safety
Revises: 0001_initial_schema
Create Date: 2026-10-30 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_phase4_intake_and_safety"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    is_sqlite = bind.dialect.name == "sqlite"
    UUID_TYPE = sa.String(36) if is_sqlite else postgresql.UUID(as_uuid=True)
    JSON_TYPE = sa.JSON() if is_sqlite else postgresql.JSONB(astext_type=sa.Text())

    # 1. inbound_messages
    op.create_table(
        "inbound_messages",
        sa.Column("id", UUID_TYPE, primary_key=True),
        sa.Column("channel", sa.String(30), nullable=False),  # email | whatsapp
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("sender", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status", sa.String(30), nullable=False, server_default="received"
        ),  # received | ignored | ingested | failed
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("source_file_ids", JSON_TYPE, nullable=False, server_default="[]"),
        sa.Column("raw_meta", JSON_TYPE, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_inbound_messages_channel_external_id",
        "inbound_messages",
        ["channel", "external_id"],
        unique=True,
    )
    op.create_index("ix_inbound_messages_status", "inbound_messages", ["status"])

    # 2. outbound_messages (Transactional Outbox)
    op.create_table(
        "outbound_messages",
        sa.Column("id", UUID_TYPE, primary_key=True),
        sa.Column("invoice_id", UUID_TYPE, sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("channel", sa.String(30), nullable=False),  # email | whatsapp
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("template_key", sa.String(100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "status", sa.String(30), nullable=False, server_default="pending"
        ),  # pending | sent | failed
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outbound_messages_status", "outbound_messages", ["status"])
    op.create_index("ix_outbound_messages_invoice_id", "outbound_messages", ["invoice_id"])

    # 3. Add columns to invoices table (expand-first, all nullable)
    op.add_column(
        "invoices",
        sa.Column(
            "inbound_message_id", UUID_TYPE, sa.ForeignKey("inbound_messages.id"), nullable=True
        ),
    )
    op.add_column(
        "invoices",
        sa.Column("claimed_by", UUID_TYPE, sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("claim_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "invoices",
        sa.Column("sender", sa.String(255), nullable=True),
    )
    op.create_index("ix_invoices_inbound_message_id", "invoices", ["inbound_message_id"])
    op.create_index("ix_invoices_claimed_by", "invoices", ["claimed_by"])


def downgrade() -> None:
    op.drop_index("ix_invoices_claimed_by", table_name="invoices")
    op.drop_index("ix_invoices_inbound_message_id", table_name="invoices")
    op.drop_column("invoices", "sender")
    op.drop_column("invoices", "claim_expires_at")
    op.drop_column("invoices", "claimed_by")
    op.drop_column("invoices", "inbound_message_id")
    op.drop_table("outbound_messages")
    op.drop_table("inbound_messages")
