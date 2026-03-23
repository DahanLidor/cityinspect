"""
WhatsApp Bot — state machine for field worker interactions.

In dev/test mode (WHATSAPP_TOKEN not set) all sends are logged only.
Production: Meta Cloud API v19.0.

Message flow per step:
  1. System opens step → sends template message with action buttons
  2. Worker taps button → inbound webhook → state machine resolves action
  3. If gates required (photo) → state transitions to waiting_photo
  4. Photo received → gate fulfilled → advance workflow
"""
from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.comms.renderer import renderer

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Button label limits (WhatsApp: max 20 chars) ──────────────────────────────
_ACTION_LABELS: dict[str, str] = {
    "approve": "✅ אשר",
    "reject": "❌ דחה",
    "reject_redo": "🔄 חזור לביצוע",
    "assign_contractor": "👷 שבץ קבלן",
    "assign_team": "👥 שבץ צוות",
    "confirm_time": "📅 אשר זמן",
    "request_reschedule": "🔁 תזמן מחדש",
    "decline": "🚫 סרב",
    "arrived": "📍 הגעתי",
    "safety_ready": "🦺 בטיחות מוכן",
    "work_done": "🔧 עבודה הושלמה",
    "close": "🔒 סגור טיקט",
}


class WhatsAppBot:

    def __init__(self) -> None:
        self._token = getattr(settings, "whatsapp_token", "") or ""
        self._phone_number_id = getattr(settings, "whatsapp_phone_number_id", "") or ""
        self._mock_mode = not bool(self._token)
        if self._mock_mode:
            logger.info("WhatsApp bot in MOCK mode (no token configured)")

    # ── Outbound ──────────────────────────────────────────────────────────────

    async def send_step_notification(
        self,
        whatsapp_id: str,
        city_id: str,
        template_name: str,
        context: dict[str, Any],
        allowed_actions: list[str],
    ) -> bool:
        """
        Send a structured message with interactive buttons.
        Returns True if sent successfully.
        """
        body = renderer.render(city_id, template_name, context)
        buttons = self._build_buttons(allowed_actions)

        if self._mock_mode:
            logger.info(
                "[MOCK WhatsApp] → %s\n%s\nButtons: %s",
                whatsapp_id, body, [b["reply"]["title"] for b in buttons],
            )
            return True

        return await self._send_interactive(whatsapp_id, body, buttons)

    async def send_text(self, whatsapp_id: str, text: str) -> bool:
        """Send a plain text message."""
        if self._mock_mode:
            logger.info("[MOCK WhatsApp] → %s\n%s", whatsapp_id, text)
            return True

        return await self._send_request({
            "messaging_product": "whatsapp",
            "to": whatsapp_id,
            "type": "text",
            "text": {"body": text},
        })

    async def send_photo_request(self, whatsapp_id: str, label: str) -> bool:
        """Ask user to send a photo."""
        return await self.send_text(whatsapp_id, f"📷 {label}\n\nאנא שלח תמונה כדי להמשיך.")

    # ── Inbound message parsing ────────────────────────────────────────────────

    def parse_inbound(self, payload: dict) -> dict[str, Any] | None:
        """
        Parse raw Meta webhook payload.
        Returns {whatsapp_id, type, action, text, media_id} or None if unparseable.
        """
        try:
            entry = payload["entry"][0]["changes"][0]["value"]
            message = entry["messages"][0]
            whatsapp_id = message["from"]
            msg_type = message["type"]

            result: dict[str, Any] = {"whatsapp_id": whatsapp_id, "type": msg_type}

            if msg_type == "interactive":
                result["action"] = message["interactive"]["button_reply"]["id"]
            elif msg_type == "text":
                result["text"] = message["text"]["body"]
            elif msg_type in ("image", "document", "video"):
                result["media_id"] = message[msg_type]["id"]
                result["mime_type"] = message[msg_type].get("mime_type", "")

            return result
        except (KeyError, IndexError, TypeError) as exc:
            logger.debug("Could not parse inbound message: %s", exc)
            return None

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_buttons(self, actions: list[str]) -> list[dict]:
        buttons = []
        for action in actions[:3]:  # WhatsApp max 3 buttons
            label = _ACTION_LABELS.get(action, action[:20])
            buttons.append({"type": "reply", "reply": {"id": action, "title": label}})
        return buttons

    async def _send_interactive(self, to: str, body: str, buttons: list[dict]) -> bool:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body[:1024]},
                "action": {"buttons": buttons},
            },
        }
        return await self._send_request(payload)

    async def _send_request(self, payload: dict) -> bool:
        url = f"https://graph.facebook.com/v19.0/{self._phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                return True
        except httpx.HTTPError as exc:
            logger.error("WhatsApp API error: %s", exc)
            return False


# Module singleton
whatsapp_bot = WhatsAppBot()
