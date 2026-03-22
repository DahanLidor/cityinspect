"""
Integration tests for the full AI pipeline runner.
All external API calls (Claude, Google Maps) are mocked.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.pipeline import run_pipeline
from app.models import Detection, Ticket


@pytest.fixture
async def pipeline_detection(db: AsyncSession):
    """Creates a ticket + detection pair for pipeline testing."""
    ticket = Ticket(defect_type="pothole", severity="medium", lat=32.0853, lng=34.7818)
    db.add(ticket)
    await db.flush()

    detection = Detection(
        defect_type="pothole", severity="medium",
        lat=32.0853, lng=34.7818,
        defect_depth_cm=8.0, defect_width_cm=30.0, surface_area_m2=0.3,
        ticket_id=ticket.id, pipeline_status="pending",
    )
    db.add(detection)
    await db.commit()
    await db.refresh(detection)
    return detection, ticket


@pytest.mark.asyncio
async def test_pipeline_updates_status(db: AsyncSession, pipeline_detection):
    detection, ticket = pipeline_detection

    vlm_mock = AsyncMock(return_value={
        "hazard_detected": True, "hazard_type": "pothole",
        "severity_hint": "high", "confidence": 0.85,
        "description": "בור עמוק", "liability_risk": "גבוה",
        "analysis_source": "claude_vlm",
    })
    env_mock = AsyncMock(return_value={
        "nearby_places": [], "risk_factors": [], "environment_score": 40, "source": "estimated",
    })

    with patch("app.agents.pipeline.agent_vlm_analyze", vlm_mock), \
         patch("app.agents.pipeline.agent_environment", env_mock):
        result = await run_pipeline(
            db, detection.id, ticket.id,
            detection.lat, detection.lng,
            "", "", {"defect_depth_cm": 8, "defect_width_cm": 30, "surface_area_m2": 0.3},
        )

    assert result["detection_id"] == detection.id
    assert "score" in result
    assert result["score"]["final_score"] > 0

    # Reload detection and check pipeline_status
    refreshed = (await db.execute(select(Detection).where(Detection.id == detection.id))).scalar_one()
    assert refreshed.pipeline_status == "done"


@pytest.mark.asyncio
async def test_pipeline_marks_error_on_failure(db: AsyncSession, pipeline_detection):
    detection, ticket = pipeline_detection

    with patch("app.agents.pipeline.agent_vlm_analyze", AsyncMock(side_effect=RuntimeError("VLM crashed"))):
        with pytest.raises(RuntimeError):
            await run_pipeline(
                db, detection.id, ticket.id,
                detection.lat, detection.lng,
                "", "", {},
            )

    refreshed = (await db.execute(select(Detection).where(Detection.id == detection.id))).scalar_one()
    assert refreshed.pipeline_status == "error"


@pytest.mark.asyncio
async def test_pipeline_duplicate_detection(db: AsyncSession, pipeline_detection):
    """When dedup finds a duplicate, pipeline should store score.severity='duplicate'."""
    from datetime import datetime, timezone

    detection, ticket = pipeline_detection

    # Add an existing detection at the same spot
    existing = Detection(
        defect_type="pothole", severity="medium",
        lat=32.0853, lng=34.7818,
        image_hash="samehash",
        ticket_id=ticket.id,
        detected_at=datetime.now(timezone.utc),
    )
    db.add(existing)
    await db.flush()

    vlm_mock = AsyncMock(return_value={
        "hazard_detected": True, "hazard_type": "pothole",
        "severity_hint": "medium", "confidence": 0.7,
        "description": "test", "liability_risk": "", "analysis_source": "fallback",
    })
    env_mock = AsyncMock(return_value={"environment_score": 20, "nearby_places": [], "risk_factors": [], "source": "estimated"})

    with patch("app.agents.pipeline.agent_vlm_analyze", vlm_mock), \
         patch("app.agents.pipeline.agent_environment", env_mock):
        result = await run_pipeline(
            db, detection.id, ticket.id,
            detection.lat, detection.lng,
            "", "samehash", {"defect_depth_cm": 5, "defect_width_cm": 20, "surface_area_m2": 0.1},
        )

    assert result["dedup"]["is_duplicate"] is True
    assert result["score"]["severity"] == "duplicate"
