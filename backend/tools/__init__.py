"""Application services and adapters around the pure calculation core.

Historically this package held everything, including the calculation itself.
The deterministic engine has since moved to `domain/calculation/`, where the
absence of I/O is enforced by `tests/test_architecture.py` rather than assumed.

What remains here legitimately touches the outside world or orchestrates
several domain calls: rule-pack loading, source adapters, reference dataset
runners, portfolio assembly, simulation.

Tools are plain Python callables. The Agent Framework wraps them as
`FunctionTool` when passed via `Agent(tools=[...])`. A tool's return value is
what the model sees, so it should stay short and JSON-friendly; the structured
`calculation_trail` the UI renders lives in a separate `TrailRecorder` (a
ContextVar) so formula bookkeeping never enters the model's context.

`TrailRecorder` is re-exported here so existing imports keep working, but it
now *lives* in the domain — a derivation record is part of what the
calculation means, not a service wrapped around it.
"""
from domain.calculation.trail import (
    TrailRecorder,
    current_recorder,
    reset_recorder,
    set_recorder,
)

__all__ = ["TrailRecorder", "current_recorder", "set_recorder", "reset_recorder"]
