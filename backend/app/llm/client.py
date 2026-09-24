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
from collections.abc import AsyncIterator
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
        app_settings = get_settings()
        self._client = httpx.AsyncClient(
            base_url=self._settings.base_url.rstrip("/"),
            # Long read timeout (a generation can take a while) but fail fast when the tunnel is unreachable.
            timeout=httpx.Timeout(self._settings.timeout_seconds, connect=10.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16, keepalive_expiry=120.0),
            headers={"ngrok-skip-browser-warning": "1"},
        )
        self._configured_style = (app_settings.llm_api_style or "auto").lower()
        self._style: str | None = None if self._configured_style == "auto" else self._configured_style
        self._app_settings = app_settings
        self._semaphore: asyncio.Semaphore | None = None
        # Circuit breaker + cached health (kept fresh by the background heartbeat).
        self._down_until = 0.0
        self._failures = 0
        self._healthy: bool | None = None
        self._healthy_at = 0.0

    @property
    def model(self) -> str:
        return self._settings.model

    # -- connection state -----------------------------------------------------------------------
    def _open_circuit(self) -> None:
        self._failures += 1
        if self._failures >= 2:
            self._down_until = time.monotonic() + self._app_settings.llm_circuit_cooldown_seconds
            self._healthy = False

    def _record_success(self) -> None:
        self._failures = 0
        self._down_until = 0.0
        self._healthy, self._healthy_at = True, time.monotonic()

    def _check_circuit(self) -> None:
        if time.monotonic() < self._down_until:
            raise LLMUnavailableError(
                f"The LLM at {self._settings.base_url} is not responding (retrying automatically in a few seconds). "
                "Start/restart the Colab server and update LLM_BASE_URL in backend/.env if the URL changed."
            )

    async def _resolve_style(self) -> str:
        """'openai' (vLLM) or 'generate' (the old transformers wrapper); auto-detected once via /v1/models."""
        if self._style:
            return self._style
        try:
            response = await self._client.get("/v1/models", timeout=10)
        except Exception as exc:  # noqa: BLE001
            raise LLMUnavailableError(f"Cannot reach the LLM at {self._settings.base_url}: {exc}") from exc
        if response.headers.get("ngrok-error-code"):
            raise LLMUnavailableError(_offline_message(self._settings.base_url))
        self._style = "openai" if response.status_code == 200 else "generate"
        logger.info("LLM API style detected: %s", self._style)
        return self._style

    def _concurrency_limit(self, style: str) -> int:
        s = self._app_settings
        return max(1, s.llm_max_concurrency_vllm if style == "openai" else s.llm_max_concurrency)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        retry=retry_if_exception(_should_retry),
    )
    async def _call_generate(self, prompt: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        """Sends one prompt; returns {"response": str, "usage": {...}} whatever the server flavour."""
        self._check_circuit()
        style = await self._resolve_style()
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._concurrency_limit(style))
        async with self._semaphore:
            try:
                if style == "openai":
                    data = await self._post_openai(prompt, temperature, max_tokens)
                else:
                    data = await self._post_generate(prompt, temperature, max_tokens)
            except LLMUnavailableError:
                self._failures = 2
                self._open_circuit()
                raise
            except (httpx.ConnectError, httpx.TimeoutException):
                self._open_circuit()
                raise
        self._record_success()
        return data

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code >= 400 and response.headers.get("ngrok-error-code"):
            raise LLMUnavailableError(_offline_message(self._settings.base_url))
        response.raise_for_status()

    async def _post_openai(self, prompt: str, temperature: float, max_tokens: int) -> dict[str, Any]:
        response = await self._client.post("/v1/chat/completions", json=self._openai_body(prompt, temperature, max_tokens))
        self._raise_for_status(response)
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        content = (choice.get("message") or {}).get("content") or ""
        return {"response": content, "usage": data.get("usage") or {}}

    def _openai_body(self, prompt: str, temperature: float, max_tokens: int, stream: bool = False) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._settings.model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": self._settings.top_p,
            # Qwen3 would otherwise spend tokens on a <think> block; the agents want the answer only.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if stream:
            body["stream"] = True
        return body

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
        self._raise_for_status(response)
        return response.json()

    async def stream_text(
        self, messages: list[dict[str, Any]], temperature: float | None = None, max_tokens: int | None = None
    ) -> AsyncIterator[str]:
        """Yields the reply token-by-token (vLLM). On the old /generate server the full text arrives as one chunk."""
        self._check_circuit()
        prompt = _flatten_messages(messages, None)
        temp = temperature if temperature is not None else self._settings.temperature
        limit = max_tokens if max_tokens is not None else self._settings.max_tokens
        if await self._resolve_style() != "openai":
            yield (await self._call_generate(prompt, temp, limit)).get("response", "")
            return
        async with self._client.stream(
            "POST", "/v1/chat/completions", json=self._openai_body(prompt, temp, limit, stream=True)
        ) as response:
            if response.status_code >= 400:
                await response.aread()
                self._raise_for_status(response)
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                try:
                    delta = (json.loads(payload).get("choices") or [{}])[0].get("delta", {}).get("content")
                except ValueError:
                    continue
                if delta:
                    yield delta
        self._record_success()

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
                usage=_usage(data),
                latency_ms=latency_ms,
            )
        return LLMResult(content=raw_text, tool_calls=[], usage=_usage(data), latency_ms=latency_ms)

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
        """Cheap connectivity probe (server's own /health route, no generation). Also refreshes the cached state."""
        try:
            response = await self._client.get("/health", timeout=10)
            ok = response.status_code == 200 and not response.headers.get("ngrok-error-code")
        except Exception:
            logger.debug("LLM health check failed", exc_info=True)
            ok = False
        self._healthy, self._healthy_at = ok, time.monotonic()
        if ok:
            self._down_until, self._failures = 0.0, 0
        return ok

    async def ensure_available(self, max_age: float = 15.0) -> None:
        """Preflight: raises LLMUnavailableError in ~1s if the server is down (instead of failing mid-run)."""
        if self._healthy and time.monotonic() - self._healthy_at < max_age:
            return
        if not await self.health_check():
            raise LLMUnavailableError(_offline_message(self._settings.base_url))

    async def heartbeat(self, interval: float) -> None:
        """Background loop: keeps the tunnel warm and the cached health fresh."""
        while True:
            await self.health_check()
            await asyncio.sleep(interval)


def _offline_message(base_url: str) -> str:
    return (
        f"The LLM is offline: the ngrok tunnel ({base_url}) is not connected to a running Colab server. "
        "Re-run the Colab notebook and update LLM_BASE_URL in backend/.env if the URL changed."
    )


def _usage(data: dict[str, Any]) -> LLMUsage:
    u = data.get("usage") or {}
    inp, out = int(u.get("prompt_tokens", 0) or 0), int(u.get("completion_tokens", 0) or 0)
    return LLMUsage(input_tokens=inp, output_tokens=out, total_tokens=int(u.get("total_tokens", inp + out) or 0))


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
