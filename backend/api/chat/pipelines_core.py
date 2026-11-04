"""The three scan pipelines: eligibility, the full portfolio, and discovery.

Each runs a deterministic tool and hands the agents a JSON brief; the agents
narrate it and never compute. The calculation trail is cached on `app.state` so
the `explain` intent can re-emit it.
"""
from __future__ import annotations

import uuid
from typing import Any, AsyncIterator

from api.chat.narration import _brief, _question, _stream_agent
from api.chat.evidence_tap import tap
from api.chat.scope import _detect_state
from api.chat.sse import _TELEMETRY_CONTEXT, _sse
from application.capabilities.client import client_discovery, client_eligibility
from domain.calculation.trail import TrailRecorder, reset_recorder, set_recorder


def _without_totals(facts: dict[str, Any]) -> dict[str, Any]:
    """The discovery facts as the scan's narrator has always been handed them: the totals travel to the closing summary only."""
    return {key: value for key, value in facts.items() if key != "totals"}


async def _pipeline_eligibility(app, message: str, *, scope: dict[str, Any] | None = None) -> AsyncIterator[str]:
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "eligibility"})
    scope = scope or {}
    state = str(scope.get("state") or _detect_state(message) or "GA").upper()
    account_id = scope.get("account_id")
    tax_year = scope.get("tax_year")
    method = str(scope.get("method") or "min_max").lower()
    recorder = TrailRecorder(title="Pending", citation="")
    token = set_recorder(recorder)
    try:
        yield _sse("status", {
            "phase": 3,
            "intent": "eligibility",
            "state": state,
            "client_id": account_id,
            "tax_year": tax_year,
            "method": method,
        })

        scope_text = (
            f"Selected scope: client_id={account_id}, tax_year={tax_year}, state={state}, method={method}."
        )
        async for f in _stream_agent("OrchestratorAgent", f"User question:\n{_question(message)}\n{scope_text}"):
            yield f

        # What the RUN concluded about this client, not a synthetic fixture.
        # `load_payroll_snapshot` read backend/data/payroll.csv and cited itself
        # as "not from a client feed", so the narration described 9,477 invented
        # employees while the question was about this client.
        #
        # No unscoped branch: `chat()` refuses a request without a client and a
        # tax year before dispatching, so both are always present here.
        #
        # `method="pay_period"` is what this brief has always read. The scope's
        # method selector never reached it, and the capability's default is the
        # channel's, so the portal says so explicitly (DECISIONS D-05).
        eligibility = tap(client_eligibility(
            account_id, tax_year, state, method="pay_period", window=scope.get("window"),
        )).facts
        snapshot = eligibility["snapshot"]
        credit = eligibility["credit"]
        async for f in _stream_agent("PayrollIngestAgent", _brief(f"Confirm the payroll snapshot in scope for state={state}.", snapshot)):
            yield f

        if not credit.get("no_state_pack"):
            async for f in _stream_agent("HeadcountAgent", _brief(f"Report the statutory headcount picture for {state} in one sentence.", {
                                             "state": state,
                                             "client_id": account_id,
                                             "tax_year": tax_year,
                                             "average_headcount": credit.get("average_headcount"),
                                             "prior_period_average_headcount": credit.get("prior_period_average_headcount"),
                                             "qualifying_jobs": credit.get("qualifying_jobs"),
                                         })):
                yield f


        if credit.get("no_state_pack"):
            async for f in _stream_agent("CreditRulesAgent", _brief(
                                             f"Tell the user in one sentence that we have no state rule pack for {state}, "
                                             "and that federal credits like WOTC may still apply via the portfolio scan.",
                                             {"state": state, "message": credit["message"]},
                                         )):
                yield f
            async for f in _stream_agent("ReportingAgent", _brief(
                                             f"Summarize for an exec in one sentence. Original question:\n{_question(message)}",
                                             {"state": state, "no_state_pack": True,
                                              "available_state_packs": ["GA", "NY", "SC", "NC", "TN", "FL", "OH", "CO", "VA"],
                                              "suggested_next_question": "Show me our full credit portfolio across every state."},
                                         )):
                yield f
        else:
            async for f in _stream_agent("CreditRulesAgent", _brief(f"Report the {credit['credit_name']} result in one sentence.", credit)):
                yield f

            async for f in _stream_agent("ReportingAgent", _brief(f"Summarize for an exec. Original question:\n{_question(message)}", {
                                             "credit_name": credit["credit_name"],
                                             "citation": credit["citation"],
                                             "qualifying_jobs": credit["qualifying_jobs"],
                                             "annual_credit_usd": credit["annual_credit_usd"],
                                             "lifetime_credit_usd": credit["lifetime_credit_usd"],
                                             "benefit_period_years": credit["benefit_period_years"],
                                         })):
                yield f

        if recorder.steps:
            app.state.last_trail = recorder.to_dict()
            yield _sse("calculation_trail", recorder.to_dict())
        yield _sse("done", {})
    finally:
        reset_recorder(token)
        _TELEMETRY_CONTEXT.reset(ctx_token)


async def _pipeline_portfolio(app, message: str) -> AsyncIterator[str]:
    """Full multi-state portfolio scan. No exclusions — every pack, including GA.

    Answers the 'show me our complete credit picture across every state' question.
    """
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "portfolio"})
    recorder = TrailRecorder(title="Pending", citation="")
    token = set_recorder(recorder)
    try:
        yield _sse("status", {"phase": 3, "intent": "portfolio"})

        async for f in _stream_agent("OrchestratorAgent", f"User question:\n{_question(message)}\nIntent: full multi-state portfolio across every rule pack."):
            yield f

        result = tap(client_discovery(exclude_codes=[])).facts  # no exclusions — include GA + every other pack
        async for f in _stream_agent("CreditDiscoveryAgent", _brief(
                                         "List EVERY hit as a short bullet (jurisdiction, credit name, lifetime credit, citation). "
                                         "This is the full portfolio — do NOT exclude Georgia. "
                                         "Then call out which packs were considered but produced no hit, and why.",
                                         _without_totals(result),
                                     )):
            yield f

        totals = result["totals"]
        async for f in _stream_agent("ReportingAgent", _brief(
                                         f"Summarize the full multi-state portfolio for an exec. Original question:\n{_question(message)}",
                                         {"portfolio_total_annual_usd": totals["annual_credit_usd"],
                                          "portfolio_total_lifetime_usd": totals["lifetime_credit_usd"],
                                          "hit_count": totals["hit_count"],
                                          "hits": result["hits"]},
                                     )):
            yield f

        if recorder.steps:
            app.state.last_trail = recorder.to_dict()
            yield _sse("calculation_trail", recorder.to_dict())
        yield _sse("done", {})
    finally:
        reset_recorder(token)
        _TELEMETRY_CONTEXT.reset(ctx_token)


async def _pipeline_discovery(app, message: str) -> AsyncIterator[str]:
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "discovery"})
    recorder = TrailRecorder(title="Pending", citation="")
    token = set_recorder(recorder)
    try:
        yield _sse("status", {"phase": 3, "intent": "discovery"})

        async for f in _stream_agent("OrchestratorAgent", f"User question:\n{_question(message)}\nIntent: discover additional credits across the rule library."):
            yield f

        # Exclude GA_JTC since the user's asking what *other* credits apply.
        result = tap(client_discovery(exclude_codes=["GA_JTC"])).facts
        async for f in _stream_agent("CreditDiscoveryAgent", _brief(
                                         "List each hit as a short bullet (jurisdiction, credit name, "
                                         "rough lifetime credit, citation). Mention which packs were considered.",
                                         _without_totals(result),
                                     )):
            yield f

        # Reporting closes with an exec line about the discovery total.
        totals = result["totals"]
        async for f in _stream_agent("ReportingAgent", _brief(
                                         f"Summarize the discovery scan for an exec. Original question:\n{_question(message)}",
                                         {"total_other_credits_lifetime_usd": totals["lifetime_credit_usd"], "hit_count": totals["hit_count"], "hits": result["hits"]},
                                     )):
            yield f

        if recorder.steps:
            app.state.last_trail = recorder.to_dict()
            yield _sse("calculation_trail", recorder.to_dict())
        yield _sse("done", {})
    finally:
        reset_recorder(token)
        _TELEMETRY_CONTEXT.reset(ctx_token)
