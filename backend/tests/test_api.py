"""Basic API smoke tests for the CityInspect backend."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    resp = await client.post("/api/v1/login", json={
        "username": "nonexistent",
        "password": "wrongpassword",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/incident/upload")
    assert resp.status_code in (401, 403, 422)
