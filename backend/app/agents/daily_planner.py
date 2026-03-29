"""
Daily Planner Agent — builds optimized daily work plans for field workers.

Given a worker (Person), finds matching open tickets, considers:
  - Worker's roles & skills
  - Geographic proximity (home base → tickets)
  - SLA deadlines (urgent first)
  - Ticket clustering (nearby tickets grouped)
  - Weather conditions
  - Worker constraints (max hours, vehicle type)

Returns a structured JSON plan via Claude API.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime, timezone
from typing import Any

import anthropic
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Detection, DailyPlan, Person, SystemConfig, Ticket

logger = get_logger(__name__)
settings = get_settings()

# ── Defaults ────────────────────────────────────────────────────────────────

DEFAULT_CONFIG = {
    "work_radius_km": 15,
    "nearby_radius_m": 500,
    "break_after_hours": 4,
    "work_hours": {"start": "08:00", "end": "16:00"},
    "priority_weights": {"sla": 0.4, "severity": 0.3, "distance": 0.2, "cluster": 0.1},
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _get_config(db: AsyncSession) -> dict:
    """Load system config, falling back to defaults."""
    config = dict(DEFAULT_CONFIG)
    result = await db.execute(select(SystemConfig))
    for row in result.scalars().all():
        try:
            config[row.key] = json.loads(row.value_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return config


async def _get_open_tickets_for_worker(
    db: AsyncSession,
    person: Person,
    config: dict,
) -> list[dict]:
    """Find open tickets matching worker's skills within work radius."""
    specialties = json.loads(person.specialties_json or "[]")
    skills = json.loads(person.skills_json or "[]")
    radius_km = config.get("work_radius_km", 15)

    # Get all open/in-progress tickets for the city
    result = await db.execute(
        select(Ticket)
        .where(Ticket.city_id == person.city_id)
        .where(Ticket.status.in_(["new", "open", "in_progress"]))
    )
    tickets = list(result.scalars().all())

    matching = []
    for t in tickets:
        # Check if defect_type matches worker's specialties
        if specialties and t.defect_type not in specialties:
            continue

        # Check distance from home base
        if person.home_base_lat and person.home_base_lon:
            dist = _haversine_km(person.home_base_lat, person.home_base_lon, t.lat, t.lng)
            if dist > radius_km:
                continue
        else:
            dist = 0

        # Get latest detection for sensor data and image
        det_result = await db.execute(
            select(Detection)
            .where(Detection.ticket_id == t.id)
            .order_by(Detection.detected_at.desc())
            .limit(1)
        )
        det = det_result.scalar_one_or_none()

        ticket_info: dict[str, Any] = {
            "ticket_id": t.id,
            "defect_type": t.defect_type,
            "severity": t.severity,
            "score": t.score,
            "lat": t.lat,
            "lng": t.lng,
            "address": t.address,
            "status": t.status,
            "distance_km": round(dist, 2),
            "sla_deadline": t.sla_deadline.isoformat() if t.sla_deadline else None,
            "sla_breached": t.sla_breached,
            "detection_count": t.detection_count,
        }

        if det:
            ticket_info["image_caption"] = det.image_caption
            ticket_info["weather_condition"] = det.weather_condition
            ticket_info["ambient_temp_c"] = det.ambient_temp_c

            # Parse sensor data if available
            try:
                sensor = json.loads(det.sensor_data_json or "{}")
                if sensor:
                    ticket_info["sensor_data"] = sensor
            except (json.JSONDecodeError, TypeError):
                pass

            # Parse environment notes
            try:
                notes = json.loads(det.notes or "{}")
                env = notes.get("environment", {})
                if env:
                    ticket_info["environment"] = env
            except (json.JSONDecodeError, TypeError):
                pass

        matching.append(ticket_info)

    # Sort: SLA breached first, then by score descending
    matching.sort(key=lambda t: (
        not t.get("sla_breached", False),
        -(t.get("score", 0) or 0),
        t.get("distance_km", 999),
    ))

    return matching


def _build_prompt(person: Person, tickets: list[dict], config: dict, plan_date: date) -> str:
    """Build the Claude prompt for daily plan generation."""
    specialties = json.loads(person.specialties_json or "[]")
    skills = json.loads(person.skills_json or "[]")
    availability = json.loads(person.availability_json or "{}")

    # Determine work hours for today
    weekday = plan_date.weekday()
    if weekday == 4:
        slot = availability.get("fri", "07:00-13:00")
    elif weekday == 5:
        slot = availability.get("sat", "")
    else:
        slot = availability.get("sun_thu", "07:00-17:00")

    prompt = f"""You are a work planning assistant for a municipal maintenance team.
Build an optimized daily work plan for the following worker.

## Worker Profile
- Name: {person.name}
- Role: {person.role}
- Specialties: {', '.join(specialties)}
- Skills: {', '.join(skills)}
- Vehicle: {person.vehicle_type or 'none'}
- Max daily hours: {person.max_daily_hours}
- Working hours today: {slot}
- Home base: ({person.home_base_lat}, {person.home_base_lon})

## Date
{plan_date.isoformat()} ({['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'][plan_date.weekday()]})

## Open Tickets ({len(tickets)} matching)
```json
{json.dumps(tickets, ensure_ascii=False, default=str, indent=2)}
```

## Planning Rules
1. Prioritize SLA-breached tickets (they are overdue)
2. Group nearby tickets (within {config.get('nearby_radius_m', 500)}m) into clusters
3. Optimize route to minimize driving time
4. Schedule a break after {config.get('break_after_hours', 4)} hours
5. Don't exceed max daily hours ({person.max_daily_hours}h)
6. Consider weather — avoid outdoor asphalt work in rain
7. Start from home base, end near home base if possible
8. Estimate repair duration based on defect type and severity:
   - pothole (low): 30min, (medium): 45min, (high/critical): 60min
   - road_crack: 20-40min, sidewalk: 30-50min, drainage: 45-90min
9. Include equipment list based on defect types

## Required Output Format (JSON only)
```json
{{
  "worker_name": "...",
  "date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "end_time": "HH:MM",
  "total_estimated_hours": 0.0,
  "total_distance_km": 0.0,
  "tasks": [
    {{
      "order": 1,
      "ticket_id": 0,
      "address": "...",
      "defect_type": "...",
      "severity": "...",
      "sla_remaining_hours": null,
      "estimated_duration_min": 0,
      "drive_time_min": 0,
      "arrive_by": "HH:MM",
      "equipment": ["..."],
      "notes": "...",
      "nearby_tickets": []
    }},
    {{ "order": "break", "time": "HH:MM", "duration_min": 30 }}
  ],
  "equipment_summary": ["item — quantity"],
  "weather_warning": "...",
  "summary_he": "סיכום קצר בעברית של תוכנית העבודה"
}}
```

Return ONLY valid JSON, no markdown formatting or explanation."""

    return prompt


async def generate_daily_plan(
    db: AsyncSession,
    person_id: int,
    plan_date: date | None = None,
) -> DailyPlan:
    """Generate a daily work plan for a worker using Claude AI."""
    if plan_date is None:
        plan_date = date.today()

    person = await db.get(Person, person_id)
    if not person:
        raise ValueError(f"Person {person_id} not found")

    config = await _get_config(db)
    tickets = await _get_open_tickets_for_worker(db, person, config)

    if not tickets:
        # No tickets — create empty plan
        plan = DailyPlan(
            city_id=person.city_id,
            person_id=person.id,
            plan_date=plan_date,
            status="draft",
            plan_json=json.dumps({
                "worker_name": person.name,
                "date": plan_date.isoformat(),
                "tasks": [],
                "summary_he": "אין משימות פתוחות התואמות לעובד זה",
            }, ensure_ascii=False),
            total_tasks=0,
            total_hours=0,
            total_distance_km=0,
        )
        db.add(plan)
        await db.flush()
        return plan

    prompt = _build_prompt(person, tickets, config, plan_date)

    # Call Claude API
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = response.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]

    try:
        plan_data = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("Failed to parse AI plan response: %s", raw[:500])
        plan_data = {"error": "Failed to parse AI response", "raw": raw[:1000]}

    tasks = plan_data.get("tasks", [])
    real_tasks = [t for t in tasks if isinstance(t.get("order"), int)]

    plan = DailyPlan(
        city_id=person.city_id,
        person_id=person.id,
        plan_date=plan_date,
        status="draft",
        plan_json=json.dumps(plan_data, ensure_ascii=False, default=str),
        total_tasks=len(real_tasks),
        total_hours=plan_data.get("total_estimated_hours", 0),
        total_distance_km=plan_data.get("total_distance_km", 0),
    )
    db.add(plan)
    await db.flush()
    logger.info("Daily plan created", extra={"plan_id": plan.id, "person": person.name, "tasks": len(real_tasks)})
    return plan
