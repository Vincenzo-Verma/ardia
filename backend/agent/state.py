"""LangGraph AgentState TypedDict for the autonomous research agent."""

from __future__ import annotations

from typing import List, Literal, Optional

from typing_extensions import TypedDict

from agent.models import ReportDraft, ScoredResult, SearchResult, SubQuery

__all__ = ["AgentState"]


class AgentState(TypedDict):
    """Single shared state passed through every node in the LangGraph pipeline."""

    question: str
    mode: Literal["quick", "standard", "deep"]
    sub_queries: List[SubQuery]
    search_results: List[SearchResult]
    scored_results: List[ScoredResult]
    draft: Optional[ReportDraft]
    iteration: int
    output_url: Optional[str]
    error: Optional[str]
