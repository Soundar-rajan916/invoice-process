from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.core.telemetry import (
    extract_trace_context,
    inject_trace_headers,
    metrics_registry,
    trace_span,
)
from app.models.entities import Extraction, Invoice, SourceFile, User
from app.services.push import push_invoice


# ---------------------------------------------------------------------------
# 1. Prometheus Metrics Endpoint Test (6.2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prometheus_metrics_endpoint(client: AsyncClient, db_session: AsyncSession):
    # Record some synthetic activity
    metrics_registry.record_429()
    metrics_registry.record_llm_usage(
        model="llama-3.3-70b",
        prompt_tokens=500,
        completion_tokens=150,
        latency_seconds=1.2,
    )
    metrics_registry.record_push_result("success")
    metrics_registry.record_reviewer_edit()
    metrics_registry.record_watchdog_requeue()

    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]

    body = resp.text
    # Verify all required Prometheus metric families are present
    assert "invoiceflow_invoices_by_status" in body
    assert "invoiceflow_circuit_breaker_state" in body
    assert "invoiceflow_review_claims_active" in body
    assert "invoiceflow_reconciliation_findings_total" in body
    assert "invoiceflow_queue_depth" in body
    assert "invoiceflow_llm_tokens_total" in body
    assert "invoiceflow_llm_cost_usd_total" in body
    assert "invoiceflow_rate_limit_429_total" in body
    assert "invoiceflow_push_attempts_total" in body
    assert "invoiceflow_reviewer_edits_total" in body
    assert "invoiceflow_watchdog_requeues_total" in body


# ---------------------------------------------------------------------------
# 2. OpenTelemetry Tracing Test (6.2)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_opentelemetry_tracing_propagation():
    test_inv_id = str(uuid.uuid4())
    async with trace_span("pipeline.process", {"invoice_id": test_inv_id}) as span:
        assert span is not None

    headers: dict[str, str] = {}
    inject_trace_headers(headers)
    assert isinstance(headers, dict)

    ctx = extract_trace_context(headers)
    assert ctx is not None


# ---------------------------------------------------------------------------
# 3. Shadow Mode Ingestion & Comparison Report (6.5)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_shadow_mode_push_disabled(db_session: AsyncSession):
    # Setup test file
    source = SourceFile(
        sha256=uuid.uuid4().hex,
        original_filename="shadow_inv.pdf",
        content_type="application/pdf",
        size_bytes=1000,
        storage_key=f"originals/{uuid.uuid4().hex}.pdf",
        source="upload",
    )
    db_session.add(source)
    await db_session.flush()

    user = User(
        email=f"approver_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("Pass123!"),
        role="reviewer",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    invoice = Invoice(
        source_file_id=source.id,
        status="APPROVED",
        approved_by=user.id,
        approved_at=datetime.now(UTC),
        supplier_gstin="33AAAAA0000A1Z5",
        normalized_invoice_number="SHADOW100",
        financial_year="2026-27",
    )
    db_session.add(invoice)
    await db_session.flush()

    ext = Extraction(
        invoice_id=invoice.id,
        kind="model",
        version=1,
        model_id="mock-model",
        prompt_version="v1.0",
        raw_response={},
        data={"total": 2500.0, "invoice_number": "INV-SHADOW-100", "invoice_date": "2026-04-10"},
    )
    db_session.add(ext)
    await db_session.flush()

    invoice.approved_extraction_id = ext.id
    await db_session.commit()

    # 1. With SHADOW_MODE=True, push is disabled and status remains APPROVED
    with patch.object(settings, "SHADOW_MODE", True):
        res = await push_invoice(db_session, invoice.id)
        assert res is not None
        assert res.status == "APPROVED"
        assert res.is_shadow is True
        assert res.status_reason == "shadow_mode_push_disabled"


@pytest.mark.asyncio
async def test_shadow_import_and_report(client: AsyncClient, db_session: AsyncSession):
    admin = User(
        email=f"shadow_admin_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("AdminPass123!"),
        role="admin",
        is_active=True,
    )
    db_session.add(admin)
    await db_session.commit()

    token = create_access_token(admin.id, "admin")
    headers = {
        "Authorization": f"Bearer {token}",
        "X-Requested-With": "XMLHttpRequest",
    }

    # CSV with 2 records
    csv_content = (
        "invoice_number,supplier_gstin,invoice_date,total\n"
        "INV-2026-001,33AAAAA0000A1Z5,2026-04-10,2360.00\n"
        "INV-2026-002,27ABCDE1234F1Z5,2026-04-11,5400.00\n"
    )

    files = {"file": ("ground_truth.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    resp = await client.post("/api/v1/admin/shadow/import", headers=headers, files=files)
    assert resp.status_code == 200
    batch_id = resp.json()["batch_id"]
    assert resp.json()["total_imported"] == 2

    # Query shadow report
    report_resp = await client.get(f"/api/v1/admin/shadow/report?batch_id={batch_id}", headers=headers)
    assert report_resp.status_code == 200
    data = report_resp.json()
    assert data["total_shadow_records"] == 2
    assert "overall_agreement_pct" in data
    assert "mismatches_by_supplier" in data
