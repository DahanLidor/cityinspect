"""
Agent: Repair Recommender — recommends repair method, materials, and cost.

Uses a built-in REPAIR_DB of recipes per defect type and size category,
calculates material quantities from geometry estimates, and checks
weather constraints. This is a sync function (no API calls).
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Size classification thresholds (area in m²) ────────────────────────
_SIZE_THRESHOLDS = {
    "small": 0.05,    # up to 0.05 m²
    "medium": 0.25,   # up to 0.25 m²
    # above 0.25 m² = large
}

# ── Repair database: recipes per defect type and size ──────────────────
REPAIR_DB: Dict[str, Dict[str, Dict[str, Any]]] = {
    "pothole": {
        "small": {
            "method": "Cold patch fill",
            "method_he": "מילוי טלאי קר",
            "materials": [
                {"name": "Cold asphalt mix", "name_he": "תערובת אספלט קרה", "unit": "kg", "qty_per_m2": 80},
                {"name": "Tack coat", "name_he": "שכבת הדבקה", "unit": "liter", "qty_per_m2": 2},
            ],
            "estimated_hours": 0.5,
            "base_cost_nis": 350,
            "team_size": 2,
            "equipment": ["מהדק ידני", "מגרפה"],
        },
        "medium": {
            "method": "Hot asphalt patch",
            "method_he": "טלאי אספלט חם",
            "materials": [
                {"name": "Hot mix asphalt", "name_he": "אספלט חם", "unit": "kg", "qty_per_m2": 120},
                {"name": "Tack coat", "name_he": "שכבת הדבקה", "unit": "liter", "qty_per_m2": 3},
                {"name": "Compaction sand", "name_he": "חול הידוק", "unit": "kg", "qty_per_m2": 20},
            ],
            "estimated_hours": 1.5,
            "base_cost_nis": 1200,
            "team_size": 3,
            "equipment": ["מכבש רטט", "מכונת חיתוך אספלט", "מגרפה"],
        },
        "large": {
            "method": "Full depth asphalt replacement",
            "method_he": "החלפת אספלט בעומק מלא",
            "materials": [
                {"name": "Hot mix asphalt", "name_he": "אספלט חם", "unit": "kg", "qty_per_m2": 200},
                {"name": "Aggregate base", "name_he": "בסיס מצע", "unit": "kg", "qty_per_m2": 150},
                {"name": "Tack coat", "name_he": "שכבת הדבקה", "unit": "liter", "qty_per_m2": 4},
                {"name": "Geotextile fabric", "name_he": "יריעת ג׳אוטקסטיל", "unit": "m2", "qty_per_m2": 1.1},
            ],
            "estimated_hours": 4.0,
            "base_cost_nis": 4500,
            "team_size": 4,
            "equipment": ["מכבש רטט", "מכונת כרסום", "משאית אספלט", "מחפרון"],
        },
    },
    "crack": {
        "small": {
            "method": "Crack sealing",
            "method_he": "איטום סדקים",
            "materials": [
                {"name": "Crack sealant", "name_he": "חומר איטום סדקים", "unit": "liter", "qty_per_m2": 5},
            ],
            "estimated_hours": 0.5,
            "base_cost_nis": 200,
            "team_size": 1,
            "equipment": ["אקדח איטום", "מבער גז"],
        },
        "medium": {
            "method": "Crack routing and sealing",
            "method_he": "חריצה ואיטום סדקים",
            "materials": [
                {"name": "Crack sealant", "name_he": "חומר איטום סדקים", "unit": "liter", "qty_per_m2": 8},
                {"name": "Backer rod", "name_he": "חוט מילוי", "unit": "m", "qty_per_m2": 5},
            ],
            "estimated_hours": 1.0,
            "base_cost_nis": 600,
            "team_size": 2,
            "equipment": ["מכונת חריצה", "אקדח איטום", "מבער גז"],
        },
        "large": {
            "method": "Mill and overlay",
            "method_he": "כרסום וריבוד מחדש",
            "materials": [
                {"name": "Hot mix asphalt", "name_he": "אספלט חם", "unit": "kg", "qty_per_m2": 100},
                {"name": "Tack coat", "name_he": "שכבת הדבקה", "unit": "liter", "qty_per_m2": 3},
            ],
            "estimated_hours": 3.0,
            "base_cost_nis": 3500,
            "team_size": 4,
            "equipment": ["מכונת כרסום", "משאית אספלט", "מכבש רטט"],
        },
    },
    "broken_sidewalk": {
        "small": {
            "method": "Concrete patch",
            "method_he": "טלאי בטון",
            "materials": [
                {"name": "Ready-mix concrete", "name_he": "בטון מוכן", "unit": "kg", "qty_per_m2": 150},
                {"name": "Bonding agent", "name_he": "חומר הדבקה", "unit": "liter", "qty_per_m2": 1},
            ],
            "estimated_hours": 1.0,
            "base_cost_nis": 400,
            "team_size": 2,
            "equipment": ["ערבל בטון", "מריחה", "פלס"],
        },
        "medium": {
            "method": "Slab replacement",
            "method_he": "החלפת לוח מדרכה",
            "materials": [
                {"name": "Concrete slab", "name_he": "לוח בטון", "unit": "unit", "qty_per_m2": 4},
                {"name": "Leveling sand", "name_he": "חול פילוס", "unit": "kg", "qty_per_m2": 50},
                {"name": "Cement mortar", "name_he": "מלט", "unit": "kg", "qty_per_m2": 20},
            ],
            "estimated_hours": 2.0,
            "base_cost_nis": 1500,
            "team_size": 3,
            "equipment": ["מסור בטון", "מחפרון קטן", "פלס"],
        },
        "large": {
            "method": "Full sidewalk reconstruction",
            "method_he": "שיקום מדרכה מלא",
            "materials": [
                {"name": "Concrete slabs", "name_he": "לוחות בטון", "unit": "unit", "qty_per_m2": 4},
                {"name": "Sub-base aggregate", "name_he": "מצע תת-בסיס", "unit": "kg", "qty_per_m2": 200},
                {"name": "Leveling sand", "name_he": "חול פילוס", "unit": "kg", "qty_per_m2": 60},
                {"name": "Edge curbing", "name_he": "אבני שפה", "unit": "m", "qty_per_m2": 2},
            ],
            "estimated_hours": 6.0,
            "base_cost_nis": 5000,
            "team_size": 4,
            "equipment": ["מסור בטון", "מחפרון", "מכבש", "משאית"],
        },
    },
    "drainage": {
        "small": {
            "method": "Drain clearing",
            "method_he": "ניקוי ביוב/ניקוז",
            "materials": [
                {"name": "Drain cleaner", "name_he": "חומר ניקוי ביוב", "unit": "liter", "qty_per_m2": 5},
            ],
            "estimated_hours": 1.0,
            "base_cost_nis": 300,
            "team_size": 2,
            "equipment": ["צינור לחץ", "כלי חפירה"],
        },
        "medium": {
            "method": "Grate replacement and pipe cleaning",
            "method_he": "החלפת סבכה וניקוי צנרת",
            "materials": [
                {"name": "Drainage grate", "name_he": "סבכת ניקוז", "unit": "unit", "qty_per_m2": 1},
                {"name": "Concrete frame", "name_he": "מסגרת בטון", "unit": "unit", "qty_per_m2": 1},
            ],
            "estimated_hours": 2.0,
            "base_cost_nis": 1800,
            "team_size": 3,
            "equipment": ["מנוף קטן", "צינור לחץ", "כלי חפירה"],
        },
        "large": {
            "method": "Drainage system reconstruction",
            "method_he": "שיקום מערכת ניקוז",
            "materials": [
                {"name": "PVC drainage pipe", "name_he": "צינור ניקוז PVC", "unit": "m", "qty_per_m2": 3},
                {"name": "Catch basin", "name_he": "בור ניקוז", "unit": "unit", "qty_per_m2": 0.5},
                {"name": "Gravel backfill", "name_he": "חצץ מילוי", "unit": "kg", "qty_per_m2": 300},
            ],
            "estimated_hours": 8.0,
            "base_cost_nis": 12000,
            "team_size": 5,
            "equipment": ["מחפרון", "משאית", "צינור לחץ", "מכבש"],
        },
    },
    "signage": {
        "small": {
            "method": "Sign re-mounting",
            "method_he": "חיזוק והרכבה מחדש של שלט",
            "materials": [
                {"name": "Mounting bolts", "name_he": "ברגי חיזוק", "unit": "unit", "qty_per_m2": 4},
            ],
            "estimated_hours": 0.5,
            "base_cost_nis": 200,
            "team_size": 2,
            "equipment": ["סולם", "מברגה חשמלית"],
        },
        "medium": {
            "method": "Sign replacement",
            "method_he": "החלפת שלט",
            "materials": [
                {"name": "Traffic sign", "name_he": "שלט תנועה", "unit": "unit", "qty_per_m2": 1},
                {"name": "Sign post", "name_he": "עמוד שלט", "unit": "unit", "qty_per_m2": 1},
                {"name": "Concrete base", "name_he": "בסיס בטון", "unit": "kg", "qty_per_m2": 50},
            ],
            "estimated_hours": 1.5,
            "base_cost_nis": 1200,
            "team_size": 2,
            "equipment": ["מחפרון קטן", "סולם", "מברגה חשמלית"],
        },
        "large": {
            "method": "Full signage system installation",
            "method_he": "התקנת מערכת תמרור מלאה",
            "materials": [
                {"name": "Traffic signs", "name_he": "שלטי תנועה", "unit": "unit", "qty_per_m2": 3},
                {"name": "Sign posts", "name_he": "עמודי שילוט", "unit": "unit", "qty_per_m2": 2},
                {"name": "Concrete foundations", "name_he": "יסודות בטון", "unit": "unit", "qty_per_m2": 2},
            ],
            "estimated_hours": 4.0,
            "base_cost_nis": 4000,
            "team_size": 3,
            "equipment": ["מחפרון", "משאית", "מנוף", "ערבל בטון"],
        },
    },
}

# ── Fallback recipe for unknown defect types ───────────────────────────
_FALLBACK_RECIPE = {
    "method": "General repair",
    "method_he": "תיקון כללי",
    "materials": [
        {"name": "Repair materials", "name_he": "חומרי תיקון", "unit": "kit", "qty_per_m2": 1},
    ],
    "estimated_hours": 2.0,
    "base_cost_nis": 1000,
    "team_size": 2,
    "equipment": ["ציוד כללי"],
}

# ── Weather codes that prevent asphalt work ────────────────────────────
_RAIN_WEATHER_CODES = {51, 53, 55, 61, 63, 65, 80, 81, 82, 95, 96, 99}
# Codes that prevent concrete work (heavy rain / storm)
_HEAVY_RAIN_CODES = {63, 65, 81, 82, 95, 96, 99}


def _classify_size(area_m2: float) -> str:
    """Classify defect size from area."""
    if area_m2 <= _SIZE_THRESHOLDS["small"]:
        return "small"
    if area_m2 <= _SIZE_THRESHOLDS["medium"]:
        return "medium"
    return "large"


def _normalize_defect_type(defect_type: str) -> str:
    """Map various defect type names to REPAIR_DB keys."""
    mapping = {
        "pothole": "pothole",
        "crack": "crack",
        "road_crack": "crack",
        "broken_sidewalk": "broken_sidewalk",
        "sidewalk": "broken_sidewalk",
        "drainage": "drainage",
        "drainage_blocked": "drainage",
        "signage": "signage",
        "broken_light": "signage",
        "road_damage": "pothole",
    }
    return mapping.get(defect_type, "")


def agent_repair_recommender(
    defect_type: str,
    geometry_result: dict | None = None,
    weather: dict | None = None,
) -> Dict[str, Any]:
    """
    Recommend repair method, materials, and cost estimate.

    This is a sync function — no API calls needed.

    Args:
        defect_type: Type of defect (pothole, crack, etc.).
        geometry_result: Output from geometry estimator (for dimensions).
        weather: Weather dict from environment agent.

    Returns:
        Complete repair recommendation with materials, cost, and constraints.
    """
    logger.info("Repair recommender starting", extra={"defect_type": defect_type})

    geometry_result = geometry_result or {}
    weather = weather or {}

    # ── Determine size category ─────────────────────────────────────
    area_m2 = float(geometry_result.get("estimated_area_m2", 0.05))
    size = _classify_size(area_m2)

    # ── Look up recipe ──────────────────────────────────────────────
    normalized_type = _normalize_defect_type(defect_type)
    type_recipes = REPAIR_DB.get(normalized_type, {})
    recipe = type_recipes.get(size, _FALLBACK_RECIPE)

    # ── Calculate material quantities ───────────────────────────────
    effective_area = max(area_m2, 0.01)  # minimum 0.01 m² for calculations
    materials: List[Dict[str, Any]] = []
    for mat in recipe["materials"]:
        qty = round(mat["qty_per_m2"] * effective_area, 2)
        # Enforce minimum quantities
        qty = max(qty, 0.5 if mat["unit"] in ("liter", "m") else 1)
        materials.append({
            "name": mat["name"],
            "name_he": mat["name_he"],
            "unit": mat["unit"],
            "quantity": qty,
        })

    # ── Cost estimation ─────────────────────────────────────────────
    base_cost = recipe["base_cost_nis"]
    # Scale cost by area ratio vs expected size
    expected_area = {
        "small": _SIZE_THRESHOLDS["small"],
        "medium": _SIZE_THRESHOLDS["medium"],
        "large": 0.5,
    }
    area_ratio = effective_area / max(expected_area[size], 0.01)
    estimated_cost_nis = round(base_cost * max(1.0, area_ratio))

    # ── Weather constraints ─────────────────────────────────────────
    weather_code = weather.get("weather_code", 0) or 0
    can_repair_today = True
    weather_warning: str | None = None

    is_asphalt_work = normalized_type in ("pothole", "crack") or "asphalt" in recipe["method"].lower()
    is_concrete_work = normalized_type in ("broken_sidewalk",) or "concrete" in recipe["method"].lower()

    if is_asphalt_work and weather_code in _RAIN_WEATHER_CODES:
        can_repair_today = False
        weather_warning = "לא ניתן לבצע עבודות אספלט בגשם — יש להמתין למזג אוויר יבש"
    elif is_concrete_work and weather_code in _HEAVY_RAIN_CODES:
        can_repair_today = False
        weather_warning = "לא ניתן ליצוק בטון בגשם חזק — יש להמתין"
    elif weather_code in _RAIN_WEATHER_CODES:
        weather_warning = "מזג אוויר גשום — עבודות חוץ עלולות להתעכב"

    # Temperature warnings
    temp = weather.get("temperature_c")
    if temp is not None:
        temp = float(temp)
        if is_asphalt_work and temp < 10:
            weather_warning = (weather_warning or "") + " | טמפרטורה נמוכה — אספלט חם עלול להתקרר מהר"
        if is_concrete_work and temp > 35:
            weather_warning = (weather_warning or "") + " | טמפרטורה גבוהה — בטון עלול להתייבש מהר מדי"

    result = {
        "method": recipe["method"],
        "method_he": recipe["method_he"],
        "materials": materials,
        "estimated_hours": recipe["estimated_hours"],
        "estimated_cost_nis": estimated_cost_nis,
        "team_size": recipe["team_size"],
        "can_repair_today": can_repair_today,
        "weather_warning": weather_warning,
        "equipment_needed": recipe["equipment"],
        "defect_type": defect_type,
        "size_category": size,
        "area_m2": round(area_m2, 4),
    }

    logger.info(
        "Repair recommendation done",
        extra={
            "method": recipe["method"],
            "cost_nis": estimated_cost_nis,
            "can_repair": can_repair_today,
            "size": size,
        },
    )
    return result
