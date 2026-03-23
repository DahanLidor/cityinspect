"""
People / CRM routes.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.database import DbSession
from app.core.security import get_current_user
from app.models import Person, User
from app.services.people_engine import PeopleEngine

router = APIRouter(prefix="/api/v1/people", tags=["people"])


class PersonOut(BaseModel):
    id: int
    city_id: str
    external_id: str
    name: str
    role: str
    phone: str
    whatsapp_id: str
    email: str
    specialties: list[str]
    current_workload: int
    is_active: bool
    manager_id: int | None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm(cls, p: Person) -> "PersonOut":
        try:
            specialties = json.loads(p.specialties_json or "[]")
        except (json.JSONDecodeError, TypeError):
            specialties = []
        return cls(
            id=p.id,
            city_id=p.city_id,
            external_id=p.external_id or "",
            name=p.name,
            role=p.role,
            phone=p.phone,
            whatsapp_id=p.whatsapp_id,
            email=p.email,
            specialties=specialties,
            current_workload=p.current_workload,
            is_active=p.is_active,
            manager_id=p.manager_id,
        )


@router.get("", response_model=list[PersonOut])
async def list_people(
    city_id: str = Query("tel-aviv"),
    role: str | None = Query(None),
    active_only: bool = Query(True),
    db: DbSession = None,
    _: User = Depends(get_current_user),
):
    query = select(Person).where(Person.city_id == city_id)
    if role:
        query = query.where(Person.role == role)
    if active_only:
        query = query.where(Person.is_active == True)
    query = query.order_by(Person.role, Person.name)

    result = await db.execute(query)
    people = result.scalars().all()
    return [PersonOut.from_orm(p) for p in people]


@router.post("/sync")
async def sync_contacts(
    city_id: str = Query("tel-aviv"),
    db: DbSession = None,
    current_user: User = Depends(get_current_user),
):
    """Reload contacts.yaml and upsert into DB. Admin only."""
    if current_user.role not in ("admin", "city_manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="נדרשת הרשאת מנהל")

    engine = PeopleEngine(db)
    count = await engine.sync_contacts(city_id)
    await db.commit()
    return {"synced": count, "city_id": city_id}


@router.get("/{person_id}", response_model=PersonOut)
async def get_person(
    person_id: int,
    db: DbSession = None,
    _: User = Depends(get_current_user),
):
    person = await db.get(Person, person_id)
    if not person:
        raise HTTPException(status.HTTP_404_NOT_FOUND)
    return PersonOut.from_orm(person)
