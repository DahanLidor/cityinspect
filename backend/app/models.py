"""
SQLAlchemy ORM models.
All models inherit from app.core.database.Base.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, MappedColumn, relationship

from app.core.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    username: Mapped[str] = MappedColumn(String(64), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = MappedColumn(String(128), nullable=False)
    hashed_pw: Mapped[str] = MappedColumn(String(256), nullable=False)
    role: Mapped[str] = MappedColumn(String(32), default="field_team")
    is_active: Mapped[bool] = MappedColumn(Boolean, default=True)
    created_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)

    detections: Mapped[list["Detection"]] = relationship("Detection", back_populates="reporter_user", foreign_keys="Detection.reporter_user_id")


class Detection(Base):
    __tablename__ = "detections"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    detected_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)

    # Sensor / vehicle metadata
    vehicle_id: Mapped[str] = MappedColumn(String(64), default="UNKNOWN")
    vehicle_model: Mapped[str] = MappedColumn(String(128), default="Unknown")
    vehicle_sensor_version: Mapped[str] = MappedColumn(String(32), default="v1.0")
    vehicle_speed_kmh: Mapped[float] = MappedColumn(Float, default=0.0)
    vehicle_heading_deg: Mapped[float] = MappedColumn(Float, default=0.0)

    reported_by: Mapped[str] = MappedColumn(String(32), default="system")
    reporter_user_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("users.id"), nullable=True)

    # Core defect
    defect_type: Mapped[str] = MappedColumn(String(64), nullable=False)
    severity: Mapped[str] = MappedColumn(String(16), nullable=False)
    lat: Mapped[float] = MappedColumn(Float, nullable=False)
    lng: Mapped[float] = MappedColumn(Float, nullable=False)

    # Engineering geometry (from LiDAR)
    defect_length_cm: Mapped[float] = MappedColumn(Float, default=0.0)
    defect_width_cm: Mapped[float] = MappedColumn(Float, default=0.0)
    defect_depth_cm: Mapped[float] = MappedColumn(Float, default=0.0)
    defect_volume_m3: Mapped[float] = MappedColumn(Float, default=0.0)
    repair_material_m3: Mapped[float] = MappedColumn(Float, default=0.0)
    surface_area_m2: Mapped[float] = MappedColumn(Float, default=0.0)

    # Environmental conditions
    ambient_temp_c: Mapped[float] = MappedColumn(Float, default=25.0)
    asphalt_temp_c: Mapped[float] = MappedColumn(Float, default=28.0)
    weather_condition: Mapped[str] = MappedColumn(String(32), default="Clear")
    wind_speed_kmh: Mapped[float] = MappedColumn(Float, default=10.0)
    humidity_pct: Mapped[float] = MappedColumn(Float, default=50.0)
    visibility_m: Mapped[int] = MappedColumn(Integer, default=1000)

    # Media & AI output
    image_url: Mapped[str] = MappedColumn(String(512), default="")
    image_hash: Mapped[str] = MappedColumn(String(64), default="")
    image_caption: Mapped[str] = MappedColumn(String(512), default="")
    notes: Mapped[str] = MappedColumn(Text, default="")

    # Pipeline status
    pipeline_status: Mapped[str] = MappedColumn(String(16), default="pending")  # pending|running|done|error

    # FK
    ticket_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("tickets.id"), nullable=True)

    # Relationships
    ticket: Mapped[Optional["Ticket"]] = relationship("Ticket", back_populates="detections")
    reporter_user: Mapped[Optional[User]] = relationship("User", back_populates="detections", foreign_keys=[reporter_user_id])


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow)

    defect_type: Mapped[str] = MappedColumn(String(64), nullable=False)
    severity: Mapped[str] = MappedColumn(String(16), nullable=False)
    lat: Mapped[float] = MappedColumn(Float, nullable=False)
    lng: Mapped[float] = MappedColumn(Float, nullable=False)
    address: Mapped[str] = MappedColumn(String(256), default="")
    status: Mapped[str] = MappedColumn(String(32), default="new")  # new|verified|assigned|in_progress|resolved
    detection_count: Mapped[int] = MappedColumn(Integer, default=1)

    # Relationships
    detections: Mapped[list[Detection]] = relationship("Detection", back_populates="ticket", lazy="selectin")
    work_order_id: Mapped[Optional[int]] = MappedColumn(Integer, ForeignKey("work_orders.id"), nullable=True)
    work_order: Mapped[Optional["WorkOrder"]] = relationship("WorkOrder", back_populates="tickets")


class WorkOrder(Base):
    __tablename__ = "work_orders"

    id: Mapped[int] = MappedColumn(Integer, primary_key=True, index=True)
    created_at: Mapped[datetime] = MappedColumn(DateTime(timezone=True), default=_utcnow)
    title: Mapped[str] = MappedColumn(String(256), default="")
    status: Mapped[str] = MappedColumn(String(32), default="pending")  # pending|active|completed
    team: Mapped[str] = MappedColumn(String(128), default="")
    priority: Mapped[int] = MappedColumn(Integer, default=1)
    ticket_ids_json: Mapped[str] = MappedColumn(Text, default="[]")

    tickets: Mapped[list[Ticket]] = relationship("Ticket", back_populates="work_order")
