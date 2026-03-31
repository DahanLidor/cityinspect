"""
Tests for detection upload + ticket dedup logic.
"""
from __future__ import annotations

import io
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ticket
from app.services.ticket_service import find_or_create_ticket, haversine


# ── Haversine ────────────────────────────────────────────────────────────────

def test_haversine_same_point():
    assert haversine(32.0, 34.0, 32.0, 34.0) == pytest.approx(0.0, abs=1e-3)


def test_haversine_known_distance():
    # Tel Aviv to Jerusalem ≈ 54 km
    dist = haversine(32.0853, 34.7818, 31.7683, 35.2137)
    assert 50_000 < dist < 70_000


def test_haversine_30m():
    """Two points ~30m apart."""
    lat1, lng1 = 32.0853, 34.7818
    # ~30m north
    lat2 = lat1 + (30 / 111_000)
    dist = haversine(lat1, lng1, lat2, lng1)
    assert 25 < dist < 35


# ── Ticket service ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_find_or_create_new_ticket(db: AsyncSession):
    ticket, is_new = await find_or_create_ticket(db, "pothole", "medium", 32.0853, 34.7818, "Test")
    assert is_new is True
    assert ticket.id is not None
    assert ticket.defect_type == "pothole"


@pytest.mark.asyncio
async def test_find_existing_ticket_nearby(db: AsyncSession):
    # Create initial ticket
    t1, _ = await find_or_create_ticket(db, "pothole", "low", 32.0853, 34.7818, "Original")

    # 10m away, same type → should return existing
    lat2 = 32.0853 + (10 / 111_000)
    t2, is_new = await find_or_create_ticket(db, "pothole", "medium", lat2, 34.7818, "Close")

    assert is_new is False
    assert t2.id == t1.id
    assert t2.detection_count == 2


@pytest.mark.asyncio
async def test_severity_escalates(db: AsyncSession):
    t1, _ = await find_or_create_ticket(db, "road_crack", "low", 32.0810, 34.7780, "A")
    lat2 = 32.0810 + (5 / 111_000)
    t2, is_new = await find_or_create_ticket(db, "road_crack", "critical", lat2, 34.7780, "B")
    assert is_new is False
    assert t2.severity == "critical"


@pytest.mark.asyncio
async def test_far_away_creates_new_ticket(db: AsyncSession):
    await find_or_create_ticket(db, "pothole", "medium", 32.0853, 34.7818, "A")
    # 500m away
    lat2 = 32.0853 + (500 / 111_000)
    _, is_new = await find_or_create_ticket(db, "pothole", "medium", lat2, 34.7818, "B")
    assert is_new is True


@pytest.mark.asyncio
async def test_different_type_creates_new_ticket(db: AsyncSession):
    await find_or_create_ticket(db, "pothole", "medium", 32.0853, 34.7818, "A")
    _, is_new = await find_or_create_ticket(db, "road_crack", "medium", 32.0853, 34.7818, "B")
    assert is_new is True


# ── Upload endpoint ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_requires_auth(client: AsyncClient):
    resp = await client.post("/api/v1/incident/upload")
    assert resp.status_code in (401, 403, 422)


@pytest.mark.asyncio
async def test_upload_creates_detection(client: AsyncClient, auth_headers: dict, monkeypatch):
    """Upload with a valid JPEG creates a detection + ticket."""
    # Patch pipeline to avoid actual API calls
    monkeypatch.setattr("app.routers.detections.asyncio.create_task", lambda coro: None)

    # Minimal valid JPEG bytes (magic header)
    fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 200

    resp = await client.post(
        "/api/v1/incident/upload",
        data={
            "defect_type": "pothole",
            "severity": "medium",
            "lat": "32.0853",
            "lng": "34.7818",
        },
        files={"image": ("test.jpg", io.BytesIO(fake_jpeg), "image/jpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "detection_id" in data
    assert "ticket_id" in data
    assert data["is_new_ticket"] is True


@pytest.mark.asyncio
async def test_upload_invalid_file_type(client: AsyncClient, auth_headers: dict):
    """Upload with a text file should be rejected."""
    resp = await client.post(
        "/api/v1/incident/upload",
        data={"defect_type": "pothole", "severity": "medium", "lat": "32.0853", "lng": "34.7818"},
        files={"image": ("malicious.exe", io.BytesIO(b"MZ\x90\x00evil"), "application/octet-stream")},
        headers=auth_headers,
    )
    assert resp.status_code in (415, 422)


@pytest.mark.asyncio
async def test_upload_no_image_allowed(client: AsyncClient, auth_headers: dict, monkeypatch):
    """Upload without image should succeed (image is optional)."""
    monkeypatch.setattr("app.routers.detections.asyncio.create_task", lambda coro: None)
    resp = await client.post(
        "/api/v1/incident/upload",
        data={"defect_type": "sidewalk", "severity": "low", "lat": "32.0810", "lng": "34.7780"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
