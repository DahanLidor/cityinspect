"""City-level intelligence engine — health scoring, trends, recommendations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


def _grade(score: float) -> str:
    if score > 85:
        return "A"
    if score > 70:
        return "B"
    if score > 55:
        return "C"
    if score > 40:
        return "D"
    return "F"


class CityIntelligenceEngine:
    """Computes a 0-100 city health score and generates recommendations."""

    # ── Main health score ────────────────────────────────────────────────────

    async def compute_city_health(self, db: AsyncSession, city_id: str) -> dict:
        now = datetime.now(timezone.utc)
        thirty_days_ago = now - timedelta(days=30)
        sixty_days_ago = now - timedelta(days=60)

        # ---------- basic counts ----------
        row = (await db.execute(text(
            "SELECT"
            "  COUNT(*)                                                   AS total,"
            "  SUM(CASE WHEN status != 'resolved' THEN 1 ELSE 0 END)     AS open_tickets,"
            "  SUM(CASE WHEN status != 'resolved' AND severity = 'critical' THEN 1 ELSE 0 END) AS critical_open "
            "FROM tickets WHERE city_id = :cid"
        ), {"cid": city_id})).one()

        total_tickets = row.total or 0
        open_tickets = row.open_tickets or 0
        critical_open = row.critical_open or 0

        # ---------- average resolve time (days) ----------
        resolve_row = (await db.execute(text(
            "SELECT AVG("
            "  (JULIANDAY(updated_at) - JULIANDAY(created_at))"
            ") AS avg_days "
            "FROM tickets WHERE city_id = :cid AND status = 'resolved'"
        ), {"cid": city_id})).one()
        avg_resolve_days = round(resolve_row.avg_days or 0, 2)

        # ---------- SLA compliance ----------
        sla_row = (await db.execute(text(
            "SELECT"
            "  COUNT(*)                                         AS total_sla,"
            "  SUM(CASE WHEN sla_breached = 0 THEN 1 ELSE 0 END) AS met "
            "FROM tickets "
            "WHERE city_id = :cid AND sla_deadline IS NOT NULL"
        ), {"cid": city_id})).one()
        total_sla = sla_row.total_sla or 0
        sla_compliance_pct = round((sla_row.met or 0) / total_sla, 4) if total_sla else 1.0

        # ---------- defect trend (last 30d vs previous 30d) ----------
        trend_row = (await db.execute(text(
            "SELECT"
            "  SUM(CASE WHEN created_at >= :t30 THEN 1 ELSE 0 END) AS last30,"
            "  SUM(CASE WHEN created_at >= :t60 AND created_at < :t30 THEN 1 ELSE 0 END) AS prev30 "
            "FROM tickets WHERE city_id = :cid"
        ), {"cid": city_id, "t30": thirty_days_ago, "t60": sixty_days_ago})).one()
        last30 = trend_row.last30 or 0
        prev30 = trend_row.prev30 or 0

        if prev30 == 0:
            trend_pct_change = 0.0
            defect_trend = "stable"
        else:
            trend_pct_change = round(((last30 - prev30) / prev30) * 100, 1)
            if trend_pct_change < -5:
                defect_trend = "declining"
            elif trend_pct_change > 5:
                defect_trend = "rising"
            else:
                defect_trend = "stable"

        # ---------- resolved last 30 days ----------
        resolved_30d_row = (await db.execute(text(
            "SELECT COUNT(*) AS cnt FROM tickets "
            "WHERE city_id = :cid AND status = 'resolved' AND updated_at >= :t30"
        ), {"cid": city_id, "t30": thirty_days_ago})).one()
        resolved_last_30d = resolved_30d_row.cnt or 0

        # ── Score calculation (4 pillars, 25 pts each) ───────────────────────

        # 1. Critical defects per 100 tickets — lower is better
        if total_tickets > 0:
            critical_rate = (critical_open / total_tickets) * 100
            pillar_critical = max(0, 25 - critical_rate * 5)
        else:
            pillar_critical = 25.0

        # 2. Average resolve time — lower is better (0 days = 25, >=14 days = 0)
        pillar_resolve = max(0, 25 - (avg_resolve_days / 14) * 25)

        # 3. SLA compliance — higher is better
        pillar_sla = sla_compliance_pct * 25

        # 4. Defect trend — declining is better
        if defect_trend == "declining":
            pillar_trend = 25.0
        elif defect_trend == "stable":
            pillar_trend = 15.0
        else:
            pillar_trend = max(0, 15 - abs(trend_pct_change) * 0.2)

        health_score = int(round(
            pillar_critical + pillar_resolve + pillar_sla + pillar_trend
        ))
        health_score = max(0, min(100, health_score))

        # ── Recommendations ──────────────────────────────────────────────────
        recommendations: list[dict] = []

        if avg_resolve_days > 7:
            recommendations.append({
                "priority": "high",
                "area": "response_time",
                "text_he": "זמן תיקון ממוצע גבוה — מומלץ להגדיל צוות",
            })
        if sla_compliance_pct < 0.7:
            recommendations.append({
                "priority": "high",
                "area": "sla",
                "text_he": "עמידה ב-SLA נמוכה — יש לבדוק צווארי בקבוק בתהליך",
            })
        if critical_open > 5:
            recommendations.append({
                "priority": "critical",
                "area": "critical_defects",
                "text_he": "ריכוז גבוה של תקלות קריטיות פתוחות — נדרשת התייחסות מיידית",
            })
        if defect_trend == "rising":
            recommendations.append({
                "priority": "medium",
                "area": "trend",
                "text_he": "מגמת עלייה בתקלות — מומלץ לבדוק סיבות שורש",
            })
        if open_tickets > 0 and total_tickets > 0 and (open_tickets / total_tickets) > 0.5:
            recommendations.append({
                "priority": "medium",
                "area": "backlog",
                "text_he": "יותר ממחצית הטיקטים פתוחים — יש לטפל בצבר",
            })

        return {
            "health_score": health_score,
            "grade": _grade(health_score),
            "metrics": {
                "total_tickets": total_tickets,
                "open_tickets": open_tickets,
                "critical_open": critical_open,
                "avg_resolve_days": avg_resolve_days,
                "sla_compliance_pct": sla_compliance_pct,
                "defect_trend": defect_trend,
                "trend_pct_change": trend_pct_change,
                "resolved_last_30d": resolved_last_30d,
            },
            "recommendations": recommendations,
        }

    # ── Monthly trends ───────────────────────────────────────────────────────

    async def get_trends(
        self, db: AsyncSession, city_id: str, months: int = 6
    ) -> list:
        """Return monthly breakdown for the last *months* months."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=months * 30)

        rows = (await db.execute(text(
            "SELECT"
            "  strftime('%Y-%m', created_at) AS month,"
            "  COUNT(*)                       AS total,"
            "  SUM(CASE WHEN status = 'resolved' THEN 1 ELSE 0 END) AS resolved,"
            "  AVG(score)                     AS avg_score "
            "FROM tickets "
            "WHERE city_id = :cid AND created_at >= :cutoff "
            "GROUP BY month ORDER BY month"
        ), {"cid": city_id, "cutoff": cutoff})).all()

        results: list[dict] = []
        for r in rows:
            month_total = r.total or 0
            month_resolved = r.resolved or 0
            # Simple per-month health proxy: resolved ratio * 100
            month_health = int(round((month_resolved / month_total) * 100)) if month_total else 0
            results.append({
                "month": r.month,
                "total": month_total,
                "resolved": month_resolved,
                "avg_score": round(r.avg_score or 0, 1),
                "health_score": month_health,
            })

        return results
