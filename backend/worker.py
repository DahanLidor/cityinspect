"""
Celery worker + Beat schedule.

Queues:
  pipeline  — AI detection pipeline
  sla       — SLA watcher (every 60s)

Usage:
  # Worker (processes tasks)
  celery -A worker.celery_app worker --loglevel=info -Q pipeline,sla

  # Beat (schedules periodic tasks)
  celery -A worker.celery_app beat --loglevel=info
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from celery import Celery
from celery.schedules import crontab
from celery.utils.log import get_task_logger

from app.core.config import get_settings

settings = get_settings()
logger = get_task_logger(__name__)

celery_app = Celery(
    "cityinspect",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Jerusalem",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "worker.run_pipeline_task": {"queue": "pipeline"},
        "worker.check_sla_task": {"queue": "sla"},
    },
    beat_schedule={
        "sla-watcher": {
            "task": "worker.check_sla_task",
            "schedule": 60.0,  # every 60 seconds
        },
    },
)


# ── AI Pipeline ───────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="worker.run_pipeline_task",
    max_retries=3,
    default_retry_delay=60,
)
def run_pipeline_task(
    self,
    detection_id: int,
    ticket_id: int,
    lat: float,
    lng: float,
    image_url: str,
    image_hash: str,
    detection_dict: Dict[str, Any],
) -> Dict[str, Any]:
    """Celery task wrapping the async pipeline runner."""
    async def _run():
        from app.agents.pipeline import run_pipeline
        from app.core.database import _async_session

        async with _async_session() as db:
            return await run_pipeline(
                db, detection_id, ticket_id, lat, lng, image_url, image_hash, detection_dict
            )

    try:
        result = asyncio.run(_run())
        logger.info("Pipeline task complete for detection #%d", detection_id)
        return result
    except Exception as exc:
        logger.error("Pipeline task failed for detection #%d: %s", detection_id, exc)
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 30)


# ── SLA Watcher ───────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="worker.check_sla_task",
    max_retries=1,
)
def check_sla_task(self) -> Dict[str, Any]:
    """Periodic task: scan for overdue steps and escalate."""
    async def _run():
        from app.core.database import _async_session
        from app.services.sla_watcher import check_sla_violations

        async with _async_session() as db:
            return await check_sla_violations(db)

    try:
        result = asyncio.run(_run())
        if result["escalated"] > 0:
            logger.info("SLA watcher: escalated %d steps", result["escalated"])
        return result
    except Exception as exc:
        logger.error("SLA watcher failed: %s", exc)
        raise self.retry(exc=exc, countdown=30)
