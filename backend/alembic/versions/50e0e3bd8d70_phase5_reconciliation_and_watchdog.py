"""phase5_reconciliation_and_watchdog

Revision ID: 50e0e3bd8d70
Revises: 0002_phase4
Create Date: 2026-10-30

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "50e0e3bd8d70"
down_revision: str | None = "0002_phase4_intake_and_safety"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. reconciliation_runs table
    op.create_table(
        "reconciliation_runs",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="running"),
        sa.Column("total_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_matched", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_discrepancies", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("summary", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 2. reconciliation_findings table
    op.create_table(
        "reconciliation_findings",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column(
            "run_id",
            sa.UUID(),
            sa.ForeignKey("reconciliation_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "invoice_id",
            sa.UUID(),
            sa.ForeignKey("invoices.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "finding_type", sa.String(length=50), nullable=False
        ),  # missing_in_accounting | missing_in_invoiceflow | amount_mismatch | status_mismatch
        sa.Column(
            "severity", sa.String(length=20), nullable=False, server_default="warning"
        ),  # warning | error
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    # 3. Add watchdog columns to invoices
    op.add_column(
        "invoices",
        sa.Column("watchdog_requeue_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("invoices", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "heartbeat_at")
    op.drop_column("invoices", "watchdog_requeue_count")
    op.drop_table("reconciliation_findings")
    op.drop_table("reconciliation_runs")
