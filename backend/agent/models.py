"""Pydantic v2 data contracts for the autonomous research agent."""

from __future__ import annotations

from datetime import datetime
from typing import List, Literal

from pydantic import BaseModel, ConfigDict, computed_field

__all__ = [
    "SubQuery",
    "SearchResult",
    "ScoredResult",
    "ReportSection",
    "ReportDraft",
]


class SubQuery(BaseModel):
    """A focused search sub-query derived from the user's research question."""

    model_config = ConfigDict(frozen=True)

    text: str
    intent: Literal["factual", "comparative", "recent"]
    parent_question: str


class SearchResult(BaseModel):
    """A single web search result retrieved for a sub-query."""

    model_config = ConfigDict(frozen=True)

    sub_query: str
    url: str
    title: str
    snippet: str
    fetched_at: datetime


class ScoredResult(SearchResult):
    """A search result enriched with quality scores from the evaluator."""

    model_config = ConfigDict(frozen=True)

    relevance: float
    recency: float
    credibility: float

    @computed_field
    @property
    def composite(self) -> float:
        """Mean of relevance, recency, and credibility rounded to 4 decimal places."""
        return round((self.relevance + self.recency + self.credibility) / 3, 4)


class ReportSection(BaseModel):
    """A single themed section within the research report."""

    model_config = ConfigDict(frozen=True)

    heading: str
    body: str
    citations: List[str]


class ReportDraft(BaseModel):
    """A structured draft of the research report produced by the synthesizer."""

    model_config = ConfigDict(frozen=True)

    title: str
    sections: List[ReportSection]
    bibliography: List[str]
    gaps: List[str]
    iteration: int
