"""The what-if pipeline: a straight-line headcount change at one location."""
from __future__ import annotations

import re
import uuid
from typing import AsyncIterator

from api.chat.narration import _brief, _stream_agent
from api.chat.sse import _TELEMETRY_CONTEXT, _sse
from application.capabilities.simulate import simulate_headcount
from domain.calculation.trail import TrailRecorder, reset_recorder, set_recorder


_NUM_RE = re.compile(r"\b(\d{1,3})\b")
# Capital-letter-only so we stop before lowercase words like 'next'.
_CITY_RE = re.compile(r"\bin ([A-Z][a-zA-Z]+(?: [A-Z][a-zA-Z]+)?)")
_REDUCE_TOKENS = ("lose", "lay off", "layoff", "laid off", "cut", "eliminate",
                  "eliminat", "reduce", "reduction", "close", "downsize",
                  "let go", "remove", "minus", "-")


def _extract_simulation(message: str) -> tuple[int, str]:
    n_match = _NUM_RE.search(message)
    n = int(n_match.group(1)) if n_match else 5
    c_match = _CITY_RE.search(message)
    city = c_match.group(1).strip() if c_match else "Atlanta"
    lower = message.lower()
    if any(tok in lower for tok in _REDUCE_TOKENS):
        n = -abs(n)
    return n, city


async def _pipeline_simulate(app, message: str) -> AsyncIterator[str]:
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "simulate"})
    new_hires, city = _extract_simulation(message)
    recorder = TrailRecorder(title="Pending", citation="")
    token = set_recorder(recorder)
    try:
        yield _sse("status", {"phase": 3, "intent": "simulate", "new_hires": new_hires, "city": city})

        direction_verb = "remove" if new_hires < 0 else "add"
        magnitude = abs(new_hires)
        ack = (
            f"User asked a what-if: {direction_verb} {magnitude} headcount in {city}. "
            "Acknowledge in one sentence; the simulation runs next."
        )
        async for f in _stream_agent("OrchestratorAgent", ack):
            yield f

        sim = simulate_headcount(city, new_hires).facts

        async for f in _stream_agent("HeadcountAgent", _brief(
                                         f"Report the projected headcount shift for {city} in one sentence.",
                                         {"location": city, "headcount_change": new_hires, "direction": direction_verb,
                                          "baseline_net_new_headcount": sim["baseline"]["net_new_headcount"],
                                          "projected_net_new_headcount": sim["projected"]["net_new_headcount"]},
                                     )):
            yield f

        async for f in _stream_agent("CreditRulesAgent", _brief("Report the projected credit in one sentence.", {
                                         "direction": direction_verb,
                                         "baseline_annual_credit_usd": sim["baseline"]["annual_credit_usd"],
                                         "projected_annual_credit_usd": sim["projected"]["annual_credit_usd"],
                                         "projected_lifetime_credit_usd": sim["projected"]["lifetime_credit_usd"],
                                         "citation": sim["citation"],
                                     })):
            yield f

        async for f in _stream_agent("ReportingAgent", _brief(
                                         f"Summarize the what-if delta for an exec. Original question: {message}",
                                         {"fte_change": new_hires, "direction": direction_verb,
                                          "location": city,
                                          "delta_annual_usd": sim["delta"]["annual_credit_usd"],
                                          "delta_lifetime_usd": sim["delta"]["lifetime_credit_usd"],
                                          "citation": sim["citation"]},
                                     )):
            yield f

        if recorder.steps:
            app.state.last_trail = recorder.to_dict()
            yield _sse("calculation_trail", recorder.to_dict())
        yield _sse("done", {})
    finally:
        reset_recorder(token)
        _TELEMETRY_CONTEXT.reset(ctx_token)
