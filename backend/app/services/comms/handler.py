"""
Inbound WhatsApp message handler.
Resolves person → ticket → workflow engine → action.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import bus, Events
from app.models import Conversation, Person, Ticket
from app.services.comms.whatsapp import whatsapp_bot
from app.services.workflow.engine import WorkflowEngine

logger = logging.getLogger(__name__)


class InboundHandler:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.engine = WorkflowEngine(db)

    async def handle(self, parsed: dict[str, Any]) -> None:
        """
        Route an inbound WhatsApp message.
        parsed = {whatsapp_id, type, action?, text?, media_id?}
        """
        whatsapp_id = parsed.get("whatsapp_id")
        if not whatsapp_id:
            return

        person = await self._find_person(whatsapp_id)
        if not person:
            logger.info("Unknown WhatsApp sender: %s", whatsapp_id)
            await whatsapp_bot.send_text(whatsapp_id, "מספר זה אינו רשום במערכת.")
            return

        # Find active conversation
        conv = await self._find_conversation(person.id)
        if not conv:
            await whatsapp_bot.send_text(whatsapp_id, "אין לך משימות פעילות כרגע.")
            return

        ticket = await self.db.get(Ticket, conv.ticket_id)
        if not ticket:
            return

        msg_type = parsed.get("type")

        # ── Button press (action) ──────────────────────────────────────────
        if msg_type == "interactive":
            action = parsed.get("action", "")
            await self._handle_action(person, ticket, conv, action)

        # ── Photo upload ───────────────────────────────────────────────────
        elif msg_type in ("image", "document", "video") and conv.state == "waiting_photo":
            media_id = parsed.get("media_id", "")
            await self._handle_photo(person, ticket, conv, media_id)

        # ── Free text (not expected in normal flow) ────────────────────────
        elif msg_type == "text":
            text = parsed.get("text", "")
            await self._handle_text(person, ticket, conv, text)

    async def _handle_action(
        self,
        person: Person,
        ticket: Ticket,
        conv: Conversation,
        action: str,
    ) -> None:
        can, reason = await self.engine.can_act(ticket, person, action)
        if not can:
            await whatsapp_bot.send_text(person.whatsapp_id, f"❌ {reason}")
            return

        # If action advances workflow, check pending photo gates first
        import json
        current_step = await self.engine._get_open_step(ticket)
        if current_step:
            from app.services.workflow.protocol_loader import protocol_loader
            step_def = protocol_loader.get_step(ticket.city_id, ticket.defect_type, current_step.step_id)
            gates = step_def.get("required_gates", []) if step_def else []
            gate_data = json.loads(current_step.data_json or "{}")
            missing = [g for g in gates if g["key"] not in gate_data]

            if missing:
                # Transition conversation to waiting_photo
                conv.state = "waiting_photo"
                conv.pending_gates_json = json.dumps([g["key"] for g in missing], ensure_ascii=False)
                await self.db.flush()
                await whatsapp_bot.send_photo_request(person.whatsapp_id, missing[0]["label"])
                return

        try:
            await self.engine.advance(ticket, person, action)
            await self.db.commit()
            conv.state = "done"
            await self.db.flush()
            await whatsapp_bot.send_text(person.whatsapp_id, "✅ הפעולה בוצעה בהצלחה.")
        except Exception as exc:
            await self.db.rollback()
            logger.error("Workflow advance failed: %s", exc)
            await whatsapp_bot.send_text(person.whatsapp_id, f"שגיאה: {exc}")

    async def _handle_photo(
        self,
        person: Person,
        ticket: Ticket,
        conv: Conversation,
        media_id: str,
    ) -> None:
        import json

        current_step = await self.engine._get_open_step(ticket)
        if not current_step:
            return

        pending = json.loads(conv.pending_gates_json or "[]")
        if not pending:
            return

        # Upload first pending gate
        gate_key = pending[0]
        await self.engine.upload_gate_data(ticket, person, gate_key, {"media_id": media_id})
        await bus.emit(Events.ACTION_RECEIVED, {
            "city_id": ticket.city_id,
            "ticket_id": ticket.id,
            "gate_key": gate_key,
            "media_id": media_id,
        })

        pending = pending[1:]
        conv.pending_gates_json = json.dumps(pending)

        if pending:
            from app.services.workflow.protocol_loader import protocol_loader
            step_def = protocol_loader.get_step(ticket.city_id, ticket.defect_type, current_step.step_id)
            all_gates = step_def.get("required_gates", []) if step_def else []
            next_gate_def = next((g for g in all_gates if g["key"] == pending[0]), None)
            if next_gate_def:
                await whatsapp_bot.send_photo_request(person.whatsapp_id, next_gate_def["label"])
        else:
            conv.state = "waiting_action"
            await self.db.flush()
            await whatsapp_bot.send_text(person.whatsapp_id, "✅ כל הצילומים התקבלו. כעת תוכל לאשר את הפעולה.")

        await self.db.flush()

    async def _handle_text(
        self,
        person: Person,
        ticket: Ticket,
        conv: Conversation,
        text: str,
    ) -> None:
        # Inform user to use buttons
        await whatsapp_bot.send_text(
            person.whatsapp_id,
            "אנא השתמש בכפתורים למטה לביצוע פעולות. הערות חופשיות אינן נתמכות כרגע.",
        )

    async def _find_person(self, whatsapp_id: str) -> Person | None:
        result = await self.db.execute(
            select(Person).where(Person.whatsapp_id == whatsapp_id).where(Person.is_active == True)
        )
        return result.scalars().first()

    async def _find_conversation(self, person_id: int) -> Conversation | None:
        result = await self.db.execute(
            select(Conversation)
            .where(Conversation.person_id == person_id)
            .where(Conversation.state.notin_(["done"]))
            .order_by(Conversation.last_message_at.desc())
        )
        return result.scalars().first()
