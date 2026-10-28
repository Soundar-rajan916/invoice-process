from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import Any

import httpx
import structlog
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.entities import Extraction, Invoice, PushAttempt, ReviewEvent

logger = structlog.get_logger("invoiceflow.push")


def compute_idempotency_key(
    supplier_gstin: str,
    normalized_inv_num: str,
    financial_year: str,
    invoice_id: uuid.UUID | None = None,
    dup_overridden: bool = False,
) -> str:
    raw_key = f"{supplier_gstin}|{normalized_inv_num}|{financial_year}"
    base_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    if dup_overridden and invoice_id:
        return f"{base_hash}|{invoice_id}"
    return base_hash


async def push_invoice(
    session: AsyncSession,
    invoice_id: uuid.UUID,
    client: httpx.AsyncClient | None = None,
) -> Invoice | None:
    """R2 & R3: Idempotently pushes an approved invoice to the accounting software API.
    - Uses approved_extraction_id (NEVER current_extraction_id).
    - Idempotency-Key guarantees deduplication at accounting API.
    - Atomic compare-and-set state transitions.
    """
    # 1. Compare-and-Set: APPROVED -> PUSHING
    stmt = (
        update(Invoice)
        .where(Invoice.id == invoice_id, Invoice.status == "APPROVED")
        .values(status="PUSHING")
        .execution_options(synchronize_session=False)
    )
    res = await session.execute(stmt)
    if getattr(res, "rowcount", 0) == 0:
        logger.warning(
            "Invoice is not in APPROVED state; skipping push",
            invoice_id=str(invoice_id),
        )
        return None

    # Audit transition
    session.add(
        ReviewEvent(
            invoice_id=invoice_id,
            action="status_change",
            payload={"from_status": "APPROVED", "to_status": "PUSHING"},
        )
    )
    await session.commit()

    invoice = await session.get(Invoice, invoice_id, populate_existing=True)
    if not invoice:
        return None

    # R2 Guarantee: Must use approved_extraction_id
    if not invoice.approved_extraction_id:
        invoice.status = "PUSH_FAILED"
        invoice.status_reason = "No approved extraction ID found on invoice"
        await session.commit()
        return invoice

    approved_ext = await session.get(Extraction, invoice.approved_extraction_id)
    if not approved_ext:
        invoice.status = "PUSH_FAILED"
        invoice.status_reason = f"Approved extraction {invoice.approved_extraction_id} not found"
        await session.commit()
        return invoice

    # Compute Idempotency-Key
    idempotency_key = compute_idempotency_key(
        supplier_gstin=invoice.supplier_gstin or "",
        normalized_inv_num=invoice.normalized_invoice_number or "",
        financial_year=invoice.financial_year or "",
        invoice_id=invoice.id,
        dup_overridden=invoice.dup_overridden,
    )
    invoice.idempotency_key = idempotency_key

    # Build accounting payload from approved extraction data
    payload = approved_ext.data

    headers = {
        "Idempotency-Key": idempotency_key,
        "Authorization": f"Bearer {settings.ACCOUNTING_API_KEY}",
        "Content-Type": "application/json",
    }

    url = f"{settings.ACCOUNTING_API_URL.rstrip('/')}/api/invoices"
    max_attempts = settings.PUSH_MAX_ATTEMPTS

    local_client = client or httpx.AsyncClient(timeout=10.0)
    should_close_client = client is None

    try:
        for attempt_no in range(1, max_attempts + 1):
            http_status = None
            resp_json: dict[str, Any] | None = None
            err_msg: str | None = None

            try:
                resp = await local_client.post(url, json=payload, headers=headers)
                http_status = resp.status_code
                try:
                    resp_json = resp.json()
                except Exception:
                    resp_json = {"text": resp.text}

                # Record attempt
                session.add(
                    PushAttempt(
                        invoice_id=invoice.id,
                        attempt_no=attempt_no,
                        http_status=http_status,
                        response=resp_json,
                        error=None,
                    )
                )

                if http_status in (200, 201):
                    # Push Succeeded
                    accounting_id = resp_json.get("accounting_id") if resp_json else None
                    invoice.status = "PUSHED"
                    invoice.accounting_id = accounting_id
                    invoice.status_reason = None
                    session.add(
                        ReviewEvent(
                            invoice_id=invoice.id,
                            action="status_change",
                            payload={
                                "from_status": "PUSHING",
                                "to_status": "PUSHED",
                                "accounting_id": accounting_id,
                                "attempts": attempt_no,
                            },
                        )
                    )
                    await session.commit()
                    return invoice

                # Non-retryable client error (4xx other than 429)
                if 400 <= http_status < 500 and http_status != 429:
                    invoice.status = "PUSH_FAILED"
                    invoice.status_reason = (
                        f"Accounting API client error HTTP {http_status}: {resp_json}"
                    )
                    session.add(
                        ReviewEvent(
                            invoice_id=invoice.id,
                            action="status_change",
                            payload={"from_status": "PUSHING", "to_status": "PUSH_FAILED"},
                        )
                    )
                    await session.commit()
                    return invoice

            except Exception as e:
                err_msg = str(e)
                session.add(
                    PushAttempt(
                        invoice_id=invoice.id,
                        attempt_no=attempt_no,
                        http_status=None,
                        response=None,
                        error=err_msg,
                    )
                )

            # Retryable failure (429, 5xx, or network exception)
            await session.commit()
            if attempt_no < max_attempts:
                # Exponential backoff: 0.1s, 0.2s, 0.4s... (short in dev/test)
                backoff = min(0.1 * (2 ** (attempt_no - 1)), 2.0)
                await asyncio.sleep(backoff)

        # Max attempts exhausted
        invoice.status = "PUSH_FAILED"
        invoice.status_reason = f"Push failed after {max_attempts} attempts"
        session.add(
            ReviewEvent(
                invoice_id=invoice.id,
                action="status_change",
                payload={"from_status": "PUSHING", "to_status": "PUSH_FAILED"},
            )
        )
        await session.commit()
        return invoice

    finally:
        if should_close_client:
            await local_client.aclose()
