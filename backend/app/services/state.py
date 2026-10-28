from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import InvalidStateTransitionError
from app.models.entities import Invoice, ReviewEvent

# Explicit allowed transitions table
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "RECEIVED": {"PROCESSING"},
    "PROCESSING": {"NEEDS_REVIEW", "RESEND_REQUESTED", "FAILED"},
    "NEEDS_REVIEW": {
        "APPROVED",
        "REJECTED",
        "REJECTED_DUPLICATE",
        "RESEND_REQUESTED",
        "NEEDS_REVIEW",  # self-transition on field edit / issue override
    },
    "APPROVED": {
        "PUSHING",
        "NEEDS_REVIEW",  # Invalidation on edit before push (R2)
    },
    "PUSHING": {
        "PUSHED",
        "APPROVED",  # Retryable failure, attempt recorded
        "PUSH_FAILED",  # Exhausted max attempts
    },
    "PUSHED": set(),  # Terminal state
    "REJECTED": set(),  # Terminal state
    "REJECTED_DUPLICATE": {"NEEDS_REVIEW"},  # Allowed if reviewer overrides duplicate
    "RESEND_REQUESTED": set(),
    "FAILED": {"PROCESSING"},  # Admin retry
    "PUSH_FAILED": {"APPROVED"},  # Admin retry
}


async def transition_invoice_status(
    session: AsyncSession,
    invoice: Invoice,
    target_status: str,
    actor_id: uuid.UUID | None = None,
    action: str = "status_change",
    reason: str | None = None,
    extra_payload: dict[str, Any] | None = None,
) -> Invoice:
    """Safely transitions an invoice's status according to the state machine rules.
    Writes a review_event audit log row on every transition.
    R2 Guarantee: There is no path directly to APPROVED or PUSHED without passing through NEEDS_REVIEW.
    """
    current_status = invoice.status
    allowed = ALLOWED_TRANSITIONS.get(current_status, set())

    if target_status not in allowed:
        raise InvalidStateTransitionError(
            current_status=current_status,
            target_status=target_status,
            reason=f"Status '{current_status}' can only transition to: {sorted(allowed)}",
        )

    # R2 Guarantee: Never allow APPROVED without human reviewer
    if target_status == "APPROVED" and actor_id is None and action != "retry":
        raise InvalidStateTransitionError(
            current_status=current_status,
            target_status=target_status,
            reason="Invoices cannot be approved without an authenticated reviewer.",
        )

    invoice.status = target_status
    if reason:
        invoice.status_reason = reason

    payload = {
        "from_status": current_status,
        "to_status": target_status,
        "reason": reason,
        **(extra_payload or {}),
    }

    event = ReviewEvent(
        invoice_id=invoice.id,
        actor_id=actor_id,
        action=action,
        payload=payload,
    )
    session.add(event)
    await session.flush()
    return invoice
