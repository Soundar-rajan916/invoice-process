from __future__ import annotations

import asyncio
import hashlib
import uuid
from pathlib import Path
from typing import Any

import httpx
import structlog
import yaml
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import accounting_circuit_breaker
from app.core.config import settings
from app.models.entities import Extraction, Invoice, PushAttempt, ReviewEvent

logger = structlog.get_logger("invoiceflow.push")


class ConfigurableAccountingClient:
    """Configurable accounting software HTTP client reading policy from config/accounting.yaml."""

    def __init__(self, config_path: str = "config/accounting.yaml") -> None:
        p = Path(config_path)
        if p.exists():
            try:
                cfg = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:
                cfg = {}
        else:
            cfg = {}

        self.url = cfg.get("url") or f"{settings.ACCOUNTING_API_URL.rstrip('/')}/api/invoices"
        self.timeout = float(cfg.get("timeout_seconds", 15.0))
        retry = cfg.get("retry_policy", {})
        self.max_attempts = int(retry.get("max_attempts", settings.PUSH_MAX_ATTEMPTS))
        self.backoff_factor = float(retry.get("backoff_factor", 2.0))
        self.initial_delay = float(retry.get("initial_delay_seconds", 1.0))
        self.retryable_codes = set(retry.get("retryable_status_codes", [429, 500, 502, 503, 504]))
        self.custom_headers = cfg.get("custom_headers", {})
        self.error_mapping = cfg.get("error_mapping", {})


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
    - Protected by accounting_circuit_breaker.
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

    # Check SHADOW_MODE (Phase 6)
    if settings.SHADOW_MODE:
        logger.info(
            "SHADOW_MODE active: external push skipped",
            invoice_id=str(invoice.id),
        )
        invoice.status = "APPROVED"
        invoice.is_shadow = True
        invoice.status_reason = "shadow_mode_push_disabled"
        session.add(
            ReviewEvent(
                invoice_id=invoice.id,
                action="shadow_mode_push_disabled",
                payload={"message": "External push skipped because SHADOW_MODE is active"},
            )
        )
        await session.commit()
        return invoice

    # Circuit Breaker Check (R4)
    if not await accounting_circuit_breaker.is_allowed():
        logger.warning(
            "Accounting circuit breaker is OPEN, transitioning to WAITING_PROVIDER",
            invoice_id=str(invoice.id),
        )
        invoice.status = "WAITING_PROVIDER"
        invoice.status_reason = (
            "Downstream accounting service temporarily unavailable (circuit breaker open)"
        )
        session.add(
            ReviewEvent(
                invoice_id=invoice.id,
                action="status_change",
                payload={
                    "from_status": "PUSHING",
                    "to_status": "WAITING_PROVIDER",
                    "reason": "accounting_circuit_breaker_open",
                },
            )
        )
        await session.commit()
        return invoice

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

    # Circuit Breaker Fast-Fail Check
    if not await accounting_circuit_breaker.is_allowed():
        invoice.status = "PUSH_FAILED"
        invoice.status_reason = "Accounting service circuit breaker is OPEN. Fast-failing push."
        session.add(
            ReviewEvent(
                invoice_id=invoice.id,
                action="status_change",
                payload={
                    "from_status": "PUSHING",
                    "to_status": "PUSH_FAILED",
                    "reason": "circuit_breaker_open",
                },
            )
        )
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

    acct_config = ConfigurableAccountingClient()
    headers = {
        "Idempotency-Key": idempotency_key,
        "Authorization": f"Bearer {settings.ACCOUNTING_API_KEY}",
        "Content-Type": "application/json",
        **acct_config.custom_headers,
    }

    url = acct_config.url
    max_attempts = acct_config.max_attempts

    local_client = client or httpx.AsyncClient(timeout=acct_config.timeout)
    should_close_client = client is None

    try:
        delay = acct_config.initial_delay
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
                    await accounting_circuit_breaker.record_success()
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
                    error_detail = (
                        acct_config.error_mapping.get(http_status)
                        or f"HTTP {http_status}: {resp_json}"
                    )
                    invoice.status = "PUSH_FAILED"
                    invoice.status_reason = (
                        f"Accounting API client error: HTTP {http_status} - {error_detail}"
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

                # Server error or 429: record breaker failure and prepare backoff
                await accounting_circuit_breaker.record_failure(f"HTTP {http_status}")

            except Exception as e:
                err_msg = str(e)
                await accounting_circuit_breaker.record_failure(err_msg)
                session.add(
                    PushAttempt(
                        invoice_id=invoice.id,
                        attempt_no=attempt_no,
                        http_status=None,
                        response=None,
                        error=err_msg,
                    )
                )

            # If retries remain and error was retryable, back off exponentially
            if attempt_no < max_attempts:
                logger.warning(
                    "Accounting push attempt failed; retrying with backoff",
                    invoice_id=str(invoice_id),
                    attempt=attempt_no,
                    delay=delay,
                    http_status=http_status,
                    error=err_msg,
                )
                await asyncio.sleep(delay)
                delay *= acct_config.backoff_factor
            else:
                # Retries exhausted
                invoice.status = "PUSH_FAILED"
                invoice.status_reason = f"Accounting push exhausted {max_attempts} attempts. Last error: {err_msg or http_status}"
                session.add(
                    ReviewEvent(
                        invoice_id=invoice.id,
                        action="status_change",
                        payload={
                            "from_status": "PUSHING",
                            "to_status": "PUSH_FAILED",
                            "attempts": max_attempts,
                        },
                    )
                )
                await session.commit()
                return invoice

    finally:
        if should_close_client:
            await local_client.aclose()

    return invoice
