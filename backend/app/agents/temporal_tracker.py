"""
Agent: Temporal Tracker — tracks how a defect changes over time.

Queries previous detections for the same ticket to determine whether
the defect is worsening, stable, or improving, and raises alerts
when intervention is needed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Trend thresholds ────────────────────────────────────────────────────
_WORSENING_DELTA = 5.0    # score increase per observation to flag worsening
_IMPROVING_DELTA = -5.0   # score decrease per observation to flag improving
_ALERT_SCORE = 70         # score above this triggers an alert
_ALERT_DAYS_OPEN = 30     # days open above this triggers a delay alert


def _parse_datetime(val: Any) -> datetime | None:
    """Safely parse a datetime from DB (handles strings from SQLite)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val
    if isinstance(val, str):
        try:
            dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except (ValueError, TypeError):
            return None
    return None


def _determine_trend(scores: List[float]) -> str:
    """
    Determine trend direction from a list of chronological scores.

    Returns: 'worsening', 'improving', or 'stable'.
    """
    if len(scores) < 2:
        return "stable"

    # Compare average of last half vs first half
    mid = len(scores) // 2
    first_half_avg = sum(scores[:mid]) / max(mid, 1)
    second_half_avg = sum(scores[mid:]) / max(len(scores) - mid, 1)
    delta = second_half_avg - first_half_avg

    if delta >= _WORSENING_DELTA:
        return "worsening"
    elif delta <= _IMPROVING_DELTA:
        return "improving"
    return "stable"


async def agent_temporal_tracker(
    db: AsyncSession,
    ticket_id: int,
    detection_id: int,
    current_score: float,
) -> Dict[str, Any]:
    """
    Track defect progression over time for a given ticket.

    Args:
        db: Async database session.
        ticket_id: The ticket to track.
        detection_id: Current detection (excluded from history).
        current_score: Current severity score (0-100).

    Returns:
        Dict with tracking info, trend, observations, alerts.
    """
    logger.info(
        "Temporal tracker starting",
        extra={"ticket_id": ticket_id, "detection_id": detection_id},
    )

    # ── Fetch previous detections for this ticket ───────────────────
    result = await db.execute(
        text(
            "SELECT id, detected_at, notes, pipeline_status "
            "FROM detections "
            "WHERE ticket_id = :tid AND id != :did "
            "ORDER BY detected_at ASC"
        ),
        {"tid": ticket_id, "did": detection_id},
    )
    previous = result.fetchall()

    # ── Build score history ─────────────────────────────────────────
    score_history: List[Dict[str, Any]] = []
    timestamps: List[datetime] = []

    for row in previous:
        detected_at = _parse_datetime(row.detected_at)
        if detected_at:
            timestamps.append(detected_at)

        # Try to extract score from notes JSON
        score_val = None
        if row.notes:
            try:
                import json
                notes = json.loads(row.notes)
                scorer = notes.get("scorer", {})
                score_val = scorer.get("final_score")
            except (json.JSONDecodeError, TypeError):
                pass

        score_history.append({
            "detection_id": row.id,
            "detected_at": detected_at.isoformat() if detected_at else None,
            "score": score_val,
        })

    # Add current score
    now = datetime.now(timezone.utc)
    score_history.append({
        "detection_id": detection_id,
        "detected_at": now.isoformat(),
        "score": current_score,
    })

    # ── Calculate trend ─────────────────────────────────────────────
    numeric_scores = [
        entry["score"] for entry in score_history if entry["score"] is not None
    ]
    trend = _determine_trend(numeric_scores)

    # ── Time calculations ───────────────────────────────────────────
    first_seen = timestamps[0] if timestamps else now
    days_open = (now - first_seen).days

    # ── Build observations ──────────────────────────────────────────
    observations: List[str] = []
    total_detections = len(score_history)

    observations.append(f"סה\"כ {total_detections} צפיות בכרטיס זה")

    if days_open > 0:
        observations.append(f"המפגע פתוח {days_open} ימים")

    if trend == "worsening":
        observations.append("המפגע מחמיר — מומלץ לטפל בהקדם")
    elif trend == "improving":
        observations.append("המפגע משתפר — ייתכן שהתבצע תיקון חלקי")
    else:
        observations.append("מצב המפגע יציב")

    if len(numeric_scores) >= 2:
        latest = numeric_scores[-1]
        previous_avg = sum(numeric_scores[:-1]) / len(numeric_scores[:-1])
        diff = latest - previous_avg
        if abs(diff) > 2:
            direction = "עלייה" if diff > 0 else "ירידה"
            observations.append(
                f"{direction} של {abs(diff):.0f} נקודות מהממוצע הקודם"
            )

    # ── Alert logic ─────────────────────────────────────────────────
    alert: str | None = None

    if trend == "worsening" and current_score >= _ALERT_SCORE:
        alert = "התראה: מפגע מחמיר עם חומרה גבוהה — נדרשת התערבות מיידית"
    elif days_open > _ALERT_DAYS_OPEN and current_score >= 50:
        alert = f"התראה: מפגע פתוח {days_open} ימים ללא טיפול"
    elif trend == "worsening":
        alert = "שים לב: מגמת החמרה — מומלץ לתזמן טיפול"

    tracking_result = {
        "tracking": {
            "ticket_id": ticket_id,
            "detection_id": detection_id,
            "total_observations": total_detections,
            "current_score": current_score,
        },
        "trend": trend,
        "observations": observations,
        "days_open": days_open,
        "first_seen": first_seen.isoformat(),
        "score_history": score_history,
        "alert": alert,
    }

    logger.info(
        "Temporal tracking done",
        extra={
            "ticket_id": ticket_id,
            "trend": trend,
            "days_open": days_open,
            "observations": total_detections,
            "alert": alert is not None,
        },
    )
    return tracking_result
