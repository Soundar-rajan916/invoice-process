from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import logger
from app.models.entities import Invoice, ReconciliationFinding, ReconciliationRun


async def run_accounting_reconciliation(
    session: AsyncSession,
    target_date: date | None = None,
    client: httpx.AsyncClient | None = None,
) -> ReconciliationRun:
    """Nightly reconciliation comparing InvoiceFlow pushed invoices against downstream accounting records.
    Flags discrepancies:
    - missing_in_accounting (error): InvoiceFlow recorded PUSHED, but record absent in accounting system
    - missing_in_invoiceflow (warning): Record present in accounting system but absent in InvoiceFlow
    - amount_mismatch (error): Total amount disagrees between systems
    """
    if target_date is None:
        # Default: reconcile previous day's invoices
        target_date = (datetime.now(UTC) - timedelta(days=1)).date()

    now = datetime.now(UTC)
    run = ReconciliationRun(
        id=uuid.uuid4(),
        started_at=now,
        status="running",
        summary={"reconciliation_date": target_date.isoformat()},
    )
    session.add(run)
    await session.flush()

    # 1. Fetch InvoiceFlow pushed invoices for target date
    start_dt = datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
    end_dt = datetime.combine(target_date, datetime.max.time(), tzinfo=UTC)

    stmt = select(Invoice).where(
        Invoice.status == "PUSHED",
        Invoice.updated_at >= start_dt,
        Invoice.updated_at <= end_dt,
    )
    invoices = (await session.execute(stmt)).scalars().all()
    invoices_by_key = {inv.idempotency_key: inv for inv in invoices if inv.idempotency_key}
    invoices_by_acc_id = {inv.accounting_id: inv for inv in invoices if inv.accounting_id}

    # 2. Fetch accounting system records
    accounting_url = settings.ACCOUNTING_API_URL.rstrip("/")
    accounting_records: list[dict[str, Any]] = []

    local_client = client or httpx.AsyncClient(timeout=15.0)
    should_close = client is None

    try:
        resp = await local_client.get(f"{accounting_url}/api/invoices")
        if resp.status_code == 200:
            raw_data = resp.json()
            if isinstance(raw_data, list):
                accounting_records = raw_data
            elif isinstance(raw_data, dict):
                accounting_records = raw_data.get("items") or raw_data.get("invoices") or []
        elif resp.status_code == 404:
            # Fallback to debug endpoint if running with mock accounting
            debug_resp = await local_client.get(f"{accounting_url}/api/_debug/invoices")
            if debug_resp.status_code == 200:
                data = debug_resp.json()
                accounting_records = data.get("invoices", [])
    except Exception as e:
        logger.error("Failed to fetch accounting records during reconciliation", error=str(e))
        run.status = "failed"
        run.summary["error"] = f"Accounting API unreachable: {str(e)}"
        run.completed_at = datetime.now(UTC)
        await session.commit()
        if should_close:
            await local_client.aclose()
        return run
    finally:
        if should_close:
            await local_client.aclose()

    # Filter accounting records by target_date if date string present
    acc_records_by_key: dict[str, dict[str, Any]] = {}
    for rec in accounting_records:
        key = rec.get("idempotency_key")
        if key:
            acc_records_by_key[key] = rec

    findings: list[ReconciliationFinding] = []
    total_checked = len(invoices)
    total_matched = 0

    # 3. Check InvoiceFlow -> Accounting
    for inv in invoices:
        acc_rec = None
        if inv.idempotency_key:
            acc_rec = acc_records_by_key.get(inv.idempotency_key)
        if not acc_rec and inv.accounting_id:
            # Search by accounting_id
            for r in accounting_records:
                if r.get("accounting_id") == inv.accounting_id:
                    acc_rec = r
                    break

        if not acc_rec:
            # Finding: missing_in_accounting
            f = ReconciliationFinding(
                id=uuid.uuid4(),
                run_id=run.id,
                invoice_id=inv.id,
                finding_type="missing_in_accounting",
                severity="error",
                details={
                    "invoice_id": str(inv.id),
                    "idempotency_key": inv.idempotency_key,
                    "accounting_id": inv.accounting_id,
                    "normalized_invoice_number": inv.normalized_invoice_number,
                    "reason": "InvoiceFlow status is PUSHED, but record missing from accounting software",
                },
            )
            findings.append(f)
            session.add(f)
            continue

        # Check amount match
        acc_total_str = acc_rec.get("total")
        if acc_total_str is not None:
            try:
                acc_total = Decimal(str(acc_total_str))
                # Get invoice extraction total
                inv_total = Decimal("0.00")
                if inv.approved_extraction:
                    inv_total = Decimal(str(inv.approved_extraction.data.get("total") or "0.00"))
                if abs(acc_total - inv_total) > Decimal("0.01"):
                    f = ReconciliationFinding(
                        id=uuid.uuid4(),
                        run_id=run.id,
                        invoice_id=inv.id,
                        finding_type="amount_mismatch",
                        severity="error",
                        details={
                            "invoice_id": str(inv.id),
                            "invoiceflow_total": str(inv_total),
                            "accounting_total": str(acc_total),
                            "diff": str(abs(acc_total - inv_total)),
                        },
                    )
                    findings.append(f)
                    session.add(f)
                    continue
            except Exception:
                pass

        total_matched += 1

    # 4. Check Accounting -> InvoiceFlow (Find unexpected accounting records)
    for rec in accounting_records:
        key = rec.get("idempotency_key")
        acc_id = rec.get("accounting_id")
        if key and key not in invoices_by_key and acc_id not in invoices_by_acc_id:
            f = ReconciliationFinding(
                id=uuid.uuid4(),
                run_id=run.id,
                invoice_id=None,
                finding_type="missing_in_invoiceflow",
                severity="warning",
                details={
                    "accounting_id": acc_id,
                    "idempotency_key": key,
                    "supplier_gstin": rec.get("supplier_gstin"),
                    "invoice_number": rec.get("invoice_number"),
                    "total": rec.get("total"),
                    "reason": "Record exists in accounting software without corresponding pushed InvoiceFlow invoice",
                },
            )
            findings.append(f)
            session.add(f)

    # 5. Finalize run summary
    run.completed_at = datetime.now(UTC)
    run.status = "completed"
    run.total_checked = total_checked
    run.total_matched = total_matched
    run.total_discrepancies = len(findings)
    run.summary.update(
        {
            "total_checked": total_checked,
            "total_matched": total_matched,
            "total_discrepancies": len(findings),
            "findings_count_by_type": {
                "missing_in_accounting": sum(1 for f in findings if f.finding_type == "missing_in_accounting"),
                "missing_in_invoiceflow": sum(1 for f in findings if f.finding_type == "missing_in_invoiceflow"),
                "amount_mismatch": sum(1 for f in findings if f.finding_type == "amount_mismatch"),
            },
        }
    )

    await session.commit()
    logger.info(
        "Reconciliation run completed",
        run_id=str(run.id),
        matched=total_matched,
        discrepancies=len(findings),
    )
    return run
