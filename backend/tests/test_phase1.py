from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingestors.base import IncomingFile
from app.ingestors.upload import UploadIngestor
from app.models.entities import Extraction, ReviewEvent
from app.services.pipeline import process_invoice_pipeline


@pytest.mark.asyncio
async def test_reupload_same_bytes_skipped(db_session: AsyncSession):
    ingestor = UploadIngestor(db_session)
    pdf_bytes = b"%PDF-1.4 test invoice content here with sufficient bytes for testing"

    file1 = IncomingFile(filename="inv_orig.pdf", content=pdf_bytes, content_type="application/pdf")
    res1 = await ingestor.ingest(file1)
    assert not res1.is_duplicate

    # Re-upload same exact bytes
    file2 = IncomingFile(filename="inv_copy.pdf", content=pdf_bytes, content_type="application/pdf")
    res2 = await ingestor.ingest(file2)
    assert res2.is_duplicate
    assert res2.invoice_id == res1.invoice_id

    # Check duplicate_file_skipped audit event
    events = (
        (
            await db_session.execute(
                select(ReviewEvent).where(
                    ReviewEvent.invoice_id == res1.invoice_id,
                    ReviewEvent.action == "duplicate_file_skipped",
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(events) == 1
    assert events[0].payload["sha256"] == res1.sha256


@pytest.mark.asyncio
async def test_blurry_fixture_resend_requested(db_session: AsyncSession):
    # Generate an artificial severely blurred image fixture using OpenCV (R1)
    img = np.ones((600, 600, 3), dtype=np.uint8) * 255
    cv2.putText(img, "Tax Invoice", (50, 100), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    # Apply heavy Gaussian blur to push variance of Laplacian way below 50.0
    blurred = cv2.GaussianBlur(img, (55, 55), 0)

    _, buf = cv2.imencode(".jpg", blurred)
    blurred_bytes = buf.tobytes()

    ingestor = UploadIngestor(db_session)
    file_input = IncomingFile(
        filename="blurry.jpg", content=blurred_bytes, content_type="image/jpeg"
    )
    ingest_res = await ingestor.ingest(file_input)

    # Process through pipeline
    inv = await process_invoice_pipeline(db_session, ingest_res.invoice_id)
    assert inv is not None
    assert inv.status == "RESEND_REQUESTED"
    assert "too blurry" in (inv.status_reason or "")


@pytest.mark.asyncio
async def test_idempotent_task_double_delivery(db_session: AsyncSession):
    pdf_path = Path("data/synthetic/pdfs/INV_0001.pdf")
    if not pdf_path.exists():
        pytest.skip("Synthetic data not generated yet")

    pdf_bytes = pdf_path.read_bytes()
    ingestor = UploadIngestor(db_session)
    res = await ingestor.ingest(
        IncomingFile(filename="INV_0001.pdf", content=pdf_bytes, content_type="application/pdf")
    )

    # First delivery
    inv1 = await process_invoice_pipeline(db_session, res.invoice_id)
    assert inv1 is not None
    assert inv1.status == "NEEDS_REVIEW"

    # Second delivery (duplicate delivery in Celery)
    inv2 = await process_invoice_pipeline(db_session, res.invoice_id)
    # Second delivery must return None (skipped compare-and-set) and not double-process
    assert inv2 is None


@pytest.mark.asyncio
async def test_multipage_pdf_page_count(db_session: AsyncSession):
    # Find a multi-page PDF from synthetic data
    manifest_path = Path("data/synthetic/manifest.jsonl")
    if not manifest_path.exists():
        pytest.skip("Synthetic manifest not found")

    multipage_file = None
    import json

    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("pages", 1) > 1:
                multipage_file = rec["file"]
                expected_pages = rec["pages"]
                break

    if not multipage_file:
        pytest.skip("No multipage invoices in synthetic data")

    pdf_path = Path("data/synthetic/pdfs") / multipage_file
    pdf_bytes = pdf_path.read_bytes()

    ingestor = UploadIngestor(db_session)
    res = await ingestor.ingest(
        IncomingFile(filename=multipage_file, content=pdf_bytes, content_type="application/pdf")
    )

    inv = await process_invoice_pipeline(db_session, res.invoice_id)
    assert inv is not None
    assert inv.page_count == expected_pages


@pytest.mark.asyncio
async def test_mock_extractor_dataset_accuracy(db_session: AsyncSession):
    """Uploads 20 synthetic invoices and verifies they all reach NEEDS_REVIEW
    with extractions equal to ground truth.
    """
    manifest_path = Path("data/synthetic/manifest.jsonl")
    if not manifest_path.exists():
        pytest.skip("Synthetic manifest not found")

    import json

    records = []
    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
            if len(records) >= 20:
                break

    assert len(records) >= 20

    ingestor = UploadIngestor(db_session)
    for rec in records:
        pdf_path = Path("data/synthetic/pdfs") / rec["file"]
        if not pdf_path.exists():
            continue

        res = await ingestor.ingest(
            IncomingFile(
                filename=rec["file"], content=pdf_path.read_bytes(), content_type="application/pdf"
            )
        )
        inv = await process_invoice_pipeline(db_session, res.invoice_id)
        assert inv is not None
        assert inv.status == "NEEDS_REVIEW"

        # Check extraction equals ground truth
        ext = await db_session.get(Extraction, inv.current_extraction_id)
        assert ext is not None
        assert ext.data["invoice_number"] == rec["invoice_number"]
        assert ext.data["supplier_gstin"] == rec["supplier_gstin"]
        assert len(ext.data["line_items"]) == len(rec["line_items"])
