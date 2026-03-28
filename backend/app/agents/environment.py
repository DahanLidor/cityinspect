"""
Agent 2: Environment — free-API proximity & weather analysis.

Sources (all free, no API keys required):
  • Nominatim (OpenStreetMap) — reverse geocoding, road type
  • Overpass API (OpenStreetMap) — nearby sensitive places
  • Open-Meteo — current weather
"""
from __future__ import annotations

import math
from typing import Any, Dict

import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

# Overpass: (OSM tag, Hebrew label, risk weight)
_POI_QUERIES = [
    ('amenity=school',          'בית ספר',        25),
    ('amenity=hospital',        'בית חולים',      20),
    ('amenity=kindergarten',    'גן ילדים',        22),
    ('highway=bus_stop',        'תחנת אוטובוס',   15),
    ('amenity=place_of_worship','בית כנסת/מסגד',  10),
    ('shop=mall',               'מרכז מסחרי',     12),
    ('amenity=marketplace',     'שוק',             8),
]

_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"

_HEADERS = {"User-Agent": "CityInspect/1.0 (municipal infrastructure monitoring)"}


def _haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6_371_000
    p = math.pi / 180
    a = (math.sin((lat2 - lat1) * p / 2) ** 2
         + math.cos(lat1 * p) * math.cos(lat2 * p)
         * math.sin((lng2 - lng1) * p / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _wmo_to_hebrew(code: int) -> str:
    """Convert WMO weather interpretation code to Hebrew label."""
    if code == 0:
        return "שמיים בהירים"
    if code in (1, 2, 3):
        return "מעונן חלקית"
    if code in (45, 48):
        return "ערפל"
    if code in (51, 53, 55):
        return "טפטוף"
    if code in (61, 63, 65):
        return "גשם"
    if code in (71, 73, 75):
        return "שלג"
    if code in (80, 81, 82):
        return "גשם ממטרים"
    if code in (95, 96, 99):
        return "סופת רעמים"
    return "לא ידוע"


async def _get_weather(lat: float, lng: float, client: httpx.AsyncClient) -> dict:
    try:
        resp = await client.get(
            _OPENMETEO_URL,
            params={
                "latitude": lat,
                "longitude": lng,
                "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code,precipitation",
                "timezone": "auto",
                "forecast_days": 1,
            },
            timeout=8,
        )
        if resp.status_code != 200:
            return {}
        cur = resp.json().get("current", {})
        return {
            "temperature_c": cur.get("temperature_2m"),
            "humidity_pct": cur.get("relative_humidity_2m"),
            "wind_speed_kmh": cur.get("wind_speed_10m"),
            "weather_code": cur.get("weather_code"),
            "weather_label": _wmo_to_hebrew(cur.get("weather_code", 0)),
            "precipitation_mm": cur.get("precipitation", 0),
        }
    except Exception as exc:
        logger.warning("Open-Meteo failed", extra={"error": str(exc)})
        return {}


async def _get_address(lat: float, lng: float, client: httpx.AsyncClient) -> dict:
    try:
        resp = await client.get(
            _NOMINATIM_URL,
            params={"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 18, "addressdetails": 1},
            headers=_HEADERS,
            timeout=8,
        )
        if resp.status_code != 200:
            return {}
        data = resp.json()
        addr = data.get("address", {})
        return {
            "display_name": data.get("display_name", ""),
            "road": addr.get("road", addr.get("pedestrian", "")),
            "suburb": addr.get("suburb", addr.get("neighbourhood", "")),
            "city": addr.get("city", addr.get("town", addr.get("village", ""))),
            "road_type": data.get("type", ""),
            "osm_category": data.get("category", ""),
        }
    except Exception as exc:
        logger.warning("Nominatim failed", extra={"error": str(exc)})
        return {}


async def _get_nearby_pois(lat: float, lng: float, radius: int, client: httpx.AsyncClient) -> list[dict]:
    """Query Overpass API for sensitive POIs within radius metres."""
    # Build union query for all POI types
    union_parts = "\n".join(
        f'  nwr[{tag}](around:{radius},{lat},{lng});'
        for tag, _, _ in _POI_QUERIES
    )
    query = f"[out:json][timeout:10];\n(\n{union_parts}\n);\nout center 20;"

    try:
        resp = await client.post(
            _OVERPASS_URL,
            content=query,
            headers={"Content-Type": "application/x-www-form-urlencoded", **_HEADERS},
            timeout=12,
        )
        if resp.status_code != 200:
            return []

        elements = resp.json().get("elements", [])
        results = []
        for el in elements[:30]:
            # Get lat/lng — node has lat/lon directly; way/relation has center
            el_lat = el.get("lat") or (el.get("center", {}).get("lat"))
            el_lng = el.get("lon") or (el.get("center", {}).get("lon"))
            if el_lat is None or el_lng is None:
                continue

            dist = _haversine(lat, lng, el_lat, el_lng)
            tags = el.get("tags", {})
            name = tags.get("name", tags.get("name:he", ""))

            # Match tag to label+weight
            label, weight = "מקום", 5
            for osm_tag, lbl, wgt in _POI_QUERIES:
                key, _, val = osm_tag.partition("=")
                if tags.get(key) == val:
                    label = lbl
                    weight = wgt
                    break

            results.append({
                "name": name or label,
                "type": label,
                "distance_m": round(dist),
                "weight": weight,
            })

        # Sort by distance
        results.sort(key=lambda x: x["distance_m"])
        return results

    except Exception as exc:
        logger.warning("Overpass API failed", extra={"error": str(exc)})
        return []


async def agent_environment(lat: float, lng: float) -> Dict[str, Any]:
    """
    Assess environmental context using free OpenStreetMap + Open-Meteo APIs.
    Returns nearby POIs, weather, address, risk score.
    """
    async with httpx.AsyncClient() as client:
        # Run all three queries concurrently would require asyncio.gather —
        # but since httpx is already async, do them sequentially (simpler, avoids gather import)
        weather = await _get_weather(lat, lng, client)
        address = await _get_address(lat, lng, client)
        pois = await _get_nearby_pois(lat, lng, 300, client)

    # --- Compute risk score ---
    env_score = 0
    risk_factors = []

    # POI proximity risk
    for poi in pois[:10]:
        dist = poi["distance_m"]
        weight = poi.get("weight", 5)
        contribution = int(weight * max(0.0, 1.0 - dist / 300))
        env_score += contribution
        if contribution > 0:
            risk_factors.append(f"{poi['type']} במרחק {dist} מ׳")

    # Weather risk
    wcode = weather.get("weather_code", 0)
    precip = weather.get("precipitation_mm", 0) or 0
    wind = weather.get("wind_speed_kmh", 0) or 0

    if wcode in (61, 63, 65, 80, 81, 82):
        env_score += 15
        risk_factors.append(f"גשם פעיל ({precip:.1f} מ\"מ)")
    elif wcode in (95, 96, 99):
        env_score += 25
        risk_factors.append("סופת רעמים")
    elif wcode in (71, 73, 75):
        env_score += 20
        risk_factors.append("שלג")

    if wind > 40:
        env_score += 10
        risk_factors.append(f"רוח חזקה ({wind:.0f} קמ\"ש)")

    logger.info(
        "Environment agent done",
        extra={
            "lat": lat,
            "lng": lng,
            "pois": len(pois),
            "env_score": min(env_score, 100),
            "weather": weather.get("weather_label", "?"),
        },
    )

    return {
        "nearby_places": pois[:10],
        "risk_factors": risk_factors,
        "environment_score": min(env_score, 100),
        "weather": weather,
        "address": address,
        "source": "openstreetmap+open-meteo",
    }
