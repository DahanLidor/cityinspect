"""
Work order routes.
"""
from __future__ import annotations

import json
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user
from app.models import User, WorkOrder
from app.schemas import WorkOrderOut

router = APIRouter(prefix="/api/v1", tags=["work_orders"])


@router.get("/work-orders", response_model=List[WorkOrderOut])
async def list_work_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[WorkOrderOut]:
    result = await db.execute(select(WorkOrder).order_by(WorkOrder.created_at.desc()))
    orders = result.scalars().all()
    out = []
    for wo in orders:
        try:
            ids = json.loads(wo.ticket_ids_json) if wo.ticket_ids_json else []
        except Exception:
            ids = []
        out.append(WorkOrderOut(
            id=wo.id,
            created_at=wo.created_at,
            title=wo.title,
            status=wo.status,
            team=wo.team,
            priority=wo.priority,
            ticket_ids=ids,
        ))
    return out
