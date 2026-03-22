"""
Detection creation logic: compute geometry, persist, queue pipeline.
"""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import Detection

logger = get_logger(__name__)


def compute_geometry(length_cm: float, width_cm: float, depth_cm: float) -> dict:
    vol = round((length_cm * width_cm * depth_cm) / 1_000_000, 6)
    area = round((length_cm * width_cm) / 10_000, 4)
    return {
        "defect_volume_m3": vol,
        "surface_area_m2": area,
        "repair_material_m3": round(vol * 1.2, 6),
    }


async def create_detection(
    db: AsyncSession,
    *,
    ticket_id: int,
    defect_type: str,
    severity: str,
    lat: float,
    lng: float,
    vehicle_id: str = "UNKNOWN",
    vehicle_model: str = "Unknown",
    vehicle_sensor_version: str = "v1.0",
    reported_by: str = "system",
    reporter_user_id: Optional[int] = None,
    defect_length_cm: float = 0.0,
    defect_width_cm: float = 0.0,
    defect_depth_cm: float = 0.0,
    notes: str = "",
    image_url: str = "",
    image_hash: str = "",
    image_caption: str = "",
    ambient_temp_c: float = 25.0,
    asphalt_temp_c: float = 28.0,
    weather_condition: str = "Clear",
    wind_speed_kmh: float = 10.0,
    humidity_pct: float = 50.0,
    visibility_m: int = 1000,
) -> Detection:
    geo = compute_geometry(defect_length_cm, defect_width_cm, defect_depth_cm)

    detection = Detection(
        ticket_id=ticket_id,
        defect_type=defect_type,
        severity=severity,
        lat=lat,
        lng=lng,
        vehicle_id=vehicle_id,
        vehicle_model=vehicle_model,
        vehicle_sensor_version=vehicle_sensor_version,
        reported_by=reported_by,
        reporter_user_id=reporter_user_id,
        defect_length_cm=defect_length_cm,
        defect_width_cm=defect_width_cm,
        defect_depth_cm=defect_depth_cm,
        notes=notes,
        image_url=image_url,
        image_hash=image_hash,
        image_caption=image_caption,
        ambient_temp_c=ambient_temp_c,
        asphalt_temp_c=asphalt_temp_c,
        weather_condition=weather_condition,
        wind_speed_kmh=wind_speed_kmh,
        humidity_pct=humidity_pct,
        visibility_m=visibility_m,
        pipeline_status="pending",
        **geo,
    )

    db.add(detection)
    await db.flush()
    logger.info("Detection created", extra={"detection_id": detection.id, "ticket_id": ticket_id})
    return detection
