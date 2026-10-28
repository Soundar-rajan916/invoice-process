from __future__ import annotations

import re
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import logger
from app.models.entities import Invoice


def normalize_invoice_number(raw_num: str | None) -> str:
    """Normalizes invoice number: uppercase, strips leading zeros from every digit run,
    and removes all non-alphanumeric chars.
    'INV-0042', 'inv 42', and ' INV/042 ' all become 'INV42'.
    """
    if not raw_num:
        return ""
    cleaned = raw_num.strip().upper()
    # Strip leading zeros from each digit run (e.g. 0042 -> 42)
    stripped_runs = re.sub(r"\d+", lambda m: str(int(m.group(0))), cleaned)
    # Remove all non-alphanumeric chars
    normalized = re.sub(r"[^A-Z0-9]", "", stripped_runs)
    return normalized


def get_financial_year(d: date | None) -> str | None:
    """Computes Indian Financial Year (April 1 to March 31).
    2026-03-31 -> '2025-26'
    2026-04-01 -> '2026-27'
    """
    if not d:
        return None
    if d.month >= 4:
        return f"{d.year}-{(d.year + 1) % 100:02d}"
    else:
        return f"{d.year - 1}-{d.year % 100:02d}"


async def check_duplicates(
    session: AsyncSession,
    invoice_id: uuid.UUID,
    supplier_gstin: str | None,
    normalized_inv_num: str | None,
    financial_year: str | None,
    invoice_date: date | None,
    total: Decimal | None,
) -> tuple[uuid.UUID | None, list[dict[str, Any]]]:
    """Applies Layer 2 (exact business key) and Layer 3 (fuzzy total/date) duplicate detection.
    Returns: (dup_of_id, list_of_issue_dicts)
    """
    issues: list[dict[str, Any]] = []
    dup_of_id: uuid.UUID | None = None

    if not supplier_gstin or not normalized_inv_num or not financial_year:
        return None, []

    # Layer 2: Exact business key match (supplier_gstin, normalized_invoice_number, financial_year)
    stmt = (
        select(Invoice)
        .where(
            Invoice.id != invoice_id,
            Invoice.supplier_gstin == supplier_gstin,
            Invoice.normalized_invoice_number == normalized_inv_num,
            Invoice.financial_year == financial_year,
            Invoice.dup_of_id.is_(None),
            ~Invoice.status.in_(["REJECTED", "REJECTED_DUPLICATE"]),
        )
        .order_by(Invoice.created_at.asc())
    )
    existing_canonical = (await session.execute(stmt)).scalars().first()

    if existing_canonical:
        dup_of_id = existing_canonical.id
        issues.append(
            {
                "code": "duplicate",
                "field": "invoice_number",
                "severity": "error",
                "message": (
                    f"Duplicate invoice detected: matches existing invoice {existing_canonical.id} "
                    f"with key ({supplier_gstin}, {normalized_inv_num}, {financial_year})."
                ),
            }
        )
        logger.info(
            "Layer 2 business key duplicate detected",
            invoice_id=str(invoice_id),
            dup_of_id=str(dup_of_id),
        )
        return dup_of_id, issues

    # Layer 3: Fuzzy match (same supplier GSTIN, same total, same date, but different normalized number)
    if total is not None and invoice_date is not None:
        fuzzy_stmt = select(Invoice).where(
            Invoice.id != invoice_id,
            Invoice.supplier_gstin == supplier_gstin,
            Invoice.dup_of_id.is_(None),
            ~Invoice.status.in_(["REJECTED", "REJECTED_DUPLICATE"]),
        )
        candidates = (await session.execute(fuzzy_stmt)).scalars().all()
        from app.models.entities import Extraction

        for cand in candidates:
            if cand.current_extraction_id:
                ext_cand = await session.get(Extraction, cand.current_extraction_id)
                if ext_cand and ext_cand.data:
                    c_total = ext_cand.data.get("total")
                    c_date = ext_cand.data.get("invoice_date")
                    if (
                        c_total is not None
                        and str(c_total) == str(total)
                        and c_date == invoice_date.isoformat()
                    ):
                        issues.append(
                            {
                                "code": "possible_duplicate",
                                "field": "invoice_number",
                                "severity": "warning",
                                "message": (
                                    f"Possible duplicate: same supplier ({supplier_gstin}), total ({total}), "
                                    f"and date ({invoice_date}) matches invoice {cand.id}."
                                ),
                            }
                        )
                        break

    return None, issues
