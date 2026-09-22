"""Langfuse tracing wrapper (agentic-research-intelligence-platform.md, section 17).

Degrades to a no-op when LANGFUSE_ENABLED is false or credentials are
missing, so the app runs fine without an observability backend configured.
"""
from __future__ import annotations

import functools
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any, TypeVar

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])

_langfuse_client = None
_ENABLED = False


def _init() -> None:
    global _langfuse_client, _ENABLED
    settings = get_settings()
    if not settings.langfuse_enabled or not settings.langfuse_public_key or not settings.langfuse_secret_key:
        _ENABLED = False
        return
    try:
        from langfuse import Langfuse

        _langfuse_client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        _ENABLED = True
        logger.info("Langfuse observability enabled (host=%s)", settings.langfuse_host)
    except Exception:  # noqa: BLE001
        logger.warning("Langfuse init failed, falling back to no-op tracing", exc_info=True)
        _ENABLED = False


_init()


def is_enabled() -> bool:
    return _ENABLED


@contextmanager
def trace_span(name: str, **metadata: Any):
    """Context manager that records a span's duration and metadata.

    Usage:
        with trace_span("research_agent", query=query) as span:
            ...
            span["tool_calls"] = 3
    """
    start = time.perf_counter()
    data: dict[str, Any] = dict(metadata)
    try:
        yield data
    finally:
        data["duration_ms"] = (time.perf_counter() - start) * 1000
        if _ENABLED and _langfuse_client is not None:
            try:
                _langfuse_client.event(name=name, metadata=data)
            except Exception:  # noqa: BLE001
                logger.debug("Langfuse event emit failed", exc_info=True)
        else:
            logger.debug("trace[%s] %s", name, data)


def observe(name: str | None = None) -> Callable[[F], F]:
    """Decorator variant of trace_span for sync/async functions."""

    def decorator(func: F) -> F:
        span_name = name or func.__name__

        if _is_coroutine_function(func):

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                with trace_span(span_name):
                    return await func(*args, **kwargs)

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            with trace_span(span_name):
                return func(*args, **kwargs)

        return sync_wrapper  # type: ignore[return-value]

    return decorator


def _is_coroutine_function(func: Callable[..., Any]) -> bool:
    import inspect

    return inspect.iscoroutinefunction(func)


def flush() -> None:
    if _ENABLED and _langfuse_client is not None:
        try:
            _langfuse_client.flush()
        except Exception:  # noqa: BLE001
            logger.debug("Langfuse flush failed", exc_info=True)
