"""
Agent: Geometry Estimator — estimates defect dimensions from camera intrinsics.

Uses focal length, field of view, image resolution, and camera pitch to
calculate Ground Sample Distance (GSD) and estimate physical defect size
without requiring LiDAR hardware.
"""
from __future__ import annotations

import math
from typing import Any, Dict

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Depth estimation heuristics by severity ─────────────────────────────
_DEPTH_BY_SEVERITY = {
    "critical": 8.0,   # cm — deep pothole / severe damage
    "high": 5.0,
    "medium": 3.0,
    "low": 1.0,
}

# ── Default camera parameters (iPhone 14 Pro main camera) ──────────────
_DEFAULT_FOCAL_LENGTH_MM = 6.86
_DEFAULT_SENSOR_HEIGHT_MM = 5.6    # approximate for 1/1.28" sensor
_DEFAULT_FOV_DEG = 77.0
_DEFAULT_IMAGE_WIDTH = 4032
_DEFAULT_IMAGE_HEIGHT = 3024
_DEFAULT_CAMERA_HEIGHT_M = 1.5     # typical handheld height


def _calculate_gsd(
    focal_length_mm: float,
    camera_height_m: float,
    pitch_deg: float,
    image_width_px: int,
    fov_deg: float,
) -> float:
    """
    Calculate Ground Sample Distance (GSD) in cm/pixel.

    GSD = (sensor_width_on_ground / image_width_px)

    For a downward-looking camera at height H with pitch angle θ:
        distance_to_ground = H / cos(θ)
        ground_width = 2 * distance_to_ground * tan(FOV/2)
        GSD = ground_width / image_width_px (converted to cm)
    """
    pitch_rad = math.radians(abs(pitch_deg)) if pitch_deg else 0.0

    # Clamp pitch to avoid division by zero at 90 degrees
    if pitch_rad >= math.radians(85):
        pitch_rad = math.radians(85)

    # Distance from camera to the ground plane
    cos_pitch = math.cos(pitch_rad) if pitch_rad < math.radians(89) else 0.02
    distance_to_ground = camera_height_m / cos_pitch

    # Width of ground covered in the image
    fov_rad = math.radians(fov_deg)
    ground_width_m = 2.0 * distance_to_ground * math.tan(fov_rad / 2.0)

    # GSD in cm per pixel
    gsd = (ground_width_m * 100.0) / image_width_px

    return gsd


def _estimate_camera_height(pitch_deg: float, focal_length_mm: float) -> float:
    """
    Heuristic: estimate camera height from pitch angle.
    If pointing steeply down, user is probably standing (1.5m).
    If nearly horizontal, user might be crouching closer.
    """
    if abs(pitch_deg) > 60:
        return 1.5  # standing, phone pointed down
    elif abs(pitch_deg) > 30:
        return 1.2  # angled view
    else:
        return 1.0  # close-up or crouching


async def agent_geometry_estimator(
    sensor_data: dict | None = None,
    vlm_result: dict | None = None,
) -> Dict[str, Any]:
    """
    Estimate defect physical dimensions from camera intrinsics and VLM output.

    Args:
        sensor_data: Device sensor data with lens/camera info.
        vlm_result: VLM analysis result with severity_hint and confidence.

    Returns:
        Dict with estimated dimensions, area, GSD, and confidence.
    """
    logger.info("Geometry estimator starting")

    sensor_data = sensor_data or {}
    vlm_result = vlm_result or {}

    # ── Extract camera parameters ───────────────────────────────────
    lens = sensor_data.get("lens") or sensor_data.get("camera") or {}
    focal_length_mm = float(lens.get("focal_length_mm", _DEFAULT_FOCAL_LENGTH_MM))
    fov_deg = float(lens.get("fov_deg", _DEFAULT_FOV_DEG))

    resolution = sensor_data.get("image_resolution") or sensor_data.get("resolution") or {}
    image_width = int(resolution.get("width", _DEFAULT_IMAGE_WIDTH))
    image_height = int(resolution.get("height", _DEFAULT_IMAGE_HEIGHT))

    camera = sensor_data.get("camera") or sensor_data.get("attitude") or {}
    pitch_deg = float(camera.get("pitch", -60.0))  # negative = looking down

    camera_height_m = float(
        sensor_data.get("camera_height_m", _estimate_camera_height(pitch_deg, focal_length_mm))
    )

    # ── Calculate GSD ───────────────────────────────────────────────
    gsd = _calculate_gsd(focal_length_mm, camera_height_m, pitch_deg, image_width, fov_deg)

    # ── Estimate defect size from VLM confidence as proxy ───────────
    # Higher confidence typically correlates with larger, more visible defects.
    # We use confidence as a rough bounding-box percentage proxy.
    confidence = float(vlm_result.get("confidence", 0.5))
    severity_hint = vlm_result.get("severity_hint", "medium")

    # Estimate bounding box as percentage of image
    # Confidence 0.9+ → defect fills ~20% of image width
    # Confidence 0.5  → defect fills ~8% of image width
    bbox_width_frac = 0.04 + (confidence * 0.18)   # 4%–22% of image
    bbox_height_frac = 0.03 + (confidence * 0.15)   # 3%–18% of image

    # Convert to physical dimensions
    width_px = image_width * bbox_width_frac
    height_px = image_height * bbox_height_frac

    estimated_width_cm = round(width_px * gsd, 1)
    estimated_length_cm = round(height_px * gsd, 1)

    # ── Depth estimation from severity ──────────────────────────────
    base_depth = _DEPTH_BY_SEVERITY.get(severity_hint, 3.0)
    # Scale by confidence
    estimated_depth_cm = round(base_depth * (0.5 + confidence * 0.5), 1)

    # ── Area in square metres ───────────────────────────────────────
    estimated_area_m2 = round(
        (estimated_width_cm / 100.0) * (estimated_length_cm / 100.0), 4
    )

    # ── Estimation confidence ───────────────────────────────────────
    # Lower if we used defaults (no real sensor data)
    estimation_confidence = 0.7
    if not sensor_data.get("lens") and not sensor_data.get("camera"):
        estimation_confidence = 0.3  # all defaults
    elif not sensor_data.get("camera", {}).get("pitch"):
        estimation_confidence = 0.5  # no pitch data

    method = "camera_intrinsics"
    if estimation_confidence <= 0.3:
        method = "heuristic_defaults"

    result = {
        "estimated_width_cm": estimated_width_cm,
        "estimated_length_cm": estimated_length_cm,
        "estimated_depth_cm": estimated_depth_cm,
        "estimated_area_m2": estimated_area_m2,
        "gsd_cm_per_pixel": round(gsd, 4),
        "confidence": round(estimation_confidence, 2),
        "method": method,
        "camera_params": {
            "focal_length_mm": focal_length_mm,
            "fov_deg": fov_deg,
            "pitch_deg": pitch_deg,
            "camera_height_m": camera_height_m,
            "image_resolution": f"{image_width}x{image_height}",
        },
    }

    logger.info(
        "Geometry estimation done",
        extra={
            "width_cm": estimated_width_cm,
            "length_cm": estimated_length_cm,
            "depth_cm": estimated_depth_cm,
            "gsd": round(gsd, 4),
            "method": method,
        },
    )
    return result
