"""`AiTelemetry` over OpenTelemetry, following the GenAI semantic conventions. [AI-06]

One span per model call (`chat {model}`) and the two standard client metrics —
`gen_ai.client.operation.duration` and `gen_ai.client.token.usage` — plus counters
for the resilience layer (`ai.retries`, `ai.breaker_opens`, `ai.bulkhead_rejections`,
`ai.budget_refusals`). With `azure-monitor-opentelemetry` configured (main.py) they
land in Application Insights; with nothing configured the OpenTelemetry API is a
no-op and this costs nothing.

WHAT NEVER REACHES A SPAN. A prompt carries engine figures and an answer can quote
them, so neither the text nor anything derived from it is recorded — no prompt, no
completion, no identifier, not even a hash of them. What is recorded is shape: which
agent and role, which provider and model, how many characters, how many tokens,
how it ended. Attributes pass through an allow-list, so a caller cannot widen what
leaves by passing a new keyword; anything off the list is dropped, not recorded.
"""
from __future__ import annotations

import time
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.trace import Status, StatusCode

from domain.ai import ModelRole, ModelUsage

#: What a span or metric may carry besides the standard GenAI attributes.
ALLOWED_EXTRA = frozenset({"agent_version", "prompt_chars", "output_chars", "hops", "fallback_used", "estimated_usage"})
_ALLOWED_COUNTER_ATTRS = frozenset({"provider", "scope", "agent"})
_MAX_TEXT = 64
_TOKEN_BUCKETS = [1, 4, 16, 64, 256, 1024, 4096, 16384, 65536]
_DURATION_BUCKETS = [0.01, 0.02, 0.04, 0.08, 0.16, 0.32, 0.64, 1.28, 2.56, 5.12, 10.24, 20.48, 40.96]


def _scalar(value: Any) -> Any:
    if isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, (tuple, list)):
        return ",".join(str(v) for v in value)[:_MAX_TEXT]
    return str(value)[:_MAX_TEXT]


def _allowed(attributes: dict[str, Any]) -> dict[str, Any]:
    return {f"tcc.{k}": _scalar(v) for k, v in attributes.items() if k in ALLOWED_EXTRA and v is not None}


class OtelCallSpan:
    """One model call being observed. `finish` is safe to call once."""

    def __init__(self, span: Any, instruments: "_Instruments", base: dict[str, Any], started: float) -> None:
        self._span, self._instruments, self._base, self._started = span, instruments, base, started

    def finish(
        self, *, outcome: str, usage: ModelUsage | None = None, finish_reason: str | None = None,
        error_type: str | None = None, **attributes: Any,
    ) -> None:
        model = attributes.pop("model", None)
        labels = dict(self._base)
        if model:
            labels["gen_ai.response.model"] = str(model)[:_MAX_TEXT]
        if error_type:
            labels["error.type"] = error_type[:_MAX_TEXT]
        if finish_reason:
            self._span.set_attribute("gen_ai.response.finish_reasons", [finish_reason[:_MAX_TEXT]])
        for key, value in {**labels, "tcc.outcome": outcome, **_allowed(attributes)}.items():
            self._span.set_attribute(key, value)
        if usage is not None:
            self._record_usage(usage, labels)
        if outcome == "error":
            self._span.set_status(Status(StatusCode.ERROR, error_type or "error"))
        self._span.end()
        self._instruments.duration.record(time.perf_counter() - self._started, labels)

    def _record_usage(self, usage: ModelUsage, labels: dict[str, Any]) -> None:
        for kind, count in (("input", usage.input_tokens), ("output", usage.output_tokens)):
            if count is None:
                continue
            self._span.set_attribute(f"gen_ai.usage.{kind}_tokens", count)
            self._instruments.tokens.record(count, {**labels, "gen_ai.token.type": kind})


class _Instruments:
    def __init__(self, meter: Any) -> None:
        self.meter = meter
        self.duration = meter.create_histogram(
            "gen_ai.client.operation.duration", unit="s", description="Duration of a GenAI client operation",
            explicit_bucket_boundaries_advisory=_DURATION_BUCKETS,
        )
        self.tokens = meter.create_histogram(
            "gen_ai.client.token.usage", unit="{token}", description="Tokens used by a GenAI client operation",
            explicit_bucket_boundaries_advisory=_TOKEN_BUCKETS,
        )
        self.counters: dict[str, Any] = {}


class OtelTelemetry:
    """Pass `tracer_provider` / `meter_provider` to keep a test's telemetry out of the global."""

    def __init__(self, tracer_provider: Any = None, meter_provider: Any = None) -> None:
        self._tracer = (tracer_provider or trace.get_tracer_provider()).get_tracer("tcc.ai")
        self._instruments = _Instruments((meter_provider or metrics.get_meter_provider()).get_meter("tcc.ai"))

    def start_call(self, *, role: ModelRole, provider: str, model: str | None, agent: str) -> OtelCallSpan:
        base = {
            "gen_ai.operation.name": "chat", "gen_ai.provider.name": provider[:_MAX_TEXT],
            "gen_ai.agent.name": agent[:_MAX_TEXT], "tcc.role": getattr(role, "value", str(role)),
        }
        if model:
            base["gen_ai.request.model"] = model[:_MAX_TEXT]
        span = self._tracer.start_span(f"chat {model}" if model else "chat", kind=trace.SpanKind.CLIENT)
        return OtelCallSpan(span, self._instruments, base, time.perf_counter())

    def count(self, metric: str, value: float = 1, **attributes: Any) -> None:
        counters = self._instruments.counters
        if metric not in counters:
            counters[metric] = self._instruments.meter.create_counter(metric)
        counters[metric].add(value, {k: _scalar(v) for k, v in attributes.items() if k in _ALLOWED_COUNTER_ATTRS})
