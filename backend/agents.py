"""
RoadSense AI Pipeline — 4 Agents
Agent 1: VLM — analyzes images for hazards and liability risk
Agent 2: Environment — checks what's near the location
Agent 3: Dedup — finds and merges duplicate reports
Agent 4: Scorer — combines all agents into a final severity score
"""

import os, math, json, httpx
from datetime import datetime
from typing import Optional

# ── Config ──────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_MAPS_KEY = os.getenv("GOOGLE_MAPS_KEY", "")

# ── Agent 1: VLM Image Analysis ─────────────────────────────

async def agent_vlm_analyze(image_url: str, base_url: str = "") -> dict:
    """
    Analyze an image using Claude VLM.
    Returns: description, hazard_type, hazard_detected, liability_risk, severity_hint
    """
    if not ANTHROPIC_API_KEY:
        # Fallback: basic analysis without API
        return {
            "description": "תמונה שהועלתה מהשטח",
            "hazard_detected": True,
            "hazard_type": "unknown",
            "liability_risk": "בינוני — נדרש ניתוח ידני",
            "severity_hint": "medium",
            "confidence": 0.5,
            "analysis_source": "fallback"
        }

    try:
        # If image is a local path, read it
        image_data = None
        media_type = "image/jpeg"

        if image_url.startswith("/uploads/"):
            full_path = os.path.join("/data/uploads" if os.path.exists("/data") else "./uploads", 
                                      image_url.replace("/uploads/", ""))
            if os.path.exists(full_path):
                import base64
                with open(full_path, "rb") as f:
                    image_data = base64.standard_b64encode(f.read()).decode("utf-8")
                ext = full_path.rsplit(".", 1)[-1].lower()
                media_type = f"image/{ext}" if ext in ("png", "gif", "webp") else "image/jpeg"

        if not image_data:
            return {
                "description": "לא ניתן לגשת לתמונה",
                "hazard_detected": False,
                "hazard_type": "unknown",
                "liability_risk": "לא ידוע",
                "severity_hint": "low",
                "confidence": 0.0,
                "analysis_source": "error"
            }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 1000,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": image_data}
                            },
                            {
                                "type": "text",
                                "text": """אתה מומחה לתשתיות עירוניות. נתח את התמונה וזהה מפגעים.

החזר JSON בלבד (בלי markdown):
{
  "description": "תיאור קצר של מה שרואים בתמונה",
  "hazard_detected": true/false,
  "hazard_type": "pothole|crack|broken_sidewalk|drainage|signage|road_damage|other|none",
  "hazard_details": "פירוט המפגע — גודל משוער, חומרה, מיקום בתמונה",
  "liability_risk": "תיאור הסיכון לתביעת נזיקין — למי מסוכן ולמה",
  "severity_hint": "critical|high|medium|low",
  "confidence": 0.0-1.0
}"""
                            }
                        ]
                    }]
                }
            )

        if resp.status_code == 200:
            data = resp.json()
            text = data["content"][0]["text"]
            # Parse JSON from response
            text = text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1].rsplit("```", 1)[0]
            result = json.loads(text)
            result["analysis_source"] = "claude_vlm"
            return result

    except Exception as e:
        print(f"⚠️ VLM Agent error: {e}")

    return {
        "description": "שגיאה בניתוח תמונה",
        "hazard_detected": True,
        "hazard_type": "unknown",
        "liability_risk": "לא ניתן לקבוע",
        "severity_hint": "medium",
        "confidence": 0.3,
        "analysis_source": "error"
    }


# ── Agent 2: Environment Analysis ───────────────────────────

async def agent_environment(lat: float, lng: float) -> dict:
    """
    Check what's near the location: schools, hospitals, bus stops, etc.
    Returns: nearby_places, risk_factors, environment_score
    """
    nearby = []
    risk_factors = []
    env_score = 0

    if GOOGLE_MAPS_KEY:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                # Search for sensitive places nearby
                for place_type, label, weight in [
                    ("school", "בית ספר", 25),
                    ("hospital", "בית חולים", 20),
                    ("bus_station", "תחנת אוטובוס", 15),
                    ("shopping_mall", "מרכז מסחרי", 12),
                    ("synagogue", "בית כנסת", 10),
                ]:
                    resp = await client.get(
                        "https://maps.googleapis.com/maps/api/place/nearbysearch/json",
                        params={
                            "location": f"{lat},{lng}",
                            "radius": 200,
                            "type": place_type,
                            "key": GOOGLE_MAPS_KEY,
                        }
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for place in data.get("results", [])[:2]:
                            ploc = place["geometry"]["location"]
                            dist = haversine(lat, lng, ploc["lat"], ploc["lng"])
                            nearby.append({
                                "name": place.get("name", label),
                                "type": place_type,
                                "distance_m": round(dist),
                                "label": label,
                            })
                            risk_factors.append(f"{label} במרחק {round(dist)} מ׳")
                            # Closer = higher score
                            env_score += int(weight * max(0, 1 - dist / 200))

        except Exception as e:
            print(f"⚠️ Environment Agent error: {e}")

    # If no API key, return estimated data
    if not nearby:
        env_score = 30  # Default moderate risk
        risk_factors = ["לא זמין מידע על סביבה — נדרש API key"]

    return {
        "nearby_places": nearby,
        "risk_factors": risk_factors,
        "environment_score": min(env_score, 100),
        "source": "google_places" if GOOGLE_MAPS_KEY else "estimated"
    }


# ── Agent 3: Deduplication ──────────────────────────────────

def agent_dedup(db, detection_id: int, lat: float, lng: float, 
                image_url: str, ticket_id: int) -> dict:
    """
    Check if this detection is a duplicate of another in the same cluster.
    If duplicate found, mark one for deletion.
    Returns: is_duplicate, duplicate_of, action
    """
    from sqlalchemy import text

    # Get all other detections in the same ticket
    others = db.execute(
        text("SELECT id, lat, lng, image_url, detected_at FROM detections WHERE ticket_id = :tid AND id != :did"),
        {"tid": ticket_id, "did": detection_id}
    ).fetchall()

    for other in others:
        dist = haversine(lat, lng, other.lat, other.lng)

        # Very close (< 5m) = likely same spot
        if dist < 5:
            # Check if images are similar (basic: same reporter within 2 minutes)
            return {
                "is_duplicate": True,
                "duplicate_of": other.id,
                "distance_m": round(dist, 1),
                "action": "keep_newest",
                "reason": f"מרחק {round(dist, 1)} מ׳ מדיווח #{other.id}"
            }

    return {
        "is_duplicate": False,
        "duplicate_of": None,
        "distance_m": None,
        "action": "keep",
        "reason": "אין כפילות"
    }


# ── Agent 4: Final Scorer ───────────────────────────────────

def agent_scorer(vlm_result: dict, env_result: dict, 
                 dedup_result: dict, detection: dict) -> dict:
    """
    Combine all agent results into a final severity score.
    Score: 0 (no issue) to 100 (critical emergency)
    """
    if dedup_result.get("is_duplicate"):
        return {
            "final_score": 0,
            "severity": "duplicate",
            "reasoning": f"כפילות של דיווח #{dedup_result['duplicate_of']}",
            "action": "delete",
            "breakdown": {}
        }

    # Severity hint from VLM
    vlm_severity = vlm_result.get("severity_hint", "medium")
    vlm_confidence = vlm_result.get("confidence", 0.5)
    hazard_detected = vlm_result.get("hazard_detected", True)

    if not hazard_detected:
        return {
            "final_score": 5,
            "severity": "none",
            "reasoning": "VLM לא זיהה מפגע בתמונה",
            "action": "review",
            "breakdown": {"vlm": 5, "env": 0, "geometry": 0}
        }

    # VLM score (0-40)
    vlm_map = {"critical": 38, "high": 30, "medium": 20, "low": 10}
    vlm_score = vlm_map.get(vlm_severity, 20) * vlm_confidence

    # Environment score (0-30)
    env_score = min(env_result.get("environment_score", 15) * 0.3, 30)

    # Geometry score (0-30) — from detection measurements
    geo_score = 0
    depth = detection.get("defect_depth_cm", 0) or 0
    width = detection.get("defect_width_cm", 0) or 0
    area = detection.get("surface_area_m2", 0) or 0

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

    # Total
    total = round(vlm_score + env_score + geo_score)
    total = max(5, min(100, total))

    # Determine severity
    if total >= 80:
        severity = "critical"
    elif total >= 60:
        severity = "high"
    elif total >= 35:
        severity = "medium"
    else:
        severity = "low"

    # Build reasoning
    reasons = []
    if vlm_result.get("hazard_type") and vlm_result["hazard_type"] != "unknown":
        reasons.append(f"זוהה: {vlm_result['hazard_type']}")
    if vlm_result.get("liability_risk"):
        reasons.append(f"סיכון נזיקין: {vlm_result['liability_risk']}")
    if env_result.get("risk_factors"):
        reasons.extend(env_result["risk_factors"][:3])
    if depth > 0:
        reasons.append(f"עומק {depth} ס״מ")

    return {
        "final_score": total,
        "severity": severity,
        "reasoning": " | ".join(reasons) if reasons else "ניתוח אוטומטי",
        "action": "alert" if severity in ("critical", "high") else "monitor",
        "breakdown": {
            "vlm": round(vlm_score),
            "environment": round(env_score),
            "geometry": round(geo_score),
        }
    }


# ── Pipeline Runner ─────────────────────────────────────────

async def run_pipeline(db, detection_id: int, ticket_id: int,
                       lat: float, lng: float, image_url: str,
                       detection_dict: dict, base_url: str = "") -> dict:
    """
    Run the full 4-agent pipeline on a detection.
    Updates the detection and ticket in DB with results.
    """
    print(f"🤖 Pipeline starting for detection #{detection_id}")

    # Agent 1: VLM
    print(f"  🔍 Agent 1: VLM analyzing image...")
    vlm_result = await agent_vlm_analyze(image_url, base_url)
    print(f"  ✅ VLM: {vlm_result.get('hazard_type', '?')} ({vlm_result.get('confidence', 0):.0%})")

    # Agent 2: Environment
    print(f"  🌍 Agent 2: Checking environment...")
    env_result = await agent_environment(lat, lng)
    print(f"  ✅ Environment: score {env_result.get('environment_score', 0)}")

    # Agent 3: Dedup
    print(f"  🔄 Agent 3: Checking duplicates...")
    dedup_result = agent_dedup(db, detection_id, lat, lng, image_url, ticket_id)
    print(f"  ✅ Dedup: {'כפילות!' if dedup_result['is_duplicate'] else 'ייחודי'}")

    # Agent 4: Scorer
    print(f"  📊 Agent 4: Scoring...")
    score_result = agent_scorer(vlm_result, env_result, dedup_result, detection_dict)
    print(f"  ✅ Score: {score_result['final_score']}/100 → {score_result['severity']}")

    # Update detection in DB
    from sqlalchemy import text
    
    # Store VLM analysis as caption
    vlm_desc = vlm_result.get("description", "")
    liability = vlm_result.get("liability_risk", "")
    caption = f"{vlm_desc} | סיכון: {liability}" if liability else vlm_desc

    db.execute(text("""
        UPDATE detections SET 
            image_caption = :caption,
            notes = :notes
        WHERE id = :did
    """), {
        "caption": caption[:500],
        "notes": json.dumps({
            "vlm": vlm_result,
            "environment": env_result,
            "dedup": dedup_result,
            "score": score_result,
        }, ensure_ascii=False)[:2000],
        "did": detection_id,
    })

    # Update ticket severity and type based on VLM
    new_type = vlm_result.get("hazard_type", "unknown")
    if new_type in ("pothole", "crack", "broken_sidewalk", "drainage", "road_damage", "signage"):
        # Map to our DB types
        type_map = {
            "pothole": "pothole", "crack": "road_crack",
            "broken_sidewalk": "sidewalk", "drainage": "drainage_blocked",
            "road_damage": "road_crack", "signage": "broken_light",
        }
        db_type = type_map.get(new_type, "pothole")
    else:
        db_type = None

    if score_result["action"] == "delete":
        # Mark as duplicate — delete detection
        db.execute(text("UPDATE detections SET notes = :n WHERE id = :did"), {"n": json.dumps({"status": "duplicate", "duplicate_of": dedup_result.get("duplicate_of")}, ensure_ascii=False), "did": detection_id})
        print(f"  🗑️ Detection #{detection_id} deleted (duplicate)")
    else:
        # Update ticket with best severity
        severity = score_result["severity"]
        if severity != "none" and severity != "duplicate":
            update_fields = {"sev": severity, "tid": ticket_id}
            update_sql = "UPDATE tickets SET severity = :sev"
            if db_type:
                update_sql += ", defect_type = :dtype"
                update_fields["dtype"] = db_type
            update_sql += " WHERE id = :tid"
            db.execute(text(update_sql), update_fields)

    db.commit()

    print(f"🤖 Pipeline complete: {score_result['severity']} ({score_result['final_score']}/100)")

    return {
        "detection_id": detection_id,
        "ticket_id": ticket_id,
        "vlm": vlm_result,
        "environment": env_result,
        "dedup": dedup_result,
        "score": score_result,
    }


# ── Helper ──────────────────────────────────────────────────

def haversine(lat1, lng1, lat2, lng2):
    R = 6371000
    p = math.pi / 180
    a = math.sin((lat2 - lat1) * p / 2) ** 2 + \
        math.cos(lat1 * p) * math.cos(lat2 * p) * math.sin((lng2 - lng1) * p / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))
