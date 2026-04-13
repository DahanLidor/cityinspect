"""
Daily Plans router — generate and manage AI work plans for field workers.
"""
from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.models import DailyPlan, Person, SystemConfig, User

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/daily-plans", tags=["daily-plans"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class WorkerOut(BaseModel):
    id: int
    name: str
    role: str
    specialties: list[str]
    skills: list[str]
    vehicle_type: str
    current_workload: int
    home_base_lat: float | None
    home_base_lon: float | None

class PlanOut(BaseModel):
    id: int
    person_id: int
    person_name: str
    plan_date: date
    status: str
    total_tasks: int
    total_hours: float
    total_distance_km: float
    plan: dict
    created_at: datetime

class GenerateRequest(BaseModel):
    person_id: int
    plan_date: date | None = None

class ConfigOut(BaseModel):
    key: str
    value: dict | list | int | float | str

class ConfigUpdate(BaseModel):
    key: str
    value: dict | list | int | float | str


# ── Workers list ─────────────────────────────────────────────────────────────

@router.get("/workers", response_model=list[WorkerOut])
async def list_workers(
    city_id: str = Query("tel-aviv"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List field workers eligible for daily plan generation."""
    result = await db.execute(
        select(Person)
        .where(Person.city_id == city_id)
        .where(Person.is_active)
        .where(Person.role.in_(["contractor", "field_worker", "inspector", "work_manager"]))
        .order_by(Person.role, Person.name)
    )
    people = result.scalars().all()
    return [
        WorkerOut(
            id=p.id,
            name=p.name,
            role=p.role,
            specialties=json.loads(p.specialties_json or "[]"),
            skills=json.loads(p.skills_json or "[]"),
            vehicle_type=p.vehicle_type or "",
            current_workload=p.current_workload or 0,
            home_base_lat=p.home_base_lat,
            home_base_lon=p.home_base_lon,
        )
        for p in people
    ]


# ── Generate plan ────────────────────────────────────────────────────────────

@router.post("/generate", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
async def generate_plan(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Generate a daily work plan for a worker using AI."""
    from app.agents.daily_planner import generate_daily_plan

    person = await db.get(Person, body.person_id)
    if not person:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Worker not found")

    try:
        plan = await generate_daily_plan(db, body.person_id, body.plan_date)
        await db.commit()
        await db.refresh(plan)
    except Exception as exc:
        logger.error("Plan generation failed: %s", exc)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, f"Plan generation failed: {exc}")

    return PlanOut(
        id=plan.id,
        person_id=plan.person_id,
        person_name=person.name,
        plan_date=plan.plan_date,
        status=plan.status,
        total_tasks=plan.total_tasks,
        total_hours=plan.total_hours,
        total_distance_km=plan.total_distance_km,
        plan=json.loads(plan.plan_json),
        created_at=plan.created_at,
    )


# ── List plans ───────────────────────────────────────────────────────────────

@router.get("", response_model=list[PlanOut])
async def list_plans(
    city_id: str = Query("tel-aviv"),
    plan_date: date | None = None,
    person_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(DailyPlan).where(DailyPlan.city_id == city_id)
    if plan_date:
        query = query.where(DailyPlan.plan_date == plan_date)
    if person_id:
        query = query.where(DailyPlan.person_id == person_id)
    query = query.order_by(DailyPlan.created_at.desc()).limit(50)

    result = await db.execute(query)
    plans = result.scalars().all()

    out = []
    for p in plans:
        person = await db.get(Person, p.person_id)
        out.append(PlanOut(
            id=p.id,
            person_id=p.person_id,
            person_name=person.name if person else "?",
            plan_date=p.plan_date,
            status=p.status,
            total_tasks=p.total_tasks,
            total_hours=p.total_hours,
            total_distance_km=p.total_distance_km,
            plan=json.loads(p.plan_json),
            created_at=p.created_at,
        ))
    return out


# ── Get single plan ──────────────────────────────────────────────────────────

@router.get("/{plan_id}", response_model=PlanOut)
async def get_plan(
    plan_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plan = await db.get(DailyPlan, plan_id)
    if not plan:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    person = await db.get(Person, plan.person_id)
    return PlanOut(
        id=plan.id,
        person_id=plan.person_id,
        person_name=person.name if person else "?",
        plan_date=plan.plan_date,
        status=plan.status,
        total_tasks=plan.total_tasks,
        total_hours=plan.total_hours,
        total_distance_km=plan.total_distance_km,
        plan=json.loads(plan.plan_json),
        created_at=plan.created_at,
    )


# ── System config ────────────────────────────────────────────────────────────

@router.get("/config/all", response_model=list[ConfigOut])
async def get_all_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(SystemConfig))
    rows = result.scalars().all()
    return [ConfigOut(key=r.key, value=json.loads(r.value_json)) for r in rows]


@router.put("/config", response_model=ConfigOut)
async def upsert_config(
    body: ConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = await db.get(SystemConfig, body.key)
    if existing:
        existing.value_json = json.dumps(body.value, ensure_ascii=False, default=str)
        existing.updated_by = user.username
    else:
        cfg = SystemConfig(
            key=body.key,
            value_json=json.dumps(body.value, ensure_ascii=False, default=str),
            updated_by=user.username,
        )
        db.add(cfg)
    await db.commit()
    return ConfigOut(key=body.key, value=body.value)
