"""Regression tests for malformed and schema-invalid LLM responses."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

from langchain_core.messages import AIMessage

# Application imports construct Settings, so mocked tests need no real credentials.
for _key in ("HUGGINGFACE_API_KEY", "LANGSMITH_API_KEY", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY"):
    os.environ.setdefault(_key, "offline-test-placeholder")

from agent.models import ScoredResult, SearchResult, SubQuery
from agent.nodes.evaluator import run_evaluator
from agent.nodes.planner import run_planner
from agent.nodes.synthesizer import run_synthesizer
from agent.state import AgentState
from agent.structured_output import StructuredResponseError

from tasks import run_research


class QueueLLM:
    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.message_counts: list[int] = []

    async def ainvoke(self, messages: list[object]) -> AIMessage:
        self.calls += 1
        self.message_counts.append(len(messages))
        if not self.responses:
            raise AssertionError("The node invoked the LLM more times than expected.")
        return AIMessage(content=self.responses.pop(0))


def _evaluation_state() -> AgentState:
    return {
        "question": "What is changing in fusion energy?",
        "mode": "standard",
        "sub_queries": [],
        "search_results": [
            SearchResult(
                sub_query="fusion energy",
                url="https://example.test/fusion",
                title="Fusion update",
                snippet="A representative result.",
                fetched_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
            )
        ],
        "scored_results": [],
        "draft": None,
        "iteration": 0,
        "output_url": None,
        "error": None,
    }


def _synthesis_state() -> AgentState:
    sub_query = SubQuery(
        text="fusion energy",
        intent="factual",
        parent_question="What is changing in fusion energy?",
    )
    scored_result = ScoredResult(
        sub_query=sub_query.text,
        url="https://example.test/fusion",
        title="Fusion update",
        snippet="A representative result.",
        fetched_at=datetime(2026, 11, 1, tzinfo=timezone.utc),
        relevance=0.9,
        recency=0.8,
        credibility=0.7,
    )
    return {
        "question": "What is changing in fusion energy?",
        "mode": "standard",
        "sub_queries": [sub_query],
        "search_results": [],
        "scored_results": [scored_result],
        "iteration": 0,
        "draft": None,
        "output_url": None,
        "error": None,
    }


def _valid_evaluation() -> str:
    return (
        '{"scores":[{"url":"https://example.test/fusion",'
        '"relevance":0.9,"recency":0.8,"credibility":0.7}]}'
    )


def _valid_draft() -> str:
    return (
        '{"title":"Fusion update",'
        '"sections":[{"heading":"Progress",'
        '"body":"A reported milestone (https://example.test/fusion).",'
        '"citations":["https://example.test/fusion"]}],'
        '"bibliography":["https://example.test/fusion"],'
        '"gaps":[],"iteration":0}'
    )


class StructuredResponseRetryTests(IsolatedAsyncioTestCase):
    async def test_evaluator_extracts_fenced_json_with_trailing_text(self) -> None:
        llm = QueueLLM(f"Result follows:\n```json\n{_valid_evaluation()}\n```\nDone.")
        with (
            patch("agent.nodes.evaluator.get_llm", return_value=llm),
            patch("agent.nodes.evaluator.publish", new_callable=AsyncMock),
        ):
            result = await run_evaluator(_evaluation_state(), {})

        self.assertEqual(llm.calls, 1)
        scored = result["scored_results"]
        self.assertEqual(len(scored), 1)
        self.assertAlmostEqual(scored[0].relevance, 0.9)

    async def test_evaluator_retries_schema_invalid_response(self) -> None:
        invalid = (
            '{"scores":[{"url":"https://example.test/fusion",'
            '"relevance":"high","recency":0.8,"credibility":0.7}]}'
        )
        llm = QueueLLM(invalid, _valid_evaluation())
        with (
            patch("agent.nodes.evaluator.get_llm", return_value=llm),
            patch("agent.nodes.evaluator.publish", new_callable=AsyncMock),
        ):
            result = await run_evaluator(_evaluation_state(), {})

        self.assertEqual(llm.calls, 2)
        self.assertGreater(llm.message_counts[1], llm.message_counts[0])
        self.assertEqual(len(result["scored_results"]), 1)

    async def test_evaluator_retries_non_object_json_root(self) -> None:
        llm = QueueLLM(f"[{_valid_evaluation()}]", _valid_evaluation())
        with (
            patch("agent.nodes.evaluator.get_llm", return_value=llm),
            patch("agent.nodes.evaluator.publish", new_callable=AsyncMock),
        ):
            result = await run_evaluator(_evaluation_state(), {})

        self.assertEqual(llm.calls, 2)
        self.assertEqual(len(result["scored_results"]), 1)

    async def test_evaluator_retry_exhaustion_is_bounded_and_stage_specific(self) -> None:
        llm = QueueLLM("not JSON", "still not JSON")
        with (
            patch("agent.nodes.evaluator.get_llm", return_value=llm),
            patch("agent.nodes.evaluator.publish", new_callable=AsyncMock),
        ):
            with self.assertRaises(StructuredResponseError) as error:
                await run_evaluator(_evaluation_state(), {})

        self.assertEqual(error.exception.stage, "evaluator")
        self.assertEqual(error.exception.attempts, 2)
        self.assertEqual(llm.calls, 2)

    async def test_synthesizer_recovers_fenced_json_and_trailing_text(self) -> None:
        llm = QueueLLM(f"```json\n{_valid_draft()}\n```\nComplete.")
        with (
            patch("agent.nodes.synthesizer.get_llm", return_value=llm),
            patch("agent.nodes.synthesizer.publish", new_callable=AsyncMock),
        ):
            result = await run_synthesizer(_synthesis_state(), {})

        self.assertEqual(llm.calls, 1)
        self.assertEqual(result["draft"].title, "Fusion update")
        self.assertEqual(result["iteration"], 1)

    async def test_synthesizer_retries_missing_required_field(self) -> None:
        invalid = _valid_draft().replace(',"iteration":0', "")
        llm = QueueLLM(invalid, _valid_draft())
        with (
            patch("agent.nodes.synthesizer.get_llm", return_value=llm),
            patch("agent.nodes.synthesizer.publish", new_callable=AsyncMock),
        ):
            result = await run_synthesizer(_synthesis_state(), {})

        self.assertEqual(llm.calls, 2)
        self.assertEqual(result["draft"].title, "Fusion update")

    async def test_synthesizer_retries_wrong_json_field_type(self) -> None:
        invalid = _valid_draft().replace('"iteration":0', '"iteration":"0"')
        llm = QueueLLM(invalid, _valid_draft())
        with (
            patch("agent.nodes.synthesizer.get_llm", return_value=llm),
            patch("agent.nodes.synthesizer.publish", new_callable=AsyncMock),
        ):
            result = await run_synthesizer(_synthesis_state(), {})

        self.assertEqual(llm.calls, 2)
        self.assertEqual(result["draft"].iteration, 0)

    async def test_synthesizer_retry_exhaustion_is_bounded_and_stage_specific(self) -> None:
        llm = QueueLLM("{}", "[]")
        with (
            patch("agent.nodes.synthesizer.get_llm", return_value=llm),
            patch("agent.nodes.synthesizer.publish", new_callable=AsyncMock),
        ):
            with self.assertRaises(StructuredResponseError) as error:
                await run_synthesizer(_synthesis_state(), {})

        self.assertEqual(error.exception.stage, "synthesizer")
        self.assertEqual(error.exception.attempts, 2)
        self.assertEqual(llm.calls, 2)

    async def test_planner_retains_one_repair_attempt(self) -> None:
        llm = QueueLLM(
            "not JSON",
            '{"sub_queries":[{"text":"fusion energy policy",'
            '"intent":"factual"}]}',
        )
        with (
            patch("agent.nodes.planner.get_llm", return_value=llm),
            patch("agent.nodes.planner.publish", new_callable=AsyncMock),
        ):
            state: AgentState = {
                "question": "What is changing in fusion energy?",
                "mode": "standard",
                "sub_queries": [],
                "search_results": [],
                "scored_results": [],
                "draft": None,
                "iteration": 0,
                "output_url": None,
                "error": None,
            }
            result = await run_planner(state, {})

        self.assertEqual(llm.calls, 2)
        self.assertEqual(result["sub_queries"][0].parent_question, "What is changing in fusion energy?")

    def test_task_returns_useful_failure_after_structured_response_exhaustion(self) -> None:
        error = StructuredResponseError("evaluator", 2)
        with (
            patch("agent.graph.run", new_callable=AsyncMock, side_effect=error),
            patch("tasks._publish_error_sync") as publish_error,
            patch("tasks.logger.exception"),
        ):
            result = run_research.run("What is changing in fusion energy?", "standard")

        self.assertEqual(result["status"], "failed")
        self.assertIn("evaluator", result["error"])
        self.assertIn("2 attempts", result["error"])
        publish_error.assert_called_once_with(None, result["error"])


if __name__ == "__main__":
    import unittest

    unittest.main()
