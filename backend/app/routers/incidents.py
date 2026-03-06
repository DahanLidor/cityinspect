"""Incident CRUD and upload endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import User
from app.models.schemas import IncidentMapItem, IncidentResponse
from app.services.incident_service import IncidentService
from app.utils.auth import get_current_user
from app.utils.storage import get_storage

router = APIRouter(prefix="/api/v1", tags=["incidents"])


@router.post("/incident/upload", response_model=IncidentResponse, status_code=status.HTTP_201_CREATED)
async def upload_incident(
    image: UploadFile = File(...),
    depth_map: UploadFile | None = File(None),
    latitude: float = Form(...),
    longitude: float = Form(...),
    captured_at: str = Form(...),
    device_info: str = Form("{}"),
    lidar_measurements: str = Form("{}"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept an incident report from the mobile app.

    - RGB image (required)
    - LiDAR depth map (optional binary)
    - GPS coordinates, timestamp, device info, LiDAR measurements as form fields
    """
    image_bytes = await image.read()
    depth_bytes = await depth_map.read() if depth_map else None

    try:
        lidar_data = json.loads(lidar_measurements) if lidar_measurements else {}
    except json.JSONDecodeError:
        lidar_data = {}

    try:
        device = json.loads(device_info) if device_info else {}
    except json.JSONDecodeError:
        device = {}

    try:
        ts = datetime.fromisoformat(captured_at)
    except ValueError:
        raise HTTPException(status_code=400, detail="captured_at must be ISO 8601 format")

    storage = get_storage()
    service = IncidentService(db, storage)

    incident = await service.process_upload(
        user_id=user.id,
        image_bytes=image_bytes,
        depth_map_bytes=depth_bytes,
        latitude=latitude,
        longitude=longitude,
        captured_at=ts,
        device_info=device,
        lidar_measurements=lidar_data if lidar_data else None,
    )

    return IncidentResponse.model_validate(incident)


@router.get("/incident/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve a single incident by ID."""
    storage = get_storage()
    service = IncidentService(db, storage)
    incident = await service.get_incident(incident_id)

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    return IncidentResponse.model_validate(incident)


@router.get("/incidents/map", response_model=list[IncidentMapItem])
async def incidents_map(
    min_lat: float = Query(-90, ge=-90, le=90),
    max_lat: float = Query(90, ge=-90, le=90),
    min_lon: float = Query(-180, ge=-180, le=180),
    max_lon: float = Query(180, ge=-180, le=180),
    limit: int = Query(500, ge=1, le=2000),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return incidents within a bounding box for map rendering."""
    storage = get_storage()
    service = IncidentService(db, storage)
    incidents = await service.get_incidents_for_map(min_lat, max_lat, min_lon, max_lon, limit)
    return [IncidentMapItem.model_validate(i) for i in incidents]


@router.patch("/incident/{incident_id}/status", response_model=IncidentResponse)
async def update_incident_status(
    incident_id: uuid.UUID,
    status: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an incident's status (reported, confirmed, in_progress, resolved, dismissed)."""
    valid = {"reported", "confirmed", "in_progress", "resolved", "dismissed"}
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")

    storage = get_storage()
    service = IncidentService(db, storage)
    incident = await service.get_incident(incident_id)

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.status = status
    if status == "resolved":
        from datetime import datetime, timezone
        incident.resolved_at = datetime.now(timezone.utc)

    return IncidentResponse.model_validate(incident)


@router.patch("/incident/{incident_id}/status", response_model=IncidentResponse)
async def update_incident_status(
    incident_id: uuid.UUID,
    status: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update an incident's status (reported, confirmed, in_progress, resolved, dismissed)."""
    valid = {"reported", "confirmed", "in_progress", "resolved", "dismissed"}
    if status not in valid:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid}")

    storage = get_storage()
    service = IncidentService(db, storage)
    incident = await service.get_incident(incident_id)

    if incident is None:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident.status = status
    if status == "resolved":
        from datetime import datetime, timezone
        incident.resolved_at = datetime.now(timezone.utc)

    return IncidentResponse.model_validate(incident)
