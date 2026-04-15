"""FastAPI application exposing the research agent REST and SSE endpoints."""

from __future__ import annotations

import json
import logging

import redis.asyncio as aioredis
from celery.result import AsyncResult
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from api.schemas import ResearchRequest, ResearchResponse
from config import settings

logger = logging.getLogger(__name__)

app = FastAPI(title="Research Agent API")

_CORS_ORIGINS = ["*"] if settings.environment == "development" else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    """Return a simple liveness check."""
    return {"status": "ok"}


@app.post("/research", response_model=ResearchResponse, status_code=202)
async def create_research_job(request: ResearchRequest) -> ResearchResponse:
    """Enqueue a research job and return its job ID."""
    from tasks import run_research

    task = run_research.delay(request.question, request.mode)
    logger.info("Enqueued job %s", task.id)
    return ResearchResponse(job_id=task.id, status="queued")


@app.get("/research/{job_id}", response_model=ResearchResponse)
async def get_research_status(job_id: str) -> ResearchResponse:
    """Poll the status of an existing research job."""
    result = AsyncResult(job_id)

    if result.state == "PENDING":
        return ResearchResponse(job_id=job_id, status="queued")
    if result.state == "STARTED":
        return ResearchResponse(job_id=job_id, status="running")
    if result.state == "SUCCESS":
        data = result.result
        return ResearchResponse(
            job_id=job_id,
            status=data.get("status", "done"),
            output_url=data.get("output_url"),
            error=data.get("error"),
        )
    return ResearchResponse(
        job_id=job_id,
        status="failed",
        error=str(result.result) if result.result else "Unknown error",
    )


@app.get("/research/{job_id}/stream")
async def stream_research(job_id: str, request: Request) -> StreamingResponse:
    """SSE endpoint — replays event history then streams live events from Redis pub/sub."""

    async def generator():
        r = aioredis.from_url(settings.redis_url)
        try:
            # Replay any events that were published before the client connected
            history = await r.lrange(f"research:{job_id}:events", 0, -1)
            for item in history:
                yield f"data: {item.decode()}\n\n"

            # If the last event was terminal, stop here
            if history:
                last = json.loads(history[-1])
                if last.get("type") in ("done", "error"):
                    return

            # Subscribe for live events
            async with r.pubsub() as pubsub:
                await pubsub.subscribe(f"research:{job_id}")
                while True:
                    if await request.is_disconnected():
                        break
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True, timeout=30.0
                    )
                    if message is None:
                        yield ": keepalive\n\n"
                        continue
                    data = message["data"].decode()
                    yield f"data: {data}\n\n"
                    event = json.loads(data)
                    if event.get("type") in ("done", "error"):
                        break
        finally:
            await r.aclose()

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
