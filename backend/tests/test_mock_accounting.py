from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_mock_accounting_requires_idempotency_key(mock_accounting_client: AsyncClient):
    payload = {
        "supplier_gstin": "33AAAAA0000A1Z5",
        "invoice_number": "INV-001",
        "invoice_date": "2026-04-01",
        "supplier_name": "Test Supplier",
        "total": "1200.00",
        "line_items": [],
    }
    resp = await mock_accounting_client.post("/api/invoices", json=payload)
    assert resp.status_code == 400
    assert "Idempotency-Key header is strictly required" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_mock_accounting_creates_and_replays_idempotently(
    mock_accounting_client: AsyncClient,
):
    payload = {
        "supplier_gstin": "33AAAAA0000A1Z5",
        "invoice_number": "INV-002",
        "invoice_date": "2026-04-01",
        "supplier_name": "Test Supplier",
        "total": "2500.00",
        "line_items": [{"description": "Item 1", "amount": "2500.00"}],
    }
    headers = {"Idempotency-Key": "test-key-unique-12345"}

    # 1. First push: 201 Created
    resp1 = await mock_accounting_client.post("/api/invoices", json=payload, headers=headers)
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert "accounting_id" in data1
    accounting_id = data1["accounting_id"]
    assert data1["idempotency_key"] == "test-key-unique-12345"

    # 2. Replayed push: 200 OK with identical payload
    resp2 = await mock_accounting_client.post("/api/invoices", json=payload, headers=headers)
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["accounting_id"] == accounting_id

    # 3. GET /api/invoices/{accounting_id}
    resp3 = await mock_accounting_client.get(f"/api/invoices/{accounting_id}")
    assert resp3.status_code == 200
    assert resp3.json()["total"] == "2500.00"

    # 4. Debug endpoint
    resp_debug = await mock_accounting_client.get("/api/_debug/invoices")
    assert resp_debug.status_code == 200
    assert resp_debug.json()["count"] >= 1
