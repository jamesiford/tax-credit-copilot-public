"""Deadlines, spans and what-if numbers: the rules that bound a turn. [CH-08]"""
from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.core import replies, telemetry
from app.core.settings import OrchestratorConfigError, load_settings
from app.core.toolset import numbers_in
from orch_harness import ENV, FakeGateway, build_rig

PREPARE = {"tools": [{"tool": "engagement_set_prepare", "args": {"program_code": "GA_JTC", "scope": "in_scope"}}]}
ASK = "Mark Cascade's GA_JTC engagement as in scope"


def say(rig, text):
    return asyncio.run(rig.say(text))


def with_deadline(rig, seconds):
    rig.pipeline._s = replace(rig.pipeline._s, turn_timeout_seconds=seconds)


def test_a_turn_past_its_deadline_says_so_and_changes_nothing():
    rig = build_rig([{"delay": 1.0, "tools": [{"tool": "client_trend", "args": {}}]}, {"text": "done"}])
    with_deadline(rig, 0.2)
    reply = say(rig, "How has Cascade trended?")
    assert reply.kind == "failure" and reply.text == replies.TIMED_OUT
    assert not [t for t in rig.gateway.tools_called() if t.endswith("_commit")]


def test_a_confirm_that_runs_out_of_time_is_unknown_never_retried_and_not_confirmable_again():
    gateway = FakeGateway(delays={"engagement_set_commit": 1.0})
    rig = build_rig([PREPARE, {"text": "Here is the preview."}], gateway=gateway)
    say(rig, ASK)
    with_deadline(rig, 0.2)
    lost = say(rig, "confirm")
    assert lost.kind == "commit_refused" and "can't say whether it was made" in lost.text and "won't retry" in lost.text
    again = say(rig, "confirm")
    assert again.kind == "commit_refused" and "nothing waiting" in again.text
    assert gateway.tools_called().count("engagement_set_commit") == 1


def test_the_turn_deadline_is_bounded_and_documented_in_the_settings():
    assert load_settings(ENV).turn_timeout_seconds == 90
    assert load_settings({**ENV, "CHANNEL_TURN_TIMEOUT_SECONDS": "30"}).turn_timeout_seconds == 30
    for bad in ("5", "601", "soon"):
        with pytest.raises(OrchestratorConfigError):
            load_settings({**ENV, "CHANNEL_TURN_TIMEOUT_SECONDS": bad})


@pytest.fixture
def spans():
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    telemetry.set_tracer(provider.get_tracer("test"))
    yield exporter
    telemetry.set_tracer(None)


def test_a_span_per_tool_call_carries_the_tool_and_its_outcome_and_no_payroll(spans):
    rig = build_rig([{"tools": [{"tool": "client_trend", "args": {}}]}, {"text": "The table shows each year."}])
    say(rig, "How has Cascade trended?")
    finished = spans.get_finished_spans()
    assert [s.name for s in finished] == ["tcc.tool.client_resolve", "tcc.tool.client_trend"]
    for span in finished:
        assert set(span.attributes) <= {"tcc.tool", "tcc.tool.kind", "tcc.channel", "tcc.correlation_id", "tcc.outcome", "tcc.error_code"}
        assert span.attributes["tcc.outcome"] == "ok" and span.attributes["tcc.channel"] == "teams"
    dump = json.dumps([dict(s.attributes) for s in finished])
    for forbidden in ("Cascade", "410.13", "494.25", "2001", "Pat Writer"):
        assert forbidden not in dump


def test_a_failed_call_is_a_span_with_an_error_code_and_still_no_content(spans):
    gateway = FakeGateway(overrides={"client_trend": lambda _a: (502, {"error": {"code": "api_unreachable", "message": "Cascade is down"}})})
    say(build_rig([{"tools": [{"tool": "client_trend", "args": {}}]}, {"text": "x"}], gateway=gateway), "How has Cascade trended?")
    failed = [s for s in spans.get_finished_spans() if s.name == "tcc.tool.client_trend"][0]
    assert failed.attributes["tcc.outcome"] == "error" and failed.attributes["tcc.error_code"] == "api_unreachable"
    assert "Cascade is down" not in json.dumps(dict(failed.attributes))


def test_the_readers_numbers_are_digits_or_the_words_one_to_twelve():
    assert numbers_in("hired 2 people at 35.5 hours") == {2.0, 35.5}
    assert numbers_in("what if we hired Three and one more") == {3.0, 1.0}
    assert numbers_in("TY2023 site A-1") == set(), "an identifier's digits and a year inside a label are not quantities"


def test_a_what_if_number_the_model_chose_is_dropped_and_the_readers_is_kept():
    gateway = FakeGateway()
    rig = build_rig([{"tools": [{"tool": "simulate", "args": {
        "worksite_id": "A-1", "action": "add_headcount", "magnitude": 4, "hire_weekly_hours": 40, "hire_hourly_rate": 22.5}}]},
        {"text": "The what-if is shown."}], gateway=gateway)
    say(rig, "What if Cascade hired 4 people at site A-1 in 2023 at 22.5 an hour?")
    sent = [c.args for c in gateway.calls if c.tool == "simulate"][0]
    assert sent["magnitude"] == 4 and sent["hire_hourly_rate"] == 22.5 and "hire_weekly_hours" not in sent
