"""
Ticket business logic: find-or-create, severity escalation, Haversine dedup.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Ticket

settings = get_settings()
logger = get_logger(__name__)

_SEVERITY_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return distance in metres between two WGS-84 points."""
    R = 6_371_000
    p = math.pi / 180
    dlat = (lat2 - lat1) * p
    dlng = (lng2 - lng1) * p
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin(dlng / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def find_or_create_ticket(
    db: AsyncSession,
    defect_type: str,
    severity: str,
    lat: float,
    lng: float,
    address: str,
) -> Tuple[Ticket, bool]:
    """
    Returns (ticket, is_new).
    Searches for an open ticket of the same type within GPS_RADIUS metres.
    Duplicate time-window: ignores tickets resolved more than 48 h ago (they
    become a new issue) — handled automatically because we filter status != resolved.
    """
    radius = settings.duplicate_gps_radius_m
    cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.duplicate_time_window_hours)

    result = await db.execute(
        select(Ticket).where(
            Ticket.defect_type == defect_type,
            Ticket.status != "resolved",
            Ticket.created_at >= cutoff,
        )
    )
    candidates = result.scalars().all()

    best: Optional[Ticket] = None
    best_dist = float("inf")
    for t in candidates:
        d = haversine(lat, lng, t.lat, t.lng)
        if d < radius and d < best_dist:
            best = t
            best_dist = d

    if best:
        best.detection_count += 1
        if _SEVERITY_ORDER.get(severity, 0) > _SEVERITY_ORDER.get(best.severity, 0):
            best.severity = severity
        logger.info("Existing ticket updated", extra={"ticket_id": best.id, "distance_m": round(best_dist, 1)})
        return best, False

    ticket = Ticket(defect_type=defect_type, severity=severity, lat=lat, lng=lng, address=address)
    db.add(ticket)
    await db.flush()  # get id without committing
    logger.info("New ticket created", extra={"ticket_id": ticket.id})
    return ticket, True
