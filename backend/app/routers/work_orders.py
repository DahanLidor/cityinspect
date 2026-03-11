from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from database import get_db
from models import WorkOrder, Ticket, Detection
from schemas import WorkOrderOut, StatsOut
from services.optimizer import generate_work_orders
from datetime import datetime, timedelta

router = APIRouter(tags=["work_orders"])


@router.get("/api/work-orders", response_model=List[WorkOrderOut])
def get_work_orders(db: Session = Depends(get_db)):
    return db.query(WorkOrder).order_by(WorkOrder.created_at.desc()).all()


@router.post("/api/work-orders/generate", response_model=List[WorkOrderOut])
async def create_work_orders(db: Session = Depends(get_db)):
    orders = generate_work_orders(db)
    from main import broadcast
    await broadcast({"type": "work_order_generated", "count": len(orders)})
    return orders


@router.get("/api/stats/summary", response_model=StatsOut)
def get_stats(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0)
    hour_ago = now - timedelta(hours=1)

    open_statuses = ["new", "verified", "assigned", "in_progress"]
    total_open = db.query(Ticket).filter(Ticket.status.in_(open_statuses)).count()
    critical = db.query(Ticket).filter(Ticket.severity == "critical", Ticket.status.in_(open_statuses)).count()
    in_prog = db.query(Ticket).filter(Ticket.status == "in_progress").count()
    resolved_today = db.query(Ticket).filter(
        Ticket.status == "resolved", Ticket.updated_at >= today_start
    ).count()
    det_last_hour = db.query(Detection).filter(Detection.detected_at >= hour_ago).count()

    # Detections per hour for last 6 hours
    per_hour = []
    for i in range(5, -1, -1):
        start = now - timedelta(hours=i+1)
        end = now - timedelta(hours=i)
        count = db.query(Detection).filter(
            Detection.detected_at >= start, Detection.detected_at < end
        ).count()
        per_hour.append({"hour": f"{start.hour:02d}:00", "count": count})

    # By type
    from sqlalchemy import func
    type_rows = db.query(Ticket.defect_type, func.count()).group_by(Ticket.defect_type).all()
    severity_rows = db.query(Ticket.severity, func.count()).group_by(Ticket.severity).all()

    return StatsOut(
        total_open=total_open,
        critical_count=critical,
        in_progress=in_prog,
        resolved_today=resolved_today,
        detections_last_hour=det_last_hour,
        detections_per_hour=per_hour,
        by_type={r[0]: r[1] for r in type_rows},
        by_severity={r[0]: r[1] for r in severity_rows}
    )
