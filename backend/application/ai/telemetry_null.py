"""The do-nothing telemetry adapter. [AI-04]

Resilience code reports retries, breaker openings and refusals through the
`AiTelemetry` port. Until a real adapter is composed (the OpenTelemetry one, AI-06)
this satisfies the port, so no caller ever checks for `None`.
"""
from __future__ import annotations

from typing import Any

from domain.ai import ModelRole, ModelUsage


class NullSpan:
    def finish(
        self, *, outcome: str, usage: ModelUsage | None = None, finish_reason: str | None = None,
        error_type: str | None = None, **attributes: Any,
    ) -> None:
        return None


class NullTelemetry:
    def start_call(self, *, role: ModelRole, provider: str, model: str | None, agent: str) -> NullSpan:
        return NullSpan()

    def count(self, metric: str, value: float = 1, **attributes: Any) -> None:
        return None
