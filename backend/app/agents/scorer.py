"""
Agent 4: Scorer — deterministic severity scoring combining VLM + env + geometry.
"""
from __future__ import annotations

from typing import Any, Dict

from app.core.logging import get_logger

logger = get_logger(__name__)

_SEVERITY_THRESHOLDS = [(80, "critical"), (60, "high"), (35, "medium"), (0, "low")]
_VLM_SCORE_MAP = {"critical": 38, "high": 30, "medium": 20, "low": 10}


def agent_scorer(
    vlm_result: Dict[str, Any],
    env_result: Dict[str, Any],
    dedup_result: Dict[str, Any],
    detection: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Combine all agent outputs into a final [0–100] severity score.

    Weights:
      VLM severity × confidence  →  0–40
      Environment proximity      →  0–30
      LiDAR geometry             →  0–30
    """
    if dedup_result.get("is_duplicate"):
        return {
            "final_score": 0,
            "severity": "duplicate",
            "reasoning": f"כפילות של דיווח #{dedup_result.get('duplicate_of')}",
            "action": "mark_duplicate",
            "breakdown": {},
        }

    hazard_detected = vlm_result.get("hazard_detected", True)
    if not hazard_detected:
        return {
            "final_score": 5,
            "severity": "none",
            "reasoning": "VLM לא זיהה מפגע בתמונה",
            "action": "review",
            "breakdown": {"vlm": 5, "env": 0, "geometry": 0},
        }

    # VLM component (0-40)
    vlm_severity = vlm_result.get("severity_hint", "medium")
    vlm_confidence = float(vlm_result.get("confidence", 0.5))
    vlm_score = _VLM_SCORE_MAP.get(vlm_severity, 20) * vlm_confidence

    # Environment component (0-30)
    env_score = min(float(env_result.get("environment_score", 15)) * 0.3, 30.0)

    # Geometry component (0-30) from LiDAR measurements
    depth = float(detection.get("defect_depth_cm") or 0)
    width = float(detection.get("defect_width_cm") or 0)
    area = float(detection.get("surface_area_m2") or 0)

    geo_score = 0.0
    if depth > 10:
        geo_score += 15
    elif depth > 5:
        geo_score += 8
    elif depth > 2:
        geo_score += 4

    if width > 50:
        geo_score += 10
    elif width > 20:
        geo_score += 5

    if area > 0.5:
        geo_score += 5

    total = max(5, min(100, round(vlm_score + env_score + geo_score)))

    severity = "low"
    for threshold, label in _SEVERITY_THRESHOLDS:
        if total >= threshold:
            severity = label
            break

    # Build readable reasoning
    reasons = []
    hazard_type = vlm_result.get("hazard_type")
    if hazard_type and hazard_type not in ("unknown", "none"):
        reasons.append(f"זוהה: {hazard_type}")
    liability = vlm_result.get("liability_risk")
    if liability:
        reasons.append(f"סיכון נזיקין: {liability}")
    for rf in (env_result.get("risk_factors") or [])[:2]:
        reasons.append(rf)
    if depth > 0:
        reasons.append(f"עומק {depth} ס״מ")

    result = {
        "final_score": total,
        "severity": severity,
        "reasoning": " | ".join(reasons) or "ניתוח אוטומטי",
        "action": "alert" if severity in ("critical", "high") else "monitor",
        "breakdown": {
            "vlm": round(vlm_score),
            "environment": round(env_score),
            "geometry": round(geo_score),
        },
    }
    logger.info("Scorer result", extra={"score": total, "severity": severity})
    return result
