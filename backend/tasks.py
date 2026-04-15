"""Celery task definitions for the research agent."""

from __future__ import annotations

import asyncio
import json
import logging

import redis
from celery import Celery

from config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "research_agent",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]

_TTL = 3600


def _publish_error_sync(job_id: str, error: str) -> None:
    """Publish a terminal error event using a sync Redis client — safe after asyncio.run() closes."""
    r = redis.from_url(settings.redis_url)
    payload = json.dumps({"type": "error", "error": error})
    key = f"research:{job_id}:events"
    r.rpush(key, payload)
    r.expire(key, _TTL)
    r.publish(f"research:{job_id}", payload)
    r.close()


@celery_app.task(name="run_research", bind=True)
def run_research(self, question: str, mode: str) -> dict:
    """Run the full research agent pipeline and return status and output URL."""
    job_id: str = self.request.id
    try:
        from agent.graph import run

        state = asyncio.run(run(question, mode, job_id=job_id))
        return {"status": "done", "output_url": state["output_url"]}
    except Exception as exc:
        logger.exception("Research job failed for question=%r", question)
        try:
            _publish_error_sync(job_id, str(exc))
        except Exception:
            logger.warning("Failed to publish error event for job %s", job_id)
        return {"status": "failed", "error": str(exc)}
