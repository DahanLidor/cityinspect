"""
seed_demo.py — Populate CityInspect with realistic Tel Aviv demo data.
Run: python seed_demo.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import SessionLocal, engine, Base
from models import User, Detection, Ticket, WorkOrder
from routes.auth import get_password_hash
from services.deduplication import mock_reverse_geocode
from datetime import datetime, timedelta
import random, math

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# ── Wipe existing demo data ────────────────────────────
db.query(Detection).delete()
db.query(Ticket).delete()
db.query(WorkOrder).delete()
db.query(User).delete()
db.commit()

# ── Users ─────────────────────────────────────────────
users = [
    User(username="admin",  hashed_password=get_password_hash("admin123"),  full_name="System Admin",    role="admin"),
    User(username="yossi",  hashed_password=get_password_hash("field123"),  full_name="Yossi Cohen",     role="field_team"),
    User(username="dana",   hashed_password=get_password_hash("field123"),  full_name="Dana Levi",       role="field_team"),
    User(username="demo",   hashed_password=get_password_hash("demo123"),   full_name="Demo Viewer",     role="viewer"),
]
for u in users:
    db.add(u)
db.commit()
print("✅ Users created")

# ── Vehicles ──────────────────────────────────────────
vehicles = [
    {"id": "V001", "model": "Ford Transit V001",       "sensor": "SensorArray-v2.1"},
    {"id": "V002", "model": "Renault Master V002",     "sensor": "SensorArray-v2.2"},
    {"id": "V003", "model": "Mercedes Sprinter V003",  "sensor": "SensorArray-v2.3"},
    {"id": "V004", "model": "Ford Transit V004",       "sensor": "SensorArray-v2.3"},
    {"id": "V005", "model": "Renault Master V005",     "sensor": "SensorArray-v2.2"},
]

# ── Pothole images (Wikimedia Commons — freely licensed) ──
IMAGES = {
    "pothole": [
        ("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Pothole_on_D2128_%28Poland%29.jpg/640px-Pothole_on_D2128_%28Poland%29.jpg", "Pothole ~8cm deep, wet asphalt"),
        ("https://upload.wikimedia.org/wikipedia/commons/thumb/0/0b/Pothole_at_Abergavenny.jpg/640px-Pothole_at_Abergavenny.jpg", "Large pothole near pedestrian crossing"),
        ("https://upload.wikimedia.org/wikipedia/commons/thumb/5/58/Pothole_on_Route_2_%28Poland%29.jpg/640px-Pothole_on_Route_2_%28Poland%29.jpg", "Pothole with water accumulation"),
    ],
    "road_crack": [
        ("https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Road_cracks.jpg/640px-Road_cracks.jpg", "Longitudinal crack, 2mm width"),
    ],
    "drainage_blocked": [
        ("https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Blocked_drain.jpg/640px-Blocked_drain.jpg", "Blocked drainage grate, debris accumulation"),
    ],
    "broken_light": [
        ("https://upload.wikimedia.org/wikipedia/commons/thumb/4/4e/Street_light.jpg/640px-Street_light.jpg", "Street light — lamp failure detected"),
    ],
    "sidewalk": [
        ("https://upload.wikimedia.org/wikipedia/commons/thumb/1/1c/Broken_sidewalk.jpg/640px-Broken_sidewalk.jpg", "Broken sidewalk slab, trip hazard"),
    ],
}
DEFAULT_IMG = ("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Pothole_on_D2128_%28Poland%29.jpg/640px-Pothole_on_D2128_%28Poland%29.jpg", "Infrastructure defect detected")

DEFECT_TYPES = ["pothole", "road_crack", "broken_light", "drainage_blocked", "sidewalk"]
SEVERITIES   = ["low", "medium", "high", "critical"]
WEATHERS     = ["Clear", "Cloudy", "Rain", "Fog", "Partly Cloudy"]

# Tel Aviv bounding box
LAT_MIN, LAT_MAX = 32.050, 32.110
LNG_MIN, LNG_MAX = 34.760, 34.820

def rand_tel_aviv():
    return round(random.uniform(LAT_MIN, LAT_MAX), 6), round(random.uniform(LNG_MIN, LNG_MAX), 6)

def rand_geometry(defect_type):
    if defect_type == "pothole":
        L, W, D = random.uniform(20, 80), random.uniform(15, 60), random.uniform(3, 15)
    elif defect_type == "road_crack":
        L, W, D = random.uniform(50, 300), random.uniform(0.5, 3), random.uniform(0.5, 2)
    else:
        L, W, D = random.uniform(30, 100), random.uniform(20, 80), random.uniform(1, 5)
    return round(L, 1), round(W, 1), round(D, 1)

# ── Generate 35 detections ────────────────────────────
now = datetime.utcnow()
all_tickets = {}  # (approx_lat, approx_lng, defect_type) → Ticket

for i in range(35):
    lat, lng = rand_tel_aviv()
    defect_type = random.choice(DEFECT_TYPES)
    severity    = random.choices(SEVERITIES, weights=[20, 35, 30, 15])[0]
    vehicle     = random.choice(vehicles)
    weather     = random.choice(WEATHERS)
    ambient     = round(random.uniform(14, 28), 1)
    asphalt     = round(ambient + random.uniform(8, 22), 1)
    days_ago    = random.uniform(0, 7)
    detected_at = now - timedelta(days=days_ago, hours=random.uniform(0, 12))
    L, W, D     = rand_geometry(defect_type)
    volume      = round((L * W * D) / 1_000_000, 6)
    repair      = round(volume * 1.2, 6)
    area        = round((L * W) / 10_000, 4)

    imgs = IMAGES.get(defect_type, [DEFAULT_IMG])
    img_url, img_caption = random.choice(imgs)

    # Deduplication: snap to 0.001° grid
    key = (round(lat, 2), round(lng, 2), defect_type)
    if key in all_tickets and random.random() > 0.6:
        ticket = all_tickets[key]
        ticket.detection_count += 1
        is_new = False
    else:
        address = mock_reverse_geocode(lat, lng)
        ticket = Ticket(
            defect_type=defect_type, severity=severity,
            lat=lat, lng=lng, address=address,
            status=random.choices(
                ["new", "verified", "assigned", "in_progress", "resolved"],
                weights=[25, 20, 20, 20, 15]
            )[0],
            detection_count=1,
            vehicle_ids=[vehicle["id"]],
            created_at=detected_at
        )
        db.add(ticket)
        db.flush()
        all_tickets[key] = ticket
        is_new = True

    detection = Detection(
        vehicle_id=vehicle["id"], vehicle_model=vehicle["model"],
        vehicle_sensor_version=vehicle["sensor"],
        vehicle_speed_kmh=round(random.uniform(5, 60), 1),
        vehicle_heading_deg=round(random.uniform(0, 360), 1),
        reported_by="simulator",
        defect_type=defect_type, severity=severity,
        lat=lat, lng=lng,
        defect_length_cm=L, defect_width_cm=W, defect_depth_cm=D,
        defect_volume_m3=volume, repair_material_m3=repair, surface_area_m2=area,
        ambient_temp_c=ambient, asphalt_temp_c=asphalt,
        weather_condition=weather,
        wind_speed_kmh=round(random.uniform(0, 40), 1),
        humidity_pct=round(random.uniform(30, 90), 1),
        visibility_m=random.choice([2000, 5000, 8000, 10000]),
        image_url=img_url, image_caption=img_caption,
        notes=random.choice(["", "Near school entrance", "Busy intersection", "High pedestrian traffic", ""]),
        ticket_id=ticket.id,
        detected_at=detected_at
    )
    db.add(detection)

db.commit()
print(f"✅ 35 detections + {len(all_tickets)} tickets created")

# ── 2 completed WorkOrders ────────────────────────────
resolved = db.query(Ticket).filter(Ticket.status == "resolved").limit(6).all()
if len(resolved) >= 2:
    wo1 = WorkOrder(
        ticket_ids=[t.id for t in resolved[:3]],
        assigned_team="Road Maintenance Team A",
        estimated_duration_min=120, status="completed", route_optimized=True,
        created_at=now - timedelta(days=3)
    )
    wo2 = WorkOrder(
        ticket_ids=[t.id for t in resolved[3:6]],
        assigned_team="Electrical Infrastructure Team",
        estimated_duration_min=90, status="completed", route_optimized=True,
        created_at=now - timedelta(days=1)
    )
    db.add_all([wo1, wo2])
    db.commit()
    print("✅ 2 completed WorkOrders created")

db.close()
print("\n🚀 Demo data ready! Run: uvicorn main:app --reload --port 8000")
