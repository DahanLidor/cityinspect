"""Enterprise webhook dispatcher — signs and POSTs event payloads to registered URLs."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models import SystemConfig

logger = get_logger(__name__)

# Supported event types
WEBHOOK_EVENTS = frozenset({
    "ticket.created",
    "ticket.scored",
    "ticket.severity_changed",
    "ticket.resolved",
    "sla.breached",
})


def _sign_payload(payload_bytes: bytes, secret: str) -> str:
    """Return hex HMAC-SHA256 signature for the given payload."""
    return hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()


class WebhookService:
    """Fire-and-forget webhook dispatcher.

    Webhook registrations are stored in the ``system_config`` table under
    key ``"webhooks"`` with a JSON value shaped as::

        [
            {"url": "https://...", "events": ["ticket.created", ...], "secret": "s3cr3t"},
            ...
        ]
    """

    async def _load_hooks(self, db: AsyncSession) -> list[dict]:
        result = await db.execute(
            select(SystemConfig).where(SystemConfig.key == "webhooks")
        )
        row = result.scalar_one_or_none()
        if not row:
            return []
        try:
            hooks = json.loads(row.value_json)
            return hooks if isinstance(hooks, list) else []
        except (json.JSONDecodeError, TypeError):
            logger.warning("Invalid webhooks config in system_config table")
            return []

    async def dispatch(self, db: AsyncSession, event: str, payload: dict) -> None:
        """Send *event* with *payload* to every matching registered webhook.

        Non-blocking: errors are logged but never propagated.
        """
        if event not in WEBHOOK_EVENTS:
            logger.warning("Unknown webhook event %s — skipping", event)
            return

        hooks = await self._load_hooks(db)
        if not hooks:
            return

        envelope = {
            "event": event,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload,
        }
        body_bytes = json.dumps(envelope, default=str).encode()

        for hook in hooks:
            url = hook.get("url")
            subscribed_events: list[str] = hook.get("events", [])
            secret: str = hook.get("secret", "")

            if not url:
                continue
            if subscribed_events and event not in subscribed_events:
                continue

            headers = {
                "Content-Type": "application/json",
                "X-CityInspect-Event": event,
            }
            if secret:
                headers["X-CityInspect-Signature"] = _sign_payload(body_bytes, secret)

            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.post(url, content=body_bytes, headers=headers)
                logger.info(
                    "Webhook delivered",
                    extra={"url": url, "event": event, "status": resp.status_code},
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Webhook delivery failed",
                    extra={"url": url, "event": event, "error": str(exc)},
                )
