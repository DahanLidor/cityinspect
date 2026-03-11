from sqlalchemy.orm import Session
from models import Ticket, WorkOrder
from services.deduplication import haversine_distance
from datetime import datetime


SEVERITY_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1}
TEAM_MAP = {
    "pothole": "Road Maintenance Team A",
    "road_crack": "Road Maintenance Team A",
    "broken_light": "Electrical Infrastructure Team",
    "drainage_blocked": "Sewage & Drainage Team",
    "drain_overflow": "Sewage & Drainage Team",
    "sidewalk": "Sidewalk Repair Team",
}


def priority_score(ticket: Ticket) -> float:
    sw = SEVERITY_WEIGHTS.get(ticket.severity, 1)
    age_hours = (datetime.utcnow() - ticket.created_at).total_seconds() / 3600
    return sw * 3 + ticket.detection_count * 2 + age_hours * 0.5


def cluster_tickets(tickets: list[Ticket], radius_m=50) -> list[list[Ticket]]:
    assigned = set()
    clusters = []
    for t in tickets:
        if t.id in assigned:
            continue
        cluster = [t]
        assigned.add(t.id)
        for other in tickets:
            if other.id in assigned:
                continue
            if haversine_distance(t.lat, t.lng, other.lat, other.lng) <= radius_m:
                cluster.append(other)
                assigned.add(other.id)
        clusters.append(cluster)
    return clusters


def generate_work_orders(db: Session) -> list[WorkOrder]:
    open_tickets = db.query(Ticket).filter(
        Ticket.status.in_(["new", "verified"]),
        Ticket.work_order_id.is_(None)
    ).all()

    if not open_tickets:
        return []

    clusters = cluster_tickets(open_tickets)
    clusters.sort(key=lambda c: sum(priority_score(t) for t in c), reverse=True)

    work_orders = []
    for cluster in clusters:
        primary_type = cluster[0].defect_type
        team = TEAM_MAP.get(primary_type, "General Maintenance Team")
        duration = 30 + len(cluster) * 20

        wo = WorkOrder(
            ticket_ids=[t.id for t in cluster],
            assigned_team=team,
            estimated_duration_min=duration,
            status="pending",
            route_optimized=True
        )
        db.add(wo)
        db.flush()

        for ticket in cluster:
            ticket.work_order_id = wo.id
            ticket.status = "assigned"

        db.commit()
        db.refresh(wo)
        work_orders.append(wo)

    return work_orders
