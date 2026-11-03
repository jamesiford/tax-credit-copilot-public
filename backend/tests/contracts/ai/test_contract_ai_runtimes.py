"""One behavioural contract, every model adapter. [AI-02, AI-03]

Liskov: anything that implements `AgentRuntime` must be substitutable for any
other. These tests state what that means — streamed deltas concatenate to the
text, an abandoned stream stops the upstream call, SDK and HTTP failures arrive as
the small error taxonomy and never as a provider type, usage is reported when the
provider has it — and run it against each adapter. A new adapter joins by adding
one entry to `ADAPTERS`.
"""
from __future__ import annotations

import asyncio

import pytest

from domain.ai import (
    AgentSpec, ModelAuth, ModelBadRequest, ModelRateLimited, ModelUnavailable, ModelUsage, StreamEnd, TextDelta,
)
from tests.ai_fakes import FakeAgent, foundry_runtime_over

SPEC = AgentSpec(name="ReportingAgent", instructions="Narrate the brief.")
PROMPT = "Brief: annual credit."


class _HttpError(Exception):
    def __init__(self, status, headers=None):
        super().__init__(f"http {status}")
        self.status_code = status
        self.response = type("R", (), {"status_code": status, "headers": headers or {}})()


def _foundry(chunks=("Hello ", "world"), error=None, closed=None):
    class Agent(FakeAgent):
        async def run(self, prompt, stream=True):
            try:
                if error is not None and not chunks:
                    raise error
                for chunk in chunks:
                    yield type("U", (), {"text": chunk})()
                if error is not None:
                    raise error
            finally:
                if closed is not None:
                    closed.append(True)

    return foundry_runtime_over(Agent())


ADAPTERS = {"foundry_prompt_agent": _foundry}


@pytest.fixture(params=sorted(ADAPTERS))
def make(request):
    return ADAPTERS[request.param]


def _drain(runtime):
    async def run():
        return [event async for event in runtime.stream(SPEC, PROMPT)]

    return asyncio.run(run())


def test_deltas_concatenate_to_the_text(make):
    events = _drain(make(chunks=("Hello ", "wor", "ld")))
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "Hello world"


def test_the_stream_ends_with_who_answered(make):
    events = _drain(make())
    end = events[-1]
    assert isinstance(end, StreamEnd) and end.provider and end.provider == make().name


def test_an_empty_delta_is_never_emitted(make):
    events = _drain(make(chunks=("", "x", "")))
    assert [e.text for e in events if isinstance(e, TextDelta)] == ["x"]


def test_abandoning_the_stream_stops_the_upstream_call(make):
    closed: list[bool] = []

    async def run():
        runtime = make(chunks=("a", "b", "c"), closed=closed)
        stream = runtime.stream(SPEC, PROMPT)
        async for event in stream:
            if isinstance(event, TextDelta):
                break
        await stream.aclose()

    asyncio.run(run())
    assert closed == [True]


@pytest.mark.parametrize("error, expected", [
    (_HttpError(401), ModelAuth),
    (_HttpError(403), ModelAuth),
    (_HttpError(400), ModelBadRequest),
    (_HttpError(429, {"retry-after": "7"}), ModelRateLimited),
    (_HttpError(503), ModelUnavailable),
    (RuntimeError("socket closed"), ModelUnavailable),
])
def test_failures_arrive_as_the_taxonomy_never_as_a_provider_type(make, error, expected):
    with pytest.raises(expected):
        _drain(make(chunks=(), error=error))


def test_a_rate_limit_carries_what_the_provider_said_about_waiting(make):
    with pytest.raises(ModelRateLimited) as caught:
        _drain(make(chunks=(), error=_HttpError(429, {"retry-after": "7"})))
    assert caught.value.retry_after == 7.0


def test_retryability_is_part_of_the_taxonomy():
    assert ModelUnavailable().retryable and ModelRateLimited().retryable
    assert not ModelBadRequest().retryable and not ModelAuth().retryable


def test_usage_when_reported_is_a_model_usage(make):
    for event in _drain(make()):
        if isinstance(event, ModelUsage):
            assert event.total >= 0 and (event.input_tokens or 0) >= 0


def test_the_runtime_reports_a_status_and_a_name(make):
    runtime = make()
    assert runtime.name and runtime.status().state in ("ready", "warming", "degraded", "unavailable", "disabled")
    assert runtime.ready_for("ReportingAgent") in (True, False)
