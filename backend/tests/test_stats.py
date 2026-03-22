"""
Tests for stats summary endpoint.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ticket


@pytest.mark.asyncio
async def test_stats_empty(client: AsyncClient, auth_headers: dict):
    resp = await client.get("/api/v1/stats/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "total_tickets" in data
    assert "open_tickets" in data
    assert "critical_tickets" in data
    assert "by_type" in data
    assert "by_status" in data
    assert "by_severity" in data


@pytest.mark.asyncio
async def test_stats_counts(client: AsyncClient, auth_headers: dict, db: AsyncSession):
    # Add known tickets
    tickets = [
        Ticket(defect_type="pothole", severity="critical", lat=32.0, lng=34.0, address="A", status="new"),
        Ticket(defect_type="road_crack", severity="medium", lat=32.1, lng=34.1, address="B", status="resolved"),
        Ticket(defect_type="sidewalk", severity="low", lat=32.2, lng=34.2, address="C", status="in_progress"),
    ]
    db.add_all(tickets)
    await db.commit()

    resp = await client.get("/api/v1/stats/summary", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_tickets"] >= 3
    assert data["open_tickets"] >= 2  # new + in_progress
    assert data["critical_tickets"] >= 1
    assert data["by_type"]["pothole"] >= 1
    assert data["by_status"]["resolved"] >= 1


@pytest.mark.asyncio
async def test_stats_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/stats/summary")
    assert resp.status_code == 401
