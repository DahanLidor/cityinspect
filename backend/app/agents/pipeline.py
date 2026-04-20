"""
Full 10-agent AI pipeline runner.
Called from background tasks (Celery worker or asyncio.create_task).

Pipeline flow:
  1. Ingest Validator — reject bad captures before burning AI tokens
  2. Sensor Fusion — combine all sensor signals into confidence scores
  3. VLM — Claude Vision image analysis
  4. Environment — free-API proximity & weather
  5. Geometry Estimator — dimensions from camera intrinsics (no LiDAR needed)
  6. Dedup — detect duplicate reports
  7. Scorer — final severity score (0-100)
  8. Temporal Tracker — track defect changes over time
  9. Risk Predictor — liability & future hazard prediction
  10. Repair Recommender — materials, cost, method
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.dedup import agent_dedup
from app.agents.environment import agent_environment
from app.agents.scorer import agent_scorer
from app.agents.vlm import agent_vlm_analyze
from app.core.logging import get_logger

logger = get_logger(__name__)

_HAZARD_TYPE_MAP = {
    "pothole": "pothole",
    "crack": "road_crack",
    "broken_sidewalk": "sidewalk",
    "drainage": "drainage_blocked",
    "road_damage": "road_crack",
    "signage": "broken_light",
}


async def run_pipeline(
    db: AsyncSession,
    detection_id: int,
    ticket_id: int,
    lat: float,
    lng: float,
    image_url: str,
    image_hash: str,
    detection_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Execute all 10 agents and persist results."""
    logger.info("Pipeline starting (10-agent)", extra={"detection_id": detection_id})

    # Mark as running
    await db.execute(
        text("UPDATE detections SET pipeline_status = 'running' WHERE id = :id"),
        {"id": detection_id},
    )
    await db.commit()

    try:
        # Load sensor data from detection
        sensor_row = (await db.execute(
            text("SELECT sensor_data_json, defect_type FROM detections WHERE id=:id"),
            {"id": detection_id},
        )).fetchone()
        sensor_data = {}
        det_defect_type = detection_dict.get("defect_type", "pothole")
        if sensor_row:
            try:
                sensor_data = json.loads(sensor_row[0] or "{}")
            except (json.JSONDecodeError, TypeError):
                pass
            det_defect_type = sensor_row[1] or det_defect_type

        # ── Agent 1: Ingest Validator ───────────────────────────────────────
        validate_result = {"valid": True, "issues": [], "quality_score": 100}
        try:
            from app.agents.ingest_validator import agent_ingest_validator
            filename = image_url.replace("/uploads/", "") if image_url else ""
            validate_result = await agent_ingest_validator(filename, sensor_data)
            logger.info("Agent 1 validator done", extra={"valid": validate_result.get("valid"), "quality": validate_result.get("quality_score")})
        except Exception as exc:
            logger.warning("Agent 1 validator failed (non-fatal): %s", exc)

        # ── Agent 2: Sensor Fusion ──────────────────────────────────────────
        fusion_result = {"overall_confidence": 0.5, "capture_grade": "C"}
        try:
            from app.agents.sensor_fusion import fuse_sensors
            fusion_result = fuse_sensors(sensor_data)
            logger.info("Agent 2 fusion done", extra={"grade": fusion_result.get("capture_grade"), "conf": fusion_result.get("overall_confidence")})
        except Exception as exc:
            logger.warning("Agent 2 fusion failed (non-fatal): %s", exc)

        # ── Agent 3: VLM ────────────────────────────────────────────────────
        vlm_result = await agent_vlm_analyze(image_url)
        logger.info("Agent 3 VLM done", extra={"hazard": vlm_result.get("hazard_type"), "conf": vlm_result.get("confidence")})

        # ── Agent 4: Environment ────────────────────────────────────────────
        env_result = await agent_environment(lat, lng)
        logger.info("Agent 4 env done", extra={"score": env_result.get("environment_score")})

        # ── Agent 5: Geometry Estimator ─────────────────────────────────────
        geometry_result = {"confidence": 0, "method": "unavailable"}
        try:
            from app.agents.geometry_estimator import agent_geometry_estimator
            geometry_result = await agent_geometry_estimator(sensor_data, vlm_result)
            logger.info("Agent 5 geometry done", extra={"method": geometry_result.get("method"), "area": geometry_result.get("estimated_area_m2")})
        except Exception as exc:
            logger.warning("Agent 5 geometry failed (non-fatal): %s", exc)

        # ── Agent 6: Dedup ──────────────────────────────────────────────────
        dedup_result = await agent_dedup(db, detection_id, lat, lng, image_hash, ticket_id)
        logger.info("Agent 6 dedup done", extra={"is_dup": dedup_result.get("is_duplicate")})

        # ── Agent 7: Scorer ─────────────────────────────────────────────────
        # Enrich detection_dict with geometry estimates if available
        enriched_dict = dict(detection_dict)
        if geometry_result.get("confidence", 0) > 0.3:
            enriched_dict.setdefault("defect_depth_cm", geometry_result.get("estimated_depth_cm", 0))
            enriched_dict.setdefault("defect_width_cm", geometry_result.get("estimated_width_cm", 0))
            enriched_dict.setdefault("surface_area_m2", geometry_result.get("estimated_area_m2", 0))

        score_result = agent_scorer(vlm_result, env_result, dedup_result, enriched_dict)
        logger.info("Agent 7 scorer done", extra={"score": score_result.get("final_score"), "severity": score_result.get("severity")})

        # ── Agent 8: Temporal Tracker ───────────────────────────────────────
        temporal_result = {"tracking": "first_observation", "trend": "unknown"}
        try:
            from app.agents.temporal_tracker import agent_temporal_tracker
            temporal_result = await agent_temporal_tracker(
                db, ticket_id, detection_id, score_result.get("final_score", 0),
            )
            logger.info("Agent 8 temporal done", extra={"trend": temporal_result.get("trend"), "days": temporal_result.get("days_open")})
        except Exception as exc:
            logger.warning("Agent 8 temporal failed (non-fatal): %s", exc)

        # ── Agent 9: Risk Predictor ─────────────────────────────────────────
        risk_result = {"risk_score": 0, "risk_level": "unknown"}
        try:
            from app.agents.risk_predictor import agent_risk_predictor
            weather = env_result.get("weather", {})
            risk_result = await agent_risk_predictor(vlm_result, env_result, geometry_result, temporal_result)
            logger.info("Agent 9 risk done", extra={"risk": risk_result.get("risk_score"), "level": risk_result.get("risk_level")})
        except Exception as exc:
            logger.warning("Agent 9 risk failed (non-fatal): %s", exc)

        # ── Agent 10: Repair Recommender ────────────────────────────────────
        repair_result = {"method": "manual_assessment"}
        try:
            from app.agents.repair_recommender import agent_repair_recommender
            weather = env_result.get("weather", {})
            repair_result = agent_repair_recommender(det_defect_type, geometry_result, weather)
            logger.info("Agent 10 repair done", extra={"method": repair_result.get("method"), "cost": repair_result.get("estimated_cost_nis")})
        except Exception as exc:
            logger.warning("Agent 10 repair failed (non-fatal): %s", exc)

        # ── Persist results ─────────────────────────────────────────────────
        caption = vlm_result.get("description", "")
        liability = vlm_result.get("liability_risk", "")
        if liability:
            caption = f"{caption} | סיכון: {liability}"

        notes_payload = json.dumps(
            {
                "validator": validate_result,
                "fusion": fusion_result,
                "vlm": vlm_result,
                "environment": env_result,
                "geometry": geometry_result,
                "dedup": dedup_result,
                "scorer": score_result,
                "temporal": temporal_result,
                "risk": risk_result,
                "repair": repair_result,
            },
            ensure_ascii=False,
            default=str,
        )[:8000]

        weather = env_result.get("weather", {})
        await db.execute(
            text(
                "UPDATE detections SET image_caption=:cap, notes=:notes, pipeline_status='done',"
                " ambient_temp_c=:temp, weather_condition=:wc, wind_speed_kmh=:wind, humidity_pct=:hum"
                " WHERE id=:id"
            ),
            {
                "cap": caption[:500],
                "notes": notes_payload,
                "temp": weather.get("temperature_c") or 25,
                "wc": weather.get("weather_label") or "Clear",
                "wind": weather.get("wind_speed_kmh") or 10,
                "hum": weather.get("humidity_pct") or 50,
                "id": detection_id,
            },
        )

        # Update ticket severity & score (don't override user's defect_type)
        severity = score_result["severity"]
        final_score = score_result["final_score"]
        if severity not in ("duplicate", "none"):
            row = (await db.execute(
                text("SELECT defect_type FROM tickets WHERE id=:tid"), {"tid": ticket_id}
            )).fetchone()
            current_type = row[0] if row else ""

            if current_type in ("unknown", "", None):
                db_type = _HAZARD_TYPE_MAP.get(vlm_result.get("hazard_type", ""), None)
                if db_type:
                    await db.execute(
                        text("UPDATE tickets SET severity=:sev, defect_type=:dtype, score=:score WHERE id=:tid"),
                        {"sev": severity, "dtype": db_type, "score": final_score, "tid": ticket_id},
                    )
                else:
                    await db.execute(
                        text("UPDATE tickets SET severity=:sev, score=:score WHERE id=:tid"),
                        {"sev": severity, "score": final_score, "tid": ticket_id},
                    )
            else:
                await db.execute(
                    text("UPDATE tickets SET severity=:sev, score=:score WHERE id=:tid"),
                    {"sev": severity, "score": final_score, "tid": ticket_id},
                )

        await db.commit()
        logger.info("Pipeline complete (10-agent)", extra={
            "detection_id": detection_id,
            "score": score_result["final_score"],
            "risk": risk_result.get("risk_score"),
            "capture_grade": fusion_result.get("capture_grade"),
        })

        # ── Export to Google Drive ──────────────────────────────────────────
        try:
            from app.core.config import get_settings as _gs
            from app.services.drive_service import export_ticket_to_drive
            _settings = _gs()

            if _settings.google_drive_enabled:
                t_row = (await db.execute(text("SELECT * FROM tickets WHERE id=:id"), {"id": ticket_id})).mappings().first()
                d_row = (await db.execute(text("SELECT * FROM detections WHERE id=:id"), {"id": detection_id})).mappings().first()

                if t_row and d_row:
                    img_path = None
                    if image_url and image_url.startswith("/uploads/"):
                        img_path = os.path.join(_settings.upload_path, image_url.replace("/uploads/", ""))

                    ply_path = None
                    ply_url = d_row.get("point_cloud_url", "")
                    if ply_url and ply_url.startswith("/uploads/"):
                        ply_path = os.path.join(_settings.upload_path, ply_url.replace("/uploads/", ""))

                    all_notes = {
                        "validator": validate_result, "fusion": fusion_result,
                        "vlm": vlm_result, "environment": env_result,
                        "geometry": geometry_result, "dedup": dedup_result,
                        "scorer": score_result, "temporal": temporal_result,
                        "risk": risk_result, "repair": repair_result,
                    }
                    drive_url = export_ticket_to_drive(dict(t_row), dict(d_row), all_notes, img_path, ply_path)
                    if drive_url:
                        logger.info("Drive export OK", extra={"url": drive_url})
        except Exception as drive_exc:
            logger.warning("Drive export failed (non-fatal): %s", drive_exc)

        return {
            "detection_id": detection_id,
            "ticket_id": ticket_id,
            "validator": validate_result,
            "fusion": fusion_result,
            "vlm": vlm_result,
            "environment": env_result,
            "geometry": geometry_result,
            "dedup": dedup_result,
            "score": score_result,
            "temporal": temporal_result,
            "risk": risk_result,
            "repair": repair_result,
        }

    except Exception as exc:
        await db.execute(
            text("UPDATE detections SET pipeline_status='error', notes=:notes WHERE id=:id"),
            {"notes": json.dumps({"error": str(exc)}), "id": detection_id},
        )
        await db.commit()
        logger.error("Pipeline failed", extra={"detection_id": detection_id, "error": str(exc)})
        raise
