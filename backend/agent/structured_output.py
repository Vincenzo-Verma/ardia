"""Shared extraction, validation, and bounded retry for LLM JSON responses."""

from __future__ import annotations

import json
from typing import Any, Protocol, TypeVar

from langchain_core.messages import BaseMessage, HumanMessage
from pydantic import BaseModel, ValidationError

ResponseT = TypeVar("ResponseT", bound=BaseModel)


class StructuredLLM(Protocol):
    async def ainvoke(self, messages: list[BaseMessage]) -> BaseMessage: ...


class StructuredResponseError(RuntimeError):
    """Raised when an LLM cannot produce a valid response within the retry bound."""

    def __init__(self, stage: str, attempts: int) -> None:
        self.stage = stage
        self.attempts = attempts
        super().__init__(f"The {stage} could not produce a valid response after {attempts} attempts.")


def _decode_json_object(raw: str) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise ValueError("response content must be text")

    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        decoder = json.JSONDecoder()
        start = raw.find("{")
        if start < 0:
            raise ValueError("response did not contain a JSON object")
        try:
            value, _ = decoder.raw_decode(raw, start)
        except json.JSONDecodeError as error:
            raise ValueError("response did not contain a valid JSON object") from error

    if isinstance(value, dict):
        return value

    raise ValueError("response root must be a JSON object")


def _validation_feedback(error: Exception) -> str:
    if isinstance(error, ValidationError):
        details = error.errors(include_input=False)
        messages = [
            f"{'.'.join(str(part) for part in detail['loc'])}: {detail['msg']}"
            for detail in details[:8]
        ]
        if messages:
            return "; ".join(messages)
    return "response did not contain a valid JSON object matching the required schema"


async def invoke_structured(
    llm: StructuredLLM,
    messages: list[BaseMessage],
    response_model: type[ResponseT],
    stage: str,
    max_attempts: int = 2,
) -> ResponseT:
    """Invoke an LLM and validate its first JSON object, retrying invalid output once."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least one")

    conversation = list(messages)
    for attempt in range(1, max_attempts + 1):
        response = await llm.ainvoke(conversation)
        try:
            if not isinstance(response.content, str):
                raise ValueError("response content must be text")
            payload = _decode_json_object(response.content)
            return response_model.model_validate(payload, strict=True)
        except (ValueError, ValidationError) as error:
            if attempt == max_attempts:
                raise StructuredResponseError(stage, max_attempts) from error
            feedback = _validation_feedback(error)
            conversation.extend(
                [
                    response,
                    HumanMessage(
                        content=(
                            f"Your previous response was invalid: {feedback}. "
                            "Return only a valid JSON object matching the requested schema."
                        )
                    ),
                ]
            )

    raise AssertionError("bounded response loop exited unexpectedly")
