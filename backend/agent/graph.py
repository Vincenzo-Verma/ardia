"""LangGraph graph definition for the autonomous research agent pipeline."""

from __future__ import annotations

import logging
from typing import Literal

from langgraph.graph import END, START, StateGraph

from agent.nodes.evaluator import run_evaluator
from agent.nodes.formatter import run_formatter
from agent.nodes.planner import run_planner
from agent.nodes.retriever import run_retriever
from agent.nodes.synthesizer import run_synthesizer
from agent.state import AgentState

logger = logging.getLogger(__name__)

_MODE_MAX = {"quick": 1, "standard": 2, "deep": 3}


def should_continue(state: AgentState) -> Literal["retriever", "formatter"]:
    """Decide whether to loop back for gap retrieval or proceed to formatting."""
    draft = state["draft"]
    mode_max = _MODE_MAX[state["mode"]]
    if not draft.gaps or state["iteration"] >= mode_max:
        return "formatter"
    return "retriever"


def _build_graph() -> StateGraph:
    """Construct and compile the research agent StateGraph."""
    builder = StateGraph(AgentState)

    builder.add_node("planner", run_planner)
    builder.add_node("retriever", run_retriever)
    builder.add_node("evaluator", run_evaluator)
    builder.add_node("synthesizer", run_synthesizer)
    builder.add_node("formatter", run_formatter)

    builder.add_edge(START, "planner")
    builder.add_edge("planner", "retriever")
    builder.add_edge("retriever", "evaluator")
    builder.add_edge("evaluator", "synthesizer")
    builder.add_conditional_edges(
        "synthesizer",
        should_continue,
        {"retriever": "retriever", "formatter": "formatter"},
    )
    builder.add_edge("formatter", END)

    return builder.compile(checkpointer=None)


graph = _build_graph()


async def run(question: str, mode: str = "standard", job_id: str = "") -> AgentState:
    """Invoke the research agent graph and return the final state."""
    initial_state: AgentState = {
        "question": question,
        "mode": mode,
        "sub_queries": [],
        "search_results": [],
        "scored_results": [],
        "draft": None,
        "iteration": 0,
        "output_url": None,
        "error": None,
    }
    config = {"configurable": {"job_id": job_id}} if job_id else {}
    logger.info("Starting research run: question=%r mode=%s job_id=%s", question, mode, job_id)
    return await graph.ainvoke(initial_state, config=config)
