"""Evaluator node: scores search results for relevance, recency, and credibility."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from agent.events import publish
from agent.llm import get_llm
from agent.models import ScoredResult, SearchResult
from agent.state import AgentState
from agent.structured_output import invoke_structured

logger = logging.getLogger(__name__)


class _EvaluationScore(BaseModel):
    url: str
    relevance: float = Field(strict=True, ge=0, le=1)
    recency: float = Field(strict=True, ge=0, le=1)
    credibility: float = Field(strict=True, ge=0, le=1)


class _EvaluatorResponse(BaseModel):
    scores: List[_EvaluationScore]


_SYSTEM_PROMPT = (
    "You are a research quality evaluator. Score each search result on three dimensions.\n"
    "\n"
    "Dimensions (each 0.0–1.0):\n"
    "- relevance: how directly the snippet answers the sub-query\n"
    "- recency: how recent the information is (1.0 = current year, 0.5 = 1–3 years ago, 0.0 = older)\n"
    "- credibility: source authority (1.0 = gov/academic/major news, 0.5 = industry blogs, 0.0 = forums/wikis)\n"
    "\n"
    "Output ONLY valid JSON. No preamble, no markdown fences.\n"
    'Schema: {"scores": [{"url": "...", "relevance": 0.0, "recency": 0.0, "credibility": 0.0}]}'
)


def _build_user_message(results: List[SearchResult]) -> str:
    """Serialise search results into a JSON array for the evaluator prompt."""
    return json.dumps([
        {"url": r.url, "sub_query": r.sub_query, "title": r.title, "snippet": r.snippet}
        for r in results
    ])


async def run_evaluator(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Score all search results in a single LLM call and filter by composite threshold."""
    job_id: str = config.get("configurable", {}).get("job_id", "")
    search_results = state["search_results"]

    await publish(job_id, {"type": "stage_start", "stage": "evaluator",
                           "message": f"Evaluating quality of {len(search_results)} results..."})

    llm = get_llm(max_new_tokens=2048)
    messages = [
        SystemMessage(content=_SYSTEM_PROMPT),
        HumanMessage(content=_build_user_message(search_results)),
    ]
    data = await invoke_structured(llm, messages, _EvaluatorResponse, "evaluator")

    score_map: Dict[str, _EvaluationScore] = {score.url: score for score in data.scores}

    scored: List[ScoredResult] = []
    for r in search_results:
        score = score_map.get(r.url)
        if score is None:
            continue
        scored.append(ScoredResult(
            sub_query=r.sub_query, url=r.url, title=r.title,
            snippet=r.snippet, fetched_at=r.fetched_at,
            relevance=score.relevance, recency=score.recency,
            credibility=score.credibility,
        ))

    filtered = [s for s in scored if s.composite >= 0.6]
    if not filtered:
        logger.warning("No results passed composite threshold 0.6; returning all %d scored results.", len(scored))
        filtered = scored

    await publish(job_id, {"type": "stage_done", "stage": "evaluator",
                           "message": f"{len(filtered)} of {len(scored)} results passed the quality threshold"})

    return {"scored_results": filtered}
