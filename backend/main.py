import os, json, math, random, hashlib
from datetime import datetime, timedelta
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from pydantic import BaseModel
from jose import jwt, JWTError
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# ── Config ──────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cityinspect.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

SECRET_KEY = os.getenv("SECRET_KEY", "cityinspect-secret-2024")
ALGORITHM  = "HS256"
UPLOAD_DIR = "/data/uploads" if os.path.exists("/data") else "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ── DB ──────────────────────────────────────────────────────
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id         = Column(Integer, primary_key=True)
    username   = Column(String, unique=True)
    full_name  = Column(String)
    hashed_pw  = Column(String)
    role       = Column(String, default="field_team")
    is_active  = Column(Boolean, default=True)

class Detection(Base):
    __tablename__ = "detections"
    id                    = Column(Integer, primary_key=True)
    detected_at           = Column(DateTime, default=datetime.utcnow)
    vehicle_id            = Column(String, default="UNKNOWN")
    vehicle_model         = Column(String, default="Unknown")
    vehicle_sensor_version= Column(String, default="v1.0")
    vehicle_speed_kmh     = Column(Float,   default=0)
    vehicle_heading_deg   = Column(Float,   default=0)
    reported_by           = Column(String,  default="system")
    defect_type           = Column(String)
    severity              = Column(String)
    lat                   = Column(Float)
    lng                   = Column(Float)
    defect_length_cm      = Column(Float,   default=0)
    defect_width_cm       = Column(Float,   default=0)
    defect_depth_cm       = Column(Float,   default=0)
    defect_volume_m3      = Column(Float,   default=0)
    repair_material_m3    = Column(Float,   default=0)
    surface_area_m2       = Column(Float,   default=0)
    ambient_temp_c        = Column(Float,   default=25)
    asphalt_temp_c        = Column(Float,   default=28)
    weather_condition     = Column(String,  default="Clear")
    wind_speed_kmh        = Column(Float,   default=10)
    humidity_pct          = Column(Float,   default=50)
    visibility_m          = Column(Integer, default=1000)
    image_url             = Column(String,  default="")
    image_caption         = Column(String,  default="")
    notes                 = Column(Text,    default="")
    ticket_id             = Column(Integer, ForeignKey("tickets.id"), nullable=True)

class Ticket(Base):
    __tablename__ = "tickets"
    id              = Column(Integer, primary_key=True)
    created_at      = Column(DateTime, default=datetime.utcnow)
    defect_type     = Column(String)
    severity        = Column(String)
    lat             = Column(Float)
    lng             = Column(Float)
    address         = Column(String, default="")
    status          = Column(String, default="new")
    detection_count = Column(Integer, default=1)
    detections      = relationship("Detection", backref="ticket", foreign_keys=[Detection.ticket_id])

class WorkOrder(Base):
    __tablename__ = "work_orders"
    id          = Column(Integer, primary_key=True)
    created_at  = Column(DateTime, default=datetime.utcnow)
    title       = Column(String)
    status      = Column(String, default="pending")
    team        = Column(String)
    priority    = Column(Integer, default=1)
    ticket_ids  = Column(Text, default="[]")

with engine.connect() as conn:
    conn.execute(__import__("sqlalchemy").text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    conn.commit()
Base.metadata.create_all(bind=engine)

# ── Auth ─────────────────────────────────────────────────────
ph = PasswordHasher()
security = HTTPBearer(auto_error=False)

def hash_pw(pw):       return ph.hash(pw)
def verify_pw(pw, h):
    try: return ph.verify(h, pw)
    except: return False
def make_token(data):  return jwt.encode({**data, "exp": datetime.utcnow() + timedelta(days=30)}, SECRET_KEY, ALGORITHM)

def get_db():
    db = SessionLocal()
    try:   yield db
    finally: db.close()

def current_user(creds: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    if not creds: raise HTTPException(401, "Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user = db.query(User).filter_by(username=payload.get("sub")).first()
        if not user: raise HTTPException(401)
        return user
    except JWTError: raise HTTPException(401)

# ── Seed ─────────────────────────────────────────────────────
def seed(db: Session):
    if db.query(User).count() > 0: return
    users = [
        User(username="admin", full_name="מנהל מערכת", hashed_pw=hash_pw("admin123"), role="admin"),
        User(username="yossi", full_name="יוסי כהן",   hashed_pw=hash_pw("field123"), role="field_team"),
        User(username="dana",  full_name="דנה לוי",    hashed_pw=hash_pw("field123"), role="field_team"),
        User(username="demo",  full_name="Demo User",  hashed_pw=hash_pw("demo123"),  role="viewer"),
    ]
    db.add_all(users); db.commit()

    images = {
        "pothole":          ("https://upload.wikimedia.org/wikipedia/commons/thumb/3/3e/Pothole_on_D2128_%28Poland%29.jpg/640px-Pothole_on_D2128_%28Poland%29.jpg", "בור בכביש"),
        "road_crack":       ("https://upload.wikimedia.org/wikipedia/commons/thumb/b/b5/Road_cracks.jpg/640px-Road_cracks.jpg", "סדק בכביש"),
        "broken_light":     ("", "פנס תקול"),
        "drainage_blocked": ("https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Blocked_drain.jpg/640px-Blocked_drain.jpg", "ביוב חסום"),
        "sidewalk":         ("", "מדרכה שבורה"),
    }
    base_coords = [
        (32.0853, 34.7818), (32.0810, 34.7780), (32.0900, 34.7850),
        (32.0780, 34.7900), (32.0830, 34.7750), (32.0870, 34.7820),
        (32.0920, 34.7790), (32.0760, 34.7840), (32.0840, 34.7870),
        (32.0890, 34.7760), (32.0815, 34.7825), (32.0865, 34.7835),
    ]
    defect_types = ["pothole","road_crack","broken_light","drainage_blocked","sidewalk"]
    severities   = ["low","medium","high","critical"]
    
    for i, (lat, lng) in enumerate(base_coords):
        dtype = defect_types[i % len(defect_types)]
        sev   = severities[i % len(severities)]
        img_url, caption = images[dtype]
        
        t = Ticket(defect_type=dtype, severity=sev, lat=lat, lng=lng,
                   address=f"רחוב הרצל {i+1}, תל אביב", status=random.choice(["new","verified","assigned","in_progress"]),
                   detection_count=random.randint(1,4))
        db.add(t); db.flush()
        
        d = Detection(
            defect_type=dtype, severity=sev, lat=lat, lng=lng,
            vehicle_id=f"TLV-{100+i}", vehicle_model="Ford Transit Sensor v2",
            vehicle_speed_kmh=round(random.uniform(20,60),1),
            vehicle_heading_deg=round(random.uniform(0,360),1),
            reported_by="system",
            defect_length_cm=round(random.uniform(20,150),1),
            defect_width_cm=round(random.uniform(10,80),1),
            defect_depth_cm=round(random.uniform(2,15),1),
            ambient_temp_c=round(random.uniform(18,35),1),
            asphalt_temp_c=round(random.uniform(25,45),1),
            weather_condition=random.choice(["Clear","Cloudy","Partly Cloudy"]),
            wind_speed_kmh=round(random.uniform(5,30),1),
            humidity_pct=round(random.uniform(30,80),1),
            visibility_m=random.choice([500,800,1000]),
            image_url=img_url, image_caption=caption,
            notes=f"זוהה אוטומטית על ידי חיישן רכב",
            ticket_id=t.id
        )
        d.defect_volume_m3   = round((d.defect_length_cm * d.defect_width_cm * d.defect_depth_cm) / 1_000_000, 6)
        d.surface_area_m2    = round((d.defect_length_cm * d.defect_width_cm) / 10_000, 4)
        d.repair_material_m3 = round(d.defect_volume_m3 * 1.2, 6)
        db.add(d)
    
    db.commit()
    print("✅ Seed complete")

# ── WebSocket Hub ─────────────────────────────────────────────
class WSHub:
    def __init__(self):  self.conns: List[WebSocket] = []
    async def connect(self, ws: WebSocket):
        await ws.accept(); self.conns.append(ws)
    def disconnect(self, ws: WebSocket):
        self.conns = [c for c in self.conns if c != ws]
    async def broadcast(self, data: dict):
        dead = []
        for ws in self.conns:
            try:   await ws.send_text(json.dumps(data))
            except: dead.append(ws)
        for ws in dead: self.disconnect(ws)

hub = WSHub()

# ── Haversine Dedup ───────────────────────────────────────────
def haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    p = math.pi/180
    a = math.sin((lat2-lat1)*p/2)**2 + math.cos(lat1*p)*math.cos(lat2*p)*math.sin((lng2-lng1)*p/2)**2
    return 2*R*math.asin(math.sqrt(a))

def find_or_create_ticket(db, dtype, sev, lat, lng, address):
    existing = db.query(Ticket).filter(
        Ticket.defect_type == dtype,
        Ticket.status.notin_(["resolved"])
    ).all()
    for t in existing:
        if haversine(lat, lng, t.lat, t.lng) < 30:
            t.detection_count += 1
            sev_order = {"low":0,"medium":1,"high":2,"critical":3}
            if sev_order.get(sev,0) > sev_order.get(t.severity,0):
                t.severity = sev
            db.commit()
            return t, False
    t = Ticket(defect_type=dtype, severity=sev, lat=lat, lng=lng, address=address)
    db.add(t); db.commit(); db.refresh(t)
    return t, True

# ── Schemas ───────────────────────────────────────────────────
class LoginIn(BaseModel):
    username: str
    password: str

class TicketUpdate(BaseModel):
    status: Optional[str] = None
    severity: Optional[str] = None

# ── App ───────────────────────────────────────────────────────
app = FastAPI(title="CityInspect API", version="2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Serve frontend static files if they exist
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "build")
if os.path.exists(frontend_path):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_path, "static")), name="static")

@app.on_event("startup")
def startup():
    db = SessionLocal()
    seed(db); db.close()

@app.get("/health")
def health(): return {"status": "ok", "version": "2.0"}

# ── Auth Routes ───────────────────────────────────────────────
@app.post("/api/auth/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=body.username).first()
    if not user or not verify_pw(body.password, user.hashed_pw):
        raise HTTPException(401, "שם משתמש או סיסמה שגויים")
    token = make_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer",
            "user": {"id": user.id, "username": user.username, "full_name": user.full_name, "role": user.role, "is_active": user.is_active}}

@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "full_name": user.full_name, "role": user.role, "is_active": user.is_active}

# ── Detection Routes ──────────────────────────────────────────
@app.post("/api/detections/upload")
async def upload_detection(
    defect_type: str = Form(...), severity: str = Form(...),
    lat: float = Form(...), lng: float = Form(...),
    defect_length_cm: float = Form(0), defect_width_cm: float = Form(0), defect_depth_cm: float = Form(0),
    notes: str = Form(""), reported_by: str = Form("system"),
    vehicle_id: str = Form("UNKNOWN"), vehicle_model: str = Form("Unknown"),
    vehicle_sensor_version: str = Form("v1.0"), image_caption: str = Form(""),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db), user: User = Depends(current_user)
):
    image_url = ""
    if image and image.filename:
        ext  = image.filename.split(".")[-1]
        name = f"{hashlib.md5(f'{lat}{lng}{datetime.utcnow()}'.encode()).hexdigest()[:8]}.{ext}"
        path = os.path.join(UPLOAD_DIR, name)
        with open(path, "wb") as f: f.write(await image.read())
        image_url = f"/uploads/{name}"

    address = f"{lat:.4f}, {lng:.4f}"
    ticket, is_new = find_or_create_ticket(db, defect_type, severity, lat, lng, address)

    vol  = round((defect_length_cm * defect_width_cm * defect_depth_cm) / 1_000_000, 6)
    area = round((defect_length_cm * defect_width_cm) / 10_000, 4)

    d = Detection(
        defect_type=defect_type, severity=severity, lat=lat, lng=lng,
        vehicle_id=vehicle_id, vehicle_model=vehicle_model,
        vehicle_sensor_version=vehicle_sensor_version,
        vehicle_speed_kmh=0, vehicle_heading_deg=0,
        reported_by=reported_by, notes=notes,
        defect_length_cm=defect_length_cm, defect_width_cm=defect_width_cm, defect_depth_cm=defect_depth_cm,
        defect_volume_m3=vol, surface_area_m2=area, repair_material_m3=round(vol*1.2,6),
        image_url=image_url, image_caption=image_caption,
        ticket_id=ticket.id
    )
    db.add(d); db.commit(); db.refresh(d)

    await hub.broadcast({"type": "new_detection", "ticket_id": ticket.id, "is_new_ticket": is_new,
                          "defect_type": defect_type, "severity": severity, "lat": lat, "lng": lng})
    return {"detection_id": d.id, "ticket_id": ticket.id, "is_new_ticket": is_new, "address": address}

@app.post("/api/detections")
async def create_detection(body: dict, db: Session = Depends(get_db), user: User = Depends(current_user)):
    lat, lng = body.get("lat", 32.0853), body.get("lng", 34.7818)
    dtype, sev = body.get("defect_type","pothole"), body.get("severity","medium")
    address = body.get("address", f"{lat:.4f}, {lng:.4f}")
    ticket, is_new = find_or_create_ticket(db, dtype, sev, lat, lng, address)
    d = Detection(**{k: v for k, v in body.items() if k in Detection.__table__.columns}, ticket_id=ticket.id)
    db.add(d); db.commit(); db.refresh(d)
    await hub.broadcast({"type": "new_detection", "ticket_id": ticket.id})
    return {"detection_id": d.id, "ticket_id": ticket.id, "is_new_ticket": is_new, "address": address}

# ── Ticket Routes ─────────────────────────────────────────────
def ticket_to_dict(t):
    dets = []
    for d in t.detections:
        dets.append({c.name: getattr(d, c.name) for c in d.__table__.columns
                     if c.name != "detected_at"} | {"detected_at": d.detected_at.isoformat() if d.detected_at else ""})
    return {c.name: getattr(t, c.name) for c in t.__table__.columns
            if c.name != "created_at"} | {"created_at": t.created_at.isoformat() if t.created_at else "", "detections": dets}

@app.get("/api/tickets")
def get_tickets(status: Optional[str] = None, limit: int = 100, db: Session = Depends(get_db), user: User = Depends(current_user)):
    q = db.query(Ticket)
    if status:
        statuses = [s.strip() for s in status.split(",")]
        q = q.filter(Ticket.status.in_(statuses))
    return [ticket_to_dict(t) for t in q.order_by(Ticket.created_at.desc()).limit(limit).all()]

@app.get("/api/tickets/{tid}")
def get_ticket(tid: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.query(Ticket).filter_by(id=tid).first()
    if not t: raise HTTPException(404)
    return ticket_to_dict(t)

@app.patch("/api/tickets/{tid}")
async def update_ticket(tid: int, body: TicketUpdate, db: Session = Depends(get_db), user: User = Depends(current_user)):
    t = db.query(Ticket).filter_by(id=tid).first()
    if not t: raise HTTPException(404)
    if body.status:   t.status = body.status
    if body.severity: t.severity = body.severity
    db.commit(); db.refresh(t)
    await hub.broadcast({"type": "ticket_updated", "ticket_id": t.id, "status": t.status})
    return ticket_to_dict(t)

# ── Stats ─────────────────────────────────────────────────────
@app.get("/api/stats/summary")
def stats(db: Session = Depends(get_db), user: User = Depends(current_user)):
    tickets = db.query(Ticket).all()
    return {
        "total_tickets":    len(tickets),
        "open_tickets":     sum(1 for t in tickets if t.status != "resolved"),
        "critical_tickets": sum(1 for t in tickets if t.severity == "critical" and t.status != "resolved"),
        "resolved_today":   sum(1 for t in tickets if t.status == "resolved"),
        "by_type":   {dt: sum(1 for t in tickets if t.defect_type == dt) for dt in ["pothole","road_crack","broken_light","drainage_blocked","sidewalk"]},
        "by_status": {s: sum(1 for t in tickets if t.status == s) for s in ["new","verified","assigned","in_progress","resolved"]},
    }

# ── Work Orders ───────────────────────────────────────────────
@app.get("/api/work-orders")
def get_work_orders(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{"id": w.id, "title": w.title, "status": w.status, "team": w.team, "priority": w.priority,
             "created_at": w.created_at.isoformat(), "ticket_ids": json.loads(w.ticket_ids)} for w in db.query(WorkOrder).all()]

# ── WebSocket ─────────────────────────────────────────────────
@app.websocket("/ws")
async def websocket(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True: await ws.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(ws)

# ── Static uploads ────────────────────────────────────────────
from fastapi.responses import FileResponse
@app.get("/uploads/{filename}")
def get_upload(filename: str):
    path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(path): raise HTTPException(404)
    return FileResponse(path)
