"""
Unit tests for all 4 AI pipeline agents.
External API calls are mocked — tests are fully offline.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.dedup import agent_dedup
from app.agents.environment import agent_environment
from app.agents.scorer import agent_scorer
from app.agents.vlm import agent_vlm_analyze


# ── VLM Agent ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vlm_no_api_key():
    """Falls back gracefully when no API key configured."""
    with patch("app.agents.vlm.settings") as mock_settings:
        mock_settings.anthropic_api_key = ""
        result = await agent_vlm_analyze("/uploads/test.jpg")
    assert result["analysis_source"] == "fallback"
    assert "hazard_type" in result
    assert "confidence" in result


@pytest.mark.asyncio
async def test_vlm_missing_image():
    """Returns error dict when image file doesn't exist."""
    with patch("app.agents.vlm.settings") as mock_settings:
        mock_settings.anthropic_api_key = "fake-key"
        mock_settings.upload_path = "/nonexistent"
        result = await agent_vlm_analyze("/uploads/missing.jpg")
    assert result["hazard_detected"] is False
    assert result["analysis_source"] == "error"


@pytest.mark.asyncio
async def test_vlm_api_success(tmp_path):
    """Parses Claude API response correctly."""
    img = tmp_path / "test.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)

    api_response = {
        "content": [{"text": json.dumps({
            "description": "בור גדול",
            "hazard_detected": True,
            "hazard_type": "pothole",
            "hazard_details": "עמוק",
            "liability_risk": "גבוה",
            "severity_hint": "high",
            "confidence": 0.9,
        })}]
    }

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = api_response

    with patch("app.agents.vlm.settings") as mock_settings, \
         patch("app.agents.vlm.httpx.AsyncClient") as mock_client_cls:
        mock_settings.anthropic_api_key = "fake-key"
        mock_settings.upload_path = str(tmp_path)
        mock_settings.allowed_image_types = ["image/jpeg"]

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await agent_vlm_analyze("/uploads/test.jpg")

    assert result["hazard_type"] == "pothole"
    assert result["confidence"] == 0.9
    assert result["analysis_source"] == "claude_vlm"


# ── Environment Agent ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_environment_free_apis_mocked():
    """Environment agent uses free APIs (Nominatim, Overpass, Open-Meteo) — mock httpx."""
    # Mock all 3 HTTP calls to return empty/minimal data
    nominatim_resp = MagicMock()
    nominatim_resp.status_code = 200
    nominatim_resp.json.return_value = {"address": {"road": "Herzl St", "city": "Tel Aviv"}, "display_name": "Herzl St, Tel Aviv"}

    overpass_resp = MagicMock()
    overpass_resp.status_code = 200
    overpass_resp.json.return_value = {"elements": []}

    weather_resp = MagicMock()
    weather_resp.status_code = 200
    weather_resp.json.return_value = {"current_weather": {"temperature": 22, "windspeed": 10, "weathercode": 0}}

    with patch("app.agents.environment.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[nominatim_resp, overpass_resp, weather_resp])
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await agent_environment(32.0853, 34.7818)

    assert "environment_score" in result
    assert isinstance(result.get("nearby_places", []), list)


@pytest.mark.asyncio
async def test_environment_api_failure_fallback():
    """Environment agent returns fallback when APIs fail."""
    with patch("app.agents.environment.httpx.AsyncClient") as mock_client_cls:
        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=Exception("Network error"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        result = await agent_environment(32.0853, 34.7818)

    assert "environment_score" in result
    assert isinstance(result, dict)


# ── Dedup Agent ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dedup_no_duplicates(db: AsyncSession):
    """New detection with no nearby siblings → not a duplicate."""
    result = await agent_dedup(db, detection_id=1, lat=32.0853, lng=34.7818,
                                image_hash="abc123", ticket_id=999)
    assert result["is_duplicate"] is False
    assert result["action"] == "keep"


@pytest.mark.asyncio
async def test_dedup_gps_duplicate(db: AsyncSession):
    """Two detections < 5m apart within 2h → duplicate."""
    from datetime import datetime, timezone
    from app.models import Detection, Ticket

    ticket = Ticket(defect_type="pothole", severity="medium", lat=32.0853, lng=34.7818)
    db.add(ticket)
    await db.flush()

    original = Detection(
        defect_type="pothole", severity="medium",
        lat=32.08530, lng=34.78180,
        ticket_id=ticket.id,
        detected_at=datetime.now(timezone.utc),
    )
    db.add(original)
    await db.flush()

    # New detection 1m away
    result = await agent_dedup(db, detection_id=original.id + 1,
                                lat=32.08531, lng=34.78181,
                                image_hash="differenthash", ticket_id=ticket.id)
    assert result["is_duplicate"] is True
    assert result["duplicate_of"] == original.id


@pytest.mark.asyncio
async def test_dedup_image_hash_duplicate(db: AsyncSession):
    """Same image hash → duplicate regardless of GPS."""
    from datetime import datetime, timezone
    from app.models import Detection, Ticket

    ticket = Ticket(defect_type="road_crack", severity="low", lat=32.0, lng=34.0)
    db.add(ticket)
    await db.flush()

    original = Detection(
        defect_type="road_crack", severity="low",
        lat=32.0, lng=34.0,
        image_hash="samehash123",
        ticket_id=ticket.id,
        detected_at=datetime.now(timezone.utc),
    )
    db.add(original)
    await db.flush()

    result = await agent_dedup(db, detection_id=original.id + 1,
                                lat=32.9, lng=34.9,  # far away
                                image_hash="samehash123", ticket_id=ticket.id)
    assert result["is_duplicate"] is True
    assert result["reason"] == "identical_image"


# ── Scorer Agent ─────────────────────────────────────────────────────────────

def test_scorer_duplicate_input():
    dedup = {"is_duplicate": True, "duplicate_of": 5}
    result = agent_scorer({}, {}, dedup, {})
    assert result["severity"] == "duplicate"
    assert result["final_score"] == 0
    assert result["action"] == "mark_duplicate"


def test_scorer_no_hazard():
    vlm = {"hazard_detected": False}
    dedup = {"is_duplicate": False}
    result = agent_scorer(vlm, {}, dedup, {})
    assert result["severity"] == "none"
    assert result["final_score"] == 5
    assert result["action"] == "review"


def test_scorer_critical():
    vlm = {"hazard_detected": True, "severity_hint": "critical", "confidence": 1.0, "hazard_type": "pothole"}
    env = {"environment_score": 80}
    dedup = {"is_duplicate": False}
    detection = {"defect_depth_cm": 15, "defect_width_cm": 60, "surface_area_m2": 0.8}
    result = agent_scorer(vlm, env, dedup, detection)
    assert result["severity"] == "critical"
    assert result["final_score"] >= 80
    assert result["action"] == "alert"


def test_scorer_low():
    vlm = {"hazard_detected": True, "severity_hint": "low", "confidence": 0.3}
    env = {"environment_score": 5}
    dedup = {"is_duplicate": False}
    detection = {"defect_depth_cm": 1, "defect_width_cm": 5, "surface_area_m2": 0.01}
    result = agent_scorer(vlm, env, dedup, detection)
    assert result["severity"] == "low"
    assert result["action"] == "monitor"


def test_scorer_breakdown_keys():
    vlm = {"hazard_detected": True, "severity_hint": "medium", "confidence": 0.7}
    env = {"environment_score": 40}
    dedup = {"is_duplicate": False}
    result = agent_scorer(vlm, env, dedup, {"defect_depth_cm": 5})
    bd = result["breakdown"]
    assert "vlm" in bd
    assert "environment" in bd
    assert "geometry" in bd


def test_scorer_score_clamped():
    """Score must always be between 5 and 100."""
    vlm = {"hazard_detected": True, "severity_hint": "critical", "confidence": 10.0}  # absurd confidence
    env = {"environment_score": 10000}
    dedup = {"is_duplicate": False}
    result = agent_scorer(vlm, env, dedup, {"defect_depth_cm": 100, "defect_width_cm": 500, "surface_area_m2": 100})
    assert 5 <= result["final_score"] <= 100
