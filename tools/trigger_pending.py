"""Trigger processing for all pending invoices (run inside Docker api container)."""
import asyncio
import asyncpg
from app.workers.tasks import process_invoice


async def main() -> None:
    conn = await asyncpg.connect("postgresql://postgres:postgres@postgres:5432/invoiceflow")
    rows = await conn.fetch("SELECT id FROM invoices WHERE status='pending'")
    await conn.close()
    print(f"Found {len(rows)} pending invoices")
    for r in rows:
        process_invoice.delay(str(r["id"]))
        print(f"  Queued {r['id']}")


asyncio.run(main())

