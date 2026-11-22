"""Planner node: decomposes a research question into focused sub-queries."""

from __future__ import annotations

from typing import Any, Dict, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from agent.events import publish
from agent.llm import get_llm
from agent.models import SubQuery
from agent.state import AgentState
from agent.structured_output import invoke_structured

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


class _PlannerSubQuery(BaseModel):
    text: str
    intent: Literal["factual", "comparative", "recent"]


class _PlannerResponse(BaseModel):
    sub_queries: list[_PlannerSubQuery]


async def run_planner(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Call the LLM to decompose the user question into sub-queries."""
    job_id: str = config.get("configurable", {}).get("job_id", "")
    question = state["question"]

    await publish(job_id, {"type": "stage_start", "stage": "planner",
                           "message": "Breaking down your question into sub-queries..."})

    llm = get_llm(max_new_tokens=1024)
    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=question)]
    parsed = await invoke_structured(llm, messages, _PlannerResponse, "planner")
    sub_queries = [
        SubQuery(text=item.text, intent=item.intent, parent_question=question)
        for item in parsed.sub_queries
    ]

    bullets = "\n".join(f'  • "{sq.text}"' for sq in sub_queries)
    await publish(job_id, {"type": "stage_done", "stage": "planner",
                           "message": f"Created {len(sub_queries)} sub-queries:\n{bullets}"})

    return {"sub_queries": sub_queries}
