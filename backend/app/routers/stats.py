"""
Stats summary route.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import Ticket, User
from app.schemas import StatsResponse

router = APIRouter(prefix="/api/v1", tags=["stats"])

_DEFECT_TYPES = ["pothole", "road_crack", "broken_light", "drainage_blocked", "sidewalk"]
_STATUSES = ["new", "verified", "assigned", "in_progress", "resolved"]
_SEVERITIES = ["low", "medium", "high", "critical"]


@router.get("/stats/summary", response_model=StatsResponse)
async def stats_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StatsResponse:
    result = await db.execute(select(Ticket))
    tickets = result.scalars().all()

    today = date.today()

    return StatsResponse(
        total_tickets=len(tickets),
        open_tickets=sum(1 for t in tickets if t.status != "resolved"),
        critical_tickets=sum(1 for t in tickets if t.severity == "critical" and t.status != "resolved"),
        resolved_today=sum(
            1 for t in tickets
            if t.status == "resolved" and t.updated_at and t.updated_at.date() == today
        ),
        by_type={dt: sum(1 for t in tickets if t.defect_type == dt) for dt in _DEFECT_TYPES},
        by_status={s: sum(1 for t in tickets if t.status == s) for s in _STATUSES},
        by_severity={sv: sum(1 for t in tickets if t.severity == sv) for sv in _SEVERITIES},
    )
