"""
Use Cases router — serves supported defect categories per city,
and validates images against a selected use case via VLM.
"""
from __future__ import annotations

import base64
import pathlib
from typing import Optional

import anthropic
import yaml
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import get_current_user
from app.models import User

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1", tags=["use-cases"])
settings = get_settings()

def _find_muni_root() -> pathlib.Path:
    for p in [pathlib.Path("/municipalities"), pathlib.Path(__file__).parents[3] / "municipalities", pathlib.Path(__file__).parents[2] / "municipalities"]:
        if p.exists():
            return p
    return pathlib.Path("/municipalities")

_MUNI_ROOT = _find_muni_root()

# ── Cache ─────────────────────────────────────────────────────────────────────

_cache: dict[str, list[dict]] = {}


def load_use_cases(city_id: str) -> list[dict]:
    if city_id in _cache:
        return _cache[city_id]

    for candidate in [city_id, "_default"]:
        path = _MUNI_ROOT / candidate / "use_cases.yaml"
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            result = data.get("use_cases", [])
            _cache[city_id] = result
            return result

    return []


# ── Schemas ───────────────────────────────────────────────────────────────────

class UseCaseOut(BaseModel):
    id: str
    name_he: str
    name_en: str
    icon: str
    severity_default: str


class ValidationResult(BaseModel):
    valid: bool
    reason: str
    confidence: float  # 0.0 – 1.0


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/use-cases", response_model=list[UseCaseOut])
async def get_use_cases(
    city_id: str = "tel-aviv",
    user: User = Depends(get_current_user),
):
    cases = load_use_cases(city_id)
    if not cases:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=f"No use cases configured for city: {city_id}")
    return [UseCaseOut(**{k: v for k, v in uc.items() if k in UseCaseOut.model_fields}) for uc in cases]


@router.post("/validate/image", response_model=ValidationResult)
async def validate_image(
    use_case_id: str = Form(...),
    city_id: str = Form("tel-aviv"),
    image: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    # Load use case definition
    cases = load_use_cases(city_id)
    use_case = next((uc for uc in cases if uc["id"] == use_case_id), None)
    if not use_case:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=f"Unknown use case: {use_case_id}")

    # Check API key
    api_key = settings.anthropic_api_key
    if not api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail="ANTHROPIC_API_KEY not configured")

    # Read image
    raw = await image.read(10 * 1024 * 1024)  # 10 MB max
    b64 = base64.standard_b64encode(raw).decode()
    media_type = image.content_type or "image/jpeg"

    # Call VLM
    client = anthropic.AsyncAnthropic(api_key=api_key)
    prompt = f"""You are a municipal infrastructure inspection AI.

The field worker selected the defect category: "{use_case['name_en']}" ({use_case['name_he']}).
Definition: {use_case['vlm_description']}

Look at the image and determine:
1. Does the image actually show this type of defect?
2. Is there a clear, visible defect of this category in the image?

Respond ONLY with a JSON object in this exact format:
{{"valid": true/false, "reason": "one sentence explanation in Hebrew", "confidence": 0.0-1.0}}

Be strict: if the image does not clearly show this defect type, return valid=false."""

    try:
        msg = await client.messages.create(
            model="claude-opus-4-5",
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        import json
        text = msg.content[0].text.strip()
        # Extract JSON from response
        start = text.find("{")
        end = text.rfind("}") + 1
        result = json.loads(text[start:end])
        return ValidationResult(
            valid=bool(result.get("valid", False)),
            reason=result.get("reason", ""),
            confidence=float(result.get("confidence", 0.0)),
        )
    except Exception as exc:
        logger.error("VLM validation error", extra={"error": str(exc)})
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=f"VLM error: {exc}")
