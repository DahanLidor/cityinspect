"""
Celery worker for reliable background pipeline execution.

Usage:
  celery -A worker.celery_app worker --loglevel=info -Q pipeline

The pipeline is triggered by the API via .delay() which places a task on the
Redis queue. Celery retries up to 3 times with exponential back-off on failure.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

from celery import Celery
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
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_routes={"worker.run_pipeline_task": {"queue": "pipeline"}},
)


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
        logger.info(f"Pipeline task complete for detection #{detection_id}")
        return result
    except Exception as exc:
        logger.error(f"Pipeline task failed for detection #{detection_id}: {exc}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries * 30)
