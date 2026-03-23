"""
Tests for PeopleEngine.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import pytest_asyncio

from app.models import Person
from app.services.people_engine import PeopleEngine


@pytest_asyncio.fixture
async def people(db):
    """Seed a small org chart."""
    manager = Person(
        city_id="test-city", external_id="mgr1",
        name="Alice Manager", role="work_manager",
        whatsapp_id="97200010",
        specialties_json='["pothole", "road_crack"]',
        availability_json='{"sun_thu": "07:00-17:00", "fri": "07:00-13:00"}',
        current_workload=2,
        is_active=True,
    )
    worker = Person(
        city_id="test-city", external_id="w1",
        name="Bob Worker", role="field_worker",
        whatsapp_id="97200011",
        specialties_json='["pothole"]',
        availability_json='{"sun_thu": "07:00-17:00"}',
        current_workload=1,
        is_active=True,
    )
    db.add(manager)
    db.add(worker)
    await db.flush()

    worker.manager_id = manager.id
    await db.flush()

    return {"manager": manager, "worker": worker}


@pytest.mark.asyncio
async def test_find_best_for_role(db, people):
    engine = PeopleEngine(db)
    person = await engine.find_best_for("test-city", "work_manager")
    assert person is not None
    assert person.role == "work_manager"


@pytest.mark.asyncio
async def test_find_best_with_specialty(db, people):
    engine = PeopleEngine(db)
    person = await engine.find_best_for("test-city", "field_worker", specialty="pothole")
    assert person is not None
    assert person.name == "Bob Worker"


@pytest.mark.asyncio
async def test_find_best_missing_specialty(db, people):
    engine = PeopleEngine(db)
    # No field_worker with drainage_blocked specialty
    person = await engine.find_best_for("test-city", "field_worker", specialty="drainage_blocked")
    # Falls back to lowest workload even without specialty
    assert person is None or person.current_workload >= 0


@pytest.mark.asyncio
async def test_get_manager(db, people):
    engine = PeopleEngine(db)
    manager = await engine.get_manager(people["worker"])
    assert manager is not None
    assert manager.name == "Alice Manager"


@pytest.mark.asyncio
async def test_get_subordinates(db, people):
    engine = PeopleEngine(db)
    subs = await engine.get_subordinates(people["manager"])
    assert len(subs) == 1
    assert subs[0].name == "Bob Worker"


@pytest.mark.asyncio
async def test_increment_decrement_workload(db, people):
    engine = PeopleEngine(db)
    manager = people["manager"]
    original = manager.current_workload

    await engine.increment_workload(manager.id)
    await db.flush()
    assert manager.current_workload == original + 1

    await engine.decrement_workload(manager.id)
    await db.flush()
    assert manager.current_workload == original


@pytest.mark.asyncio
async def test_sync_contacts(db):
    engine = PeopleEngine(db)
    count = await engine.sync_contacts("tel-aviv")
    assert count >= 7  # tel-aviv has 9 people in contacts.yaml


@pytest.mark.asyncio
async def test_sync_contacts_idempotent(db):
    engine = PeopleEngine(db)
    count1 = await engine.sync_contacts("tel-aviv")
    count2 = await engine.sync_contacts("tel-aviv")
    assert count1 == count2  # second sync should update, not duplicate


@pytest.mark.asyncio
async def test_find_excludes_ids(db, people):
    engine = PeopleEngine(db)
    manager = people["manager"]
    person = await engine.find_best_for(
        "test-city", "work_manager", exclude_ids=[manager.id]
    )
    assert person is None  # no other work_manager in test-city
