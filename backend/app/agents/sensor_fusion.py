"""
Sensor Fusion Engine
====================

Combines all device sensor signals into a unified confidence assessment.

Key insight: each sensor has different reliability in different conditions.
GPS degrades indoors, IMU gyro noise means camera shake, LiDAR gives precise
geometry but only some devices have it, and ambient lux determines whether
image data will be usable at all.

The engine produces a single capture-grade verdict (A/B/C/D) that downstream
agents (VLM, scorer, dedup) can use to weight their own outputs.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Thresholds & weights
# ---------------------------------------------------------------------------

_GPS_MAX_ACCURACY_M = 50.0  # Beyond this we consider location unreliable

_GYRO_SHAKE_LOW = 0.5       # rad/s total — very stable
_GYRO_SHAKE_HIGH = 3.0      # rad/s total — likely blurry

_LUX_IDEAL_LOW = 1_000.0
_LUX_IDEAL_HIGH = 30_000.0
_LUX_MIN = 50.0             # Below this: too dark
_LUX_MAX = 100_000.0        # Above this: washed out / glare

_WEIGHT_LOCATION = 0.2
_WEIGHT_IMAGE = 0.5
_WEIGHT_GEOMETRY = 0.3

_GRADE_THRESHOLDS = [
    ("A", 0.8),
    ("B", 0.6),
    ("C", 0.4),
]


# ---------------------------------------------------------------------------
# Helper: clamp
# ---------------------------------------------------------------------------

def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Sub-confidence calculators
# ---------------------------------------------------------------------------

def _location_confidence(sensor_data: dict) -> tuple[float, list[str]]:
    """Derive location confidence from GPS accuracy (metres)."""
    warnings: list[str] = []
    device = sensor_data.get("device") or {}
    gps_accuracy = device.get("gps_accuracy_m")

    if gps_accuracy is None:
        logger.warning("No GPS accuracy data available")
        warnings.append("GPS accuracy data missing")
        return 0.3, warnings

    conf = _clamp(1.0 - (gps_accuracy / _GPS_MAX_ACCURACY_M))

    if gps_accuracy > 30:
        warnings.append("GPS accuracy low (>30 m)")
    elif gps_accuracy > 15:
        warnings.append("GPS accuracy moderate (>15 m)")

    return conf, warnings


def _image_confidence(sensor_data: dict) -> tuple[float, list[str]]:
    """Derive image confidence from IMU stability and ambient lighting."""
    warnings: list[str] = []

    # --- Stability (gyroscope) ---
    imu = sensor_data.get("imu") or {}
    gyro = imu.get("gyro") or {}
    gx = abs(gyro.get("x", 0.0))
    gy = abs(gyro.get("y", 0.0))
    gz = abs(gyro.get("z", 0.0))
    shake = gx + gy + gz

    if shake <= _GYRO_SHAKE_LOW:
        stability = 1.0
    elif shake >= _GYRO_SHAKE_HIGH:
        stability = 0.0
        warnings.append("Image may be blurry (high shake)")
    else:
        stability = _clamp(1.0 - (shake - _GYRO_SHAKE_LOW) / (_GYRO_SHAKE_HIGH - _GYRO_SHAKE_LOW))
        if stability < 0.5:
            warnings.append("Image may be blurry (high shake)")

    # --- Lighting (lux) ---
    env = sensor_data.get("environment") or {}
    lux = env.get("lux")

    if lux is None:
        lighting = 0.5  # Unknown — assume mediocre
        warnings.append("Ambient light data missing")
    elif lux < _LUX_MIN:
        lighting = 0.1
        warnings.append("Low light conditions")
    elif lux < _LUX_IDEAL_LOW:
        lighting = _clamp(0.3 + 0.7 * (lux - _LUX_MIN) / (_LUX_IDEAL_LOW - _LUX_MIN))
        if lighting < 0.5:
            warnings.append("Low light conditions")
    elif lux <= _LUX_IDEAL_HIGH:
        lighting = 1.0
    elif lux <= _LUX_MAX:
        lighting = _clamp(1.0 - 0.5 * (lux - _LUX_IDEAL_HIGH) / (_LUX_MAX - _LUX_IDEAL_HIGH))
    else:
        lighting = 0.3
        warnings.append("Extreme brightness — possible glare")

    # Combine stability and lighting equally for image confidence
    conf = stability * 0.6 + lighting * 0.4
    return _clamp(conf), warnings


def _geometry_confidence(sensor_data: dict) -> tuple[float, str, list[str]]:
    """Derive geometry confidence and determine the best available source."""
    warnings: list[str] = []

    lidar = sensor_data.get("lidar")
    if lidar and lidar.get("available", False):
        return 0.95, "lidar", warnings

    lens = sensor_data.get("lens") or sensor_data.get("camera") or {}
    has_intrinsics = bool(
        lens.get("focal_length") or lens.get("intrinsics") or lens.get("focal_length_mm")
    )
    if has_intrinsics:
        return 0.7, "camera_intrinsics", warnings

    warnings.append("No LiDAR or lens intrinsics — geometry is estimated")
    return 0.3, "estimated", warnings


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def fuse_sensors(sensor_data: dict) -> dict[str, Any]:
    """
    Combine all sensor signals into a confidence-weighted assessment.

    Parameters
    ----------
    sensor_data : dict
        Expected keys (all optional, gracefully degraded when absent):
        ``imu``, ``camera``, ``lens``, ``lidar``, ``device``, ``environment``.

    Returns
    -------
    dict
        ``overall_confidence``  – 0.0-1.0
        ``location_confidence`` – 0.0-1.0 (GPS accuracy)
        ``image_confidence``    – 0.0-1.0 (IMU stability + lighting)
        ``geometry_confidence`` – 0.0-1.0 (lidar > intrinsics > nothing)
        ``geometry_source``     – ``"lidar"`` | ``"camera_intrinsics"`` | ``"estimated"``
        ``capture_grade``       – ``"A"`` | ``"B"`` | ``"C"`` | ``"D"``
        ``warnings``            – list of human-readable issue strings
    """
    if not sensor_data:
        sensor_data = {}

    warnings: list[str] = []

    loc_conf, loc_warns = _location_confidence(sensor_data)
    img_conf, img_warns = _image_confidence(sensor_data)
    geo_conf, geo_source, geo_warns = _geometry_confidence(sensor_data)

    warnings.extend(loc_warns)
    warnings.extend(img_warns)
    warnings.extend(geo_warns)

    overall = _clamp(
        loc_conf * _WEIGHT_LOCATION
        + img_conf * _WEIGHT_IMAGE
        + geo_conf * _WEIGHT_GEOMETRY
    )

    # Determine capture grade
    grade = "D"
    for letter, threshold in _GRADE_THRESHOLDS:
        if overall > threshold:
            grade = letter
            break

    logger.info(
        "Sensor fusion complete: grade=%s overall=%.2f "
        "(loc=%.2f img=%.2f geo=%.2f [%s]) warnings=%d",
        grade, overall, loc_conf, img_conf, geo_conf, geo_source, len(warnings),
    )

    return {
        "overall_confidence": round(overall, 4),
        "location_confidence": round(loc_conf, 4),
        "image_confidence": round(img_conf, 4),
        "geometry_confidence": round(geo_conf, 4),
        "geometry_source": geo_source,
        "capture_grade": grade,
        "warnings": warnings,
    }
