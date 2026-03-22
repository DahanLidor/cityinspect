"""
Pydantic v2 request/response schemas.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    role: str
    is_active: bool


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Pagination ────────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    page_size: int
    pages: int


# ── Detection ─────────────────────────────────────────────────────────────────

class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    detected_at: datetime
    vehicle_id: str
    vehicle_model: str
    vehicle_sensor_version: str
    vehicle_speed_kmh: float
    vehicle_heading_deg: float
    reported_by: str
    defect_type: str
    severity: str
    lat: float
    lng: float
    defect_length_cm: float
    defect_width_cm: float
    defect_depth_cm: float
    defect_volume_m3: float
    repair_material_m3: float
    surface_area_m2: float
    ambient_temp_c: float
    asphalt_temp_c: float
    weather_condition: str
    wind_speed_kmh: float
    humidity_pct: float
    visibility_m: int
    image_url: str
    image_caption: str
    notes: str
    pipeline_status: str
    ticket_id: Optional[int]


class DetectionUploadResponse(BaseModel):
    detection_id: int
    ticket_id: int
    is_new_ticket: bool
    address: str


# ── Ticket ────────────────────────────────────────────────────────────────────

class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
    defect_type: str
    severity: str
    lat: float
    lng: float
    address: str
    status: str
    detection_count: int
    work_order_id: Optional[int]
    detections: List[DetectionOut] = []


class TicketUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(new|verified|assigned|in_progress|resolved)$")
    severity: Optional[str] = Field(None, pattern="^(low|medium|high|critical)$")

    @field_validator("status", "severity", mode="before")
    @classmethod
    def strip_and_lower(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if v else v


class TicketListResponse(BaseModel):
    items: List[TicketOut]
    total: int
    page: int
    page_size: int
    pages: int


# ── Stats ─────────────────────────────────────────────────────────────────────

class StatsResponse(BaseModel):
    total_tickets: int
    open_tickets: int
    critical_tickets: int
    resolved_today: int
    by_type: Dict[str, int]
    by_status: Dict[str, int]
    by_severity: Dict[str, int]


# ── Work Orders ───────────────────────────────────────────────────────────────

class WorkOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    title: str
    status: str
    team: str
    priority: int
    ticket_ids: List[int] = []


# ── Pipeline ──────────────────────────────────────────────────────────────────

class PipelineStatusResponse(BaseModel):
    detection_id: int
    pipeline_status: str
    caption: str
    pipeline: Dict[str, Any]


class PipelineRunResponse(BaseModel):
    detection_id: int
    ticket_id: int
    vlm: Dict[str, Any]
    environment: Dict[str, Any]
    dedup: Dict[str, Any]
    score: Dict[str, Any]
