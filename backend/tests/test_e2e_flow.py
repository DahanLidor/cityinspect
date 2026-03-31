"""
E2E flow tests: upload → pipeline → workflow → daily plan.
Tests the full system flow from detection upload through to work planning.
"""
from __future__ import annotations

import io
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Detection, Person, Ticket, WorkflowStep


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
async def field_team(db: AsyncSession):
    """Create a complete field team for workflow."""
    people = []
    for ext_id, name, role in [
        ("e2e_manager", "E2E Manager", "work_manager"),
        ("e2e_contractor", "E2E Contractor", "contractor"),
        ("e2e_inspector", "E2E Inspector", "inspector"),
        ("e2e_worker", "E2E Worker", "field_worker"),
    ]:
        p = Person(
            city_id="tel-aviv", external_id=ext_id, name=name, role=role,
            specialties_json='["pothole","road_crack"]',
            skills_json='["asphalt"]',
            vehicle_type="car",
            home_base_lat=32.08, home_base_lon=34.78,
            availability_json='{"sun_thu":"06:00-18:00","fri":"06:00-13:00"}',
        )
        db.add(p)
        people.append(p)
    await db.flush()
    return {p.role: p for p in people}


# ── E2E: Upload → Ticket Created ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_upload_creates_ticket(client: AsyncClient, auth_headers):
    """Full upload flow: image + metadata → ticket + detection created."""
    fake_image = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 100)

    resp = await client.post(
        "/api/v1/incident/upload",
        data={
            "defect_type": "pothole",
            "severity": "high",
            "lat": "32.0900",
            "lng": "34.7850",
            "reported_by": "e2e_test",
            "city_id": "tel-aviv",
            "sensor_data": json.dumps({
                "imu": {"accel": [0.1, 9.8, 0.2], "gyro": [0.01, -0.02, 0.03]},
                "camera": {"heading": 245, "pitch": -15},
                "device": {"model": "iPhone16,1", "os": "18.3"},
            }),
        },
        files={"image": ("test.jpg", fake_image, "image/jpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["ticket_id"] > 0
    assert data["detection_id"] > 0


@pytest.mark.asyncio
async def test_e2e_sensor_data_persisted(client: AsyncClient, auth_headers, db: AsyncSession):
    """Sensor data JSON is stored in the detection record."""
    sensor = {"imu": {"accel": [1, 2, 3]}, "camera": {"heading": 180}}
    fake_image = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 50)

    resp = await client.post(
        "/api/v1/incident/upload",
        data={
            "defect_type": "road_crack",
            "severity": "medium",
            "lat": "32.0800",
            "lng": "34.7700",
            "sensor_data": json.dumps(sensor),
        },
        files={"image": ("s.jpg", fake_image, "image/jpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    det_id = resp.json()["detection_id"]

    det = await db.get(Detection, det_id)
    stored = json.loads(det.sensor_data_json)
    assert stored["imu"]["accel"] == [1, 2, 3]
    assert stored["camera"]["heading"] == 180


# ── E2E: Upload → Pipeline → Scored ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_pipeline_scores_detection(db: AsyncSession):
    """Pipeline runs all 4 agents and updates detection + ticket."""
    from app.agents.pipeline import run_pipeline

    ticket = Ticket(city_id="tel-aviv", defect_type="pothole", severity="medium", lat=32.09, lng=34.78)
    db.add(ticket)
    await db.flush()

    detection = Detection(
        defect_type="pothole", severity="medium", lat=32.09, lng=34.78,
        ticket_id=ticket.id, pipeline_status="pending",
        defect_depth_cm=10, defect_width_cm=40, surface_area_m2=0.4,
    )
    db.add(detection)
    await db.commit()
    await db.refresh(detection)

    vlm = AsyncMock(return_value={
        "hazard_detected": True, "hazard_type": "pothole",
        "severity_hint": "high", "confidence": 0.9,
        "description": "Deep pothole", "liability_risk": "High",
        "analysis_source": "claude_vlm",
    })
    env = AsyncMock(return_value={
        "environment_score": 50, "nearby_places": [],
        "risk_factors": [], "source": "estimated",
        "weather": {"temperature_c": 28, "weather_label": "Clear"},
    })

    with patch("app.agents.pipeline.agent_vlm_analyze", vlm), \
         patch("app.agents.pipeline.agent_environment", env):
        result = await run_pipeline(
            db, detection.id, ticket.id, 32.09, 34.78,
            "", "", {"defect_depth_cm": 10, "defect_width_cm": 40, "surface_area_m2": 0.4},
        )

    assert result["score"]["final_score"] > 0
    assert result["score"]["severity"] in ("low", "medium", "high", "critical")
    assert result["vlm"]["hazard_type"] == "pothole"


# ── E2E: Upload → Workflow Open → Advance ────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_workflow_open_and_advance(client: AsyncClient, auth_headers, db: AsyncSession, field_team):
    """Open workflow for a ticket, then approve (advance to next step)."""
    ticket = Ticket(
        city_id="tel-aviv", defect_type="pothole", severity="high",
        lat=32.09, lng=34.78, status="new",
    )
    db.add(ticket)
    await db.flush()

    # Open workflow
    resp = await client.post(f"/api/v1/workflow/tickets/{ticket.id}/open", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["step_id"] == "manager_approval"

    # Check steps
    resp = await client.get(f"/api/v1/workflow/tickets/{ticket.id}/steps", headers=auth_headers)
    assert resp.status_code == 200
    steps = resp.json()
    assert len(steps) >= 1
    assert steps[0]["step_id"] == "manager_approval"
    assert steps[0]["status"] == "open"

    # Perform action (approve)
    manager = field_team["work_manager"]
    resp = await client.post(
        f"/api/v1/workflow/tickets/{ticket.id}/action",
        json={"action": "approve", "person_id": manager.id},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    action_data = resp.json()
    assert action_data["status"] in ("ok", "advanced")


# ── E2E: Full Flow ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_full_ticket_lifecycle(client: AsyncClient, auth_headers, db: AsyncSession):
    """Upload detection → check ticket exists → check stats update."""
    fake_image = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 100)

    # 1. Upload
    resp = await client.post(
        "/api/v1/incident/upload",
        data={
            "defect_type": "pothole",
            "severity": "critical",
            "lat": "32.0950",
            "lng": "34.7900",
            "city_id": "tel-aviv",
        },
        files={"image": ("full.jpg", fake_image, "image/jpeg")},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    ticket_id = resp.json()["ticket_id"]

    # 2. Ticket exists
    resp = await client.get(f"/api/v1/tickets/{ticket_id}", headers=auth_headers)
    assert resp.status_code == 200
    ticket = resp.json()
    assert ticket["defect_type"] == "pothole"
    assert ticket["severity"] == "critical"

    # 3. Stats include this ticket
    resp = await client.get("/api/v1/stats/summary?city_id=tel-aviv", headers=auth_headers)
    assert resp.status_code == 200
    stats = resp.json()
    assert stats.get("total_open", stats.get("open_tickets", 0)) >= 1

    # 4. Update ticket status
    resp = await client.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"status": "in_progress"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"


# ── Duplicate detection merging ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_e2e_duplicate_upload_merges(client: AsyncClient, auth_headers):
    """Two uploads at same location → same ticket (merged)."""
    fake_image1 = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 50)
    fake_image2 = io.BytesIO(b"\xff\xd8\xff" + b"\x00" * 60)

    resp1 = await client.post(
        "/api/v1/incident/upload",
        data={"defect_type": "pothole", "severity": "medium", "lat": "32.0700", "lng": "34.7600"},
        files={"image": ("a.jpg", fake_image1, "image/jpeg")},
        headers=auth_headers,
    )
    resp2 = await client.post(
        "/api/v1/incident/upload",
        data={"defect_type": "pothole", "severity": "high", "lat": "32.0700", "lng": "34.7600"},
        files={"image": ("b.jpg", fake_image2, "image/jpeg")},
        headers=auth_headers,
    )

    assert resp1.status_code == 201
    assert resp2.status_code == 201
    # Same ticket (merged due to proximity)
    assert resp1.json()["ticket_id"] == resp2.json()["ticket_id"]
    # Second one is not new
    assert resp2.json()["is_new_ticket"] is False
