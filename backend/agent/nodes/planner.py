"""Planner node: decomposes a research question into focused sub-queries."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agent.events import publish
from agent.llm import get_llm
from agent.models import SubQuery
from agent.state import AgentState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a research planning assistant. Your job is to decompose a user's\n"
    "research question into 3 to 5 focused search sub-queries.\n"
    "\n"
    "Rules:\n"
    "- Each sub-query must be independently searchable (no pronouns referencing other queries).\n"
    "- Assign one intent to each: \"factual\" (stable facts), \"comparative\" (A vs B),\n"
    '  or "recent" (news, events, current state).\n'
    "- Output ONLY valid JSON. No preamble, no markdown fences.\n"
    '- Schema: {"sub_queries": [{"text": "...", "intent": "...", "parent_question": "..."}]}'
)


class PlannerError(RuntimeError):
    """Raised when the planner fails to produce valid sub-queries after retries."""


def _parse_response(raw: str, question: str) -> list[SubQuery]:
    """Parse and validate the LLM JSON response into a list of SubQuery objects."""
    data = json.loads(raw)
    return [
        SubQuery(text=item["text"], intent=item["intent"], parent_question=question)
        for item in data["sub_queries"]
    ]


async def run_planner(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Call the LLM to decompose the user question into sub-queries."""
    job_id: str = config.get("configurable", {}).get("job_id", "")
    question = state["question"]

    await publish(job_id, {"type": "stage_start", "stage": "planner",
                           "message": "Breaking down your question into sub-queries..."})

    llm = get_llm(max_new_tokens=1024)
    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=question)]
    response = await llm.ainvoke(messages)
    raw: str = response.content
    logger.debug("Planner raw response: %s", raw)

    try:
        sub_queries = _parse_response(raw, question)
    except Exception as first_err:
        logger.warning("Planner first parse failed (%s); retrying.", first_err)
        retry_messages = messages + [
            response,
            HumanMessage(content=(
                f"Your previous response could not be parsed: {first_err}. "
                "Output ONLY valid JSON matching the schema."
            )),
        ]
        retry_response = await llm.ainvoke(retry_messages)
        raw = retry_response.content
        logger.debug("Planner retry raw response: %s", raw)
        try:
            sub_queries = _parse_response(raw, question)
        except Exception as second_err:
            raise PlannerError(
                f"Planner failed to produce valid JSON after retry: {second_err}"
            ) from second_err

    bullets = "\n".join(f'  • "{sq.text}"' for sq in sub_queries)
    await publish(job_id, {"type": "stage_done", "stage": "planner",
                           "message": f"Created {len(sub_queries)} sub-queries:\n{bullets}"})

    return {"sub_queries": sub_queries}
