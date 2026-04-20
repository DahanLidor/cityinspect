"""
Agent: Ingest Validator — validates capture quality BEFORE burning AI tokens.

Checks image quality (blur, brightness) and sensor data (GPS accuracy,
speed, orientation) to reject bad captures early.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

# ── Thresholds ──────────────────────────────────────────────────────────
_BLUR_THRESHOLD = 100.0          # Laplacian variance below this = blurry
_BRIGHTNESS_MIN = 30             # Mean pixel value below this = too dark
_BRIGHTNESS_MAX = 240            # Mean pixel value above this = overexposed
_GPS_ACCURACY_MAX_M = 50.0       # Horizontal accuracy worse than this = bad
_SPEED_MAX_MS = 30.0             # Speed above this = driving too fast for capture
_ORIENTATION_PITCH_MIN = -30.0   # Phone nearly horizontal (pitch close to 0)
_ORIENTATION_PITCH_MAX = 30.0    # degrees from horizontal — too flat


def _check_image_quality(filepath: str) -> tuple[List[str], float]:
    """
    Analyse image for blur and brightness using PIL + numpy-free approach.

    Returns (issues_list, quality_score_component).
    """
    issues: List[str] = []
    score = 50.0  # image portion of total score (out of 50)

    try:
        from PIL import Image, ImageFilter, ImageStat
    except ImportError:
        logger.warning("PIL not available — skipping image quality checks")
        return issues, score

    if not os.path.exists(filepath):
        issues.append("קובץ תמונה לא נמצא")
        return issues, 0.0

    try:
        img = Image.open(filepath)
    except Exception as exc:
        issues.append(f"שגיאה בפתיחת התמונה: {exc}")
        return issues, 0.0

    # ── Blur detection via Laplacian approximation ───────────────────
    # PIL doesn't have Laplacian directly; approximate with FIND_EDGES variance
    try:
        gray = img.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        # variance = stddev^2
        edge_variance = edge_stat.stddev[0] ** 2

        if edge_variance < _BLUR_THRESHOLD:
            issues.append(
                f"תמונה מטושטשת (variance={edge_variance:.1f}, סף={_BLUR_THRESHOLD})"
            )
            score -= 20.0
        else:
            # Bonus for very sharp images
            score += min(5.0, (edge_variance - _BLUR_THRESHOLD) / 100.0)
    except Exception as exc:
        logger.warning("Blur detection failed", extra={"error": str(exc)})

    # ── Brightness check ────────────────────────────────────────────
    try:
        gray = img.convert("L")
        stat = ImageStat.Stat(gray)
        mean_brightness = stat.mean[0]

        if mean_brightness < _BRIGHTNESS_MIN:
            issues.append(
                f"תמונה חשוכה מדי (בהירות={mean_brightness:.0f}, מינימום={_BRIGHTNESS_MIN})"
            )
            score -= 15.0
        elif mean_brightness > _BRIGHTNESS_MAX:
            issues.append(
                f"תמונה חשופה יתר (בהירות={mean_brightness:.0f}, מקסימום={_BRIGHTNESS_MAX})"
            )
            score -= 15.0
    except Exception as exc:
        logger.warning("Brightness check failed", extra={"error": str(exc)})

    # ── Resolution check ────────────────────────────────────────────
    w, h = img.size
    if w < 640 or h < 480:
        issues.append(f"רזולוציה נמוכה ({w}x{h})")
        score -= 10.0

    return issues, max(0.0, score)


def _check_sensor_data(sensor_data: dict | None) -> tuple[List[str], float]:
    """
    Validate sensor data quality (GPS, speed, orientation).

    Returns (issues_list, quality_score_component out of 50).
    """
    issues: List[str] = []
    score = 50.0  # sensor portion of total score (out of 50)

    if not sensor_data:
        issues.append("אין נתוני חיישנים")
        return issues, 25.0  # partial score — image-only is still usable

    # ── GPS accuracy ────────────────────────────────────────────────
    gps = sensor_data.get("gps") or sensor_data.get("location") or {}
    accuracy = gps.get("horizontal_accuracy") or gps.get("accuracy")
    if accuracy is not None:
        accuracy = float(accuracy)
        if accuracy > _GPS_ACCURACY_MAX_M:
            issues.append(
                f"דיוק GPS נמוך ({accuracy:.0f} מ׳, סף={_GPS_ACCURACY_MAX_M:.0f} מ׳)"
            )
            score -= 15.0
        elif accuracy > 20:
            score -= 5.0  # mild penalty

    # ── Speed check ─────────────────────────────────────────────────
    speed = sensor_data.get("speed") or sensor_data.get("speed_ms")
    if speed is not None:
        speed = float(speed)
        if speed > _SPEED_MAX_MS:
            issues.append(
                f"מהירות נסיעה גבוהה ({speed:.1f} מ/ש, סף={_SPEED_MAX_MS:.0f} מ/ש)"
            )
            score -= 15.0
        elif speed > 15:
            score -= 5.0

    # ── Orientation check ───────────────────────────────────────────
    orientation = sensor_data.get("orientation") or sensor_data.get("attitude") or {}
    pitch = orientation.get("pitch")
    if pitch is not None:
        pitch = float(pitch)
        # pitch near 0 means phone is horizontal (not pointed at ground)
        if _ORIENTATION_PITCH_MIN < pitch < _ORIENTATION_PITCH_MAX:
            issues.append(
                f"הטלפון אופקי (pitch={pitch:.0f}°) — יש לכוון את המצלמה כלפי מטה"
            )
            score -= 10.0

    return issues, max(0.0, score)


async def agent_ingest_validator(
    filename: str,
    sensor_data: dict | None = None,
) -> Dict[str, Any]:
    """
    Validate capture quality before running expensive AI agents.

    Args:
        filename: Image filename (relative to upload_path).
        sensor_data: Optional dict with gps, speed, orientation from device.

    Returns:
        {valid: bool, issues: list, quality_score: 0-100}
    """
    logger.info("Ingest validator starting", extra={"filename": filename})

    filepath = os.path.join(settings.upload_path, filename)

    # Run checks
    img_issues, img_score = _check_image_quality(filepath)
    sensor_issues, sensor_score = _check_sensor_data(sensor_data)

    all_issues = img_issues + sensor_issues
    quality_score = round(max(0, min(100, img_score + sensor_score)))

    # Valid if no critical issues and score >= 30
    valid = quality_score >= 30 and not any(
        "לא נמצא" in issue for issue in all_issues
    )

    result = {
        "valid": valid,
        "issues": all_issues,
        "quality_score": quality_score,
        "image_score": round(img_score),
        "sensor_score": round(sensor_score),
        "filename": filename,
    }

    logger.info(
        "Ingest validation done",
        extra={
            "valid": valid,
            "quality_score": quality_score,
            "issue_count": len(all_issues),
        },
    )
    return result
