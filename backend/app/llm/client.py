"""OpenAI-compatible client for the remote Qwen3 inference endpoint.

The LLM runs on Google Colab (vLLM) and is exposed through an ngrok HTTPS
tunnel (see agentic-research-intelligence-platform.md, sections 2 and 12-13).
This module is the ONLY place that talks to that endpoint directly - every
other module (agents, routes, evaluation) goes through ``LLMClient`` so the
model / endpoint can change without touching the rest of the app.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.logging import get_logger
from app.llm.config import get_llm_settings

logger = get_logger(__name__)

RETRYABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, APIStatusError)


@dataclass
class LLMUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class LLMResult:
    content: str
    reasoning_content: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: float = 0.0
    raw_finish_reason: str | None = None


class LLMClient:
    """Thin async wrapper around the OpenAI-compatible Qwen3 endpoint."""

    def __init__(self) -> None:
        self._settings = get_llm_settings()
        self._client = AsyncOpenAI(
            api_key=self._settings.api_key or "EMPTY",
            base_url=self._settings.base_url,
            timeout=self._settings.timeout_seconds,
            max_retries=0,  # we handle retries ourselves via tenacity for visibility/metrics
        )

    @property
    def model(self) -> str:
        return self._settings.model

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
    )
    async def _create_completion(self, **kwargs: Any):
        return await self._client.chat.completions.create(**kwargs)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResult:
        """Sends a chat completion request and normalizes the response."""
        kwargs: dict[str, Any] = {
            "model": self._settings.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self._settings.temperature,
            "max_tokens": max_tokens if max_tokens is not None else self._settings.max_tokens,
        }
        if tools and self._settings.supports_tool_calling:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = tool_choice or "auto"
        if response_format:
            kwargs["response_format"] = response_format

        start = time.perf_counter()
        try:
            completion = await self._create_completion(**kwargs)
        except RETRYABLE_EXCEPTIONS:
            logger.exception("LLM request failed after retries against %s", self._settings.base_url)
            raise
        latency_ms = (time.perf_counter() - start) * 1000

        choice = completion.choices[0]
        message = choice.message
        usage = completion.usage
        tool_calls = []
        for tc in message.tool_calls or []:
            tool_calls.append(
                {
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                }
            )

        reasoning_content = getattr(message, "reasoning_content", None)

        return LLMResult(
            content=message.content or "",
            reasoning_content=reasoning_content,
            tool_calls=tool_calls,
            usage=LLMUsage(
                input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                output_tokens=getattr(usage, "completion_tokens", 0) or 0,
                total_tokens=getattr(usage, "total_tokens", 0) or 0,
            ),
            latency_ms=latency_ms,
            raw_finish_reason=choice.finish_reason,
        )

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any], LLMResult]:
        """Requests a JSON object response and parses it defensively.

        Not every vLLM build honors ``response_format={"type": "json_object"}``
        for every model, so we always ask for JSON in the prompt too and fall
        back to extracting the first ``{...}`` block if strict parsing fails.
        """
        result = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        parsed = _parse_json_loose(result.content)
        return parsed, result

    async def health_check(self) -> bool:
        """Cheap connectivity probe used by GET /health."""
        try:
            await self.chat(
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=4,
            )
            return True
        except Exception:  # noqa: BLE001 - health check must never raise
            logger.warning("LLM health check failed", exc_info=True)
            return False


def _parse_json_loose(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from LLM response: %s", text[:300])
    return {}


_client_singleton: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = LLMClient()
    return _client_singleton
