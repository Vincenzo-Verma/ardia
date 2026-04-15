"""Synthesizer node: produces a structured ReportDraft from scored search results."""

from __future__ import annotations

import json
import logging
from typing import Any, Dict

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agent.events import publish
from agent.llm import get_llm
from agent.models import ReportDraft, ReportSection
from agent.state import AgentState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a research synthesis assistant. You receive a set of scored web search\n"
    "results and must produce a structured research report.\n"
    "\n"
    "Rules:\n"
    "- Group findings by theme, not by source.\n"
    "- Every factual claim must be followed by its source URL in parentheses.\n"
    "- Identify any sub-questions from the original query that are NOT answered by\n"
    '  the provided results and list them in "gaps".\n'
    "- Output ONLY valid JSON. No preamble, no markdown fences.\n"
    "- Schema:\n"
    "  {\n"
    '    "title": "...",\n'
    '    "sections": [{"heading": "...", "body": "...", "citations": ["url1", ...]}],\n'
    '    "bibliography": ["url1", "url2", ...],\n'
    '    "gaps": ["unanswered sub-query text", ...],\n'
    '    "iteration": <current iteration number as integer>\n'
    "  }"
)


def _build_user_message(state: AgentState) -> str:
    """Construct the user message with question, sub-queries, results, and iteration."""
    sub_query_list = "\n".join(f"{i + 1}. {sq.text}" for i, sq in enumerate(state["sub_queries"]))
    results_payload = json.dumps([
        {"url": r.url, "title": r.title, "snippet": r.snippet, "composite": r.composite}
        for r in state["scored_results"]
    ])
    return (
        f"Original question: {state['question']}\n\n"
        f"Sub-queries:\n{sub_query_list}\n\n"
        f"Scored results:\n{results_payload}\n\n"
        f"Current iteration: {state['iteration']}"
    )


async def run_synthesizer(state: AgentState, config: RunnableConfig) -> Dict[str, Any]:
    """Call the LLM to synthesise scored results into a structured ReportDraft."""
    job_id: str = config.get("configurable", {}).get("job_id", "")
    iteration = state["iteration"]

    await publish(job_id, {"type": "stage_start", "stage": "synthesizer",
                           "message": f"Synthesizing report (pass {iteration + 1})..."})

    llm = get_llm(max_new_tokens=4096)
    messages = [SystemMessage(content=_SYSTEM_PROMPT), HumanMessage(content=_build_user_message(state))]
    response = await llm.ainvoke(messages)
    raw: str = response.content
    logger.debug("Synthesizer raw response: %s", raw)
    data = json.loads(raw)

    sections = [
        ReportSection(heading=s["heading"], body=s["body"], citations=s["citations"])
        for s in data["sections"]
    ]
    draft = ReportDraft(
        title=data["title"], sections=sections,
        bibliography=data["bibliography"], gaps=data["gaps"], iteration=data["iteration"],
    )

    if draft.gaps:
        gap_list = "\n".join(f'  • "{g}"' for g in draft.gaps)
        msg = f"Draft complete — {len(draft.gaps)} gap(s) found, refining:\n{gap_list}"
    else:
        msg = f"Report complete — {len(draft.sections)} sections, {len(draft.bibliography)} sources"

    await publish(job_id, {"type": "stage_done", "stage": "synthesizer", "message": msg})

    return {"draft": draft, "iteration": state["iteration"] + 1}
