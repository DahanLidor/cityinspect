"""
Agent 1: VLM — Claude Vision image analysis.
"""
from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

_FALLBACK = {
    "description": "תמונה שהועלתה מהשטח",
    "hazard_detected": True,
    "hazard_type": "unknown",
    "liability_risk": "בינוני — נדרש ניתוח ידני",
    "severity_hint": "medium",
    "confidence": 0.5,
    "analysis_source": "fallback",
}

_PROMPT = """אתה מומחה לתשתיות עירוניות. נתח את התמונה וזהה מפגעים.

החזר JSON בלבד (בלי markdown):
{
  "description": "תיאור קצר של מה שרואים בתמונה",
  "hazard_detected": true/false,
  "hazard_type": "pothole|crack|broken_sidewalk|drainage|signage|road_damage|other|none",
  "hazard_details": "פירוט המפגע — גודל משוער, חומרה, מיקום בתמונה",
  "liability_risk": "תיאור הסיכון לתביעת נזיקין — למי מסוכן ולמה",
  "severity_hint": "critical|high|medium|low",
  "confidence": 0.0-1.0
}"""


async def agent_vlm_analyze(image_url: str) -> Dict[str, Any]:
    """Analyze image via Claude Vision. Falls back gracefully if no API key."""
    if not settings.anthropic_api_key:
        logger.warning("VLM: no ANTHROPIC_API_KEY — using fallback")
        return _FALLBACK

    # Resolve local path
    image_data: str | None = None
    media_type = "image/jpeg"

    if image_url.startswith("/uploads/"):
        filename = image_url.replace("/uploads/", "")
        full_path = os.path.join(settings.upload_path, filename)
        if os.path.exists(full_path):
            with open(full_path, "rb") as fh:
                image_data = base64.standard_b64encode(fh.read()).decode()
            ext = full_path.rsplit(".", 1)[-1].lower()
            media_type = f"image/{ext}" if ext in ("png", "gif", "webp") else "image/jpeg"

    if not image_data:
        logger.warning("VLM: image not accessible", extra={"url": image_url})
        return {**_FALLBACK, "analysis_source": "error", "hazard_detected": False, "confidence": 0.0}

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-opus-4-5",
                    "max_tokens": 1000,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": image_data}},
                            {"type": "text", "text": _PROMPT},
                        ],
                    }],
                },
            )

        if resp.status_code == 200:
            text = resp.json()["content"][0]["text"].strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)
            result["analysis_source"] = "claude_vlm"
            logger.info("VLM analysis complete", extra={"hazard_type": result.get("hazard_type"), "confidence": result.get("confidence")})
            return result

        logger.warning("VLM API error", extra={"status": resp.status_code})
    except Exception as exc:
        logger.error("VLM agent exception", extra={"error": str(exc)})

    return {**_FALLBACK, "analysis_source": "error", "confidence": 0.3}
