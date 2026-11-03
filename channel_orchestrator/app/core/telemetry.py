"""Spans per tool call, carrying no payroll. [CH-08]

OpenTelemetry through the hosting adapter's configured provider (the Foundry runtime wires Application
Insights); with no provider these are no-ops. A span names the tool, its kind and its outcome, the channel
and the correlation id, and that is all: never an argument, a fact, a client name, a figure or a message,
because a trace store is read by people and by tools that were never cleared for payroll.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

try:  # the API package is a dependency of the hosting adapter; its absence must not stop an answer
    from opentelemetry import trace as _trace
except ImportError:  # pragma: no cover - exercised only where the package is absent
    _trace = None

_tracer: Any = None


def set_tracer(tracer: Any) -> None:
    """Use `tracer` for this process (a test's, or an explicitly configured one)."""
    global _tracer
    _tracer = tracer


def _active() -> Any:
    if _tracer is not None:
        return _tracer
    return _trace.get_tracer("tcc.orchestrator") if _trace is not None else None


class _NoSpan:
    def set_attribute(self, *_a: Any, **_k: Any) -> None:
        return None


@contextmanager
def tool_span(tool: str, kind: str, channel: str, correlation_id: str) -> Iterator[Any]:
    """A span around one tool call. Set `tcc.outcome` and `tcc.error_code` on it when the call ends."""
    tracer = _active()
    if tracer is None:
        yield _NoSpan()
        return
    with tracer.start_as_current_span(f"tcc.tool.{tool}") as span:
        for name, value in (("tcc.tool", tool), ("tcc.tool.kind", kind), ("tcc.channel", channel), ("tcc.correlation_id", correlation_id)):
            span.set_attribute(name, value)
        yield span
