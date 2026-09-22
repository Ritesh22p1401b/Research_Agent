"""Guardrail primitives shared across agents, tools and MCP servers.

See agentic-research-intelligence-platform.md section 15 ("Guardrails"):
tool limits, database safety, LLM safety and agent safety.
"""
from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class GuardrailError(Exception):
    """Base class for all guardrail violations."""


class MaxStepsExceeded(GuardrailError):
    def __init__(self, limit: int):
        super().__init__(f"Agent workflow exceeded the maximum of {limit} steps")


class MaxToolCallsExceeded(GuardrailError):
    def __init__(self, limit: int):
        super().__init__(f"Exceeded the maximum of {limit} tool calls for this request")


class ToolTimeoutError(GuardrailError):
    def __init__(self, tool_name: str, timeout: float):
        super().__init__(f"Tool '{tool_name}' timed out after {timeout}s")


class UnsafeSQLError(GuardrailError):
    """Raised when the database tool receives a non-SELECT or disallowed query."""


class StepBudget:
    """Tracks agent steps / tool calls / retries for a single request run."""

    def __init__(self, max_steps: int, max_tool_calls: int, max_retries: int):
        self.max_steps = max_steps
        self.max_tool_calls = max_tool_calls
        self.max_retries = max_retries
        self.steps = 0
        self.tool_calls = 0
        self.retries = 0
        self.llm_calls = 0
        self.started_at = time.monotonic()

    def take_step(self) -> None:
        self.steps += 1
        if self.steps > self.max_steps:
            raise MaxStepsExceeded(self.max_steps)

    def take_tool_call(self) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            raise MaxToolCallsExceeded(self.max_tool_calls)

    def take_retry(self) -> bool:
        """Returns True if another retry is allowed."""
        if self.retries >= self.max_retries:
            return False
        self.retries += 1
        return True

    def record_llm_call(self) -> None:
        self.llm_calls += 1

    @property
    def elapsed_ms(self) -> float:
        return (time.monotonic() - self.started_at) * 1000


async def run_with_timeout(
    coro_fn: Callable[..., Awaitable[T]],
    *args,
    timeout: float,
    tool_name: str = "tool",
    **kwargs,
) -> T:
    """Runs an async callable under a hard timeout guardrail."""
    try:
        return await asyncio.wait_for(coro_fn(*args, **kwargs), timeout=timeout)
    except asyncio.TimeoutError as exc:
        logger.warning("Tool timeout: %s exceeded %.1fs", tool_name, timeout)
        raise ToolTimeoutError(tool_name, timeout) from exc
