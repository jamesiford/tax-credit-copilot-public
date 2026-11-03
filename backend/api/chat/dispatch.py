"""Route, split, delegate, bundle: turn one question into one SSE stream."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

from api.chat.models import ChatRequest
from api.chat.pipelines_briefs import (
    _pipeline_at_risk, _pipeline_book, _pipeline_explain, _pipeline_situation, _pipeline_trend,
)
from api.chat.pipelines_core import _pipeline_discovery, _pipeline_eligibility, _pipeline_portfolio
from api.chat.pipelines_whatif import _pipeline_simulate
from api.chat.routing import _plan
from api.chat.scope import _clarify_stream, _missing_scope_stream, _referent, _request_scope
from api.chat.sse import _sse
from application.capabilities.catalog import CAPABILITIES, NEEDS_CLIENT as _NEEDS_CLIENT

log = logging.getLogger(__name__)


async def _stub_stream(message: str) -> AsyncIterator[str]:
    yield _sse("status", {"phase": 1, "echo": message, "note": "No model is available; scripted stream."})
    script = [
        ("OrchestratorAgent",  "Routing your question to the right specialists across our 10-state footprint. "),
        ("PayrollIngestAgent", "Loaded synthetic payroll snapshot (337 employees, 18-month window, GA · NY · SC · TX · NC · TN · FL · OH · CO · VA). "),
        ("HeadcountAgent",     "Computed Georgia FTE: 99.16 current, 84.49 baseline, 14.67 net new. "),
        ("CreditRulesAgent",   "Applied GA Jobs Tax Credit (T1B40/MZ/OZ, $3,500 band): 12.67 qualifying jobs × $3,500 × 5 yrs. "),
        ("ReportingAgent",     "GA JTC: $221,725 lifetime. Full portfolio: TN $522K · FED WOTC $487K · GA $222K and more — run 'Show me our complete credit picture' for the $1.53M total. (Stub — configure FOUNDRY_PROJECT_ENDPOINT to enable live agents.)"),
    ]
    for agent, text in script:
        yield _sse("agent_start", {"agent": agent})
        for word in text.split(" "):
            yield _sse("token", {"agent": agent, "content": word + " "})
            await asyncio.sleep(0.04)
        yield _sse("agent_end", {"agent": agent})
    yield _sse("done", {})


def _run_intent(app, intent: str, message: str, scope: dict[str, Any]):
    """One intent to one pipeline. The only place that mapping exists."""
    if intent == "discovery":
        return _pipeline_discovery(app, message)
    if intent == "book":
        return _pipeline_book(app, message, scope=scope)
    if intent == "multi_state":
        return _pipeline_portfolio(app, message)
    if intent == "situation":
        return _pipeline_situation(app, message, scope=scope)
    if intent == "trend":
        return _pipeline_trend(app, message, scope=scope)
    if intent == "at_risk":
        return _pipeline_at_risk(app, message, scope=scope)
    if intent == "explain":
        return _pipeline_explain(app, message)
    if intent == "simulate":
        return _pipeline_simulate(app, message)
    return _pipeline_eligibility(app, message, scope=scope)


async def _dispatch(app, req: ChatRequest, *, scope: dict[str, Any] | None = None) -> AsyncIterator[str]:
    """Route, split, delegate, bundle.

    One question is routinely several: "brief me on them, and what else might
    they qualify for" is two capabilities, and the old single-intent router
    answered whichever keyword it happened to match first and dropped the rest
    silently. The plan names every capability the question needs; each runs its
    own deterministic brief, and they stream in sequence under their own agent
    badges so the reader can see which answer came from where.

    SCOPE IS CHECKED PER CAPABILITY, after routing. Most briefs are about one
    client and cannot be answered without one — but `book` is the portfolio
    question, asked from the title bar where no client is selected by design.
    Refusing the whole turn there is what made "who should we reach out to?"
    unanswerable.

    `done` is emitted ONCE, at the end. Each pipeline emits its own, so they are
    swallowed here — a `done` after the first intent would stop the UI
    streaming while the rest of the answer was still coming.
    """
    planning_scope = {
        "account_id": req.client_id, "tax_year": req.tax_year, "state": req.state,
    }
    intents = await _plan(req.message, req.history, planning_scope)

    # The router may have found a one-client question the keywords did not.
    # The client-free half of the turn still answers; the one-client half asks.
    clarify = (
        _referent(req) if scope is None and any(i in _NEEDS_CLIENT for i in intents) else None
    )
    if clarify is not None:
        asked = [i for i in intents if i in _NEEDS_CLIENT]
        intents = [i for i in intents if i not in _NEEDS_CLIENT]
        yield _sse("plan", {
            "intents": intents, "needs_client": asked,
            "capabilities": {i: CAPABILITIES[i] for i in intents},
        })
        for intent in intents:
            async for frame in _run_intent(app, intent, req.message, planning_scope):
                if frame.startswith("event: done"):
                    continue
                yield frame
        async for frame in _clarify_stream(req, *clarify):
            yield frame
        yield _sse("done", {})
        return

    # Resolve the client scope only if something asked for it. `_request_scope`
    # loads statute and refuses without a client-year, which is correct for the
    # capabilities that need one and wrong for the one that does not.
    resolved = scope
    refused: list[str] = []
    if resolved is None and any(i in _NEEDS_CLIENT for i in intents):
        try:
            resolved = _request_scope(req)
        except ValueError:
            refused = [i for i in intents if i in _NEEDS_CLIENT]
            intents = [i for i in intents if i not in _NEEDS_CLIENT]

    yield _sse("plan", {
        "intents": intents,
        "needs_client": refused,
        "capabilities": {i: CAPABILITIES[i] for i in intents},
    })

    if not intents:
        # Everything asked for needs a client and none is selected. Say which,
        # rather than the generic refusal — "pick a client" is more useful when
        # the reader knows what it would unlock.
        wanted = ", ".join(refused) or "that"
        async for frame in _missing_scope_stream(
            req.message,
            detail=(
                f"That needs a client and a tax year selected on the page "
                f"({wanted}). Pick one from the scope bar, or ask who to reach "
                f"out to across the whole book — that one needs no client."
            ),
        ):
            yield frame
        return

    for position, intent in enumerate(intents):
        async for frame in _run_intent(app, intent, req.message, resolved or planning_scope):
            if frame.startswith("event: done") and position < len(intents) - 1:
                continue
            yield frame
