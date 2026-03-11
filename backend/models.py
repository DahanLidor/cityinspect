from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    role = Column(String, default="field_team")  # admin | field_team | viewer
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Detection(Base):
    __tablename__ = "detections"
    id = Column(Integer, primary_key=True, index=True)
    detected_at = Column(DateTime, default=datetime.utcnow)

    # Vehicle / sensor
    vehicle_id = Column(String, default="V001")
    vehicle_model = Column(String, default="Ford Transit")
    vehicle_sensor_version = Column(String, default="SensorArray-v2.3")
    vehicle_speed_kmh = Column(Float, default=0.0)
    vehicle_heading_deg = Column(Float, default=0.0)
    reported_by = Column(String, default="simulator")  # mobile_app | simulator | sensor
    reporter_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Core defect
    defect_type = Column(String)  # pothole | road_crack | broken_light | drainage_blocked | sidewalk
    severity = Column(String)     # low | medium | high | critical
    lat = Column(Float)
    lng = Column(Float)

    # Engineering geometry
    defect_length_cm = Column(Float, default=0.0)
    defect_width_cm = Column(Float, default=0.0)
    defect_depth_cm = Column(Float, default=0.0)
    defect_volume_m3 = Column(Float, default=0.0)
    repair_material_m3 = Column(Float, default=0.0)
    surface_area_m2 = Column(Float, default=0.0)

    # Environmental
    ambient_temp_c = Column(Float, default=20.0)
    asphalt_temp_c = Column(Float, default=35.0)
    weather_condition = Column(String, default="Clear")
    wind_speed_kmh = Column(Float, default=10.0)
    humidity_pct = Column(Float, default=50.0)
    visibility_m = Column(Integer, default=10000)

    # Media
    image_url = Column(String, default="")
    image_caption = Column(String, default="")
    notes = Column(String, default="")

    # Relations
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=True)
    ticket = relationship("Ticket", back_populates="detections")
    reporter = relationship("User")


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    defect_type = Column(String)
    severity = Column(String)
    lat = Column(Float)
    lng = Column(Float)
    address = Column(String, default="")
    status = Column(String, default="new")  # new|verified|assigned|in_progress|resolved
    detection_count = Column(Integer, default=1)
    vehicle_ids = Column(JSON, default=list)

    work_order_id = Column(Integer, ForeignKey("work_orders.id"), nullable=True)
    detections = relationship("Detection", back_populates="ticket")
    work_order = relationship("WorkOrder", back_populates="tickets")


class WorkOrder(Base):
    __tablename__ = "work_orders"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    ticket_ids = Column(JSON, default=list)
    assigned_team = Column(String)
    estimated_duration_min = Column(Integer, default=60)
    status = Column(String, default="pending")  # pending|active|completed
    route_optimized = Column(Boolean, default=True)
    tickets = relationship("Ticket", back_populates="work_order")
