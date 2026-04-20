"""Reports router — JSON and CSV exports for tickets and city summaries."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.models import Detection, Ticket, User, WorkflowStep
from app.services.intelligence import CityIntelligenceEngine

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/reports", tags=["reports"])

_engine = CityIntelligenceEngine()

# ── Helpers ──────────────────────────────────────────────────────────────────


def _detection_to_dict(d: Detection) -> dict:
    return {
        "id": d.id,
        "detected_at": d.detected_at.isoformat() if d.detected_at else None,
        "defect_type": d.defect_type,
        "severity": d.severity,
        "lat": d.lat,
        "lng": d.lng,
        "image_url": d.image_url,
        "image_caption": d.image_caption,
        "notes": d.notes,
        "pipeline_status": d.pipeline_status,
        "vehicle_id": d.vehicle_id,
    }


def _step_to_dict(s: WorkflowStep) -> dict:
    return {
        "id": s.id,
        "step_id": s.step_id,
        "step_name": s.step_name,
        "status": s.status,
        "owner_role": s.owner_role,
        "opened_at": s.opened_at.isoformat() if s.opened_at else None,
        "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        "action_taken": s.action_taken,
        "sla_met": s.sla_met,
    }


# ── 1. Full ticket JSON report ──────────────────────────────────────────────


@router.get("/ticket/{ticket_id}/json")
async def ticket_json_report(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Full JSON report for a single ticket: detections, workflow steps, etc."""
    ticket: Optional[Ticket] = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    detections = [_detection_to_dict(d) for d in (ticket.detections or [])]
    steps = [_step_to_dict(s) for s in (ticket.workflow_steps or [])]

    return {
        "ticket": {
            "id": ticket.id,
            "city_id": ticket.city_id,
            "defect_type": ticket.defect_type,
            "severity": ticket.severity,
            "score": ticket.score,
            "status": ticket.status,
            "lat": ticket.lat,
            "lng": ticket.lng,
            "address": ticket.address,
            "detection_count": ticket.detection_count,
            "created_at": ticket.created_at.isoformat() if ticket.created_at else None,
            "updated_at": ticket.updated_at.isoformat() if ticket.updated_at else None,
            "sla_deadline": ticket.sla_deadline.isoformat() if ticket.sla_deadline else None,
            "sla_breached": ticket.sla_breached,
            "protocol_id": ticket.protocol_id,
            "current_step_id": ticket.current_step_id,
        },
        "detections": detections,
        "workflow_steps": steps,
        "detection_count": len(detections),
        "workflow_step_count": len(steps),
    }


# ── 2. City summary ─────────────────────────────────────────────────────────


@router.get("/city/{city_id}/summary")
async def city_summary(
    city_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """City health score, key metrics, trends and recommendations."""
    health = await _engine.compute_city_health(db, city_id)
    trends = await _engine.get_trends(db, city_id, months=6)

    return {
        **health,
        "trends": trends,
    }


# ── 3. City CSV export ──────────────────────────────────────────────────────

_CSV_COLUMNS = [
    "id",
    "defect_type",
    "severity",
    "score",
    "lat",
    "lng",
    "address",
    "status",
    "created_at",
    "detection_count",
]


@router.get("/city/{city_id}/csv")
async def city_csv_export(
    city_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Stream all tickets for *city_id* as a CSV download."""
    result = await db.execute(
        select(Ticket)
        .where(Ticket.city_id == city_id)
        .order_by(Ticket.created_at.desc())
    )
    tickets = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_CSV_COLUMNS)

    for t in tickets:
        writer.writerow([
            t.id,
            t.defect_type,
            t.severity,
            t.score,
            t.lat,
            t.lng,
            t.address,
            t.status,
            t.created_at.isoformat() if t.created_at else "",
            t.detection_count,
        ])

    buf.seek(0)
    filename = f"{city_id}_tickets.csv"

    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
