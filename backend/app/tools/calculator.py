"""Safe arithmetic calculator tool.

Deliberately does NOT use ``eval()`` - it walks a restricted AST so the
Analysis Agent can compute numbers from LLM-provided expressions without
exposing arbitrary code execution (section 15, "LLM safety").
"""
from __future__ import annotations

import ast
import math
import operator
from typing import Any

_BINARY_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_ALLOWED_FUNCS: dict[str, Any] = {
    "abs": abs,
    "round": round,
    "min": min,
    "max": max,
    "sum": sum,
    "sqrt": math.sqrt,
    "log": math.log,
    "log10": math.log10,
    "exp": math.exp,
    "pow": math.pow,
}
_ALLOWED_NAMES: dict[str, Any] = {"pi": math.pi, "e": math.e}

MAX_EXPRESSION_LENGTH = 500


class UnsafeExpressionError(ValueError):
    pass


def calculate(expression: str) -> float:
    """Evaluates a restricted arithmetic expression and returns a float result."""
    if len(expression) > MAX_EXPRESSION_LENGTH:
        raise UnsafeExpressionError("Expression too long")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise UnsafeExpressionError(f"Invalid expression: {exc}") from exc
    return _eval_node(tree.body)


def _eval_node(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise UnsafeExpressionError(f"Unsupported constant: {node.value!r}")
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPS:
        return _BINARY_OPS[type(node.op)](_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval_node(node.operand))
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _ALLOWED_FUNCS:
            raise UnsafeExpressionError("Function not allowed")
        args = [_eval_node(arg) for arg in node.args]
        return _ALLOWED_FUNCS[node.func.id](*args)
    if isinstance(node, ast.Name):
        if node.id in _ALLOWED_NAMES:
            return _ALLOWED_NAMES[node.id]
        raise UnsafeExpressionError(f"Unknown identifier: {node.id}")
    raise UnsafeExpressionError(f"Disallowed expression element: {type(node).__name__}")


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": "Evaluate a safe arithmetic expression (numbers, + - * / // % **, sqrt/log/exp/round/min/max/sum).",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "The arithmetic expression to evaluate"},
            },
            "required": ["expression"],
        },
    },
}


async def run(expression: str) -> dict[str, Any]:
    try:
        return {"result": calculate(expression)}
    except UnsafeExpressionError as exc:
        return {"error": str(exc)}
