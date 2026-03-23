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
from app.models import Detection, Ticket, User, WorkflowStep
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

    # SLA breaches
    sla_result = await db.execute(
        select(func.count(Ticket.id)).where(Ticket.sla_breached == True)
    )
    sla_breached = sla_result.scalar() or 0

    # Overdue open steps
    now = datetime.now(timezone.utc)
    overdue_result = await db.execute(
        select(func.count(WorkflowStep.id))
        .where(WorkflowStep.status == "open")
        .where(WorkflowStep.deadline_at.isnot(None))
        .where(WorkflowStep.deadline_at < now)
    )
    overdue_steps = overdue_result.scalar() or 0

    # Detections last hour (approximate from ticket updated_at)
    det_result = await db.execute(select(Detection))
    detections = det_result.scalars().all()
    one_hour_ago = datetime.now(timezone.utc).replace(microsecond=0)
    det_last_hour = sum(
        1 for d in detections
        if d.detected_at and (now - d.detected_at).total_seconds() < 3600
    )

    today = date.today()
    open_count = sum(1 for t in tickets if t.status not in ("resolved", "closed"))
    critical_count = sum(1 for t in tickets if t.severity == "critical" and t.status not in ("resolved", "closed"))
    in_progress = sum(1 for t in tickets if t.status == "in_progress")

    return StatsResponse(
        total_tickets=len(tickets),
        open_tickets=open_count,
        critical_tickets=critical_count,
        resolved_today=sum(
            1 for t in tickets
            if t.status in ("resolved", "closed") and t.updated_at and t.updated_at.date() == today
        ),
        sla_breached=sla_breached,
        overdue_steps=overdue_steps,
        by_type={dt: sum(1 for t in tickets if t.defect_type == dt) for dt in _DEFECT_TYPES},
        by_status={s: sum(1 for t in tickets if t.status == s) for s in _STATUSES},
        by_severity={sv: sum(1 for t in tickets if t.severity == sv) for sv in _SEVERITIES},
        # Legacy compat
        total_open=open_count,
        critical_count=critical_count,
        in_progress=in_progress,
        detections_last_hour=det_last_hour,
        detections_per_hour=[{"hour": i, "count": 0} for i in range(24)],
    )
