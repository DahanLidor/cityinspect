"""
Workflow Engine — enforces "הכדור" (ball) principle.

At any point exactly ONE person owns a ticket step.
No step can be skipped unless skip_allowed: true.
Actions must match allowed_actions for the current step.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import Events, bus
from app.models import AuditLog, Conversation, Person, Ticket, WorkflowStep
from app.services.workflow.protocol_loader import protocol_loader

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowError(Exception):
    """Raised when a workflow rule is violated."""


class WorkflowEngine:
    """
    Core engine for protocol-driven ticket lifecycle.

    Usage:
        engine = WorkflowEngine(db)
        await engine.open_ticket(ticket)
        can, reason = await engine.can_act(ticket, person, "approve")
        await engine.advance(ticket, person, "approve", data={"note": "ok"})
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Open first step ───────────────────────────────────────────────────────

    async def open_ticket(self, ticket: Ticket) -> WorkflowStep:
        """Initialize workflow: create first step and assign owner."""
        first = protocol_loader.get_first_step(ticket.city_id, ticket.defect_type)
        if not first:
            raise WorkflowError(f"No protocol for defect_type={ticket.defect_type}")

        owner = await self._find_person_for_role(ticket.city_id, first["owner_role"])
        deadline = self._calc_deadline(first)

        step = WorkflowStep(
            city_id=ticket.city_id,
            ticket_id=ticket.id,
            step_id=first["id"],
            step_name=first["name"],
            status="open",
            owner_role=first["owner_role"],
            owner_person_id=owner.id if owner else None,
            opened_at=_utcnow(),
            deadline_at=deadline,
            data_json="{}",
        )
        self.db.add(step)

        ticket.current_step_id = first["id"]
        ticket.protocol_id = ticket.defect_type
        if deadline:
            ticket.sla_deadline = deadline

        await self.db.flush()
        await self._audit(ticket, None, "step.opened", {"step_id": first["id"], "owner": owner.name if owner else "unassigned"})

        if first.get("message_template") and owner:
            await self._open_conversation(ticket, step, owner)

        await bus.emit(Events.STEP_OPENED, {
            "city_id": ticket.city_id,
            "ticket_id": ticket.id,
            "step_id": first["id"],
            "owner_person_id": owner.id if owner else None,
        })

        logger.info("Ticket %d opened at step %s (owner: %s)", ticket.id, first["id"], owner.name if owner else "?")
        return step

    # ── Validate action ────────────────────────────────────────────────────────

    async def can_act(
        self,
        ticket: Ticket,
        person: Person,
        action: str,
    ) -> tuple[bool, str]:
        """Returns (True, "") if person may perform action, else (False, reason)."""
        if not ticket.current_step_id:
            return False, "Ticket has no active step"

        step = await self._get_open_step(ticket)
        if not step:
            return False, "No open step found"

        protocol_step = protocol_loader.get_step(ticket.city_id, ticket.defect_type, step.step_id)
        if not protocol_step:
            return False, f"Unknown step: {step.step_id}"

        # Role check — always enforced
        if person.role != step.owner_role:
            return False, f"This step belongs to {step.owner_role}, you are {person.role}"

        # Ownership check — if a specific person is assigned, only they may act
        if step.owner_person_id and step.owner_person_id != person.id:
            return False, f"This step is assigned to person #{step.owner_person_id}, not you"

        # Action whitelist
        allowed = protocol_step.get("allowed_actions", [])
        if action not in allowed:
            return False, f"Action '{action}' not allowed here. Allowed: {allowed}"

        # Gates check (e.g. photo required)
        gates = protocol_step.get("required_gates", [])
        current_data = json.loads(step.data_json or "{}")
        missing_gates = [g["label"] for g in gates if g["key"] not in current_data]
        if missing_gates and action in protocol_step.get("required_before_advance", []):
            return False, f"Missing required gates: {', '.join(missing_gates)}"

        return True, ""

    # ── Advance step ──────────────────────────────────────────────────────────

    async def advance(
        self,
        ticket: Ticket,
        person: Person,
        action: str,
        data: dict[str, Any] | None = None,
    ) -> WorkflowStep | None:
        """Complete current step and open next."""
        can, reason = await self.can_act(ticket, person, action)
        if not can:
            raise WorkflowError(reason)

        current_step = await self._get_open_step(ticket)
        protocol_step = protocol_loader.get_step(ticket.city_id, ticket.defect_type, current_step.step_id)

        # Handle reject_redo — jump back
        if action == "reject_redo" and protocol_step.get("on_reject_redo"):
            return await self._goto_step(ticket, person, protocol_step["on_reject_redo"], data)

        # Complete current step
        now = _utcnow()
        current_step.status = "done"
        current_step.completed_at = now
        current_step.completed_by_id = person.id
        current_step.action_taken = action

        # Response time metrics (handle timezone-naive datetimes from SQLite)
        def _tz(dt):
            if dt is None:
                return None
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

        if current_step.opened_at:
            delta = now - _tz(current_step.opened_at)
            current_step.response_time_min = round(delta.total_seconds() / 60, 1)
        if current_step.deadline_at:
            current_step.sla_met = now <= _tz(current_step.deadline_at)

        if data:
            existing = json.loads(current_step.data_json or "{}")
            existing.update(data)
            current_step.data_json = json.dumps(existing, ensure_ascii=False)

        await self._audit(ticket, person, "step.completed", {"step_id": current_step.step_id, "action": action})
        await bus.emit(Events.STEP_COMPLETED, {
            "city_id": ticket.city_id,
            "ticket_id": ticket.id,
            "step_id": current_step.step_id,
            "action": action,
            "completed_by_id": person.id,
        })

        # Is this the final step?
        if protocol_step.get("final_step"):
            ticket.status = "closed"
            ticket.current_step_id = None
            await self._audit(ticket, person, "ticket.closed", {})
            await bus.emit(Events.TICKET_CLOSED, {"city_id": ticket.city_id, "ticket_id": ticket.id})
            logger.info("Ticket %d closed by %s", ticket.id, person.name)
            await self.db.flush()
            return None

        # Open next step
        next_step_def = protocol_loader.get_next_step(ticket.city_id, ticket.defect_type, current_step.step_id)
        if not next_step_def:
            logger.warning("No next step after %s for ticket %d", current_step.step_id, ticket.id)
            return None

        next_step = await self._open_step(ticket, next_step_def)

        # Auto-advance steps with auto_trigger: true (up to 3 to avoid infinite loops)
        for _ in range(3):
            if not next_step_def.get("auto_trigger"):
                break
            auto_action = (next_step_def.get("required_before_advance") or next_step_def.get("allowed_actions") or [None])[0]
            if not auto_action:
                break
            owner = await self.db.get(Person, next_step.owner_person_id) if next_step.owner_person_id else None
            if not owner:
                owner = await self._find_person_for_role(ticket.city_id, next_step_def["owner_role"])
            if not owner:
                break  # no one to assign — leave step open

            now_auto = _utcnow()
            next_step.status = "done"
            next_step.completed_at = now_auto
            next_step.completed_by_id = owner.id
            next_step.action_taken = auto_action
            opened = next_step.opened_at
            if opened:
                oa = opened if opened.tzinfo else opened.replace(tzinfo=timezone.utc)
                next_step.response_time_min = round((now_auto - oa).total_seconds() / 60, 1)
            deadline = next_step.deadline_at
            if deadline:
                dl = deadline if deadline.tzinfo else deadline.replace(tzinfo=timezone.utc)
                next_step.sla_met = now_auto <= dl

            await self._audit(ticket, owner, "step.auto_completed", {
                "step_id": next_step.step_id,
                "action": auto_action,
            })
            await bus.emit(Events.STEP_COMPLETED, {
                "city_id": ticket.city_id,
                "ticket_id": ticket.id,
                "step_id": next_step.step_id,
                "action": auto_action,
                "completed_by_id": owner.id,
            })

            if next_step_def.get("final_step"):
                ticket.status = "closed"
                ticket.current_step_id = None
                await self.db.flush()
                return None

            after_def = protocol_loader.get_next_step(ticket.city_id, ticket.defect_type, next_step.step_id)
            if not after_def:
                break
            next_step = await self._open_step(ticket, after_def)
            next_step_def = after_def

        return next_step

    # ── Skip step ─────────────────────────────────────────────────────────────

    async def skip_step(
        self,
        ticket: Ticket,
        approver: Person,
        reason: str,
    ) -> WorkflowStep | None:
        current_step = await self._get_open_step(ticket)
        protocol_step = protocol_loader.get_step(ticket.city_id, ticket.defect_type, current_step.step_id)

        if not protocol_step.get("skip_allowed", False):
            raise WorkflowError(f"Step '{current_step.step_id}' cannot be skipped (skip_allowed: false)")

        current_step.status = "skipped"
        current_step.completed_at = _utcnow()
        current_step.skip_reason = reason
        current_step.skip_approved_by_id = approver.id

        await self._audit(ticket, approver, "step.skipped", {"step_id": current_step.step_id, "reason": reason})
        await bus.emit(Events.STEP_SKIPPED, {
            "city_id": ticket.city_id,
            "ticket_id": ticket.id,
            "step_id": current_step.step_id,
        })

        next_def = protocol_loader.get_next_step(ticket.city_id, ticket.defect_type, current_step.step_id)
        if not next_def:
            return None
        return await self._open_step(ticket, next_def)

    # ── Escalate (timeout) ────────────────────────────────────────────────────

    async def escalate_step(self, ticket: Ticket, step: WorkflowStep) -> None:
        """Called by SLA watcher when a step times out."""
        protocol_step = protocol_loader.get_step(ticket.city_id, ticket.defect_type, step.step_id)
        on_timeout = protocol_step.get("on_timeout", "escalate_up") if protocol_step else "escalate_up"

        ticket.sla_breached = True
        step.status = "timeout"
        step.completed_at = _utcnow()

        await self._audit(ticket, None, "step.timeout", {
            "step_id": step.step_id,
            "on_timeout": on_timeout,
        })
        await bus.emit(Events.STEP_TIMEOUT, {
            "city_id": ticket.city_id,
            "ticket_id": ticket.id,
            "step_id": step.step_id,
            "on_timeout": on_timeout,
        })
        await bus.emit(Events.SLA_BREACH, {
            "city_id": ticket.city_id,
            "ticket_id": ticket.id,
        })

        if on_timeout == "escalate_up":
            await self._escalate_to_manager(ticket, step)
        elif on_timeout == "reassign":
            await self._reassign_step(ticket, step)

        await self.db.flush()

    # ── Upload gate data (photo, measurement) ─────────────────────────────────

    async def upload_gate_data(
        self,
        ticket: Ticket,
        person: Person,
        gate_key: str,
        value: Any,
    ) -> None:
        step = await self._get_open_step(ticket)
        if not step:
            raise WorkflowError("No open step")
        if step.owner_person_id and step.owner_person_id != person.id:
            raise WorkflowError("You do not own this step")

        data = json.loads(step.data_json or "{}")
        data[gate_key] = value
        step.data_json = json.dumps(data, ensure_ascii=False)
        await self.db.flush()
        logger.info("Gate data uploaded: ticket=%d step=%s key=%s", ticket.id, step.step_id, gate_key)

    # ── Private helpers ────────────────────────────────────────────────────────

    async def _get_open_step(self, ticket: Ticket) -> WorkflowStep | None:
        result = await self.db.execute(
            select(WorkflowStep)
            .where(WorkflowStep.ticket_id == ticket.id)
            .where(WorkflowStep.status == "open")
            .order_by(WorkflowStep.opened_at.desc())
        )
        return result.scalars().first()

    async def _open_step(self, ticket: Ticket, step_def: dict) -> WorkflowStep:
        owner = await self._find_person_for_role(ticket.city_id, step_def["owner_role"])
        deadline = self._calc_deadline(step_def)

        step = WorkflowStep(
            city_id=ticket.city_id,
            ticket_id=ticket.id,
            step_id=step_def["id"],
            step_name=step_def["name"],
            status="open",
            owner_role=step_def["owner_role"],
            owner_person_id=owner.id if owner else None,
            opened_at=_utcnow(),
            deadline_at=deadline,
            data_json="{}",
        )
        self.db.add(step)
        ticket.current_step_id = step_def["id"]

        await self.db.flush()

        await self._audit(ticket, None, "step.opened", {
            "step_id": step_def["id"],
            "owner": owner.name if owner else "unassigned",
        })

        if step_def.get("message_template") and owner:
            await self._open_conversation(ticket, step, owner)

        await bus.emit(Events.STEP_OPENED, {
            "city_id": ticket.city_id,
            "ticket_id": ticket.id,
            "step_id": step_def["id"],
            "owner_person_id": owner.id if owner else None,
        })

        logger.info("Step opened: ticket=%d step=%s owner=%s", ticket.id, step_def["id"], owner.name if owner else "?")
        return step

    async def _goto_step(
        self,
        ticket: Ticket,
        person: Person,
        target_step_id: str,
        data: dict | None,
    ) -> WorkflowStep:
        """Jump back to a specific step (e.g. on reject_redo)."""
        # Mark current step as rejected
        current = await self._get_open_step(ticket)
        if current:
            current.status = "done"
            current.completed_at = _utcnow()
            current.completed_by_id = person.id
            current.action_taken = "reject_redo"

        step_def = protocol_loader.get_step(ticket.city_id, ticket.defect_type, target_step_id)
        if not step_def:
            raise WorkflowError(f"Target step not found: {target_step_id}")

        await self._audit(ticket, person, "step.redo", {"target": target_step_id})
        return await self._open_step(ticket, step_def)

    async def _find_person_for_role(self, city_id: str, role: str) -> Person | None:
        result = await self.db.execute(
            select(Person)
            .where(Person.city_id == city_id)
            .where(Person.role == role)
            .where(Person.is_active)
            .order_by(Person.current_workload.asc())
        )
        return result.scalars().first()

    async def _escalate_to_manager(self, ticket: Ticket, timed_out_step: WorkflowStep) -> None:
        if not timed_out_step.owner_person_id:
            return
        owner = await self.db.get(Person, timed_out_step.owner_person_id)
        if not owner or not owner.manager_id:
            logger.warning("No manager to escalate to for person %s", timed_out_step.owner_person_id)
            return

        manager = await self.db.get(Person, owner.manager_id)
        if not manager:
            return

        # Re-open step assigned to manager
        step_def = protocol_loader.get_step(ticket.city_id, ticket.defect_type, timed_out_step.step_id)
        if not step_def:
            return

        new_step = WorkflowStep(
            city_id=ticket.city_id,
            ticket_id=ticket.id,
            step_id=timed_out_step.step_id,
            step_name=timed_out_step.step_name + " (הסלמה)",
            status="open",
            owner_role=manager.role,
            owner_person_id=manager.id,
            opened_at=_utcnow(),
            deadline_at=self._calc_deadline(step_def),
            data_json="{}",
        )
        self.db.add(new_step)
        ticket.current_step_id = timed_out_step.step_id

        await bus.emit(Events.ESCALATION_TRIGGERED, {
            "city_id": ticket.city_id,
            "ticket_id": ticket.id,
            "escalated_to_id": manager.id,
            "escalated_to_name": manager.name,
        })
        logger.info("Ticket %d escalated to %s (%s)", ticket.id, manager.name, manager.role)

    async def _reassign_step(self, ticket: Ticket, timed_out_step: WorkflowStep) -> None:
        """Reassign timed-out step to another person with same role."""
        result = await self.db.execute(
            select(Person)
            .where(Person.city_id == ticket.city_id)
            .where(Person.role == timed_out_step.owner_role)
            .where(Person.is_active)
            .where(Person.id != timed_out_step.owner_person_id)
            .order_by(Person.current_workload.asc())
        )
        new_owner = result.scalars().first()
        if not new_owner:
            logger.warning("No alternative assignee for role=%s ticket=%d", timed_out_step.owner_role, ticket.id)
            return

        step_def = protocol_loader.get_step(ticket.city_id, ticket.defect_type, timed_out_step.step_id)
        new_step = WorkflowStep(
            city_id=ticket.city_id,
            ticket_id=ticket.id,
            step_id=timed_out_step.step_id,
            step_name=timed_out_step.step_name + " (שיבוץ מחדש)",
            status="open",
            owner_role=timed_out_step.owner_role,
            owner_person_id=new_owner.id,
            opened_at=_utcnow(),
            deadline_at=self._calc_deadline(step_def) if step_def else None,
            data_json="{}",
        )
        self.db.add(new_step)
        ticket.current_step_id = timed_out_step.step_id
        logger.info("Ticket %d reassigned from %d to %s", ticket.id, timed_out_step.owner_person_id or 0, new_owner.name)

    async def _open_conversation(self, ticket: Ticket, step: WorkflowStep, person: Person) -> None:
        conv = Conversation(
            city_id=ticket.city_id,
            person_id=person.id,
            ticket_id=ticket.id,
            step_id=step.step_id,
            state="waiting_action",
            pending_gates_json="[]",
        )
        self.db.add(conv)

    async def _audit(
        self,
        ticket: Ticket,
        actor: Person | None,
        action: str,
        data: dict,
    ) -> None:
        log = AuditLog(
            city_id=ticket.city_id,
            ticket_id=ticket.id,
            step_id=ticket.current_step_id,
            actor_type="person" if actor else "system",
            actor_id=actor.id if actor else None,
            actor_name=actor.name if actor else "system",
            action=action,
            data_json=json.dumps(data, ensure_ascii=False, default=str),
        )
        self.db.add(log)

    @staticmethod
    def _calc_deadline(step_def: dict) -> datetime | None:
        hours = step_def.get("timeout_hours")
        if hours:
            return _utcnow() + timedelta(hours=hours)
        return None
