"""
Agent 2: Environment — Google Places proximity analysis.
"""
from __future__ import annotations

import math
from typing import Any, Dict

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)

_PLACE_TYPES = [
    ("school",        "בית ספר",       25),
    ("hospital",      "בית חולים",     20),
    ("bus_station",   "תחנת אוטובוס",  15),
    ("shopping_mall", "מרכז מסחרי",    12),
    ("synagogue",     "בית כנסת",       10),
]


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


async def agent_environment(lat: float, lng: float) -> Dict[str, Any]:
    """Assess environmental risk based on nearby sensitive locations."""
    nearby = []
    risk_factors = []
    env_score = 0

    if not settings.google_maps_key:
        logger.warning("Environment: no GOOGLE_MAPS_KEY — returning estimated score")
        return {
            "nearby_places": [],
            "risk_factors": ["לא זמין מידע על סביבה — נדרש API key"],
            "environment_score": 30,
            "source": "estimated",
        }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for place_type, label, weight in _PLACE_TYPES:
                resp = await client.get(
                    "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                    params={"location": f"{lat},{lng}", "radius": 200, "type": place_type, "key": settings.google_maps_key},
                )
                if resp.status_code != 200:
                    continue
                for place in resp.json().get("results", [])[:2]:
                    ploc = place["geometry"]["location"]
                    dist = _haversine(lat, lng, ploc["lat"], ploc["lng"])
                    nearby.append({"name": place.get("name", label), "type": place_type, "distance_m": round(dist), "label": label})
                    risk_factors.append(f"{label} במרחק {round(dist)} מ׳")
                    env_score += int(weight * max(0, 1 - dist / 200))
    except Exception as exc:
        logger.error("Environment agent exception", extra={"error": str(exc)})

    return {
        "nearby_places": nearby,
        "risk_factors": risk_factors,
        "environment_score": min(env_score, 100),
        "source": "google_places",
    }
