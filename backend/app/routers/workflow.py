"""
Workflow routes — step actions, ticket timeline.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import DbSession
from app.core.security import get_current_user
from app.models import AuditLog, Person, Ticket, User, WorkflowStep
from app.services.workflow.engine import WorkflowEngine, WorkflowError
from app.services.workflow.protocol_loader import protocol_loader

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workflow", tags=["workflow"])


class ActionRequest(BaseModel):
    action: str
    person_id: int
    data: dict | None = None
    note: str | None = None


class StepOut(BaseModel):
    id: int
    step_id: str
    step_name: str
    status: str
    owner_role: str
    owner_person_id: int | None
    opened_at: datetime
    deadline_at: datetime | None
    completed_at: datetime | None
    action_taken: str | None
    data: dict


class AuditEntry(BaseModel):
    id: int
    action: str
    actor_name: str
    actor_type: str
    step_id: str | None
    data: dict
    timestamp: datetime


@router.post("/tickets/{ticket_id}/action")
async def perform_action(
    ticket_id: int,
    body: ActionRequest,
    db: DbSession,
    _: User = Depends(get_current_user),
):
    """Perform a workflow action on a ticket step."""
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    person = await db.get(Person, body.person_id)
    if not person:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Person not found")

    engine = WorkflowEngine(db)
    data = body.data or {}
    if body.note:
        data["note"] = body.note

    try:
        step = await engine.advance(ticket, person, body.action, data=data if data else None)
        await db.commit()
        return {
            "status": "ok",
            "next_step": step.step_id if step else None,
            "ticket_status": ticket.status,
        }
    except WorkflowError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post("/tickets/{ticket_id}/open")
async def open_ticket_workflow(
    ticket_id: int,
    db: DbSession,
    _: User = Depends(get_current_user),
):
    """Initialize workflow for a ticket (creates first step)."""
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    if ticket.current_step_id:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Workflow already started")

    engine = WorkflowEngine(db)
    try:
        step = await engine.open_ticket(ticket)
        await db.commit()
        return {"step_id": step.step_id, "owner_person_id": step.owner_person_id}
    except WorkflowError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/tickets/{ticket_id}/steps", response_model=list[StepOut])
async def get_ticket_steps(
    ticket_id: int,
    db: DbSession,
    _: User = Depends(get_current_user),
):
    """Full timeline of all workflow steps for a ticket."""
    result = await db.execute(
        select(WorkflowStep)
        .where(WorkflowStep.ticket_id == ticket_id)
        .order_by(WorkflowStep.opened_at.asc())
    )
    steps = result.scalars().all()
    return [
        StepOut(
            id=s.id,
            step_id=s.step_id,
            step_name=s.step_name,
            status=s.status,
            owner_role=s.owner_role,
            owner_person_id=s.owner_person_id,
            opened_at=s.opened_at,
            deadline_at=s.deadline_at,
            completed_at=s.completed_at,
            action_taken=s.action_taken,
            data=json.loads(s.data_json or "{}"),
        )
        for s in steps
    ]


@router.get("/tickets/{ticket_id}/audit", response_model=list[AuditEntry])
async def get_ticket_audit(
    ticket_id: int,
    db: DbSession,
    _: User = Depends(get_current_user),
):
    """Immutable audit log for a ticket."""
    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.ticket_id == ticket_id)
        .order_by(AuditLog.timestamp.asc())
    )
    logs = result.scalars().all()
    return [
        AuditEntry(
            id=lg.id,
            action=lg.action,
            actor_name=lg.actor_name,
            actor_type=lg.actor_type,
            step_id=lg.step_id,
            data=json.loads(lg.data_json or "{}"),
            timestamp=lg.timestamp,
        )
        for lg in logs
    ]


@router.get("/tickets/{ticket_id}/can-act")
async def check_can_act(
    ticket_id: int,
    person_id: int,
    action: str,
    db: DbSession,
    _: User = Depends(get_current_user),
):
    """Check if a person may perform an action on the current step."""
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(status.HTTP_404_NOT_FOUND)

    engine = WorkflowEngine(db)
    can, reason = await engine.can_act(ticket, person, action)
    return {"can_act": can, "reason": reason}


@router.post("/tickets/{ticket_id}/verify")
async def verify_ticket(
    ticket_id: int,
    db: DbSession,
    _: User = Depends(get_current_user),
):
    """
    One-click verify: opens workflow (if not started) and auto-advances
    all steps until the first non-auto-trigger step that needs a real person.
    Called from the dashboard 'אמת' button.
    """
    ticket = await db.get(Ticket, ticket_id)
    if not ticket:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Ticket not found")

    engine = WorkflowEngine(db)

    # Open workflow if not yet started
    if not ticket.current_step_id:
        try:
            await engine.open_ticket(ticket)
            await db.commit()
        except WorkflowError as exc:
            await db.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    # Auto-advance the current step if it is the first step (manager_approval)
    # using the assigned person (or the first available work_manager)
    from sqlalchemy import select as sa_select
    open_step_result = await db.execute(
        sa_select(WorkflowStep)
        .where(WorkflowStep.ticket_id == ticket_id)
        .where(WorkflowStep.status == "open")
        .order_by(WorkflowStep.opened_at.desc())
    )
    open_step = open_step_result.scalars().first()
    if not open_step:
        return {"status": "ok", "message": "Workflow already completed", "ticket_status": ticket.status}

    # Find a person with the right role to approve
    person_id = open_step.owner_person_id
    if not person_id:
        # Try the ticket's city first, then any city (fallback for demo/default city)
        for city_filter in [ticket.city_id, None]:
            q = sa_select(Person).where(Person.role == open_step.owner_role).where(Person.is_active == True)
            if city_filter is not None:
                q = q.where(Person.city_id == city_filter)
            mgr_result = await db.execute(q)
            mgr = mgr_result.scalars().first()
            if mgr:
                person_id = mgr.id
                break

    if not person_id:
        # No person found but workflow is open — update status and return
        ticket.status = "verified"
        await db.commit()
        return {"status": "ok", "message": "Verified (no assignee found)", "current_step": open_step.step_id}

    person = await db.get(Person, person_id)
    if not person:
        ticket.status = "verified"
        await db.commit()
        return {"status": "ok", "message": "Verified", "current_step": open_step.step_id}

    # Advance with approve action
    try:
        next_step = await engine.advance(ticket, person, "approve", data={"note": "אומת מהדאשבורד"})
        ticket.status = "verified"
        await db.commit()
        return {
            "status": "ok",
            "next_step": next_step.step_id if next_step else None,
            "ticket_status": ticket.status,
        }
    except WorkflowError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.get("/protocol/{city_id}/{defect_type}")
async def get_protocol(
    city_id: str,
    defect_type: str,
    _: User = Depends(get_current_user),
):
    """Return the full protocol definition for a city+defect_type."""
    protocol = protocol_loader.load(city_id, defect_type)
    if not protocol:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Protocol not found")
    return protocol
