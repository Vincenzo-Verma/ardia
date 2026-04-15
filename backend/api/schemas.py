"""Pydantic v2 request and response schemas for the research agent API."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    """Incoming request to start a research job."""

    question: str = Field(min_length=10, max_length=500)
    mode: Literal["quick", "standard", "deep"] = "standard"


class ResearchResponse(BaseModel):
    """Current state of a research job returned by the API."""

    job_id: str
    status: Literal["queued", "running", "done", "failed"]
    output_url: Optional[str] = None
    error: Optional[str] = None
