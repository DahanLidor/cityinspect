"""
Agent 3: Deduplication — GPS distance + time-window check.
Improved: considers image hash similarity in addition to GPS proximity.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

# Within-ticket proximity threshold for "same spot" duplicate detection
_DEDUP_RADIUS_M = 5.0


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def agent_dedup(
    db: AsyncSession,
    detection_id: int,
    lat: float,
    lng: float,
    image_hash: str,
    ticket_id: int,
) -> Dict[str, Any]:
    """
    Determine whether a new detection is a duplicate.

    Duplicate criteria (ANY of):
    1. GPS distance < 5 m AND captured within 2 hours of another detection in the same ticket
    2. Identical image hash (exact same photo submitted twice)
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)

    result = await db.execute(
        text(
            "SELECT id, lat, lng, image_hash, detected_at "
            "FROM detections WHERE ticket_id = :tid AND id != :did"
        ),
        {"tid": ticket_id, "did": detection_id},
    )
    others = result.fetchall()

    for row in others:
        # --- Image hash match ---
        if image_hash and row.image_hash and image_hash == row.image_hash:
            logger.info("Dedup: exact image hash match", extra={"duplicate_of": row.id})
            return {
                "is_duplicate": True,
                "duplicate_of": row.id,
                "distance_m": 0.0,
                "reason": "identical_image",
                "action": "keep_newest",
            }

        # --- GPS + time proximity ---
        dist = _haversine(lat, lng, row.lat, row.lng)
        detected_at = row.detected_at
        # Handle both naive and aware datetimes
        if detected_at and detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=timezone.utc)

        recently = detected_at and detected_at >= cutoff if detected_at else False

        if dist < _DEDUP_RADIUS_M and recently:
            logger.info("Dedup: GPS+time duplicate", extra={"duplicate_of": row.id, "distance_m": round(dist, 1)})
            return {
                "is_duplicate": True,
                "duplicate_of": row.id,
                "distance_m": round(dist, 1),
                "reason": f"מרחק {round(dist, 1)} מ׳ מדיווח #{row.id} בתוך חלון הזמן",
                "action": "keep_newest",
            }

    return {
        "is_duplicate": False,
        "duplicate_of": None,
        "distance_m": None,
        "reason": "אין כפילות",
        "action": "keep",
    }
