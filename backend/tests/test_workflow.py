"""
Tests for WorkflowEngine + ProtocolLoader.
"""
from __future__ import annotations

import json

import pytest
import pytest_asyncio

from app.models import Person, Ticket, WorkflowStep
from app.services.workflow.engine import WorkflowEngine, WorkflowError
from app.services.workflow.protocol_loader import ProtocolLoader

# ── Protocol Loader ───────────────────────────────────────────────────────────

class TestProtocolLoader:
    def setup_method(self):
        self.loader = ProtocolLoader()

    def test_load_default_pothole(self):
        protocol = self.loader.load("tel-aviv", "pothole")
        assert protocol["id"] == "pothole"
        assert len(protocol["steps"]) == 8

    def test_first_step(self):
        step = self.loader.get_first_step("tel-aviv", "pothole")
        assert step is not None
        assert step["id"] == "manager_approval"
        assert step["owner_role"] == "work_manager"

    def test_next_step(self):
        nxt = self.loader.get_next_step("tel-aviv", "pothole", "manager_approval")
        assert nxt is not None
        assert nxt["id"] == "contractor_assignment"

    def test_get_step_by_id(self):
        step = self.loader.get_step("tel-aviv", "pothole", "inspection")
        assert step is not None
        assert "approve" in step["allowed_actions"]
        assert not step.get("skip_allowed", True)

    def test_last_step_no_next(self):
        nxt = self.loader.get_next_step("tel-aviv", "pothole", "close")
        assert nxt is None

    def test_unknown_defect_returns_empty(self):
        protocol = self.loader.load("tel-aviv", "nonexistent_defect")
        assert protocol == {}

    def test_city_config_loaded(self):
        config = self.loader.load_city_config("tel-aviv")
        assert config["city"]["id"] == "tel-aviv"
        assert config["sla_hours"]["critical"] == 4

    def test_contacts_loaded(self):
        contacts = self.loader.load_contacts("tel-aviv")
        people = contacts.get("people", [])
        assert len(people) >= 5
        ids = [p["id"] for p in people]
        assert "yossi_levy" in ids
        assert "avi_contractor" in ids

    def test_cache_hit(self):
        self.loader.load("tel-aviv", "pothole")
        self.loader.load("tel-aviv", "pothole")  # should not raise
        assert ("tel-aviv", "pothole") in self.loader._cache

    def test_clear_cache(self):
        self.loader.load("tel-aviv", "pothole")
        self.loader.clear_cache()
        assert len(self.loader._cache) == 0


# ── WorkflowEngine ────────────────────────────────────────────────────────────

_WF_CITY = "test-workflow"  # Isolated city_id to avoid cross-test pollution


@pytest_asyncio.fixture
async def work_manager(db):
    p = Person(
        city_id=_WF_CITY, external_id="wm_test",
        name="Test Work Manager", role="work_manager",
        whatsapp_id="97200001", specialties_json='["pothole"]',
        availability_json='{"sun_thu": "07:00-17:00", "fri": "07:00-13:00"}',
    )
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def inspector(db):
    p = Person(
        city_id=_WF_CITY, external_id="insp_test",
        name="Test Inspector", role="inspector",
        whatsapp_id="97200002", specialties_json='["pothole"]',
        availability_json='{"sun_thu": "07:00-17:00", "fri": "07:00-13:00"}',
    )
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def ticket(db):
    t = Ticket(
        city_id=_WF_CITY, defect_type="pothole",
        severity="high", lat=32.08, lng=34.78,
        score=70, status="new",
    )
    db.add(t)
    await db.flush()
    return t


@pytest.mark.asyncio
async def test_open_ticket_creates_first_step(db, ticket, work_manager):
    engine = WorkflowEngine(db)
    step = await engine.open_ticket(ticket)
    await db.flush()

    assert step.step_id == "manager_approval"
    assert step.status == "open"
    assert step.owner_role == "work_manager"
    assert ticket.current_step_id == "manager_approval"


@pytest.mark.asyncio
async def test_can_act_correct_role(db, ticket, work_manager):
    engine = WorkflowEngine(db)
    await engine.open_ticket(ticket)
    await db.flush()

    can, reason = await engine.can_act(ticket, work_manager, "approve")
    assert can, reason


@pytest.mark.asyncio
async def test_can_act_wrong_action(db, ticket, work_manager):
    engine = WorkflowEngine(db)
    await engine.open_ticket(ticket)
    await db.flush()

    can, reason = await engine.can_act(ticket, work_manager, "nonexistent_action")
    assert not can
    assert "not allowed" in reason.lower() or "allowed" in reason


@pytest.mark.asyncio
async def test_can_act_wrong_role(db, ticket, inspector):
    engine = WorkflowEngine(db)
    await engine.open_ticket(ticket)
    await db.flush()

    # Inspector tries to act on manager_approval step
    can, reason = await engine.can_act(ticket, inspector, "approve")
    assert not can


@pytest.mark.asyncio
async def test_advance_moves_to_next_step(db, ticket, work_manager):
    engine = WorkflowEngine(db)
    await engine.open_ticket(ticket)
    await db.flush()

    next_step = await engine.advance(ticket, work_manager, "approve")
    await db.flush()

    assert next_step is not None
    # contractor_assignment is auto_trigger=true, so engine auto-advances to contractor_confirm
    assert next_step.step_id in ("contractor_assignment", "contractor_confirm")
    assert ticket.current_step_id in ("contractor_assignment", "contractor_confirm")


@pytest.mark.asyncio
async def test_advance_without_permission_raises(db, ticket, inspector):
    engine = WorkflowEngine(db)
    await engine.open_ticket(ticket)
    await db.flush()

    with pytest.raises(WorkflowError):
        await engine.advance(ticket, inspector, "approve")


@pytest.mark.asyncio
async def test_skip_not_allowed_raises(db, ticket, work_manager):
    engine = WorkflowEngine(db)
    await engine.open_ticket(ticket)
    await db.flush()

    with pytest.raises(WorkflowError, match="skip_allowed"):
        await engine.skip_step(ticket, work_manager, "test reason")


@pytest.mark.asyncio
async def test_upload_gate_data(db, ticket, work_manager):
    engine = WorkflowEngine(db)
    step = await engine.open_ticket(ticket)
    await db.flush()

    # Advance to a step that requires a photo (site_arrival)
    # First advance through manager_approval and contractor_assignment and contractor_confirm
    # For simplicity: directly set current step
    step.status = "done"
    step.completed_at = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

    # Create site_arrival step manually
    arrival_step = WorkflowStep(
        city_id="tel-aviv", ticket_id=ticket.id,
        step_id="site_arrival", step_name="הגעה לאתר",
        status="open", owner_role="contractor",
        owner_person_id=work_manager.id,
        data_json="{}",
    )
    db.add(arrival_step)
    ticket.current_step_id = "site_arrival"
    await db.flush()

    await engine.upload_gate_data(ticket, work_manager, "photo_before", {"media_id": "abc123"})
    await db.flush()

    data = json.loads(arrival_step.data_json)
    assert "photo_before" in data
    assert data["photo_before"]["media_id"] == "abc123"


@pytest.mark.asyncio
async def test_no_active_step_can_act(db, ticket, work_manager):
    engine = WorkflowEngine(db)
    # Don't open ticket
    can, reason = await engine.can_act(ticket, work_manager, "approve")
    assert not can
    assert "no active step" in reason.lower()
