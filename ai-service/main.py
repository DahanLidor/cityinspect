"""AI Detection Microservice – serves hazard classification via HTTP."""

import logging
import os
from datetime import datetime, timezone

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from hazard_detection import HazardDetector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="CityInspect AI Detection Service", version="1.0.0")

# ── Model initialization ────────────────────────────────────

MODEL_PATH = os.getenv("AI_MODEL_PATH", "/models/yolov8_hazard.pt")
CONFIDENCE = float(os.getenv("AI_CONFIDENCE_THRESHOLD", "0.45"))

detector = HazardDetector(model_path=MODEL_PATH, confidence_threshold=CONFIDENCE)


# ── Schemas ─────────────────────────────────────────────────

class DetectionResponse(BaseModel):
    hazard_type: str
    confidence: float
    bounding_box: list[float] | None = None
    model_version: str


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_version: str
    timestamp: str


# ── Endpoints ───────────────────────────────────────────────

@app.post("/detect", response_model=DetectionResponse)
async def detect_hazard(file: UploadFile = File(...)):
    """Accept an image and return hazard classification."""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image (JPEG/PNG)")

    try:
        image_bytes = await file.read()
        result = detector.detect_from_bytes(image_bytes)
    except Exception as e:
        logger.error(f"Detection error: {e}")
        raise HTTPException(status_code=500, detail="Detection failed")

    return DetectionResponse(
        hazard_type=result.hazard_type,
        confidence=result.confidence,
        bounding_box=result.bounding_box,
        model_version=result.model_version,
    )


@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="healthy",
        model_loaded=detector.model is not None,
        model_version=detector.model_version,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
