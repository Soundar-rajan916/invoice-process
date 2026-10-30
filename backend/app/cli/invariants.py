from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.entities import Invoice


async def check_invariants(session: AsyncSession) -> dict[str, Any]:
    """Runs read-only verification queries against database to ensure operational invariants (R2, R3, R4)."""
    results: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "passed": True,
        "checks": {},
    }

    # Invariant 1 (R2): No unapproved invoice was ever pushed to accounting
    stmt_unapproved = select(Invoice.id, Invoice.status).where(
        Invoice.status.in_(["PUSHING", "PUSHED"]),
        or_(Invoice.approved_by.is_(None), Invoice.approved_extraction_id.is_(None)),
    )
    unapproved_pushed = (await session.execute(stmt_unapproved)).all()
    inv1_passed = len(unapproved_pushed) == 0
    results["checks"]["r2_no_unapproved_pushes"] = {
        "passed": inv1_passed,
        "violations_count": len(unapproved_pushed),
        "violations": [str(r[0]) for r in unapproved_pushed],
        "description": "Every pushed or pushing invoice must have approved_by and approved_extraction_id (R2)",
    }
    if not inv1_passed:
        results["passed"] = False

    # Invariant 2 (R3): Every pushed invoice has an idempotency key and accounting ID
    stmt_missing_ids = select(Invoice.id).where(
        Invoice.status == "PUSHED",
        or_(Invoice.idempotency_key.is_(None), Invoice.accounting_id.is_(None)),
    )
    missing_ids = (await session.execute(stmt_missing_ids)).scalars().all()
    inv2_passed = len(missing_ids) == 0
    results["checks"]["r3_pushed_idempotency_and_accounting_id"] = {
        "passed": inv2_passed,
        "violations_count": len(missing_ids),
        "violations": [str(i) for i in missing_ids],
        "description": "Every PUSHED invoice must possess a deterministic idempotency key and accounting ID",
    }
    if not inv2_passed:
        results["passed"] = False

    # Invariant 3: Unbroken row version and non-negative counts
    stmt_bad_version = select(Invoice.id, Invoice.row_version).where(Invoice.row_version < 1)
    bad_versions = (await session.execute(stmt_bad_version)).all()
    inv3_passed = len(bad_versions) == 0
    results["checks"]["data_integrity_row_versions"] = {
        "passed": inv3_passed,
        "violations_count": len(bad_versions),
        "violations": [str(r[0]) for r in bad_versions],
        "description": "All invoice row_versions must be positive monotonic integers",
    }
    if not inv3_passed:
        results["passed"] = False

    # Invariant 4 (R4 SLA): No invoice stuck in intermediate state longer than SLA
    now = datetime.now(UTC)
    proc_sla = now - timedelta(minutes=15)
    push_sla = now - timedelta(minutes=10)
    stmt_stuck = select(Invoice.id, Invoice.status, Invoice.updated_at).where(
        or_(
            (Invoice.status == "PROCESSING") & (Invoice.updated_at < proc_sla),
            (Invoice.status == "PUSHING") & (Invoice.updated_at < push_sla),
        )
    )
    stuck_invoices = (await session.execute(stmt_stuck)).all()
    inv4_passed = len(stuck_invoices) == 0
    results["checks"]["r4_sla_intermediate_states"] = {
        "passed": inv4_passed,
        "violations_count": len(stuck_invoices),
        "violations": [
            {"id": str(r[0]), "status": r[1], "updated_at": r[2].isoformat()}
            for r in stuck_invoices
        ],
        "description": "No invoice stuck in PROCESSING (>15m) or PUSHING (>10m)",
    }
    if not inv4_passed:
        results["passed"] = False

    return results


def print_report(results: dict[str, Any]) -> None:
    print("=" * 60)
    print("INVOICEFLOW OPERATIONAL INVARIANTS REPORT")
    print(f"Timestamp: {results['timestamp']}")
    print("=" * 60)

    for name, check in results["checks"].items():
        status_str = "[PASS]" if check["passed"] else "[FAIL]"
        print(f"{status_str} {name}: {check['description']}")
        if not check["passed"]:
            print(f"       Violations ({check['violations_count']}): {check['violations'][:5]}")

    print("-" * 60)
    if results["passed"]:
        print("ALL INVARIANTS SATISFIED. SYSTEM IS CONSISTENT.")
    else:
        print("CRITICAL: ONE OR MORE INVARIANTS VIOLATED.")
    print("=" * 60)


async def main_async(args: argparse.Namespace) -> int:
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            results = await check_invariants(session)

        if args.json:
            print(json.dumps(results, indent=2))
        else:
            print_report(results)

        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=2)

        return 0 if results["passed"] else 1
    finally:
        await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="InvoiceFlow Operational Invariants Verification")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    parser.add_argument("--out", type=str, help="Path to write JSON results")
    args = parser.parse_args()

    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
