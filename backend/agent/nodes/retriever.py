"""Retriever node: performs concurrent web searches for each sub-query."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from langchain_community.utilities import DuckDuckGoSearchAPIWrapper
from langchain_core.runnables import RunnableConfig

from agent.events import publish
from agent.models import SearchResult, SubQuery
from agent.state import AgentState

logger = logging.getLogger(__name__)

_SEARCH = DuckDuckGoSearchAPIWrapper()
_MAX_RESULTS_PER_QUERY = 5
_SEARCH_TIMEOUT_S = 25.0   # per-query hard timeout
_CONCURRENCY = 2            # max simultaneous DDG requests (avoids rate-limiting)
_STAGGER_S = 0.4            # delay between query starts


def _search_sync(query: str) -> List[Dict]:
    """Run a synchronous DuckDuckGo search and return raw result dicts."""
    return _SEARCH.results(query, max_results=_MAX_RESULTS_PER_QUERY)


async def _search_one(
    sub_query: SubQuery,
    job_id: str,
    sem: asyncio.Semaphore,
    delay: float,
) -> List[SearchResult]:
    """Acquire semaphore slot, optionally stagger, then search with a hard timeout."""
    await asyncio.sleep(delay)
    async with sem:
        loop = asyncio.get_event_loop()
        try:
            raw_results: List[Dict] = await asyncio.wait_for(
                loop.run_in_executor(None, _search_sync, sub_query.text),
                timeout=_SEARCH_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            logger.warning("Search timed out for query: %r", sub_query.text)
            await publish(job_id, {"type": "progress", "stage": "retriever",
                                   "message": f'  ⚠ "{sub_query.text}" — timed out, skipping'})
            return []
        except Exception as exc:
            logger.warning("Search failed for query %r: %s", sub_query.text, exc)
            await publish(job_id, {"type": "progress", "stage": "retriever",
                                   "message": f'  ⚠ "{sub_query.text}" — error: {exc}'})
            return []

    results = [
        SearchResult(
            sub_query=sub_query.text,
            url=item.get("link", ""),
            title=item.get("title", ""),
            snippet=item.get("snippet", ""),
            fetched_at=datetime.now(timezone.utc),
        )
        for item in raw_results
        if item.get("link")
    ]

    if not results:
        logger.warning("No results returned for sub-query: %r", sub_query.text)

    count = len(results)
    msg = f'  ✓ "{sub_query.text}" — {count} result{"s" if count != 1 else ""}'
    await publish(job_id, {"type": "progress", "stage": "retriever", "message": msg})
    return results


async def run_retriever(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Search the web for all sub-queries with bounded concurrency and timeouts."""
    job_id: str = config.get("configurable", {}).get("job_id", "")
    sub_queries = state["sub_queries"]
    iteration = state["iteration"]

    label = f" (iteration {iteration + 1})" if iteration > 0 else ""
    await publish(job_id, {"type": "stage_start", "stage": "retriever",
                           "message": f"Searching the web for {len(sub_queries)} queries{label}..."})

    sem = asyncio.Semaphore(_CONCURRENCY)
    tasks = [
        _search_one(sq, job_id, sem, delay=i * _STAGGER_S)
        for i, sq in enumerate(sub_queries)
    ]
    all_results_nested = await asyncio.gather(*tasks)
    flat: List[SearchResult] = [r for batch in all_results_nested for r in batch]

    await publish(job_id, {"type": "stage_done", "stage": "retriever",
                           "message": f"Retrieved {len(flat)} results total"})

    return {"search_results": flat}
