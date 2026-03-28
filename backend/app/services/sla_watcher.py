"""
SLA Watcher — scans for timed-out workflow steps and escalates.
Also expires unverified tickets older than EXPIRY_DAYS days (never deletes).
Runs every 60 seconds via Celery Beat.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Ticket, WorkflowStep
from app.services.workflow.engine import WorkflowEngine

logger = logging.getLogger(__name__)

EXPIRY_DAYS = 7   # unverified tickets expire after this many days


async def check_sla_violations(db: AsyncSession) -> dict:
    """
    Find all open workflow steps past their deadline and escalate them.
    Returns summary of actions taken.
    """
    now = datetime.now(timezone.utc)

    result = await db.execute(
        select(WorkflowStep)
        .where(WorkflowStep.status == "open")
        .where(WorkflowStep.deadline_at.isnot(None))
        .where(WorkflowStep.deadline_at < now)
    )
    overdue_steps = result.scalars().all()

    if not overdue_steps:
        return {"checked": 0, "escalated": 0}

    engine = WorkflowEngine(db)
    escalated = 0

    for step in overdue_steps:
        ticket = await db.get(Ticket, step.ticket_id)
        if not ticket or ticket.status == "closed":
            continue
        try:
            await engine.escalate_step(ticket, step)
            escalated += 1
            logger.info(
                "SLA breach escalated: ticket=%d step=%s city=%s",
                ticket.id, step.step_id, ticket.city_id,
            )
        except Exception as exc:
            logger.error("SLA escalation failed for step %d: %s", step.id, exc)

    if escalated:
        await db.commit()

    return {"checked": len(overdue_steps), "escalated": escalated}


async def expire_old_tickets(db: AsyncSession) -> dict:
    """
    Mark unverified tickets older than EXPIRY_DAYS as 'expired'.
    Tickets are NEVER deleted — they are only status-changed.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=EXPIRY_DAYS)

    result = await db.execute(
        select(Ticket)
        .where(Ticket.status == "new")
        .where(Ticket.created_at < cutoff)
    )
    old_tickets = result.scalars().all()

    if not old_tickets:
        return {"expired": 0}

    for ticket in old_tickets:
        ticket.status = "expired"
        logger.info("Ticket %d expired (older than %d days, still unverified)", ticket.id, EXPIRY_DAYS)

    await db.commit()
    return {"expired": len(old_tickets)}
