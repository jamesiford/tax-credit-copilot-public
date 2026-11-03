"""The single-brief pipelines: situation, explain, the book, at-risk and trend.

One deterministic brief, one narration. No Orchestrator acknowledgement where
there is no routing to acknowledge — a second agent restating the scope would be
narration for its own sake.
"""
from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

from api.chat.narration import _brief, _stream_agent
from api.chat.sse import _TELEMETRY_CONTEXT, _sse
from application.capabilities.book import book_rank
from application.capabilities.client import client_at_risk, client_situation, client_trend
from application.capabilities.errors import YearNotAuthored
from application.capabilities.walkthrough import calc_walkthrough


async def _pipeline_situation(app, message: str, *, scope: dict[str, Any]) -> AsyncIterator[str]:
    """Why this client is worth calling. One brief, one narration.

    No engine and no payroll: the ranking is over recorded claims, so a per-row
    button on the book costs a query. The Orchestrator step is skipped — with a
    single deterministic brief there is no routing to acknowledge, and a second
    agent restating the scope would be narration for its own sake.
    """
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "situation"})
    try:
        account_id = scope.get("account_id")
        tax_year = scope.get("tax_year")
        yield _sse("status", {
            "phase": 3, "intent": "situation",
            "client_id": account_id, "tax_year": tax_year,
        })

        # The narrator was never handed the display name, and must not be now:
        # its prompt is byte-for-byte what it was before the extraction.
        brief = {
            key: value for key, value in client_situation(account_id, tax_year).facts.items()
            if key != "client_name"
        }
        async for f in _stream_agent("ClientSituationAgent", _brief(f"User question: {message}", brief)):
            yield f
        yield _sse("done", {})
    finally:
        _TELEMETRY_CONTEXT.reset(ctx_token)


async def _pipeline_explain(app, message: str) -> AsyncIterator[str]:
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "explain"})
    try:
        yield _sse("status", {"phase": 3, "intent": "explain"})

        cached = getattr(app.state, "last_trail", None)
        if not cached:
            async for f in _stream_agent("OrchestratorAgent", "User asked you to walk through the calculation, but no prior eligibility "
                                         "result is cached. Reply in one sentence asking them to run an eligibility "
                                         "question first."):
                yield f
            yield _sse("done", {})
            return

        brief = calc_walkthrough(trail=cached).facts
        async for f in _stream_agent("ReportingAgent", _brief(
                                         "Walk an exec through this calculation step by step in 3-5 sentences. "
                                         "Cite the statute. End by reminding them every number above is sourced from a JSON rule pack, not from the model.",
                                         brief,
                                     )):
            yield f

        yield _sse("calculation_trail", cached)
        yield _sse("done", {})
    finally:
        _TELEMETRY_CONTEXT.reset(ctx_token)


def _book_brief(limit: int = 8) -> dict[str, Any]:
    """The book exactly as the page ranks it, read from the page's own endpoint.

    The ranking lives in `book_rank`; this passes the router's read in as its
    page source so the chat and the page are literally the same call.
    """
    from api.claims import portfolio_v2

    return book_rank(limit, page_reader=portfolio_v2).facts


async def _pipeline_book(app, message: str, *, scope: dict[str, Any]) -> AsyncIterator[str]:
    """Who to call across every client. The one brief that needs NO client."""
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "book"})
    try:
        # NO YEAR, whatever the shell sends. "Who do I call" is a question about
        # a client across every year they hold; the shell's year was flattening
        # the bands exactly as it once did on the page.
        yield _sse("status", {"phase": 3, "intent": "book"})

        brief = _book_brief()
        async for f in _stream_agent("ClientSituationAgent", _brief(
                                         "Name who to reach out to first and WHY, in the order given, "
                                         "BY CLIENT NAME. Use the `reason` exactly as written — it is "
                                         "what the page shows. Lead with the reason, not the dollar "
                                         "value — a client one hire from a threshold is worth nothing "
                                         "today and is still the one to call. Name the programme and "
                                         "year for each. Do not rank them yourself; the order is "
                                         "already decided and matches the page. "
                                         "Original question: " + message,
                                         brief,
                                     )):
            yield f
        yield _sse("done", {})
    finally:
        _TELEMETRY_CONTEXT.reset(ctx_token)


async def _pipeline_at_risk(app, message: str, *, scope: dict[str, Any]) -> AsyncIterator[str]:
    """Which counted jobs could fall out of the credit."""
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "at_risk"})
    try:
        account_id = scope.get("account_id")
        tax_year = scope.get("tax_year")
        state = scope.get("state")
        method = scope.get("method") or "min_max"
        yield _sse("status", {
            "phase": 3, "intent": "at_risk",
            "client_id": account_id, "tax_year": tax_year,
        })

        try:
            brief = client_at_risk(account_id, tax_year, state, method).facts
        except YearNotAuthored as exc:
            # The narrator is told the year is declined, by name, and says so.
            brief = {"calculated": False, "declined": str(exc)}
        async for f in _stream_agent("ClientSituationAgent", _brief(
                                         "Say how many of the jobs already counted toward this "
                                         "credit sit close enough to a statutory floor to fall out "
                                         "of it, which floor binds, and what would have to change. "
                                         "This is a COMPLETED year: describe what would have to "
                                         "change to lose these jobs, never predict that they will "
                                         "be lost. Original question: " + message,
                                         brief,
                                     )):
            yield f
        yield _sse("done", {})
    finally:
        _TELEMETRY_CONTEXT.reset(ctx_token)


async def _pipeline_trend(app, message: str, *, scope: dict[str, Any]) -> AsyncIterator[str]:
    """How a client has moved across years. One Gold read, one narration."""
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "trend"})
    try:
        account_id = scope.get("account_id")
        yield _sse("status", {"phase": 3, "intent": "trend", "client_id": account_id})

        brief = client_trend(account_id).facts
        async for f in _stream_agent("ClientSituationAgent", _brief(
                                         "Describe how this client has moved across tax years, and say "
                                         "plainly whether they have been eligible every year since their "
                                         "base year. A year absent from the list carries no figure and is "
                                         "NOT a zero. Original question: " + message,
                                         brief,
                                     )):
            yield f
        yield _sse("done", {})
    finally:
        _TELEMETRY_CONTEXT.reset(ctx_token)
