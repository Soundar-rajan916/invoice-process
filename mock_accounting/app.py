from __future__ import annotations

import asyncio
import os
import random
import time
import uuid
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Response, status
from pydantic import BaseModel

app = FastAPI(title="Mock Accounting API", version="0.1.0")

# In-memory storage for accounting records and idempotency map
INVOICES_DB: dict[str, dict[str, Any]] = {}
IDEMPOTENCY_MAP: dict[str, dict[str, Any]] = {}

FAULT_RATE = float(os.getenv("FAULT_RATE", "0.0"))
LATENCY_MS = int(os.getenv("LATENCY_MS", "0"))


class InvoicePayload(BaseModel):
    supplier_gstin: str
    invoice_number: str
    invoice_date: str
    supplier_name: str
    taxable_value: str | None = None
    cgst: str | None = None
    sgst: str | None = None
    igst: str | None = None
    total: str
    line_items: list[dict[str, Any]] = []


@app.post("/api/invoices", status_code=status.HTTP_201_CREATED)
async def create_invoice(
    payload: InvoicePayload,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
) -> dict[str, Any]:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is strictly required",
        )

    # Configurable latency
    if LATENCY_MS > 0:
        await asyncio.sleep(LATENCY_MS / 1000.0)

    # Configurable fault simulation for retry testing (500 or 429)
    if FAULT_RATE > 0.0 and random.random() < FAULT_RATE:
        error_code = random.choice(
            [status.HTTP_500_INTERNAL_SERVER_ERROR, status.HTTP_429_TOO_MANY_REQUESTS]
        )
        if error_code == status.HTTP_429_TOO_MANY_REQUESTS:
            response.headers["Retry-After"] = "1"
        raise HTTPException(status_code=error_code, detail="Simulated upstream accounting fault")

    # Idempotent response replay
    if idempotency_key in IDEMPOTENCY_MAP:
        response.status_code = status.HTTP_200_OK
        return IDEMPOTENCY_MAP[idempotency_key]

    accounting_id = f"ACC-{uuid.uuid4().hex[:12].upper()}"
    record = {
        "accounting_id": accounting_id,
        "idempotency_key": idempotency_key,
        "supplier_gstin": payload.supplier_gstin,
        "invoice_number": payload.invoice_number,
        "invoice_date": payload.invoice_date,
        "supplier_name": payload.supplier_name,
        "total": payload.total,
        "line_items": payload.line_items,
        "created_at": time.time(),
    }

    INVOICES_DB[accounting_id] = record
    IDEMPOTENCY_MAP[idempotency_key] = record
    return record


@app.get("/api/invoices")
async def list_invoices() -> list[dict[str, Any]]:
    return list(INVOICES_DB.values())


@app.get("/api/invoices/{accounting_id}")
async def get_invoice(accounting_id: str) -> dict[str, Any]:
    if accounting_id not in INVOICES_DB:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Accounting invoice '{accounting_id}' not found",
        )
    return INVOICES_DB[accounting_id]


@app.get("/api/_debug/invoices")
async def debug_invoices() -> dict[str, Any]:
    """Test debugging endpoint to inspect created invoices."""
    return {
        "count": len(INVOICES_DB),
        "invoices": list(INVOICES_DB.values()),
        "idempotency_keys": list(IDEMPOTENCY_MAP.keys()),
    }


@app.post("/api/_debug/reset")
async def debug_reset() -> dict[str, str]:
    INVOICES_DB.clear()
    IDEMPOTENCY_MAP.clear()
    return {"status": "reset"}
