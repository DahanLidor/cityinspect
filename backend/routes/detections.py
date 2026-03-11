from fastapi import APIRouter, Depends, UploadFile, File, Form
from sqlalchemy.orm import Session
from database import get_db
from models import Detection
from schemas import DetectionCreate, DetectionResponse
from services.deduplication import find_or_create_ticket
import aiofiles, os, uuid
from datetime import datetime

router = APIRouter(prefix="/api/detections", tags=["detections"])
UPLOAD_DIR = "static/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def calc_geometry(length_cm: float, width_cm: float, depth_cm: float):
    volume = (length_cm * width_cm * depth_cm) / 1_000_000
    repair = volume * 1.2
    area = (length_cm * width_cm) / 10_000
    return volume, repair, area


async def _save_detection(db: Session, data: dict, image_url: str = "") -> DetectionResponse:
    length = data.get("defect_length_cm", 0)
    width = data.get("defect_width_cm", 0)
    depth = data.get("defect_depth_cm", 0)
    volume, repair, area = calc_geometry(length, width, depth)

    ticket, is_new = find_or_create_ticket(db, data)

    detection = Detection(
        **{k: v for k, v in data.items() if hasattr(Detection, k)},
        defect_volume_m3=volume,
        repair_material_m3=repair,
        surface_area_m2=area,
        ticket_id=ticket.id,
        image_url=image_url or data.get("image_url", ""),
        detected_at=datetime.utcnow()
    )
    db.add(detection)
    db.commit()
    db.refresh(detection)

    return DetectionResponse(
        detection_id=detection.id,
        ticket_id=ticket.id,
        is_new_ticket=is_new,
        address=ticket.address
    )


@router.post("", response_model=DetectionResponse)
async def create_detection(payload: DetectionCreate, db: Session = Depends(get_db)):
    from main import broadcast
    result = await _save_detection(db, payload.model_dump())
    await broadcast({"type": "new_detection", "ticket_id": result.ticket_id, "is_new": result.is_new_ticket})
    return result


@router.post("/upload", response_model=DetectionResponse)
async def create_detection_with_image(
    vehicle_id: str = Form("V001"),
    vehicle_model: str = Form("Field Agent"),
    vehicle_sensor_version: str = Form("MobileApp-v1.0"),
    vehicle_speed_kmh: float = Form(0),
    vehicle_heading_deg: float = Form(0),
    reported_by: str = Form("mobile_app"),
    defect_type: str = Form(...),
    severity: str = Form(...),
    lat: float = Form(...),
    lng: float = Form(...),
    defect_length_cm: float = Form(0),
    defect_width_cm: float = Form(0),
    defect_depth_cm: float = Form(0),
    ambient_temp_c: float = Form(20),
    asphalt_temp_c: float = Form(35),
    weather_condition: str = Form("Clear"),
    wind_speed_kmh: float = Form(10),
    humidity_pct: float = Form(50),
    visibility_m: int = Form(10000),
    image_caption: str = Form(""),
    notes: str = Form(""),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    image_url = ""
    if image and image.filename:
        ext = image.filename.split(".")[-1]
        fname = f"{uuid.uuid4()}.{ext}"
        path = os.path.join(UPLOAD_DIR, fname)
        async with aiofiles.open(path, "wb") as f:
            await f.write(await image.read())
        image_url = f"/static/uploads/{fname}"

    data = dict(
        vehicle_id=vehicle_id, vehicle_model=vehicle_model,
        vehicle_sensor_version=vehicle_sensor_version,
        vehicle_speed_kmh=vehicle_speed_kmh, vehicle_heading_deg=vehicle_heading_deg,
        reported_by=reported_by, defect_type=defect_type, severity=severity,
        lat=lat, lng=lng, defect_length_cm=defect_length_cm,
        defect_width_cm=defect_width_cm, defect_depth_cm=defect_depth_cm,
        ambient_temp_c=ambient_temp_c, asphalt_temp_c=asphalt_temp_c,
        weather_condition=weather_condition, wind_speed_kmh=wind_speed_kmh,
        humidity_pct=humidity_pct, visibility_m=visibility_m,
        image_caption=image_caption, notes=notes
    )
    from main import broadcast
    result = await _save_detection(db, data, image_url)
    await broadcast({"type": "new_detection", "ticket_id": result.ticket_id, "is_new": result.is_new_ticket})
    return result
