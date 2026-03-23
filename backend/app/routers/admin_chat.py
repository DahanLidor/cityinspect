"""
Admin Chat — Claude-powered chat for system administrators.
Stream SSE responses back to the client.
"""
from __future__ import annotations

import json
import logging
from typing import AsyncGenerator

import anthropic
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import DbSession
from app.core.security import get_current_user
from app.models import Detection, Ticket, User, WorkflowStep

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class ChatMessage(BaseModel):
    role: str  # user | assistant
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    city_id: str = "tel-aviv"


async def _build_system_prompt(db: AsyncSession, city_id: str) -> str:
    """Build a system prompt with live DB stats as context."""
    # Quick stats
    ticket_count = (await db.execute(
        select(func.count(Ticket.id)).where(Ticket.city_id == city_id)
    )).scalar() or 0

    open_tickets = (await db.execute(
        select(func.count(Ticket.id))
        .where(Ticket.city_id == city_id)
        .where(Ticket.status.notin_(["closed"]))
    )).scalar() or 0

    sla_breached = (await db.execute(
        select(func.count(Ticket.id))
        .where(Ticket.city_id == city_id)
        .where(Ticket.sla_breached == True)
    )).scalar() or 0

    overdue_steps = (await db.execute(
        select(func.count(WorkflowStep.id))
        .where(WorkflowStep.city_id == city_id)
        .where(WorkflowStep.status == "open")
        .where(WorkflowStep.deadline_at.isnot(None))
    )).scalar() or 0

    return f"""אתה עוזר AI מנהלתי של מערכת CityInspect — מערכת ניהול תקלות תשתית עירונית.

עיר נוכחית: {city_id}

נתונים עדכניים:
- סה"כ טיקטים: {ticket_count}
- טיקטים פתוחים: {open_tickets}
- SLA שהופרו: {sla_breached}
- שלבים באיחור: {overdue_steps}

תפקידך:
- לענות על שאלות ניהוליות על מצב המערכת
- לנתח מגמות ולהציג המלצות
- לעזור בהבנת הנתונים
- לייעץ בנושאי אופטימיזציה של תהליכי עבודה

ענה תמיד בעברית, בצורה מקצועית וממוקדת."""


@router.post("/chat")
async def admin_chat(
    body: ChatRequest,
    db: DbSession,
    current_user: User = Depends(get_current_user),
):
    """
    Streaming chat endpoint for admin users.
    Returns Server-Sent Events.
    """
    if current_user.role not in ("admin", "city_manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="נדרשת הרשאת מנהל")

    api_key = getattr(settings, "anthropic_api_key", "") or ""
    if not api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY לא מוגדר",
        )

    system_prompt = await _build_system_prompt(db, body.city_id)
    messages = [{"role": m.role, "content": m.content} for m in body.messages]

    async def event_stream() -> AsyncGenerator[str, None]:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        try:
            async with client.messages.stream(
                model="claude-opus-4-6",
                max_tokens=2048,
                system=system_prompt,
                messages=messages,
            ) as stream:
                async for text_chunk in stream.text_stream:
                    yield f"data: {json.dumps({'text': text_chunk}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except anthropic.APIError as exc:
            logger.error("Anthropic API error: %s", exc)
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
