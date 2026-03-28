"""
SQLAlchemy ORM models — כולל מודלים חדשים:
  Person, WorkflowStep, Conversation, WorkOrder (חדש)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey,
    Integer, String, Text, func,
)
from sqlalchemy.orm import Mapped, MappedColumn, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Users (login) ─────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    username: Mapped[str] = MappedColumn(String(64), unique=True, index=True)
    full_name: Mapped[str] = MappedColumn(String(128))
    hashed_pw: Mapped[str] = MappedColumn(String(256))
    role: Mapped[str] = MappedColumn(String(32), default="field_team")
    is_active: Mapped[bool] = MappedColumn(Boolean, default=True)
    created_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)

    detections: Mapped[list["Detection"]] = relationship(
        "Detection", back_populates="reporter_user",
        foreign_keys="Detection.reporter_user_id"
    )


# ── People (CRM — אנשי קשר) ───────────────────────────────────────────────────

class Person(Base):
    """
    כל אדם במערכת: עובד עירייה, קבלן, פועל שטח, מפקח.
    טעון מ-contacts.yaml ומסונכרן ל-DB.
    """
    __tablename__ = "people"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    city_id: Mapped[str] = MappedColumn(String(64), index=True, nullable=False)
    external_id: Mapped[str] = MappedColumn(String(64), index=True)  # id מה-yaml

    name: Mapped[str] = MappedColumn(String(128))
    role: Mapped[str] = MappedColumn(String(64))       # work_manager | contractor | ...
    manager_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("people.id"), nullable=True)

    phone: Mapped[str] = MappedColumn(String(32), default="")
    whatsapp_id: Mapped[str] = MappedColumn(String(32), default="", index=True)
    email: Mapped[str] = MappedColumn(String(128), default="")

    specialties_json: Mapped[str] = MappedColumn(Text, default="[]")    # JSON array
    availability_json: Mapped[str] = MappedColumn(Text, default="{}")   # JSON object

    is_active: Mapped[bool] = MappedColumn(Boolean, default=True)
    current_workload: Mapped[int] = MappedColumn(Integer, default=0)    # טיקטים פתוחים
    created_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    # Self-referential: מי מעל בהיררכיה
    manager: Mapped[Optional["Person"]] = relationship("Person", remote_side="Person.id", foreign_keys=[manager_id])
    subordinates: Mapped[list["Person"]] = relationship("Person", foreign_keys=[manager_id], overlaps="manager")

    conversations: Mapped[list["Conversation"]] = relationship("Conversation", back_populates="person")


# ── Tickets ────────────────────────────────────────────────────────────────────

class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    city_id: Mapped[str] = MappedColumn(String(64), index=True, nullable=False, default="default")
    created_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    defect_type: Mapped[str] = MappedColumn(String(64))
    severity: Mapped[str] = MappedColumn(String(16))
    score: Mapped[int] = MappedColumn(Integer, default=0)
    lat: Mapped[float] = MappedColumn(Float)
    lng: Mapped[float] = MappedColumn(Float)
    address: Mapped[str] = MappedColumn(String(256), default="")
    status: Mapped[str] = MappedColumn(String(32), default="new")
    detection_count: Mapped[int] = MappedColumn(Integer, default=1)

    # Workflow state
    current_step_id: Mapped[Optional[str]] = MappedColumn(String(64), nullable=True)
    protocol_id: Mapped[Optional[str]] = MappedColumn(String(64), nullable=True)
    sla_deadline: Mapped[Optional[datetime]] = MappedColumn(DateTime(timezone=True), nullable=True)
    sla_breached: Mapped[bool] = MappedColumn(Boolean, default=False)

    # Relationships
    detections: Mapped[list["Detection"]] = relationship("Detection", back_populates="ticket", lazy="selectin")
    workflow_steps: Mapped[list["WorkflowStep"]] = relationship("WorkflowStep", back_populates="ticket", lazy="selectin")
    work_order: Mapped[Optional["WorkOrder"]] = relationship("WorkOrder", back_populates="ticket", uselist=False)


# ── Detections ────────────────────────────────────────────────────────────────

class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    city_id: Mapped[str] = MappedColumn(String(64), index=True, default="default")
    detected_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)

    vehicle_id: Mapped[str] = MappedColumn(String(64), default="UNKNOWN")
    vehicle_model: Mapped[str] = MappedColumn(String(128), default="Unknown")
    vehicle_sensor_version: Mapped[str] = MappedColumn(String(32), default="v1.0")
    vehicle_speed_kmh: Mapped[float] = MappedColumn(Float, default=0.0)
    vehicle_heading_deg: Mapped[float] = MappedColumn(Float, default=0.0)

    reported_by: Mapped[str] = MappedColumn(String(32), default="system")
    reporter_user_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("users.id"), nullable=True)

    defect_type: Mapped[str] = MappedColumn(String(64))
    severity: Mapped[str] = MappedColumn(String(16))
    lat: Mapped[float] = MappedColumn(Float)
    lng: Mapped[float] = MappedColumn(Float)

    defect_length_cm: Mapped[float] = MappedColumn(Float, default=0.0)
    defect_width_cm: Mapped[float] = MappedColumn(Float, default=0.0)
    defect_depth_cm: Mapped[float] = MappedColumn(Float, default=0.0)
    defect_volume_m3: Mapped[float] = MappedColumn(Float, default=0.0)
    repair_material_m3: Mapped[float] = MappedColumn(Float, default=0.0)
    surface_area_m2: Mapped[float] = MappedColumn(Float, default=0.0)

    ambient_temp_c: Mapped[float] = MappedColumn(Float, default=25.0)
    asphalt_temp_c: Mapped[float] = MappedColumn(Float, default=28.0)
    weather_condition: Mapped[str] = MappedColumn(String(32), default="Clear")
    wind_speed_kmh: Mapped[float] = MappedColumn(Float, default=10.0)
    humidity_pct: Mapped[float] = MappedColumn(Float, default=50.0)
    visibility_m: Mapped[int] = MappedColumn(Integer, default=1000)

    image_url: Mapped[str] = MappedColumn(String(512), default="")
    image_hash: Mapped[str] = MappedColumn(String(64), default="")
    image_caption: Mapped[str] = MappedColumn(String(512), default="")
    point_cloud_url: Mapped[str] = MappedColumn(String(512), default="")
    notes: Mapped[str] = MappedColumn(Text, default="")
    pipeline_status: Mapped[str] = MappedColumn(String(16), default="pending")

    ticket_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("tickets.id"), nullable=True)
    ticket: Mapped[Optional[Ticket]] = relationship("Ticket", back_populates="detections")
    reporter_user: Mapped[Optional[User]] = relationship("User", back_populates="detections", foreign_keys=[reporter_user_id])


# ── WorkflowStep — היסטוריית שלבים ───────────────────────────────────────────

class WorkflowStep(Base):
    """
    רשומה לכל שלב שנפתח/הושלם בטיקט.
    מהווה את הציר הזמן המלא.
    """
    __tablename__ = "workflow_steps"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    city_id: Mapped[str] = MappedColumn(String(64), index=True)
    ticket_id: Mapped[int] = MappedColumn(Integer, ForeignKey("tickets.id"), index=True)
    step_id: Mapped[str] = MappedColumn(String(64))          # e.g. "manager_approval"
    step_name: Mapped[str] = MappedColumn(String(128))

    status: Mapped[str] = MappedColumn(String(16), default="open")   # open|done|skipped|timeout
    owner_person_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("people.id"), nullable=True)
    owner_role: Mapped[str] = MappedColumn(String(64))

    opened_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)
    deadline_at: Mapped[Optional[datetime]] = MappedColumn(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = MappedColumn(DateTime(timezone=True), nullable=True)
    completed_by_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("people.id"), nullable=True)

    action_taken: Mapped[Optional[str]] = MappedColumn(String(64), nullable=True)
    data_json: Mapped[str] = MappedColumn(Text, default="{}")     # תמונות, הערות, מדידות
    skip_reason: Mapped[Optional[str]] = MappedColumn(Text, nullable=True)
    skip_approved_by_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("people.id"), nullable=True)

    # Response time metrics
    response_time_min: Mapped[Optional[float]] = MappedColumn(Float, nullable=True)  # minutes from opened to completed
    sla_met: Mapped[Optional[bool]] = MappedColumn(Boolean, nullable=True)           # True if completed before deadline

    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="workflow_steps")
    owner: Mapped[Optional[Person]] = relationship("Person", foreign_keys=[owner_person_id])
    completed_by: Mapped[Optional[Person]] = relationship("Person", foreign_keys=[completed_by_id])


# ── WorkOrder ─────────────────────────────────────────────────────────────────

class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    city_id: Mapped[str] = MappedColumn(String(64), index=True)
    ticket_id: Mapped[int] = MappedColumn(Integer, ForeignKey("tickets.id"), unique=True)
    created_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)

    assigned_person_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("people.id"), nullable=True)
    approved_by_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("people.id"), nullable=True)

    scheduled_start: Mapped[Optional[datetime]] = MappedColumn(DateTime(timezone=True), nullable=True)
    scheduled_end: Mapped[Optional[datetime]] = MappedColumn(DateTime(timezone=True), nullable=True)

    protocol_id: Mapped[str] = MappedColumn(String(64))
    team_json: Mapped[str] = MappedColumn(Text, default="[]")         # JSON: [{person_id, role}]
    materials_json: Mapped[str] = MappedColumn(Text, default="[]")    # JSON: [{name, qty, unit}]
    protocol_steps_json: Mapped[str] = MappedColumn(Text, default="[]")

    estimated_hours: Mapped[float] = MappedColumn(Float, default=0.0)
    estimated_cost: Mapped[float] = MappedColumn(Float, default=0.0)
    actual_hours: Mapped[Optional[float]] = MappedColumn(Float, nullable=True)

    status: Mapped[str] = MappedColumn(String(32), default="pending")  # pending|active|done|cancelled

    ticket: Mapped[Ticket] = relationship("Ticket", back_populates="work_order")
    assigned_person: Mapped[Optional[Person]] = relationship("Person", foreign_keys=[assigned_person_id])
    approved_by: Mapped[Optional[Person]] = relationship("Person", foreign_keys=[approved_by_id])


# ── Conversation — מצב שיחת WhatsApp ─────────────────────────────────────────

class Conversation(Base):
    """
    State machine לכל שיחה: אדם × טיקט.
    הבוט יודע בכל רגע מה מצב השיחה.
    """
    __tablename__ = "conversations"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    city_id: Mapped[str] = MappedColumn(String(64), index=True)
    person_id: Mapped[int] = MappedColumn(Integer, ForeignKey("people.id"), index=True)
    ticket_id: Mapped[int] = MappedColumn(Integer, ForeignKey("tickets.id"), index=True)
    step_id: Mapped[str] = MappedColumn(String(64))               # שלב נוכחי

    state: Mapped[str] = MappedColumn(String(64), default="waiting_action")
    # waiting_action | waiting_photo | waiting_confirm | done

    last_message_at: Mapped[Optional[datetime]] = MappedColumn(DateTime(timezone=True), nullable=True)
    last_message_text: Mapped[Optional[str]] = MappedColumn(Text, nullable=True)
    pending_gates_json: Mapped[str] = MappedColumn(Text, default="[]")  # מה עוד חסר

    person: Mapped[Person] = relationship("Person", back_populates="conversations")


# ── AuditLog ──────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """כל פעולה של כל אדם/סוכן — לנצח."""
    __tablename__ = "audit_log"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    city_id: Mapped[str] = MappedColumn(String(64), index=True)
    ticket_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("tickets.id"), nullable=True, index=True)
    step_id: Mapped[Optional[str]] = MappedColumn(String(64), nullable=True)

    actor_type: Mapped[str] = MappedColumn(String(16))   # person | agent | system
    actor_id: Mapped[Optional[int]] = MappedColumn(Integer, nullable=True)
    actor_name: Mapped[str] = MappedColumn(String(128), default="system")

    action: Mapped[str] = MappedColumn(String(64))
    data_json: Mapped[str] = MappedColumn(Text, default="{}")
    timestamp: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow, index=True)
