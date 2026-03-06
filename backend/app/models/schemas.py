"""Pydantic schemas for request validation and response serialization."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


# ── Auth ────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=6)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: uuid.UUID
    role: str


# ── Incident Upload ────────────────────────────────────────

class IncidentUploadMeta(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    captured_at: datetime
    device_info: Optional[dict] = None


class LidarMeasurements(BaseModel):
    depth_m: Optional[float] = None
    width_m: Optional[float] = None
    length_m: Optional[float] = None
    surface_area_m2: Optional[float] = None
    volume_m3: Optional[float] = None


class AIDetectionResult(BaseModel):
    hazard_type: str
    confidence: float
    bounding_box: Optional[list[float]] = None
    model_version: str = ""


# ── Response Schemas ────────────────────────────────────────

class IncidentResponse(BaseModel):
    id: uuid.UUID
    hazard_type: str
    severity: str
    status: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    ai_confidence: Optional[float] = None
    depth_m: Optional[float] = None
    width_m: Optional[float] = None
    length_m: Optional[float] = None
    surface_area_m2: Optional[float] = None
    volume_m3: Optional[float] = None
    image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    report_count: int = 1
    first_reported_at: datetime
    last_reported_at: datetime
    created_by: Optional[uuid.UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class IncidentMapItem(BaseModel):
    id: uuid.UUID
    hazard_type: str
    severity: str
    status: str
    latitude: float
    longitude: float
    report_count: int
    ai_confidence: Optional[float] = None
    first_reported_at: datetime

    class Config:
        from_attributes = True


class IncidentReportResponse(BaseModel):
    id: uuid.UUID
    incident_id: Optional[uuid.UUID]
    user_id: uuid.UUID
    latitude: float
    longitude: float
    image_url: str
    ai_hazard_type: Optional[str] = None
    ai_confidence: Optional[float] = None
    lidar_depth_m: Optional[float] = None
    lidar_width_m: Optional[float] = None
    lidar_length_m: Optional[float] = None
    lidar_area_m2: Optional[float] = None
    captured_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str
    timestamp: datetime
