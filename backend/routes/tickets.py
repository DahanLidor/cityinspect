from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from database import get_db
from models import Ticket
from schemas import TicketOut, TicketUpdate
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


@router.get("", response_model=List[TicketOut])
def get_tickets(
    status: Optional[str] = Query(None),
    defect_type: Optional[str] = Query(None),
    limit: int = Query(100),
    db: Session = Depends(get_db)
):
    q = db.query(Ticket)
    if status:
        statuses = status.split(",")
        q = q.filter(Ticket.status.in_(statuses))
    if defect_type:
        q = q.filter(Ticket.defect_type == defect_type)
    return q.order_by(Ticket.created_at.desc()).limit(limit).all()


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/{ticket_id}", response_model=TicketOut)
async def update_ticket(ticket_id: int, update: TicketUpdate, db: Session = Depends(get_db)):
    ticket = db.query(Ticket).filter(Ticket.id == ticket_id).first()
    if not ticket:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket.status = update.status
    ticket.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ticket)
    from main import broadcast
    await broadcast({"type": "ticket_updated", "ticket_id": ticket.id, "status": ticket.status})
    return ticket
