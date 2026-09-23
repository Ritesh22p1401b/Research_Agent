"""Shared agent helpers: a generic tool-calling (ReAct-style) loop and a
structured-JSON call helper, both built on top of ``LLMClient``.

Every concrete agent (research/analysis/critic/report) is a thin prompt +
tool-selection layer over these two primitives, so guardrails (max steps,
max tool calls, timeouts) are enforced in exactly one place.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.guardrails import StepBudget, run_with_timeout
from app.core.logging import get_logger
from app.llm.client import LLMResult, get_llm_client
from app.tools.registry import get_tool_function, get_tool_schemas

logger = get_logger(__name__)


@dataclass
class ToolTrace:
    name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


@dataclass
class AgentRunResult:
    content: str
    tool_traces: list[ToolTrace] = field(default_factory=list)


async def run_agent_with_tools(
    system_prompt: str,
    user_prompt: str,
    tool_names: list[str],
    budget: StepBudget,
    tool_timeout_seconds: float,
    max_tool_iterations: int = 4,
) -> AgentRunResult:
    """Runs a bounded ReAct-style loop: LLM -> (tool calls)* -> final answer."""
    client = get_llm_client()
    tool_schemas = get_tool_schemas(tool_names)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    traces: list[ToolTrace] = []

    for _ in range(max_tool_iterations):
        budget.take_step()
        result: LLMResult = await client.chat(messages=messages, tools=tool_schemas)
        budget.record_llm_call()

        if not result.tool_calls:
            return AgentRunResult(content=result.content, tool_traces=traces)

        messages.append(
            {
                "role": "assistant",
                "content": result.content or None,
                "tool_calls": [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                    for tc in result.tool_calls
                ],
            }
        )

        for tool_call in result.tool_calls:
            budget.take_tool_call()
            tool_result = await _execute_tool(tool_call, tool_timeout_seconds)
            traces.append(ToolTrace(name=tool_call["name"], arguments=_safe_args(tool_call), result=tool_result))
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(tool_result)[:8000],
                }
            )

    # Final forced answer without further tool calls once the loop budget is spent.
    budget.take_step()
    final = await client.chat(messages=messages, tools=None)
    budget.record_llm_call()
    return AgentRunResult(content=final.content, tool_traces=traces)


async def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    budget: StepBudget,
    max_tokens: int | None = None,
) -> tuple[dict[str, Any], LLMResult]:
    """Single structured-output LLM call (used by Critic/Report agents)."""
    client = get_llm_client()
    budget.take_step()
    parsed, result = await client.chat_json(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=max_tokens,
    )
    budget.record_llm_call()
    return parsed, result


async def _execute_tool(tool_call: dict[str, Any], timeout: float) -> dict[str, Any]:
    name = tool_call["name"]
    func = get_tool_function(name)
    if func is None:
        return {"error": f"Unknown tool: {name}"}
    try:
        args = json.loads(tool_call["arguments"] or "{}")
    except json.JSONDecodeError:
        return {"error": "Invalid tool arguments JSON"}

    try:
        return await run_with_timeout(func, timeout=timeout, tool_name=name, **args)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Tool '%s' raised: %s", name, exc)
        return {"error": str(exc)}


def _safe_args(tool_call: dict[str, Any]) -> dict[str, Any]:
    try:
        return json.loads(tool_call["arguments"] or "{}")
    except json.JSONDecodeError:
        return {}
