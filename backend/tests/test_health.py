from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_healthz_endpoint(client: AsyncClient):
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_readyz_endpoint_shape(client: AsyncClient):
    resp = await client.get("/readyz")
    assert resp.status_code in (200, 503)
    data = resp.json()
    assert "status" in data
    assert "dependencies" in data
    assert "postgres" in data["dependencies"]
    assert "redis" in data["dependencies"]
    assert "storage" in data["dependencies"]
