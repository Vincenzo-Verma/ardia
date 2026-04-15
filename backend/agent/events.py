"""Redis pub/sub event publisher for streaming pipeline progress to SSE clients."""

from __future__ import annotations

import json

import redis.asyncio as aioredis

from config import settings

_TTL = 3600  # keep event history for 1 hour


async def publish(job_id: str, event: dict) -> None:
    """Push an event to the job's history list and broadcast it on the pub/sub channel."""
    if not job_id:
        return
    # Fresh connection each call — avoids binding to a specific event loop,
    # which breaks when asyncio.run() is called multiple times in the same process.
    r = aioredis.from_url(settings.redis_url)
    try:
        payload = json.dumps(event)
        key = f"research:{job_id}:events"
        await r.rpush(key, payload)
        await r.expire(key, _TTL)
        await r.publish(f"research:{job_id}", payload)
    finally:
        await r.aclose()
