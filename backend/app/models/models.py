"""SQLAlchemy ORM models mirroring the PostgreSQL schema."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

# from geoalchemy2 import Geography
from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# ── Enum values matching Postgres types ──────────────────────

HAZARD_TYPES = ("pothole", "broken_sidewalk", "crack", "road_damage")
SEVERITIES = ("low", "medium", "high", "critical")
STATUSES = ("reported", "confirmed", "in_progress", "resolved", "dismissed")
USER_ROLES = ("inspector", "supervisor", "admin")


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), nullable=False)
    role: Mapped[str] = mapped_column(Enum(*USER_ROLES, name="user_role"), default="inspector")
    department: Mapped[Optional[str]] = mapped_column(String(128))
    badge_number: Mapped[Optional[str]] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    incidents_created = relationship("Incident", back_populates="creator", foreign_keys="Incident.created_by")
    reports = relationship("IncidentReport", back_populates="user")


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    hazard_type: Mapped[str] = mapped_column(Enum(*HAZARD_TYPES, name="hazard_type"), nullable=False)
    severity: Mapped[str] = mapped_column(Enum(*SEVERITIES, name="incident_severity"), default="medium")
    status: Mapped[str] = mapped_column(Enum(*STATUSES, name="incident_status"), default="reported")

    location = mapped_column(String(256), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(String(512))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)

    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)
    ai_model_version: Mapped[Optional[str]] = mapped_column(String(32))

    depth_m: Mapped[Optional[float]] = mapped_column(Float)
    width_m: Mapped[Optional[float]] = mapped_column(Float)
    length_m: Mapped[Optional[float]] = mapped_column(Float)
    surface_area_m2: Mapped[Optional[float]] = mapped_column(Float)
    volume_m3: Mapped[Optional[float]] = mapped_column(Float)

    image_url: Mapped[Optional[str]] = mapped_column(String(1024))
    depth_map_url: Mapped[Optional[str]] = mapped_column(String(1024))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(1024))

    report_count: Mapped[int] = mapped_column(Integer, default=1)
    first_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    created_by: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_to: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    creator = relationship("User", back_populates="incidents_created", foreign_keys=[created_by])
    reports = relationship("IncidentReport", back_populates="incident")
    cluster = relationship("IncidentCluster", back_populates="canonical", uselist=False)


class IncidentReport(Base):
    __tablename__ = "incident_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    incident_id: Mapped[Optional[uuid.UUID]] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location = mapped_column(String(256), nullable=True)

    image_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    depth_map_url: Mapped[Optional[str]] = mapped_column(String(1024))
    image_hash: Mapped[Optional[str]] = mapped_column(String(128))

    ai_hazard_type: Mapped[Optional[str]] = mapped_column(Enum(*HAZARD_TYPES, name="hazard_type", create_type=False))
    ai_confidence: Mapped[Optional[float]] = mapped_column(Float)
    ai_raw_output: Mapped[Optional[dict]] = mapped_column(JSONB)

    lidar_depth_m: Mapped[Optional[float]] = mapped_column(Float)
    lidar_width_m: Mapped[Optional[float]] = mapped_column(Float)
    lidar_length_m: Mapped[Optional[float]] = mapped_column(Float)
    lidar_area_m2: Mapped[Optional[float]] = mapped_column(Float)
    lidar_raw_output: Mapped[Optional[dict]] = mapped_column(JSONB)

    device_info: Mapped[Optional[dict]] = mapped_column(JSONB)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    incident = relationship("Incident", back_populates="reports")
    user = relationship("User", back_populates="reports")


class IncidentCluster(Base):
    __tablename__ = "incident_clusters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    canonical_incident: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("incidents.id"), nullable=False)
    centroid = mapped_column(Geography(geometry_type="POINT", srid=4326))
    radius_m: Mapped[Optional[float]] = mapped_column(Float)
    report_count: Mapped[int] = mapped_column(Integer, default=1)
    gps_similarity: Mapped[Optional[float]] = mapped_column(Float)
    image_similarity: Mapped[Optional[float]] = mapped_column(Float)
    lidar_similarity: Mapped[Optional[float]] = mapped_column(Float)
    merged_incident_ids = mapped_column(ARRAY(UUID(as_uuid=True)), default=[])
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    canonical = relationship("Incident", back_populates="cluster")
