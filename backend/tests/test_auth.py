"""
Tests for authentication endpoints.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert "version" in data


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    resp = await client.post("/api/v1/login", json={"username": "testadmin", "password": "testpass"})
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "testadmin"
    assert data["user"]["role"] == "admin"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient):
    resp = await client.post("/api/v1/login", json={"username": "testadmin", "password": "wrongpass"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_unknown_user(client: AsyncClient):
    resp = await client.post("/api/v1/login", json={"username": "ghost", "password": "pass"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_login_empty_payload(client: AsyncClient):
    resp = await client.post("/api/v1/login", json={})
    assert resp.status_code == 422  # validation error


@pytest.mark.asyncio
async def test_me_authenticated(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/me", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["username"] == "testadmin"


@pytest.mark.asyncio
async def test_me_unauthenticated(client: AsyncClient):
    resp = await client.get("/api/v1/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_invalid_token(client: AsyncClient):
    resp = await client.get("/api/v1/me", headers={"Authorization": "Bearer invalidtoken"})
    assert resp.status_code == 401
