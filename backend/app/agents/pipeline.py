"""
Full 4-agent pipeline runner.
Called from background tasks (Celery worker or asyncio.create_task).
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
    """Execute all 4 agents sequentially and persist results."""
    logger.info("Pipeline starting", extra={"detection_id": detection_id})

    # Mark as running
    await db.execute(
        text("UPDATE detections SET pipeline_status = 'running' WHERE id = :id"),
        {"id": detection_id},
    )
    await db.commit()

    try:
        # Agent 1: VLM
        vlm_result = await agent_vlm_analyze(image_url)
        logger.info("Agent 1 VLM done", extra={"hazard": vlm_result.get("hazard_type"), "conf": vlm_result.get("confidence")})

        # Agent 2: Environment
        env_result = await agent_environment(lat, lng)
        logger.info("Agent 2 env done", extra={"score": env_result.get("environment_score")})

        # Agent 3: Dedup
        dedup_result = await agent_dedup(db, detection_id, lat, lng, image_hash, ticket_id)
        logger.info("Agent 3 dedup done", extra={"is_dup": dedup_result.get("is_duplicate")})

        # Agent 4: Scorer
        score_result = agent_scorer(vlm_result, env_result, dedup_result, detection_dict)
        logger.info("Agent 4 scorer done", extra={"score": score_result.get("final_score"), "severity": score_result.get("severity")})

        # Persist to detection
        caption = vlm_result.get("description", "")
        liability = vlm_result.get("liability_risk", "")
        if liability:
            caption = f"{caption} | סיכון: {liability}"

        notes_payload = json.dumps(
            {"vlm": vlm_result, "environment": env_result, "dedup": dedup_result, "scorer": score_result},
            ensure_ascii=False,
        )[:4000]

        # Pull real weather values from environment agent
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

        # Update ticket severity & score.
        # IMPORTANT: Do NOT override defect_type — the user's choice takes priority.
        # The VLM suggestion is stored in notes.vlm.hazard_type for reference only.
        severity = score_result["severity"]
        final_score = score_result["final_score"]
        if severity not in ("duplicate", "none"):
            # Only override defect_type if ticket currently has "unknown"
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
                # User already chose a type — only update severity + score
                await db.execute(
                    text("UPDATE tickets SET severity=:sev, score=:score WHERE id=:tid"),
                    {"sev": severity, "score": final_score, "tid": ticket_id},
                )

        await db.commit()
        logger.info("Pipeline complete", extra={"detection_id": detection_id, "score": score_result["final_score"]})

        # ── Export to Google Drive ──────────────────────────────────────────
        try:
            from app.services.drive_service import export_ticket_to_drive
            from app.core.config import get_settings as _gs
            _settings = _gs()

            if _settings.google_drive_enabled:
                # Fetch full ticket + detection rows for the JSON report
                t_row = (await db.execute(text("SELECT * FROM tickets WHERE id=:id"), {"id": ticket_id})).mappings().first()
                d_row = (await db.execute(text("SELECT * FROM detections WHERE id=:id"), {"id": detection_id})).mappings().first()

                if t_row and d_row:
                    # Resolve local file paths
                    img_path = None
                    if image_url and image_url.startswith("/uploads/"):
                        img_path = os.path.join(_settings.upload_path, image_url.replace("/uploads/", ""))

                    ply_path = None
                    ply_url = d_row.get("point_cloud_url", "")
                    if ply_url and ply_url.startswith("/uploads/"):
                        ply_path = os.path.join(_settings.upload_path, ply_url.replace("/uploads/", ""))

                    notes_dict = {"vlm": vlm_result, "environment": env_result, "dedup": dedup_result, "scorer": score_result}
                    drive_url = export_ticket_to_drive(dict(t_row), dict(d_row), notes_dict, img_path, ply_path)
                    if drive_url:
                        logger.info("Drive export OK", extra={"url": drive_url})
        except Exception as drive_exc:
            logger.warning("Drive export failed (non-fatal): %s", drive_exc)

        return {
            "detection_id": detection_id,
            "ticket_id": ticket_id,
            "vlm": vlm_result,
            "environment": env_result,
            "dedup": dedup_result,
            "score": score_result,
        }

    except Exception as exc:
        await db.execute(
            text("UPDATE detections SET pipeline_status='error', notes=:notes WHERE id=:id"),
            {"notes": json.dumps({"error": str(exc)}), "id": detection_id},
        )
        await db.commit()
        logger.error("Pipeline failed", extra={"detection_id": detection_id, "error": str(exc)})
        raise
