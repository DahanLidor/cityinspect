"""
Event Bus — Redis Streams.
כל service מדבר דרך events בלבד.

Usage:
  await bus.emit("ticket.created", {"ticket_id": 1, "city_id": "tel-aviv"})
  await bus.subscribe("ticket.created", handler)
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Event definitions ─────────────────────────────────────────────────────────

class Events:
    TICKET_CREATED       = "ticket.created"
    TICKET_UPDATED       = "ticket.updated"
    TICKET_CLOSED        = "ticket.closed"

    PIPELINE_STARTED     = "pipeline.started"
    PIPELINE_COMPLETED   = "pipeline.completed"

    STEP_OPENED          = "step.opened"
    STEP_COMPLETED       = "step.completed"
    STEP_TIMEOUT         = "step.timeout"
    STEP_SKIPPED         = "step.skipped"

    ACTION_RECEIVED      = "action.received"

    WORKORDER_CREATED    = "workorder.created"
    WORKORDER_ASSIGNED   = "workorder.assigned"

    SLA_WARNING          = "sla.warning"
    SLA_BREACH           = "sla.breach"
    ESCALATION_TRIGGERED = "escalation.triggered"

    MESSAGE_SENT         = "message.sent"
    MESSAGE_RECEIVED     = "message.received"


# ── Bus ───────────────────────────────────────────────────────────────────────

class EventBus:
    """
    Thin wrapper around Redis Streams.
    emit()     → XADD to stream
    subscribe()→ XREAD consumer group loop
    """

    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None
        self._handlers: dict[str, list[Callable]] = {}
        self._running = False

    async def connect(self) -> None:
        self._redis = await aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
        logger.info("EventBus connected to Redis")

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()

    async def emit(self, event: str, payload: dict[str, Any]) -> str:
        """Publish event to stream. Returns message id."""
        if not self._redis:
            logger.warning("EventBus not connected — event dropped: %s", event)
            return ""
        try:
            data = {"event": event, "payload": json.dumps(payload, ensure_ascii=False, default=str)}
            msg_id = await self._redis.xadd(f"cityinspect:{event}", data)
            logger.debug("Event emitted: %s → %s", event, msg_id)
            return msg_id
        except Exception as exc:
            logger.warning("EventBus emit failed — event dropped: %s (%s)", event, exc)
            return ""

    def on(self, event: str) -> Callable:
        """Decorator: register async handler for event."""
        def decorator(fn: Callable) -> Callable:
            self._handlers.setdefault(event, []).append(fn)
            return fn
        return decorator

    async def _listen(self, event: str, group: str = "workers") -> None:
        stream = f"cityinspect:{event}"
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        except Exception:
            pass  # group already exists

        while self._running:
            try:
                messages = await self._redis.xreadgroup(
                    group, "worker-1", {stream: ">"}, count=10, block=500
                )
                for _, msgs in (messages or []):
                    for msg_id, data in msgs:
                        payload = json.loads(data.get("payload", "{}"))
                        for handler in self._handlers.get(event, []):
                            try:
                                await handler(payload)
                            except Exception as exc:
                                logger.error("Handler error for %s: %s", event, exc)
                        await self._redis.xack(stream, group, msg_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("EventBus listen error on %s: %s", event, exc)
                await asyncio.sleep(1)

    async def start_listeners(self) -> None:
        self._running = True
        for event in self._handlers:
            asyncio.create_task(self._listen(event))
        logger.info("EventBus listeners started for: %s", list(self._handlers.keys()))

    async def stop(self) -> None:
        self._running = False


# Module-level singleton
bus = EventBus()
