"""When no model can narrate, the reader still gets the engine's figures. [AI-04]

The engine answers without a model; only the prose needs one. These tests drive the
real `_stream_agent` over the real composed stack with providers that fail in the
ways providers fail.
"""
from __future__ import annotations

import asyncio
import json
import re
from types import SimpleNamespace

import pytest

import api.chat as chat
from api.chat.degraded import INTERRUPTED_SENTENCE, UNAVAILABLE_SENTENCE, figures_text
from domain.ai import ModelUnavailable
from tests.ai_fakes import FlakyRuntime, install_providers

BRIEF = {"client": "Cascade", "identified_usd": "31000.00", "jobs": {"net_new": 12, "threshold": 10}}
PROMPT = "Brief the call.\n\nJSON:\n" + json.dumps(BRIEF, indent=2)


def drive(*, context=True, degrade=True, prompt=PROMPT, agent="ClientSituationAgent", runs=1):
    async def go():
        app = SimpleNamespace(state=SimpleNamespace())
        token = chat._TELEMETRY_CONTEXT.set({"app": app, "request_id": "r", "intent": "situation"}) if context else None
        try:
            frames = []
            for _ in range(runs):
                frames += [f async for f in chat._stream_agent(agent, prompt, degrade=degrade)]
            return frames
        finally:
            if token is not None:
                chat._TELEMETRY_CONTEXT.reset(token)

    return asyncio.run(go())


def tokens(frames):
    return [json.loads(m) ["content"] for m in re.findall(r"event: token\ndata: (.*)\n", "".join(frames))]


def down(name="p"):
    return FlakyRuntime(name, [ModelUnavailable("down")])


def test_figures_are_the_briefs_values_unchanged():
    text = figures_text(PROMPT)
    assert "- client: Cascade" in text and "- identified_usd: 31000.00" in text and "- jobs.net_new: 12" in text


def test_a_prompt_without_a_brief_has_no_figures():
    assert figures_text("no json here") == "" and figures_text("JSON:\n{broken") == ""


def test_a_long_brief_is_cut_and_says_how_much_is_left():
    big = "JSON:\n" + json.dumps({f"k{i}": i for i in range(50)})
    lines = figures_text(big).splitlines()
    assert len(lines) == 31 and lines[-1] == "- … and 20 more on the page."


def test_every_provider_down_yields_the_sentence_and_the_figures_not_an_error():
    install_providers(down("a"), down("b"))
    [shown] = tokens(drive())
    assert shown.startswith(UNAVAILABLE_SENTENCE) and "- identified_usd: 31000.00" in shown
    assert "failed" not in shown


def test_the_sentence_is_said_once_per_request_and_later_agents_show_figures_only():
    install_providers(down())
    first, second = tokens(drive(runs=2))
    assert UNAVAILABLE_SENTENCE in first and UNAVAILABLE_SENTENCE not in second
    assert "- client: Cascade" in second


def test_a_failure_after_text_appends_the_figures_as_the_remainder():
    install_providers(FlakyRuntime("p", [ModelUnavailable("dropped")], after="Cascade has about "))
    parts = tokens(drive())
    assert parts[0] == "Cascade has about "
    assert INTERRUPTED_SENTENCE in parts[1] and "- jobs.net_new: 12" in parts[1]


def test_a_caller_with_its_own_fallback_keeps_the_failure_marker():
    install_providers(down())
    [shown] = tokens(drive(degrade=False, agent="PageSummaryAgent"))
    assert shown.startswith("[PageSummaryAgent failed")


def test_a_prompt_with_no_figures_still_says_the_assistant_is_unavailable():
    install_providers(down())
    assert tokens(drive(prompt="plain question")) == [UNAVAILABLE_SENTENCE]


def test_a_cancelled_stream_is_recorded_and_the_cancellation_propagates(monkeypatch):
    from domain.ai import TextDelta
    from tests.ai_fakes import ScriptedRuntime

    recorded = []
    monkeypatch.setattr("api.chat.narration._record_agent_action",
                        lambda name, end, prompt, chars, ok: recorded.append((name, chars, ok)))

    class Cancelled(ScriptedRuntime):
        async def stream(self, spec, prompt):
            yield TextDelta("partial")
            raise asyncio.CancelledError

    install_providers(Cancelled("p"))

    async def go():
        return [f async for f in chat._stream_agent("ClientSituationAgent", PROMPT)]

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(go())
    assert recorded == [("ClientSituationAgent", len("partial"), False)]
