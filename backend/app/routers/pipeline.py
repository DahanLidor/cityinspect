"""
Pipeline management routes: manual trigger + status check.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Detection, User
from app.schemas import PipelineRunResponse, PipelineStatusResponse

router = APIRouter(prefix="/api/v1", tags=["pipeline"])


@router.post("/pipeline/run/{detection_id}", response_model=PipelineRunResponse)
async def run_pipeline_manual(
    detection_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PipelineRunResponse:
    """Manually (re-)trigger the AI pipeline for a detection."""
    result = await db.execute(select(Detection).where(Detection.id == detection_id))
    detection = result.scalar_one_or_none()
    if not detection:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Detection not found")

    from app.agents.pipeline import run_pipeline

    det_dict = {
        "defect_depth_cm": detection.defect_depth_cm,
        "defect_width_cm": detection.defect_width_cm,
        "defect_length_cm": detection.defect_length_cm,
        "surface_area_m2": detection.surface_area_m2,
    }
    result_data = await run_pipeline(
        db, detection.id, detection.ticket_id,
        detection.lat, detection.lng,
        detection.image_url, detection.image_hash, det_dict,
    )
    return PipelineRunResponse(**result_data)


@router.get("/pipeline/status/{detection_id}", response_model=PipelineStatusResponse)
async def pipeline_status(
    detection_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PipelineStatusResponse:
    result = await db.execute(select(Detection).where(Detection.id == detection_id))
    detection = result.scalar_one_or_none()
    if not detection:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Detection not found")

    try:
        notes = json.loads(detection.notes) if detection.notes and detection.notes.startswith("{") else {}
    except Exception:
        notes = {}

    return PipelineStatusResponse(
        detection_id=detection.id,
        pipeline_status=detection.pipeline_status,
        caption=detection.image_caption,
        pipeline=notes,
    )
