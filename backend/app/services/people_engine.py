"""
People Engine — org chart, availability, skill matching.
Syncs contacts.yaml → DB on startup.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Person
from app.services.workflow.protocol_loader import protocol_loader

logger = logging.getLogger(__name__)


class PeopleEngine:

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Find best person for a role/specialty ─────────────────────────────────

    async def find_best_for(
        self,
        city_id: str,
        role: str,
        specialty: str | None = None,
        exclude_ids: list[int] | None = None,
    ) -> Person | None:
        """
        Returns the best available person:
          1. Has required role
          2. Has the specialty (if specified)
          3. Currently available (working hours)
          4. Lowest workload
        """
        query = (
            select(Person)
            .where(Person.city_id == city_id)
            .where(Person.role == role)
            .where(Person.is_active)
        )
        if exclude_ids:
            query = query.where(Person.id.notin_(exclude_ids))

        result = await self.db.execute(query.order_by(Person.current_workload.asc()))
        candidates = result.scalars().all()

        now = datetime.now(timezone.utc)
        for person in candidates:
            if specialty and not self._has_specialty(person, specialty):
                continue
            if self._is_available(person, now):
                return person

        # Fallback: return lowest workload even if not available right now
        for person in candidates:
            if specialty and not self._has_specialty(person, specialty):
                continue
            return person

        return None

    async def get_manager(self, person: Person) -> Person | None:
        if not person.manager_id:
            return None
        return await self.db.get(Person, person.manager_id)

    async def get_subordinates(self, person: Person, role: str | None = None) -> list[Person]:
        query = select(Person).where(Person.manager_id == person.id).where(Person.is_active)
        if role:
            query = query.where(Person.role == role)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def increment_workload(self, person_id: int) -> None:
        person = await self.db.get(Person, person_id)
        if person:
            person.current_workload += 1

    async def decrement_workload(self, person_id: int) -> None:
        person = await self.db.get(Person, person_id)
        if person and person.current_workload > 0:
            person.current_workload -= 1

    # ── Sync contacts.yaml → DB ───────────────────────────────────────────────

    async def sync_contacts(self, city_id: str) -> int:
        """
        Load contacts.yaml and upsert all people into DB.
        Returns number of people synced.
        """
        contacts = protocol_loader.load_contacts(city_id)
        people_data = contacts.get("people", [])

        if not people_data:
            logger.info("No contacts to sync for city=%s", city_id)
            return 0

        # Build lookup: external_id → DB person
        existing = await self._load_existing(city_id)

        synced = 0
        for p in people_data:
            ext_id = p["id"]
            person = existing.get(ext_id)

            if person is None:
                person = Person(city_id=city_id, external_id=ext_id)
                self.db.add(person)

            person.name = p.get("name", "")
            person.role = p.get("role", "field_worker")
            person.phone = p.get("phone", "")
            person.whatsapp_id = p.get("whatsapp_id", "")
            person.email = p.get("email", "")
            person.specialties_json = json.dumps(p.get("specialties", []), ensure_ascii=False)
            person.availability_json = json.dumps(p.get("availability", {}), ensure_ascii=False)
            person.skills_json = json.dumps(p.get("skills", []), ensure_ascii=False)
            person.vehicle_type = p.get("vehicle_type", "")
            person.max_daily_hours = p.get("max_daily_hours", 8.0)
            home = p.get("home_base", {})
            if home:
                person.home_base_lat = home.get("lat")
                person.home_base_lon = home.get("lon")
            person.is_active = True
            synced += 1

        await self.db.flush()

        # Second pass: resolve manager_id references
        existing = await self._load_existing(city_id)
        for p in people_data:
            mgr_ext_id = p.get("manager_id")
            if mgr_ext_id:
                person = existing.get(p["id"])
                manager = existing.get(mgr_ext_id)
                if person and manager:
                    person.manager_id = manager.id

        await self.db.flush()
        logger.info("Synced %d contacts for city=%s", synced, city_id)
        return synced

    # ── Private ───────────────────────────────────────────────────────────────

    async def _load_existing(self, city_id: str) -> dict[str, Person]:
        result = await self.db.execute(
            select(Person).where(Person.city_id == city_id)
        )
        return {p.external_id: p for p in result.scalars().all()}

    @staticmethod
    def _has_specialty(person: Person, specialty: str) -> bool:
        try:
            specialties = json.loads(person.specialties_json or "[]")
            return specialty in specialties
        except (json.JSONDecodeError, TypeError):
            return False

    @staticmethod
    def _is_available(person: Person, now: datetime) -> bool:
        """Simple availability check based on availability_json day slots."""
        try:
            availability = json.loads(person.availability_json or "{}")
        except (json.JSONDecodeError, TypeError):
            return True  # no data → assume available

        # Weekday: 0=Monday … 6=Sunday
        weekday = now.weekday()
        day_key = None

        if weekday == 4:  # Friday
            day_key = "fri"
        elif weekday == 5:  # Saturday
            day_key = "sat"
        else:
            day_key = "sun_thu"  # Israel: Sunday=6 in Python but treated as workday

        slot = availability.get(day_key)
        if slot is None:
            return False  # not working this day

        try:
            start_str, end_str = slot.split("-")
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))

            current_minutes = now.hour * 60 + now.minute
            start_minutes = start_h * 60 + start_m
            end_minutes = end_h * 60 + end_m
            return start_minutes <= current_minutes <= end_minutes
        except (ValueError, AttributeError):
            return True
