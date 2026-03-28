"""
Detection routes: upload (multipart) + JSON creation.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.models import User
from app.schemas import DetectionUploadResponse
from app.services.detection_service import create_detection
from app.services.storage_service import save_file, save_upload
from app.services.ticket_service import find_or_create_ticket
from app.ws.hub import hub

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["detections"])


async def _fire_pipeline(
    detection_id: int,
    ticket_id: int,
    lat: float,
    lng: float,
    image_url: str,
    image_hash: str,
    detection_dict: dict,
) -> None:
    """Independent session for background pipeline execution."""
    from app.agents.pipeline import run_pipeline
    from app.core.database import _async_session

    async with _async_session() as db:
        try:
            await run_pipeline(db, detection_id, ticket_id, lat, lng, image_url, image_hash, detection_dict)
        except Exception as exc:
            logger.error("Background pipeline error", extra={"detection_id": detection_id, "error": str(exc)})


@router.post("/incident/upload", response_model=DetectionUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_detection(
    defect_type: str = Form(...),
    severity: str = Form(...),
    lat: float = Form(...),
    lng: float = Form(...),
    defect_length_cm: float = Form(0.0),
    defect_width_cm: float = Form(0.0),
    defect_depth_cm: float = Form(0.0),
    notes: str = Form(""),
    reported_by: str = Form("system"),
    vehicle_id: str = Form("UNKNOWN"),
    vehicle_model: str = Form("Unknown"),
    vehicle_sensor_version: str = Form("v1.0"),
    image_caption: str = Form(""),
    ambient_temp_c: float = Form(25.0),
    asphalt_temp_c: float = Form(28.0),
    weather_condition: str = Form("Clear"),
    wind_speed_kmh: float = Form(10.0),
    humidity_pct: float = Form(50.0),
    visibility_m: int = Form(1000),
    city_id: str = Form("tel-aviv"),
    image: Optional[UploadFile] = File(None),
    point_cloud: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DetectionUploadResponse:
    # 1. Handle image upload
    image_url = ""
    image_hash = ""
    if image and image.filename:
        image_url, image_hash = await save_upload(image)

    # 1b. Handle point cloud upload
    point_cloud_url = ""
    if point_cloud and point_cloud.filename:
        point_cloud_url, _ = await save_file(point_cloud)

    # 2. Find or create ticket
    address = f"{lat:.4f}, {lng:.4f}"
    ticket, is_new = await find_or_create_ticket(db, defect_type, severity, lat, lng, address, city_id=city_id)

    # 3. Create detection
    detection = await create_detection(
        db,
        ticket_id=ticket.id,
        defect_type=defect_type,
        severity=severity,
        lat=lat,
        lng=lng,
        vehicle_id=vehicle_id,
        vehicle_model=vehicle_model,
        vehicle_sensor_version=vehicle_sensor_version,
        reported_by=reported_by,
        reporter_user_id=user.id,
        defect_length_cm=defect_length_cm,
        defect_width_cm=defect_width_cm,
        defect_depth_cm=defect_depth_cm,
        notes=notes,
        image_url=image_url,
        image_hash=image_hash,
        image_caption=image_caption,
        point_cloud_url=point_cloud_url,
        ambient_temp_c=ambient_temp_c,
        asphalt_temp_c=asphalt_temp_c,
        weather_condition=weather_condition,
        wind_speed_kmh=wind_speed_kmh,
        humidity_pct=humidity_pct,
        visibility_m=visibility_m,
    )
    await db.commit()
    await db.refresh(detection)

    # 4. Fire AI pipeline in background (non-blocking)
    det_dict = {
        "defect_depth_cm": defect_depth_cm,
        "defect_width_cm": defect_width_cm,
        "defect_length_cm": defect_length_cm,
        "surface_area_m2": detection.surface_area_m2,
    }
    asyncio.create_task(_fire_pipeline(detection.id, ticket.id, lat, lng, image_url, image_hash, det_dict))

    # 5. Broadcast
    await hub.broadcast({
        "type": "new_detection",
        "ticket_id": ticket.id,
        "is_new_ticket": is_new,
        "defect_type": defect_type,
        "severity": severity,
        "lat": lat,
        "lng": lng,
    })

    return DetectionUploadResponse(
        detection_id=detection.id,
        ticket_id=ticket.id,
        is_new_ticket=is_new,
        address=address,
    )
