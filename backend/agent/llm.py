"""LangChain-compatible chat model using HuggingFace chat_completion.

Uses the HuggingFace Inference API chat_completion endpoint (task=conversational),
which works for any provider-hosted instruct model (including featherless-ai).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, List, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from config import settings


def _to_hf_messages(messages: List[BaseMessage]) -> list[dict]:
    """Convert LangChain messages to the HuggingFace chat format."""
    role_map = {"human": "user", "ai": "assistant", "system": "system"}
    return [{"role": role_map.get(m.type, "user"), "content": m.content} for m in messages]


class _HFChatModel(BaseChatModel):
    """Calls HuggingFace chat_completion and wraps the output as an AIMessage."""

    model: str
    api_key: str
    max_new_tokens: int = 1024
    temperature: float = Field(default=0.1)

    @property
    def _llm_type(self) -> str:
        return "huggingface-chat-completion"

    provider: str | None = None

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Synchronous chat completion."""
        from huggingface_hub import InferenceClient

        client = InferenceClient(api_key=self.api_key, provider=self.provider)
        response = client.chat_completion(
            messages=_to_hf_messages(messages),
            model=self.model,
            max_tokens=self.max_new_tokens,
            temperature=self.temperature,
        )
        text = response.choices[0].message.content
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    async def _agenerate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        """Asynchronous chat completion."""
        from huggingface_hub import AsyncInferenceClient

        client = AsyncInferenceClient(api_key=self.api_key, provider=self.provider)
        response = await client.chat_completion(
            messages=_to_hf_messages(messages),
            model=self.model,
            max_tokens=self.max_new_tokens,
            temperature=self.temperature,
        )
        text = response.choices[0].message.content
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])


@lru_cache(maxsize=8)
def get_llm(max_new_tokens: int = 1024) -> BaseChatModel:
    """Return a cached chat-completion LLM for the configured HuggingFace model."""
    return _HFChatModel(
        model=settings.llm_model,
        api_key=settings.huggingface_api_key,
        provider=settings.llm_provider,
        max_new_tokens=max_new_tokens,
    )
