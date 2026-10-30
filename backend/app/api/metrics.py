from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import get_current_user
from app.models.entities import Extraction, Invoice, ReviewEvent, Supplier, User

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/summary")
async def get_metrics_summary(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Computes operational and dashboard metrics:
    - Counts by status.
    - Median and 95th-percentile time from received to approved.
    - Reviewer edit rate per field over the last 7 days.
    - Queue age of oldest unreviewed invoice (R4 pressure indicator).
    - Token usage and estimated cost metrics (Phase 5).
    - Top 5 worst suppliers by human edit rate (Phase 5).
    """
    now = datetime.now(UTC)

    # 1. Counts by status
    count_stmt = select(Invoice.status, func.count(Invoice.id)).group_by(Invoice.status)
    counts = {r[0]: r[1] for r in (await db.execute(count_stmt)).all()}

    # 2. Time from received to approved (for approved/pushing/pushed invoices)
    approved_stmt = select(Invoice.created_at, Invoice.approved_at).where(
        Invoice.approved_at.is_not(None)
    )
    approved_rows = (await db.execute(approved_stmt)).all()
    durations_minutes = [
        max(0.0, (row[1] - row[0]).total_seconds() / 60.0)
        for row in approved_rows
        if row[0] and row[1]
    ]

    p50_duration = float(np.percentile(durations_minutes, 50)) if durations_minutes else 0.0
    p95_duration = float(np.percentile(durations_minutes, 95)) if durations_minutes else 0.0

    # 3. Oldest unreviewed invoice age (in minutes / hours)
    oldest_stmt = (
        select(Invoice.created_at)
        .where(Invoice.status == "NEEDS_REVIEW")
        .order_by(Invoice.created_at.asc())
        .limit(1)
    )
    oldest_created_at = (await db.execute(oldest_stmt)).scalar_one_or_none()
    oldest_waiting_age_minutes = (
        max(0.0, (now - oldest_created_at).total_seconds() / 60.0) if oldest_created_at else 0.0
    )

    # 4. Reviewer edit rate per field over last 7 days
    seven_days_ago = now - timedelta(days=7)
    edits_stmt = select(ReviewEvent.payload, ReviewEvent.invoice_id).where(
        ReviewEvent.action == "edit",
        ReviewEvent.created_at >= seven_days_ago,
    )
    edit_rows = (await db.execute(edits_stmt)).all()

    total_edits = len(edit_rows)
    field_edit_counts: dict[str, int] = {}
    invoice_edit_counts: dict[str, int] = {}

    for payload, inv_id in edit_rows:
        diff = payload.get("diff", {}) if isinstance(payload, dict) else {}
        for fld in diff:
            field_edit_counts[fld] = field_edit_counts.get(fld, 0) + 1
        inv_key = str(inv_id)
        invoice_edit_counts[inv_key] = invoice_edit_counts.get(inv_key, 0) + 1

    field_edit_rates = {
        fld: round(cnt / total_edits, 4) if total_edits > 0 else 0.0
        for fld, cnt in field_edit_counts.items()
    }

    # 5. Top 5 Worst Suppliers by Human Edit Rate (Phase 5)
    supplier_inv_stmt = (
        select(Invoice.supplier_gstin, func.count(Invoice.id))
        .where(Invoice.supplier_gstin.is_not(None))
        .group_by(Invoice.supplier_gstin)
    )
    supplier_inv_counts = {r[0]: r[1] for r in (await db.execute(supplier_inv_stmt)).all()}

    supplier_edits_stmt = (
        select(Invoice.supplier_gstin, func.count(ReviewEvent.id))
        .join(ReviewEvent, ReviewEvent.invoice_id == Invoice.id)
        .where(ReviewEvent.action == "edit", Invoice.supplier_gstin.is_not(None))
        .group_by(Invoice.supplier_gstin)
    )
    supplier_edit_counts = {r[0]: r[1] for r in (await db.execute(supplier_edits_stmt)).all()}

    # Fetch supplier names
    known_suppliers_stmt = select(Supplier.gstin, Supplier.name)
    known_names = {r[0]: r[1] for r in (await db.execute(known_suppliers_stmt)).all()}

    worst_suppliers = []
    for gstin, total_inv in supplier_inv_counts.items():
        edits = supplier_edit_counts.get(gstin, 0)
        rate = round(edits / total_inv, 4) if total_inv > 0 else 0.0
        worst_suppliers.append(
            {
                "gstin": gstin,
                "name": known_names.get(gstin, "Unknown Supplier"),
                "total_invoices": total_inv,
                "edit_count": edits,
                "edit_rate": rate,
            }
        )

    # Sort descending by edit_count, then edit_rate
    worst_suppliers.sort(key=lambda s: (s["edit_count"], s["edit_rate"]), reverse=True)
    top_5_worst_suppliers = worst_suppliers[:5]

    # 6. Cost and Token Tracking (Phase 5)
    ext_stmt = select(Extraction.token_usage).where(Extraction.token_usage.is_not(None))
    token_rows = (await db.execute(ext_stmt)).scalars().all()

    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    for tu in token_rows:
        if isinstance(tu, dict):
            p = tu.get("prompt_tokens", 0) or 0
            c = tu.get("completion_tokens", 0) or 0
            total_prompt_tokens += p
            total_completion_tokens += c
            total_tokens += tu.get("total_tokens", p + c) or (p + c)

    # Groq Vision Pricing: ~$0.05/1M input, ~$0.10/1M output
    cost_usd = (total_prompt_tokens * 0.00000005) + (total_completion_tokens * 0.00000010)
    invoices_counted = len(token_rows) or 1
    avg_tokens = round(total_tokens / invoices_counted, 1)
    avg_cost = round(cost_usd / invoices_counted, 4)

    return {
        "status_counts": counts,
        "oldest_waiting_age_minutes": round(oldest_waiting_age_minutes, 1),
        "median_time_to_approve_minutes": round(p50_duration, 1),
        "p95_time_to_approve_minutes": round(p95_duration, 1),
        "field_edit_rates_7d": field_edit_rates,
        "total_edits_7d": total_edits,
        "worst_suppliers": top_5_worst_suppliers,
        "cost_and_usage": {
            "total_tokens": total_tokens,
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "avg_tokens_per_invoice": avg_tokens,
            "estimated_total_cost_usd": round(cost_usd, 4),
            "estimated_cost_per_invoice_usd": avg_cost,
        },
    }
