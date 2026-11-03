"""Observe every model call, outside everything else. [AI-06]

The outermost decorator on a provider, so a call is seen whatever stopped it: an
egress refusal, a spent budget, an open breaker, a timeout. The span records the
call's SHAPE only (see `infrastructure/ai/otel_telemetry.py` for what is never
recorded): lengths and token counts, never text.

Outcomes: `ok`, `error` (with the exception CLASS name as `error.type`), `cancelled`
(the reader went away) and `abandoned` (the consumer stopped reading before the end).
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from application.ai.ports import AgentRuntime, AiTelemetry
from domain.ai import AgentSpec, ModelEvent, ModelUsage, ProviderStatus, StreamEnd, TextDelta


class ObservedRuntime:
    """Wraps a provider so every call produces one span, whatever stopped it."""

    def __init__(self, inner: AgentRuntime, telemetry: AiTelemetry) -> None:
        self._inner, self._telemetry = inner, telemetry
        self.name = inner.name

    def ready_for(self, agent_name: str) -> bool:
        return self._inner.ready_for(agent_name)

    def version_of(self, agent_name: str) -> str | None:
        return self._inner.version_of(agent_name)

    def status(self) -> ProviderStatus:
        return self._inner.status()

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        """Pass events through unchanged, and end one span with how the call finished."""
        span = self._telemetry.start_call(role=spec.role, provider=self.name, model=None, agent=spec.name)
        outcome, error_type = "abandoned", None
        usage: ModelUsage | None = None
        end: StreamEnd | None = None
        out_chars = 0
        try:
            async for event in self._inner.stream(spec, prompt):
                if isinstance(event, TextDelta):
                    out_chars += len(event.text)
                elif isinstance(event, ModelUsage):
                    usage = event
                elif isinstance(event, StreamEnd):
                    end = event
                yield event
            outcome = "ok"
        except asyncio.CancelledError:
            outcome = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - recorded by class name, then re-raised unchanged
            outcome, error_type = "error", type(exc).__name__
            raise
        finally:
            span.finish(
                outcome=outcome, usage=usage, finish_reason=getattr(end, "finish_reason", None),
                error_type=error_type, model=getattr(end, "model", None),
                agent_version=getattr(end, "agent_version", None),
                prompt_chars=len(prompt), output_chars=out_chars,
                estimated_usage=bool(usage and usage.estimated),
            )
