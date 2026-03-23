"""
WhatsApp webhook endpoints.
GET  /webhook — Meta verification challenge
POST /webhook — Inbound messages
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request, status

from app.core.config import get_settings
from app.core.database import DbSession
from app.services.comms.handler import InboundHandler
from app.services.comms.whatsapp import whatsapp_bot

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/api/v1/whatsapp", tags=["whatsapp"])

_VERIFY_TOKEN = getattr(settings, "whatsapp_verify_token", "cityinspect_dev")


@router.get("/webhook")
async def verify_webhook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification handshake."""
    if hub_mode == "subscribe" and hub_verify_token == _VERIFY_TOKEN:
        return int(hub_challenge)
    raise HTTPException(status.HTTP_403_FORBIDDEN, detail="Verification failed")


@router.post("/webhook")
async def inbound_webhook(request: Request, db: DbSession):
    """Receive inbound WhatsApp messages and route to workflow engine."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid JSON")

    parsed = whatsapp_bot.parse_inbound(payload)
    if not parsed:
        # Not a message event (e.g. status update) — return 200 to acknowledge
        return {"status": "ok"}

    handler = InboundHandler(db)
    try:
        await handler.handle(parsed)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.error("Inbound handler error: %s", exc)
        # Still return 200 to prevent Meta from retrying
    return {"status": "ok"}


@router.post("/send-test")
async def send_test_message(whatsapp_id: str, text: str):
    """Dev-only: send a test message."""
    ok = await whatsapp_bot.send_text(whatsapp_id, text)
    return {"sent": ok}
