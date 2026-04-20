"""
Agent: Risk Predictor — predicts future hazard probability and liability exposure.

Combines VLM analysis, environmental context, geometry estimation, and
temporal tracking to produce a comprehensive risk assessment with
liability cost projections in NIS.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Base liability cost per defect type (NIS/month if unresolved) ───────
_BASE_LIABILITY_NIS = {
    "pothole": 12_000,
    "crack": 4_000,
    "broken_sidewalk": 8_000,
    "drainage": 6_000,
    "drainage_blocked": 6_000,
    "signage": 3_000,
    "broken_light": 5_000,
    "road_damage": 10_000,
    "road_crack": 5_000,
    "other": 5_000,
    "unknown": 5_000,
}

# ── Risk level thresholds ──────────────────────────────────────────────
_RISK_LEVELS = [
    (80, "critical", "קריטי"),
    (60, "high", "גבוה"),
    (35, "medium", "בינוני"),
    (0, "low", "נמוך"),
]


def _calculate_base_risk(vlm_result: dict) -> float:
    """Calculate base risk score from VLM severity and confidence."""
    severity_map = {"critical": 75, "high": 55, "medium": 35, "low": 15}
    severity = vlm_result.get("severity_hint", "medium")
    confidence = float(vlm_result.get("confidence", 0.5))

    base = severity_map.get(severity, 35)
    return base * (0.5 + confidence * 0.5)


def _apply_environmental_amplifiers(
    risk: float, env_result: dict
) -> tuple[float, List[str]]:
    """Apply environmental risk amplifiers."""
    factors: List[str] = []

    # School / kindergarten nearby → 1.4x
    nearby = env_result.get("nearby_places", [])
    for place in nearby:
        ptype = place.get("type", "")
        dist = place.get("distance_m", 999)
        if ptype in ("בית ספר", "גן ילדים") and dist < 200:
            risk *= 1.4
            factors.append(f"סמיכות ל{ptype} ({dist} מ׳) — מכפיל ×1.4")
            break  # apply once

    # Hospital nearby
    for place in nearby:
        if place.get("type") == "בית חולים" and place.get("distance_m", 999) < 150:
            risk *= 1.2
            factors.append("סמיכות לבית חולים — מכפיל ×1.2")
            break

    # Rain / precipitation
    weather = env_result.get("weather", {})
    precip = float(weather.get("precipitation_mm", 0) or 0)
    weather_code = weather.get("weather_code", 0) or 0
    if precip > 0 or weather_code in (61, 63, 65, 80, 81, 82, 95, 96, 99):
        risk *= 1.3
        factors.append("גשם פעיל — מכפיל ×1.3 (סכנת החלקה מוגברת)")

    # High pedestrian area
    env_score = float(env_result.get("environment_score", 0))
    if env_score > 50:
        risk *= 1.15
        factors.append("אזור עם תנועה ציבורית רבה — מכפיל ×1.15")

    return risk, factors


def _apply_temporal_amplifiers(
    risk: float, temporal_result: dict
) -> tuple[float, List[str]]:
    """Apply temporal risk amplifiers."""
    factors: List[str] = []

    trend = temporal_result.get("trend", "stable")
    days_open = int(temporal_result.get("days_open", 0))

    # Worsening trend → 1.5x
    if trend == "worsening":
        risk *= 1.5
        factors.append("מגמת החמרה — מכפיל ×1.5")

    # Open > 30 days → 1.2x
    if days_open > 30:
        risk *= 1.2
        factors.append(f"פתוח {days_open} ימים ללא טיפול — מכפיל ×1.2")

    # Open > 90 days → additional 1.2x (cumulative negligence)
    if days_open > 90:
        risk *= 1.2
        factors.append(f"פתוח מעל 90 ימים — חשיפה משפטית מוגברת (×1.2 נוסף)")

    return risk, factors


def _apply_geometry_amplifiers(
    risk: float, geometry_result: dict
) -> tuple[float, List[str]]:
    """Apply geometry-based risk amplifiers."""
    factors: List[str] = []

    depth = float(geometry_result.get("estimated_depth_cm", 0))
    width = float(geometry_result.get("estimated_width_cm", 0))
    area = float(geometry_result.get("estimated_area_m2", 0))

    # Depth > 10cm → 1.3x
    if depth > 10:
        risk *= 1.3
        factors.append(f"עומק משוער {depth} ס\"מ — מכפיל ×1.3")
    elif depth > 5:
        risk *= 1.15
        factors.append(f"עומק משוער {depth} ס\"מ — מכפיל ×1.15")

    # Large area
    if area > 0.5:
        risk *= 1.2
        factors.append(f"שטח משוער {area} מ\"ר — מכפיל ×1.2")

    # Wide defect on road surface
    if width > 30:
        risk *= 1.1
        factors.append(f"רוחב משוער {width} ס\"מ — מכפיל ×1.1")

    return risk, factors


def _get_recommendation(risk_score: float, trend: str, days_open: int) -> str:
    """Generate Hebrew recommendation based on risk assessment."""
    if risk_score >= 80:
        return "נדרש תיקון דחוף — סיכון גבוה לתביעת נזיקין. יש לסגור את האזור ולתקן תוך 24 שעות."
    if risk_score >= 60:
        return "מומלץ תיקון בתוך שבוע. סיכון משמעותי לנזק גופני ותביעה משפטית."
    if trend == "worsening":
        return "המפגע מחמיר — מומלץ לתזמן תיקון לפני שהמצב מידרדר."
    if days_open > 30:
        return f"המפגע פתוח {days_open} ימים. ככל שהזמן עובר, החשיפה המשפטית גדלה."
    if risk_score >= 35:
        return "מומלץ לעקוב ולתזמן תיקון בתוך חודש."
    return "סיכון נמוך — ניטור תקופתי מספיק בשלב זה."


async def agent_risk_predictor(
    vlm_result: dict,
    env_result: dict,
    geometry_result: dict,
    temporal_result: dict,
) -> Dict[str, Any]:
    """
    Predict future hazard probability and liability exposure.

    Args:
        vlm_result: Output from VLM agent.
        env_result: Output from environment agent.
        geometry_result: Output from geometry estimator.
        temporal_result: Output from temporal tracker.

    Returns:
        Comprehensive risk assessment with liability projections.
    """
    logger.info("Risk predictor starting")

    all_factors: List[str] = []

    # ── Base risk from VLM ──────────────────────────────────────────
    risk = _calculate_base_risk(vlm_result)

    # ── Apply amplifiers ────────────────────────────────────────────
    risk, env_factors = _apply_environmental_amplifiers(risk, env_result)
    all_factors.extend(env_factors)

    risk, temp_factors = _apply_temporal_amplifiers(risk, temporal_result)
    all_factors.extend(temp_factors)

    risk, geo_factors = _apply_geometry_amplifiers(risk, geometry_result)
    all_factors.extend(geo_factors)

    # ── Clamp to 0–100 ──────────────────────────────────────────────
    risk_score = round(max(0, min(100, risk)))

    # ── Determine risk level ────────────────────────────────────────
    risk_level = "low"
    risk_level_he = "נמוך"
    for threshold, level, level_he in _RISK_LEVELS:
        if risk_score >= threshold:
            risk_level = level
            risk_level_he = level_he
            break

    # ── Liability exposure calculation ──────────────────────────────
    hazard_type = vlm_result.get("hazard_type", "unknown")
    base_liability = _BASE_LIABILITY_NIS.get(hazard_type, 5_000)

    # Scale liability by risk score
    liability_multiplier = risk_score / 50.0  # 1.0 at score 50, 2.0 at score 100
    liability_exposure_nis_monthly = round(base_liability * liability_multiplier)

    # ── Predicted worsening timeline ────────────────────────────────
    trend = temporal_result.get("trend", "stable")
    if trend == "worsening":
        predicted_worsening_days = 14  # expect significant deterioration in 2 weeks
    elif trend == "stable" and risk_score >= 50:
        predicted_worsening_days = 45  # moderate risk, slow degradation
    else:
        predicted_worsening_days = 90  # low risk, slow change

    days_open = int(temporal_result.get("days_open", 0))

    result = {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_level_he": risk_level_he,
        "liability_exposure_nis_monthly": liability_exposure_nis_monthly,
        "factors": all_factors,
        "recommendation": _get_recommendation(risk_score, trend, days_open),
        "predicted_worsening_days": predicted_worsening_days,
        "hazard_type": hazard_type,
        "trend": trend,
    }

    logger.info(
        "Risk prediction done",
        extra={
            "risk_score": risk_score,
            "risk_level": risk_level,
            "liability_nis": liability_exposure_nis_monthly,
            "factors_count": len(all_factors),
        },
    )
    return result
