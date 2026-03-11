from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class UserCreate(BaseModel):
    username: str
    password: str
    full_name: str
    role: str = "field_team"


class UserOut(BaseModel):
    id: int
    username: str
    full_name: str
    role: str
    is_active: bool
    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class DetectionCreate(BaseModel):
    vehicle_id: str = "V001"
    vehicle_model: str = "Ford Transit"
    vehicle_sensor_version: str = "SensorArray-v2.3"
    vehicle_speed_kmh: float = 0.0
    vehicle_heading_deg: float = 0.0
    reported_by: str = "simulator"
    defect_type: str
    severity: str
    lat: float
    lng: float
    defect_length_cm: float = 0.0
    defect_width_cm: float = 0.0
    defect_depth_cm: float = 0.0
    ambient_temp_c: float = 20.0
    asphalt_temp_c: float = 35.0
    weather_condition: str = "Clear"
    wind_speed_kmh: float = 10.0
    humidity_pct: float = 50.0
    visibility_m: int = 10000
    image_url: str = ""
    image_caption: str = ""
    notes: str = ""


class DetectionOut(BaseModel):
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
    ticket_id: Optional[int]
    class Config:
        from_attributes = True


class DetectionResponse(BaseModel):
    detection_id: int
    ticket_id: int
    is_new_ticket: bool
    address: str


class TicketOut(BaseModel):
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
    vehicle_ids: List[str]
    work_order_id: Optional[int]
    detections: List[DetectionOut] = []
    class Config:
        from_attributes = True


class TicketUpdate(BaseModel):
    status: str


class WorkOrderOut(BaseModel):
    id: int
    created_at: datetime
    ticket_ids: List[int]
    assigned_team: str
    estimated_duration_min: int
    status: str
    class Config:
        from_attributes = True


class StatsOut(BaseModel):
    total_open: int
    critical_count: int
    in_progress: int
    resolved_today: int
    detections_last_hour: int
    detections_per_hour: List[dict]
    by_type: dict
    by_severity: dict
