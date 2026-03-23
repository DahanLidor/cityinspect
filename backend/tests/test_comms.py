"""
Tests for Comms services (TemplateRenderer, WhatsAppBot mock mode).
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.comms.renderer import TemplateRenderer
from app.services.comms.whatsapp import WhatsAppBot


# ── TemplateRenderer ──────────────────────────────────────────────────────────

class TestTemplateRenderer:
    def setup_method(self):
        self.renderer = TemplateRenderer()

    def test_render_notify_manager_new_ticket(self):
        result = self.renderer.render(
            "tel-aviv",
            "notify_manager_new_ticket",
            {
                "ticket": type("T", (), {"id": 42, "address": "Dizengoff 1", "defect_type": "pothole"})(),
                "severity": "high",
                "severity_emoji": "🔴",
                "defect_label": "בור",
                "maps_link": "https://maps.example.com",
                "image_url": "",
                "caption": "בור גדול",
                "score": 85,
            },
        )
        assert result  # non-empty
        assert "42" in result or "Dizengoff" in result

    def test_render_missing_template_returns_fallback(self):
        result = self.renderer.render("tel-aviv", "nonexistent_template_xyz", {})
        assert "nonexistent_template_xyz" in result

    def test_render_contractor_assignment(self):
        result = self.renderer.render(
            "tel-aviv",
            "notify_contractor_assignment",
            {
                "work_order": type("W", (), {"id": 7})(),
                "ticket": type("T", (), {"address": "Herzl 5"})(),
                "maps_link": "https://maps.example.com",
                "defect_emoji": "🕳️",
                "protocol": type("P", (), {"name": "תיקון בור", "estimated_hours": 2})(),
                "optimal_window": "09:00-11:00",
                "team": [{"role_label": "קבלן", "count": 1}],
                "materials": [{"name": "אספלט", "quantity": 50, "unit": "kg"}],
                "approver": type("A", (), {"name": "יוסי", "phone": "052-000"})(),
            },
        )
        assert result
        assert "Herzl" in result or "7" in result


# ── WhatsAppBot (mock mode) ───────────────────────────────────────────────────

class TestWhatsAppBotMock:
    def setup_method(self):
        self.bot = WhatsAppBot()
        # Ensure mock mode
        self.bot._mock_mode = True

    @pytest.mark.asyncio
    async def test_send_text_mock(self):
        result = await self.bot.send_text("97200001", "Hello שלום")
        assert result is True

    @pytest.mark.asyncio
    async def test_send_step_notification_mock(self):
        result = await self.bot.send_step_notification(
            whatsapp_id="97200001",
            city_id="tel-aviv",
            template_name="notify_manager_new_ticket",
            context={
                "ticket": type("T", (), {"id": 1, "address": "Test", "defect_type": "pothole"})(),
                "severity": "high",
                "severity_emoji": "🔴",
                "defect_label": "בור",
                "maps_link": "https://maps.example.com",
                "image_url": "",
                "caption": "",
                "score": 70,
            },
            allowed_actions=["approve", "reject"],
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_send_photo_request_mock(self):
        result = await self.bot.send_photo_request("97200001", "תמונת לפני")
        assert result is True

    def test_parse_inbound_button(self):
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "97200001",
                            "type": "interactive",
                            "interactive": {
                                "button_reply": {"id": "approve", "title": "✅ אשר"}
                            }
                        }]
                    }
                }]
            }]
        }
        parsed = self.bot.parse_inbound(payload)
        assert parsed is not None
        assert parsed["whatsapp_id"] == "97200001"
        assert parsed["action"] == "approve"

    def test_parse_inbound_image(self):
        payload = {
            "entry": [{
                "changes": [{
                    "value": {
                        "messages": [{
                            "from": "97200002",
                            "type": "image",
                            "image": {"id": "media123", "mime_type": "image/jpeg"}
                        }]
                    }
                }]
            }]
        }
        parsed = self.bot.parse_inbound(payload)
        assert parsed is not None
        assert parsed["media_id"] == "media123"

    def test_parse_inbound_invalid_returns_none(self):
        parsed = self.bot.parse_inbound({"invalid": "payload"})
        assert parsed is None

    def test_buttons_capped_at_3(self):
        buttons = self.bot._build_buttons(["a", "b", "c", "d", "e"])
        assert len(buttons) == 3
