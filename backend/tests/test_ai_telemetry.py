"""Model-call telemetry: the right shape, and nothing that could leak. [AI-06]

The leak tests are the point. A prompt carries engine figures and a reply can quote
them, so no span or metric may carry text, an identifier, or a hash of either. The
sentinels below are put everywhere a leak could come from and then searched for in
every attribute the exporters saw.
"""
from __future__ import annotations

import asyncio

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from application.ai.observed import ObservedRuntime
from domain.ai import AgentSpec, ModelAuth, ModelRole, ModelUnavailable, ModelUsage, StreamEnd, TextDelta
from infrastructure.ai.otel_telemetry import ALLOWED_EXTRA, OtelTelemetry
from tests.ai_fakes import FlakyRuntime, ScriptedRuntime

PLANTED_PROMPT = " ".join(["SENTINEL-PROMPT-31000.00", "token", "01234567" * 3, "SSN", "123-45-" + "6789"])
PLANTED_REPLY = "SENTINEL-REPLY-Cascade-owes-31000"
SPEC = AgentSpec(name="ReportingAgent", instructions="SENTINEL-INSTRUCTIONS", role=ModelRole.NARRATOR)


@pytest.fixture
def otel():
    spans, reader = InMemorySpanExporter(), InMemoryMetricReader()
    tracer = TracerProvider()
    tracer.add_span_processor(SimpleSpanProcessor(spans))
    telemetry = OtelTelemetry(tracer, MeterProvider(metric_readers=[reader]))
    return telemetry, spans, reader


class Reporting(ScriptedRuntime):
    async def stream(self, spec, prompt):
        yield TextDelta(PLANTED_REPLY)
        yield ModelUsage(120, 30)
        yield StreamEnd(provider=self.name, model="m-1", agent_version="7", finish_reason="stop")


def run(runtime, prompt=PLANTED_PROMPT):
    async def go():
        return [e async for e in runtime.stream(SPEC, prompt)]

    return asyncio.run(go())


def everything_recorded(spans, reader) -> str:
    """Every attribute of every span and every metric data point, as one string."""
    parts = []
    for span in spans.get_finished_spans():
        parts += [span.name, str(dict(span.attributes)), str(span.status.description)]
    data = reader.get_metrics_data()
    for resource in (data.resource_metrics if data else []):
        for scope in resource.scope_metrics:
            for metric in scope.metrics:
                parts += [metric.name] + [str(dict(p.attributes)) for p in metric.data.data_points]
    return "\n".join(parts)


def test_a_call_is_one_chat_span_with_genai_attributes_and_shape_only(otel):
    telemetry, spans, _ = otel
    run(ObservedRuntime(Reporting("foundry"), telemetry))
    [span] = spans.get_finished_spans()
    a = span.attributes
    assert span.name == "chat" and span.kind.name == "CLIENT"
    assert a["gen_ai.operation.name"] == "chat" and a["gen_ai.provider.name"] == "foundry"
    assert a["gen_ai.agent.name"] == "ReportingAgent" and a["gen_ai.response.model"] == "m-1"
    assert (a["gen_ai.usage.input_tokens"], a["gen_ai.usage.output_tokens"]) == (120, 30)
    assert tuple(a["gen_ai.response.finish_reasons"]) == ("stop",)
    assert a["tcc.outcome"] == "ok" and a["tcc.prompt_chars"] == len(PLANTED_PROMPT)
    assert a["tcc.output_chars"] == len(PLANTED_REPLY) and a["tcc.agent_version"] == "7"


def test_the_standard_client_metrics_are_recorded(otel):
    telemetry, _, reader = otel
    run(ObservedRuntime(Reporting("foundry"), telemetry))
    names = {m.name: m for r in reader.get_metrics_data().resource_metrics for s in r.scope_metrics for m in s.metrics}
    assert {"gen_ai.client.operation.duration", "gen_ai.client.token.usage"} <= set(names)
    kinds = {p.attributes["gen_ai.token.type"]: p.sum for p in names["gen_ai.client.token.usage"].data.data_points}
    assert kinds == {"input": 120, "output": 30}


def test_no_prompt_reply_instruction_identifier_or_hash_reaches_a_span_or_metric(otel):
    telemetry, spans, reader = otel
    run(ObservedRuntime(Reporting("foundry"), telemetry))
    seen = everything_recorded(spans, reader)
    for needle in ("SENTINEL", "31000", "01234567", "123-45-6789", "Cascade"):
        assert needle not in seen, f"{needle!r} leaked into telemetry"


def test_an_error_is_recorded_by_class_name_never_by_message(otel):
    telemetry, spans, reader = otel
    failing = FlakyRuntime("gateway", [ModelAuth(f"denied for {PLANTED_PROMPT}")])
    with pytest.raises(ModelAuth):
        run(ObservedRuntime(failing, telemetry))
    [span] = spans.get_finished_spans()
    assert span.attributes["error.type"] == "ModelAuth" and span.attributes["tcc.outcome"] == "error"
    assert span.status.status_code.name == "ERROR"
    assert "SENTINEL" not in everything_recorded(spans, reader)


def test_a_cancelled_call_is_recorded_as_cancelled(otel):
    telemetry, spans, _ = otel

    class Cancelled(ScriptedRuntime):
        async def stream(self, spec, prompt):
            yield TextDelta("x")
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        run(ObservedRuntime(Cancelled("p"), telemetry))
    assert spans.get_finished_spans()[0].attributes["tcc.outcome"] == "cancelled"


def test_an_attribute_off_the_allow_list_is_dropped_not_recorded(otel):
    telemetry, spans, _ = otel
    span = telemetry.start_call(role=ModelRole.NARRATOR, provider="p", model="m", agent="A")
    span.finish(outcome="ok", prompt=PLANTED_PROMPT, completion=PLANTED_REPLY, employee_id="E123", prompt_chars=5)
    [done] = spans.get_finished_spans()
    assert done.name == "chat m" and done.attributes["gen_ai.request.model"] == "m"
    assert {k for k in done.attributes if k.startswith("tcc.")} <= {"tcc.outcome", "tcc.role"} | {f"tcc.{k}" for k in ALLOWED_EXTRA}
    assert "SENTINEL" not in str(dict(done.attributes)) and "E123" not in str(dict(done.attributes))


def test_counters_carry_only_provider_scope_and_agent(otel):
    telemetry, _, reader = otel
    telemetry.count("ai.retries", provider="gateway", prompt=PLANTED_PROMPT)
    [point] = [p for r in reader.get_metrics_data().resource_metrics for s in r.scope_metrics
               for m in s.metrics if m.name == "ai.retries" for p in m.data.data_points]
    assert dict(point.attributes) == {"provider": "gateway"} and point.value == 1


def test_the_composed_stack_is_observed_and_still_leaks_nothing(otel):
    from application import wiring
    from tests.ai_fakes import install_providers
    from application.ai.requests import NarrateBriefQuery
    from domain.ai import NarrationUnavailable

    telemetry, spans, reader = otel
    install_providers(Reporting("foundry"))
    wiring.set_ai_telemetry(telemetry)

    async def go(prompt):
        return [e async for e in wiring.get_mediator().stream(NarrateBriefQuery(agent_name="ReportingAgent", prompt=prompt))]

    asyncio.run(go("SENTINEL-PROMPT-31000.00"))
    with pytest.raises(NarrationUnavailable):
        asyncio.run(go(PLANTED_PROMPT))  # carries a record token and an SSN shape: refused by egress
    ok, refused = spans.get_finished_spans()
    assert ok.attributes["tcc.outcome"] == "ok"
    assert refused.attributes["error.type"] == "EgressRefused", "a refusal outside the stack is still observed"
    assert "SENTINEL" not in everything_recorded(spans, reader)
