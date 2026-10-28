from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import get_current_user
from app.models.entities import Invoice, ReviewEvent, User

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
    edits_stmt = select(ReviewEvent.payload).where(
        ReviewEvent.action == "edit",
        ReviewEvent.created_at >= seven_days_ago,
    )
    edit_events = (await db.execute(edits_stmt)).scalars().all()

    total_edits = len(edit_events)
    field_edit_counts: dict[str, int] = {}
    for p in edit_events:
        diff = p.get("diff", {}) if isinstance(p, dict) else {}
        for fld in diff:
            field_edit_counts[fld] = field_edit_counts.get(fld, 0) + 1

    field_edit_rates = {
        fld: round(cnt / total_edits, 4) if total_edits > 0 else 0.0
        for fld, cnt in field_edit_counts.items()
    }

    return {
        "status_counts": counts,
        "oldest_waiting_age_minutes": round(oldest_waiting_age_minutes, 1),
        "median_time_to_approve_minutes": round(p50_duration, 1),
        "p95_time_to_approve_minutes": round(p95_duration, 1),
        "field_edit_rates_7d": field_edit_rates,
        "total_edits_7d": total_edits,
    }
