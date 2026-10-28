from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from app.core.database import async_session_maker
from app.ingestors.base import IncomingFile
from app.ingestors.upload import UploadIngestor
from app.services.pipeline import process_invoice_pipeline


async def seed_invoices(dir_path: str, limit: int | None = None) -> None:
    pdf_dir = Path(dir_path)
    if not pdf_dir.exists():
        print(f"Directory {pdf_dir} does not exist.")
        return

    files = list(pdf_dir.glob("*.pdf"))
    if limit:
        files = files[:limit]

    print(f"Seeding {len(files)} invoices from {pdf_dir}...")

    async with async_session_maker() as session:
        ingestor = UploadIngestor(session)
        for idx, file_path in enumerate(files, start=1):
            content = file_path.read_bytes()
            inc = IncomingFile(
                filename=file_path.name,
                content=content,
                content_type="application/pdf",
            )
            result = await ingestor.ingest(inc)
            if not result.is_duplicate:
                print(
                    f"[{idx}/{len(files)}] Ingested {file_path.name} -> Invoice {result.invoice_id}"
                )
                # Run pipeline directly
                await process_invoice_pipeline(session, result.invoice_id)
            else:
                print(
                    f"[{idx}/{len(files)}] Skipped duplicate file {file_path.name} -> Existing {result.invoice_id}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed invoices into database")
    parser.add_argument("--dir", type=str, default="data/synthetic/pdfs", help="Directory of PDFs")
    parser.add_argument("--limit", type=int, default=20, help="Number of files to ingest")
    args = parser.parse_args()

    asyncio.run(seed_invoices(args.dir, args.limit))


if __name__ == "__main__":
    main()
