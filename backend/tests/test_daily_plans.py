"""
Tests for daily plans: worker listing, plan generation, system config.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DailyPlan, Person, SystemConfig, Ticket


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def worker(db: AsyncSession):
    p = Person(
        city_id="tel-aviv", external_id="test_worker",
        name="Test Worker", role="field_worker",
        specialties_json='["pothole","road_crack"]',
        skills_json='["asphalt","welding"]',
        vehicle_type="truck",
        max_daily_hours=8.0,
        home_base_lat=32.0853, home_base_lon=34.7818,
        availability_json='{"sun_thu":"07:00-17:00","fri":"07:00-13:00"}',
    )
    db.add(p)
    await db.flush()
    return p


@pytest.fixture
async def open_ticket(db: AsyncSession):
    t = Ticket(
        city_id="tel-aviv", defect_type="pothole", severity="high",
        lat=32.0900, lng=34.7850, address="Herzl 45, Tel Aviv",
        status="new", score=75,
    )
    db.add(t)
    await db.flush()
    return t


# ── Worker listing ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_workers(client: AsyncClient, auth_headers, worker):
    resp = await client.get("/api/v1/daily-plans/workers?city_id=tel-aviv", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    names = [w["name"] for w in data]
    assert "Test Worker" in names


@pytest.mark.asyncio
async def test_list_workers_filters_roles(client: AsyncClient, auth_headers, db: AsyncSession):
    """City managers should NOT appear in workers list."""
    mgr = Person(
        city_id="tel-aviv", external_id="test_mgr",
        name="City Manager", role="city_manager",
    )
    db.add(mgr)
    await db.flush()

    resp = await client.get("/api/v1/daily-plans/workers?city_id=tel-aviv", headers=auth_headers)
    names = [w["name"] for w in resp.json()]
    assert "City Manager" not in names


# ── Plan generation ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_plan_no_tickets(client: AsyncClient, auth_headers, worker):
    """Generate plan with no matching tickets → empty plan."""
    resp = await client.post(
        "/api/v1/daily-plans/generate",
        json={"person_id": worker.id},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["total_tasks"] == 0
    assert data["status"] == "draft"


@pytest.mark.asyncio
async def test_generate_plan_with_tickets(client: AsyncClient, auth_headers, worker, open_ticket):
    """Generate plan with matching ticket → AI called, plan created."""
    mock_ai_response = MagicMock()
    mock_ai_response.content = [MagicMock(text=json.dumps({
        "worker_name": "Test Worker",
        "date": "2026-04-01",
        "start_time": "08:00",
        "end_time": "14:00",
        "total_estimated_hours": 6.0,
        "total_distance_km": 12.5,
        "tasks": [
            {
                "order": 1,
                "ticket_id": open_ticket.id,
                "address": "Herzl 45",
                "defect_type": "pothole",
                "severity": "high",
                "estimated_duration_min": 45,
                "drive_time_min": 10,
                "arrive_by": "08:10",
                "equipment": ["asphalt"],
                "notes": "test",
            }
        ],
        "equipment_summary": ["asphalt"],
        "summary_he": "תוכנית בדיקה",
    }))]

    with patch("app.agents.daily_planner.anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_client.messages.create = AsyncMock(return_value=mock_ai_response)
        mock_cls.return_value = mock_client

        resp = await client.post(
            "/api/v1/daily-plans/generate",
            json={"person_id": worker.id},
            headers=auth_headers,
        )

    assert resp.status_code == 201
    data = resp.json()
    assert data["total_tasks"] == 1
    assert data["plan"]["tasks"][0]["ticket_id"] == open_ticket.id


@pytest.mark.asyncio
async def test_generate_plan_invalid_worker(client: AsyncClient, auth_headers):
    resp = await client.post(
        "/api/v1/daily-plans/generate",
        json={"person_id": 99999},
        headers=auth_headers,
    )
    assert resp.status_code == 404


# ── Plan listing ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_plans_empty(client: AsyncClient, auth_headers):
    resp = await client.get("/api/v1/daily-plans?city_id=tel-aviv", headers=auth_headers)
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


# ── System Config ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upsert_config(client: AsyncClient, auth_headers):
    resp = await client.put(
        "/api/v1/daily-plans/config",
        json={"key": "work_radius_km", "value": 20},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == 20


@pytest.mark.asyncio
async def test_get_all_config(client: AsyncClient, auth_headers):
    # First insert
    await client.put(
        "/api/v1/daily-plans/config",
        json={"key": "nearby_radius_m", "value": 500},
        headers=auth_headers,
    )
    resp = await client.get("/api/v1/daily-plans/config/all", headers=auth_headers)
    assert resp.status_code == 200
    keys = [c["key"] for c in resp.json()]
    assert "nearby_radius_m" in keys


@pytest.mark.asyncio
async def test_config_update_overwrites(client: AsyncClient, auth_headers):
    await client.put("/api/v1/daily-plans/config", json={"key": "test_key", "value": 1}, headers=auth_headers)
    await client.put("/api/v1/daily-plans/config", json={"key": "test_key", "value": 2}, headers=auth_headers)
    resp = await client.get("/api/v1/daily-plans/config/all", headers=auth_headers)
    found = [c for c in resp.json() if c["key"] == "test_key"]
    assert found[0]["value"] == 2
