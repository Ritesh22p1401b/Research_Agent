"""Custom-protocol client for the remote Qwen3 inference endpoint.

The LLM runs on Google Colab as a plain ``transformers``-based FastAPI
wrapper (NOT vLLM's OpenAI-compatible server), exposed through an ngrok
HTTPS tunnel. Its only endpoints are:

    GET  /health
    POST /generate  {"prompt": str, "max_new_tokens": int, "temperature": float,
                      "top_p": float, "do_sample": bool}
                  -> {"model": str, "response": str}

There is no chat-message format, no native tool-calling and no JSON
response-format support at the API level - ``/generate`` always wraps
whatever prompt string it receives as a single user turn via the
tokenizer's chat template server-side. This module is the ONLY place that
talks to that endpoint directly, and it emulates everything the rest of
the app expects from an OpenAI-style client so no other module has to
know the difference:

- multi-turn history / system prompts / tool results -> flattened into one
  prompt string (``_flatten_messages``).
- tool-calling -> the flattened prompt describes the available tools and
  asks the model to reply with ``{"tool_call": {"name": ..., "arguments": {}}}``
  JSON when it wants to call one; that's parsed back out of the raw text
  response into the same ``tool_calls`` shape an OpenAI response would
  have had (``_extract_tool_call``), so ``app/agents/base.py``'s ReAct loop
  needs zero changes.
- structured JSON answers -> already tolerated leniently by ``chat_json``'s
  ``_parse_json_loose`` fallback, so no API-level ``response_format`` is
  needed; callers already just ask for JSON in the prompt text.

Every other module (agents, routes, evaluation) goes through ``LLMClient``
so the model/endpoint/protocol can change again without touching the rest
of the app.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger
from app.llm.config import get_llm_settings

logger = get_logger(__name__)

RETRYABLE_EXCEPTIONS = (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)


class LLMUnavailableError(RuntimeError):
    """The Colab/ngrok LLM endpoint is offline. Not retried - retrying an offline tunnel only wastes time."""


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, LLMUnavailableError):
        return False
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500 or exc.response.status_code == 429
    return isinstance(exc, (httpx.ConnectError, httpx.TimeoutException))


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
    """Thin async wrapper around the custom Qwen3 ``/generate`` endpoint."""

    def __init__(self) -> None:
        self._settings = get_llm_settings()
        self._client = httpx.AsyncClient(
            base_url=self._settings.base_url.rstrip("/"),
            timeout=self._settings.timeout_seconds,
        )
        self._concurrency = max(1, get_settings().llm_max_concurrency)
        self._semaphore: asyncio.Semaphore | None = None

    @property
    def model(self) -> str:
        return self._settings.model

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_should_retry),
    )
    async def _call_generate(self, prompt: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._concurrency)
        async with self._semaphore:
            return await self._post_generate(prompt, temperature, max_tokens)

    async def _post_generate(self, prompt: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        response = await self._client.post(
            "/generate",
            json={
                "prompt": prompt,
                "max_new_tokens": max_tokens,
                # The server's transformers.generate() call divides by temperature
                # when do_sample=True, so avoid sending an exact 0.
                "temperature": max(temperature, 0.01),
                "top_p": self._settings.top_p,
                "do_sample": temperature > 0,
            },
        )
        if response.status_code == 404 and response.headers.get("ngrok-error-code"):
            raise LLMUnavailableError(
                "The LLM is offline: the ngrok tunnel "
                f"({self._settings.base_url}) is not connected to a running Colab server. "
                "Re-run the Colab notebook and update LLM_BASE_URL in backend/.env if the URL changed."
            )
        response.raise_for_status()
        return response.json()

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResult:
        """Sends a "chat completion" and normalizes the response.

        ``tool_choice`` and ``response_format`` are accepted only for
        interface compatibility with callers written against an
        OpenAI-style client - this server has no such options. JSON output
        is requested in the prompt text instead (see ``chat_json``) and
        tool-calling is emulated entirely through prompt text (see the
        module docstring).
        """
        use_tools = tools if tools and self._settings.supports_tool_calling else None
        prompt = _flatten_messages(messages, use_tools)
        resolved_temperature = temperature if temperature is not None else self._settings.temperature
        resolved_max_tokens = max_tokens if max_tokens is not None else self._settings.max_tokens

        start = time.perf_counter()
        try:
            data = await self._call_generate(prompt, resolved_temperature, resolved_max_tokens)
        except (*RETRYABLE_EXCEPTIONS, LLMUnavailableError):
            logger.error("LLM request failed against %s", self._settings.base_url)
            raise
        latency_ms = (time.perf_counter() - start) * 1000

        raw_text = str(data.get("response", ""))
        tool_call = _extract_tool_call(raw_text) if use_tools else None
        if tool_call:
            return LLMResult(
                content="",
                tool_calls=[
                    {
                        "id": f"call_{uuid.uuid4().hex[:8]}",
                        "name": tool_call["name"],
                        "arguments": json.dumps(tool_call.get("arguments", {})),
                    }
                ],
                usage=LLMUsage(),
                latency_ms=latency_ms,
            )
        return LLMResult(content=raw_text, tool_calls=[], usage=LLMUsage(), latency_ms=latency_ms)

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any], LLMResult]:
        """Requests a JSON object response and parses it defensively.

        There's no ``response_format`` support on this server, so callers
        already ask for JSON in the prompt text and we fall back to
        extracting the first ``{...}`` block if strict parsing fails.
        """
        result = await self.chat(messages=messages, temperature=temperature, max_tokens=max_tokens)
        parsed = _parse_json_loose(result.content)
        return parsed, result

    async def health_check(self) -> bool:
        """Cheap connectivity probe used by GET /health - hits the server's
        own lightweight ``/health`` route rather than running a generation."""
        try:
            response = await self._client.get("/health", timeout=10)
            return response.status_code == 200
        except Exception:
            logger.warning("LLM health check failed", exc_info=True)
            return False


def _flatten_messages(messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None) -> str:
    """Collapses an OpenAI-style message list into one prompt string.

    The remote server always wraps whatever we send as a single user turn,
    so system prompts, prior turns and tool-call history all have to be
    flattened into readable text here instead of sent as separate messages.
    """
    parts: list[str] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            parts.append(f"# Instructions\n{msg.get('content', '')}")
        elif role == "user":
            parts.append(f"# User\n{msg.get('content', '')}")
        elif role == "assistant":
            if msg.get("tool_calls"):
                calls = "; ".join(
                    f"called `{tc['function']['name']}` with arguments {tc['function']['arguments']}"
                    for tc in msg["tool_calls"]
                )
                parts.append(f"# Assistant\n{calls}")
            elif msg.get("content"):
                parts.append(f"# Assistant\n{msg['content']}")
        elif role == "tool":
            parts.append(f"# Tool result\n{msg.get('content', '')}")
    if tools:
        parts.append(_tool_instructions(tools))
    parts.append("# Assistant\n")
    return "\n\n".join(parts)


def _tool_instructions(tools: list[dict[str, Any]]) -> str:
    lines = ["You also have access to the following tools:"]
    for tool in tools:
        fn = tool["function"]
        lines.append(f"- {fn['name']}: {fn['description']} Arguments schema: {json.dumps(fn['parameters'])}")
    lines.append(
        "To call ONE tool, respond with a JSON object ONLY of this exact form:\n"
        '{"tool_call": {"name": "<tool name>", "arguments": {...}}}\n'
        "Do not include any other text alongside it.\n"
        "If you already have enough information, skip the tool call and respond "
        "with your final answer instead, in whatever format was requested above."
    )
    return "\n".join(lines)


def _extract_tool_call(text: str) -> dict[str, Any] | None:
    parsed = _parse_json_loose(text)
    call = parsed.get("tool_call") if isinstance(parsed, dict) else None
    if isinstance(call, dict) and call.get("name"):
        return call
    return None


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
