"""
Ticket routes: list (paginated + filtered), get, patch.
"""
from __future__ import annotations

import math
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.models import Ticket, User
from app.schemas import TicketListResponse, TicketOut, TicketUpdate
from app.ws.hub import hub

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["tickets"])


@router.get("/tickets", response_model=TicketListResponse)
async def list_tickets(
    status_filter: Optional[str] = Query(None, alias="status"),
    severity: Optional[str] = Query(None),
    defect_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketListResponse:
    q = select(Ticket)

    if status_filter:
        statuses = [s.strip() for s in status_filter.split(",")]
        q = q.where(Ticket.status.in_(statuses))
    if severity:
        q = q.where(Ticket.severity == severity)
    if defect_type:
        q = q.where(Ticket.defect_type == defect_type)

    # Total count
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginated result
    offset = (page - 1) * page_size
    q = q.order_by(Ticket.created_at.desc()).offset(offset).limit(page_size)
    result = await db.execute(q)
    tickets = result.scalars().all()

    return TicketListResponse(
        items=[TicketOut.model_validate(t) for t in tickets],
        total=total,
        page=page,
        page_size=page_size,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/tickets/{ticket_id}", response_model=TicketOut)
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ticket not found")
    return TicketOut.model_validate(ticket)


@router.patch("/tickets/{ticket_id}", response_model=TicketOut)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TicketOut:
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    if body.status is not None:
        ticket.status = body.status
    if body.severity is not None:
        ticket.severity = body.severity

    await db.commit()
    await db.refresh(ticket)

    await hub.broadcast({"type": "ticket_updated", "ticket_id": ticket.id, "status": ticket.status})
    return TicketOut.model_validate(ticket)
