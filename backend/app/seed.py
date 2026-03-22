"""
Demo data seeder — idempotent (skips if users already exist).
"""
from __future__ import annotations

import random
from datetime import timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import get_logger
from app.core.security import hash_password
from app.models import Detection, Ticket, User, WorkOrder

logger = get_logger(__name__)

_IMAGES = {
    "pothole": ("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Pothole_on_D2128_%28Poland%29.jpg/640px-Pothole_on_D2128_%28Poland%29.jpg", "בור בכביש"),
    "road_crack": ("https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Road_cracks.jpg/640px-Road_cracks.jpg", "סדק בכביש"),
    "broken_light": ("", "פנס תקול"),
    "drainage_blocked": ("https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Blocked_drain.jpg/640px-Blocked_drain.jpg", "ביוב חסום"),
    "sidewalk": ("", "מדרכה שבורה"),
}

_BASE_COORDS = [
    (32.0853, 34.7818), (32.0810, 34.7780), (32.0900, 34.7850),
    (32.0780, 34.7900), (32.0830, 34.7750), (32.0870, 34.7820),
    (32.0920, 34.7790), (32.0760, 34.7840), (32.0840, 34.7870),
    (32.0890, 34.7760), (32.0815, 34.7825), (32.0865, 34.7835),
]

_DEFECT_TYPES = ["pothole", "road_crack", "broken_light", "drainage_blocked", "sidewalk"]
_SEVERITIES = ["low", "medium", "high", "critical"]
_STATUSES = ["new", "verified", "assigned", "in_progress"]


async def seed(db: AsyncSession) -> None:
    result = await db.execute(select(User))
    if result.scalars().first():
        logger.info("Seed: already seeded, skipping")
        return

    # Users
    users = [
        User(username="admin",  full_name="מנהל מערכת", hashed_pw=hash_password("admin123"), role="admin"),
        User(username="yossi",  full_name="יוסי כהן",   hashed_pw=hash_password("field123"), role="field_team"),
        User(username="dana",   full_name="דנה לוי",    hashed_pw=hash_password("field123"), role="field_team"),
        User(username="demo",   full_name="Demo User",  hashed_pw=hash_password("demo123"),  role="viewer"),
    ]
    db.add_all(users)
    await db.flush()

    # Tickets + Detections
    for i, (lat, lng) in enumerate(_BASE_COORDS):
        dtype = _DEFECT_TYPES[i % len(_DEFECT_TYPES)]
        sev = _SEVERITIES[i % len(_SEVERITIES)]
        img_url, caption = _IMAGES[dtype]

        ticket = Ticket(
            defect_type=dtype, severity=sev, lat=lat, lng=lng,
            address=f"רחוב הרצל {i + 1}, תל אביב",
            status=random.choice(_STATUSES),
            detection_count=random.randint(1, 4),
        )
        db.add(ticket)
        await db.flush()

        length = round(random.uniform(20, 150), 1)
        width = round(random.uniform(10, 80), 1)
        depth = round(random.uniform(2, 15), 1)
        vol = round((length * width * depth) / 1_000_000, 6)
        area = round((length * width) / 10_000, 4)

        detection = Detection(
            defect_type=dtype, severity=sev, lat=lat, lng=lng,
            vehicle_id=f"TLV-{100 + i}", vehicle_model="Ford Transit Sensor v2",
            vehicle_speed_kmh=round(random.uniform(20, 60), 1),
            vehicle_heading_deg=round(random.uniform(0, 360), 1),
            reported_by="system",
            defect_length_cm=length,
            defect_width_cm=width,
            defect_depth_cm=depth,
            defect_volume_m3=vol,
            surface_area_m2=area,
            repair_material_m3=round(vol * 1.2, 6),
            ambient_temp_c=round(random.uniform(18, 35), 1),
            asphalt_temp_c=round(random.uniform(25, 45), 1),
            weather_condition=random.choice(["Clear", "Cloudy", "Partly Cloudy"]),
            wind_speed_kmh=round(random.uniform(5, 30), 1),
            humidity_pct=round(random.uniform(30, 80), 1),
            visibility_m=random.choice([500, 800, 1000]),
            image_url=img_url,
            image_caption=caption,
            notes="זוהה אוטומטית על ידי חיישן רכב",
            pipeline_status="done",
            ticket_id=ticket.id,
        )
        db.add(detection)

    await db.commit()
    logger.info("Seed complete")
