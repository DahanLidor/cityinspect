"""
Tests for ticket CRUD and pagination.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ticket


async def _create_ticket(db: AsyncSession, **kwargs) -> Ticket:
    defaults = dict(defect_type="pothole", severity="medium", lat=32.0853, lng=34.7818, address="Test St")
    defaults.update(kwargs)
    t = Ticket(**defaults)
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return t


@pytest.mark.asyncio
async def test_list_tickets_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/tickets", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data


@pytest.mark.asyncio
async def test_list_tickets_pagination(client: AsyncClient, auth_headers: dict, db: AsyncSession):
    for i in range(5):
        await _create_ticket(db, address=f"Street {i}")

    resp = await client.get("/api/v1/tickets?page=1&page_size=3", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) <= 3
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_list_tickets_status_filter(client: AsyncClient, auth_headers: dict, db: AsyncSession):
    await _create_ticket(db, status="new")
    await _create_ticket(db, status="resolved")

    resp = await client.get("/api/v1/tickets?status=new", headers=auth_headers)
    assert resp.status_code == 200
    items = resp.json()["items"]
    for item in items:
        assert item["status"] == "new"


@pytest.mark.asyncio
async def test_get_ticket(client: AsyncClient, auth_headers: dict, db: AsyncSession):
    ticket = await _create_ticket(db)
    resp = await client.get(f"/api/v1/tickets/{ticket.id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == ticket.id


@pytest.mark.asyncio
async def test_get_ticket_not_found(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/tickets/99999", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_patch_ticket_status(client: AsyncClient, auth_headers: dict, db: AsyncSession):
    ticket = await _create_ticket(db, status="new")
    resp = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"status": "verified"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "verified"


@pytest.mark.asyncio
async def test_patch_ticket_invalid_status(client: AsyncClient, auth_headers: dict, db: AsyncSession):
    ticket = await _create_ticket(db)
    resp = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"status": "invalid_status"},
        headers=auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_patch_ticket_severity(client: AsyncClient, auth_headers: dict, db: AsyncSession):
    ticket = await _create_ticket(db, severity="low")
    resp = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        json={"severity": "critical"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["severity"] == "critical"


@pytest.mark.asyncio
async def test_tickets_require_auth(client: AsyncClient):
    resp = await client.get("/api/v1/tickets")
    assert resp.status_code == 401
