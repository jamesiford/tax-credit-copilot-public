"""SSE chat endpoint with intent routing.

Five demo intents, each driving a different agent pipeline:

| Intent      | Trigger phrases                                   | Pipeline |
| ----------- | ------------------------------------------------- | -------- |
| eligibility | 'eligibility', 'jobs tax credit', default         | Orchestrator -> PayrollIngest -> Headcount -> CreditRules -> Reporting (state-aware via portfolio.chat_state_credit) |
| portfolio   | 'portfolio', 'all our states', 'every state'      | Orchestrator -> CreditDiscovery (no excludes) -> Reporting |
| discovery   | 'other credits', 'what else', 'discover'          | Orchestrator -> CreditDiscovery (excludes GA_JTC) -> Reporting |
| explain     | 'walk me through', 'how did you', 'explain'       | Reporting only, re-narrating the cached trail |
| situation   | 'situation', 'why would I call', 'brief me'       | ClientSituation only, over a deterministic claims brief (no payroll, no engine) |
| simulate    | 'what if', 'hired', 'simulate'                    | Orchestrator -> Headcount -> CreditRules -> Reporting (simulation tool) |

All numbers come from Python tools; agents only narrate the JSON they're handed.
The latest calculation trail is cached on app.state.last_trail so the 'explain'
intent can re-emit it without rerunning the whole pipeline.
"""
from __future__ import annotations

import asyncio
from contextvars import ContextVar
import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from tools.discovery import discover_credits
from tools.portfolio import (
    chat_client_context,
    chat_client_trend,
    chat_jobs_at_risk,
    chat_state_credit,
)
from tools.simulation import simulate_hiring
from domain.calculation.trail import TrailRecorder, reset_recorder, set_recorder

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])
_TELEMETRY_CONTEXT: ContextVar[dict[str, Any] | None] = ContextVar("chat_telemetry_context", default=None)


class ChatTurn(BaseModel):
    role: str
    text: str


class ChatRequest(BaseModel):
    message: str
    state: str | None = None
    client_id: int | None = None
    tax_year: int | None = None
    method: str = "min_max"
    #: Prior turns, so "their trend" and "since then" have a referent. Bounded
    #: by the caller; a conversation is context for ROUTING, never a source of
    #: figures — every number still comes from a tool.
    history: list[ChatTurn] = []
    #: The reader picked this client from a clarifying question. The sentence
    #: may still name another — they have chosen, and asking again would loop.
    client_confirmed: bool = False


def _normalise_chat_method(method: str | None) -> str:
    value = (method or "min_max").lower()
    if value not in {"min_max", "pay_period", "both"}:
        raise ValueError("method must be min_max | pay_period | both")
    return value


def _request_scope(req: ChatRequest) -> dict[str, Any]:
    if req.client_id is None or req.tax_year is None:
        raise ValueError(
            "This answer needs the selected client and tax year from the page. "
            "I will not guess against the default tenant."
        )

    method = _normalise_chat_method(req.method)
    state = (req.state or _detect_state(req.message) or "GA").upper()
    from application.queries._client_run import resolve_statute

    # NOT `resolve_client_run`. Every field below is statute or calendar; the
    # payroll it used to load was never read — `scope["run"]` had no consumer —
    # so every chat message paid a full client payroll read for metadata.
    run = resolve_statute(account_id=req.client_id, state=state, tax_year=req.tax_year)
    return {
        "state": run.state,
        "account_id": run.account_id,
        "tax_year": run.tax_year,
        "method": method,
        "program_code": run.program_code,
        "window": run.window,
        "floors": run.floors,
    }


def _chat_clients() -> list[Any]:
    """The book, as the resolver needs it. Empty rather than failing the turn."""
    from api.scope import _clients
    from application.chat_scope import ClientName

    try:
        return [ClientName(int(c["account_id"]), str(c["name"])) for c in _clients()]
    except Exception:  # noqa: BLE001 — no client list means no names to match
        log.warning("chat: client list unavailable; clarification disabled", exc_info=True)
        return []


def _referent(req: ChatRequest) -> Any:
    """Whose answer this is, or None when the reader already chose."""
    from application.chat_scope import resolve_referent

    if req.client_confirmed:
        return None
    clients = _chat_clients()
    if not clients:
        return None
    referent = resolve_referent(
        req.message, [t.model_dump() for t in req.history], req.client_id, clients,
    )
    return (referent, clients) if referent.clarify else None


def _candidate_year(client_id: int, req: ChatRequest) -> int | None:
    """The tax year a clarifying button would answer for, stated on the button.

    The page's year for the page's client. Otherwise the year the book ranks
    that client on — the cell carrying its reason to call, which is the year
    the row's own Ask button uses — so a button and the row agree. A client
    with no claims falls back to its latest calculation; one no run has reached
    offers no year, and its button cannot be pressed.
    """
    if client_id == req.client_id and req.tax_year is not None:
        return req.tax_year
    try:
        from application.queries.get_client_situation import GetClientSituationQuery
        from application.wiring import get_mediator

        lead = get_mediator().send(GetClientSituationQuery(client_id=client_id)).get("lead_tax_year")
        if lead is not None:
            return int(lead)
    except Exception:  # noqa: BLE001
        pass
    try:
        from application.wiring import get_run_manifest_repository

        manifest = get_run_manifest_repository().latest(client_id)
        return int(manifest.tax_year) if manifest is not None else None
    except Exception:  # noqa: BLE001
        return None


def _clarify_question(referent: Any, names: list[str]) -> str:
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" or {names[-1]}"
    if referent.reason == "names a different client from the one this chat is about":
        return (
            f"You asked about **{names[0]}**, but this chat is about **{names[1]}**. "
            f"Which one should I answer for?"
        )
    if len(names) == 1:
        return (
            f"Do you mean **{names[0]}**? No client is selected on the page, and I "
            f"won't guess — confirm and I'll answer for them."
        )
    if referent.reason == "no client is selected":
        return (
            f"Which client do you mean — {listed}? No client is selected on the page, "
            f"and I won't guess."
        )
    return (
        f"Which client do you mean — {listed}? I answer about one client at a time, "
        f"and I won't pick one for you."
    )


async def _clarify_stream(req: ChatRequest, referent: Any, clients: list[Any]) -> AsyncIterator[str]:
    """Ask which client, with one choice per candidate. Emits no `done`."""
    by_id = {c.client_id: c.name for c in clients}
    choices = [
        {"client_id": cid, "name": by_id.get(cid, f"Account {cid}"), "tax_year": _candidate_year(cid, req)}
        for cid in referent.candidates
    ]
    text = _clarify_question(referent, [c["name"] for c in choices])
    yield _sse("status", {"phase": 1, "echo": req.message, "clarify": True, "reason": referent.reason})
    yield _sse("agent_start", {"agent": "OrchestratorAgent"})
    yield _sse("token", {"agent": "OrchestratorAgent", "content": text})
    yield _sse("clarify", {"message": req.message, "reason": referent.reason, "choices": choices})
    yield _sse("agent_end", {"agent": "OrchestratorAgent"})


async def _clarify_only(req: ChatRequest, referent: Any, clients: list[Any]) -> AsyncIterator[str]:
    async for frame in _clarify_stream(req, referent, clients):
        yield frame
    yield _sse("done", {})


async def _missing_scope_stream(message: str, *, detail: str | None = None) -> AsyncIterator[str]:
    text = detail or (
        "This answer needs the selected client and tax year from the page. "
        "I will not guess against the default tenant or silently answer for the wrong scope."
    )
    yield _sse("status", {"phase": 1, "echo": message, "scope_missing": True, "note": text})
    yield _sse("agent_start", {"agent": "OrchestratorAgent"})
    yield _sse("token", {"agent": "OrchestratorAgent", "content": text})
    yield _sse("agent_end", {"agent": "OrchestratorAgent"})
    yield _sse("done", {})


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, separators=(',', ':'))}\n\n"


def _now_iso() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _append_audit_event(app, event: dict[str, Any]) -> None:
    if not hasattr(app.state, "audit_events"):
        app.state.audit_events = []
    app.state.audit_events.append(event)
    if len(app.state.audit_events) > 2000:
        app.state.audit_events = app.state.audit_events[-2000:]


def _record_agent_metric(app, *, agent: str, ok: bool, elapsed_ms: int, char_count: int) -> None:
    if not hasattr(app.state, "agent_metrics"):
        app.state.agent_metrics = {}
    cur = app.state.agent_metrics.get(agent, {
        "runs": 0,
        "failures": 0,
        "total_ms": 0,
        "avg_ms": 0,
        "last_run_at": None,
        "last_status": "unknown",
        "chars_streamed": 0,
    })
    cur["runs"] += 1
    if not ok:
        cur["failures"] += 1
    cur["total_ms"] += elapsed_ms
    cur["avg_ms"] = round(cur["total_ms"] / max(1, cur["runs"]))
    cur["last_run_at"] = _now_iso()
    cur["last_status"] = "ok" if ok else "error"
    cur["chars_streamed"] += char_count
    app.state.agent_metrics[agent] = cur


def _append_span(app, span: dict[str, Any]) -> None:
    if not hasattr(app.state, "agent_spans"):
        app.state.agent_spans = []
    app.state.agent_spans.append(span)
    if len(app.state.agent_spans) > 3000:
        app.state.agent_spans = app.state.agent_spans[-3000:]


# ---------------- intent detection ----------------

def _detect_state(message: str) -> str:
    m = f" {message.lower()} "
    if "georgia" in m or " ga " in m or "atlanta" in m or "savannah" in m or "macon" in m:
        return "GA"
    if "new york" in m or " ny " in m:
        return "NY"
    if "south carolina" in m or " sc " in m or " charleston" in m or "greenville" in m:
        return "SC"
    if "texas" in m or " tx " in m or "austin" in m or "houston" in m or " dallas" in m:
        return "TX"
    if "north carolina" in m or " nc " in m or "charlotte" in m or "raleigh" in m:
        return "NC"
    if "tennessee" in m or " tn " in m or "nashville" in m or "memphis" in m:
        return "TN"
    if "florida" in m or " fl " in m or "jacksonville" in m or "miami" in m or "orlando" in m:
        return "FL"
    if " ohio" in m or " oh " in m or "columbus" in m or "cincinnati" in m or "cleveland" in m:
        return "OH"
    if "colorado" in m or " co " in m or "denver" in m or "boulder" in m:
        return "CO"
    if "virginia" in m or " va " in m or "tysons" in m or "richmond" in m or "arlington" in m:
        return "VA"
    return "GA"


#: Everything the chat can actually answer, and what each one costs.
#:
#: A plan is validated against these names. The router is a language model and
#: will happily invent `trend_analysis` or `client_deep_dive`; an unrecognised
#: intent is DROPPED rather than dispatched, because a made-up intent that
#: silently runs the default pipeline answers a question nobody asked.
CAPABILITIES: dict[str, str] = {
    "book": (
        "who to call ACROSS EVERY CLIENT, ranked by why — the portfolio question. "
        "Needs no client selected; naming one would be the opposite of what was asked."
    ),
    "situation": "why this client is worth calling — bands, programmes, years. Claims only.",
    "eligibility": "the credit figure and headcount for the selected client-year.",
    "at_risk": (
        "which employees ALREADY counted toward the credit sit close enough to a "
        "statutory floor that they could fall out of it — jobs the client could lose."
    ),
    "trend": "how a client has moved across years, and whether they have been eligible since their base year.",
    "multi_state": (
        "which PROGRAMMES across every state one client may qualify for — a rule-pack "
        "scan for the selected client, NOT a view across clients."
    ),
    "discovery": "other programmes the client may qualify for, excluding the one in scope.",
    "simulate": "what-if: hiring, losing, hours or wages against the statutory engine.",
    "explain": "re-narrate the cached calculation trail, step by step.",
}

#: Which capabilities are about ONE client, and therefore cannot be answered
#: without one selected.
#:
#: The chat used to refuse every question without a client, which made the
#: portfolio question — "who should we reach out to?" — unanswerable from the
#: title bar, where no client is selected BY DESIGN. The refusal itself is
#: right and stays: it exists so nothing silently answers against the default
#: tenant. It just belongs per capability rather than across the whole door.
_NEEDS_CLIENT: frozenset[str] = frozenset({
    "situation", "eligibility", "at_risk", "trend", "multi_state",
    "discovery", "simulate", "explain",
})

#: Keyword routing, kept as the FALLBACK rather than the primary path. It is
#: what answers when the router is unavailable or returns nothing usable, and
#: it is why an unconfigured Foundry project still gives a sensible reply.
_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("explain", ("walk me through", "how did you", "how do you", "explain",
                 "show your work", "show the calculation", "show me the calculation")),
    # FIRST, and before `multi_state`. "Who should we reach out to" is the
    # portfolio question and must not be captured by a rule-pack scan whose
    # tokens overlap heavily with it.
    ("book", ("who should we", "who do we", "who to call", "which client",
              "which clients", "reach out", "call first", "best client",
              "next best customer", "next best client", "best customer",
              "targeting", "who to target", "should we target", "top target",
              "target list",
              "across our clients", "across the book", "our book",
              "top of the list", "prioriti", "worth contacting")),
    # Before `simulate`: "may fall off" and "at risk" are questions about the
    # CURRENT population, not hypotheticals, and the words overlap heavily.
    ("at_risk", ("fall off", "fall out", "falling off", "at risk", "drop off",
                 "lose eligibility", "losing eligibility", "close to the threshold",
                 "near the threshold", "barely", "marginal", "fragile",
                 "could we lose", "might we lose", "keep them")),
    ("trend", ("trend", "since their base year", "since the base year", "base year",
               "over the years", "year over year", "year-over-year", "history",
               "subsequent years", "each year", "every year", "prior years")),
    ("situation", ("situation", "why would i call", "why call", "overview of this client",
                   "client overview", "where do they stand", "what should i say",
                   "brief me", "worth calling", "why are they")),
    ("simulate", ("what if", "hired", "hire ", "simulate", "what would happen", "next month")),
    ("multi_state", ("portfolio", "every state", "all our states", "all states",
                     "all jurisdictions", "full credit picture", "complete credit picture",
                     "across our footprint", "full picture", "complete picture",
                     "every credit", "all credits", "entire footprint", "multi-state")),
    ("discovery", ("other credits", "other credit", "what else", "discover",
                   "may also qualify", "might we qualify", "additional credits")),
)


def _keyword_intents(message: str) -> list[str]:
    """Every intent the words suggest, in call order — not just the first.

    Returns a LIST because one sentence is routinely two questions: "what is
    their trend, and have they been eligible since their base year" is one
    intent, but "brief me on them and what else might they qualify for" is two.
    """
    m = message.lower()
    hits = [name for name, tokens in _KEYWORDS if any(t in m for t in tokens)]
    return hits or ["eligibility"]


def _validate_plan(raw: Any, message: str) -> list[str]:
    """Coerce whatever the router returned into intents this app can run.

    Order is preserved and duplicates collapse. An empty or unusable plan falls
    back to keywords rather than failing the turn — a chat that answers nothing
    because a router hiccupped is worse than one that answers approximately.
    """
    intents: list[str] = []
    if isinstance(raw, dict):
        raw = raw.get("intents")
    if isinstance(raw, str):
        raw = [raw]
    if isinstance(raw, list):
        for item in raw:
            name = str(item).strip().lower()
            if name in CAPABILITIES and name not in intents:
                intents.append(name)
    return intents or _keyword_intents(message)


async def _plan(registry, message: str, history: list[ChatTurn], scope: dict[str, Any]) -> list[str]:
    """Ask the router which capabilities this question needs.

    The model chooses WHICH deterministic tool runs; it never produces a
    figure. That is the line ADR-004 draws, and routing sits on the safe side
    of it — the alternative is keyword matching, which cannot split "brief me
    and tell me what else they qualify for" into two answers.
    """
    record = registry.by_name.get("OrchestratorAgent") if registry else None
    if record is None:
        return _keyword_intents(message)

    turns = "\n".join(f"{t.role}: {t.text}" for t in history[-6:])
    prompt = (
        "Route this question to one or more capabilities.\n\n"
        f"CAPABILITIES:\n{json.dumps(CAPABILITIES, indent=2)}\n\n"
        f"CONVERSATION SO FAR:\n{turns or '(none)'}\n\n"
        f"SELECTED SCOPE: client_id={scope.get('account_id')}, "
        f"tax_year={scope.get('tax_year')}, state={scope.get('state')}\n\n"
        f"QUESTION: {message}\n\n"
        'Reply with JSON ONLY: {"intents": ["name", ...]}. Use the exact names '
        "above. Include every capability the question needs, in the order they "
        "should be answered. Do not invent names. Do not explain."
    )

    text = ""
    try:
        async for update in record.agent.run(prompt, stream=True):
            text += getattr(update, "text", None) or ""
    except Exception:  # noqa: BLE001 — routing must never fail the turn
        log.exception("router failed; falling back to keywords")
        return _keyword_intents(message)

    try:
        start, end = text.index("{"), text.rindex("}") + 1
        return _validate_plan(json.loads(text[start:end]), message)
    except (ValueError, json.JSONDecodeError):
        return _validate_plan(text, message)


def _detect_intent(message: str) -> str:
    """The single best intent. Kept for callers that can only run one."""
    return _keyword_intents(message)[0]



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


# ---------------- agent streaming helper ----------------

async def _stream_agent(agent_name: str, foundry_agent, prompt: str) -> AsyncIterator[str]:
    yield _sse("agent_start", {"agent": agent_name})
    started = time.perf_counter()
    char_count = 0
    ok = True
    error_text = None
    try:
        async for update in foundry_agent.run(prompt, stream=True):
            text = getattr(update, "text", None) or ""
            if text:
                char_count += len(text)
                yield _sse("token", {"agent": agent_name, "content": text})
    except Exception as e:  # noqa: BLE001
        log.exception("Agent %s failed", agent_name)
        ok = False
        error_text = str(e)
        yield _sse("token", {"agent": agent_name, "content": f"[{agent_name} failed: {e}]"})

    ctx = _TELEMETRY_CONTEXT.get()
    if ctx is not None:
        app = ctx["app"]
        elapsed_ms = round((time.perf_counter() - started) * 1000)
        span = {
            "span_id": str(uuid.uuid4()),
            "request_id": ctx["request_id"],
            "timestamp": _now_iso(),
            "intent": ctx["intent"],
            "agent": agent_name,
            "elapsed_ms": elapsed_ms,
            "char_count": char_count,
            "status": "ok" if ok else "error",
            "error": error_text,
        }
        _append_span(app, span)
        _record_agent_metric(app, agent=agent_name, ok=ok, elapsed_ms=elapsed_ms, char_count=char_count)
        _append_audit_event(app, {
            "timestamp": span["timestamp"],
            "type": "agent_run",
            "request_id": ctx["request_id"],
            "intent": ctx["intent"],
            "agent": agent_name,
            "status": span["status"],
            "elapsed_ms": elapsed_ms,
        })
    yield _sse("agent_end", {"agent": agent_name})


def _brief(label: str, payload: dict[str, Any]) -> str:
    return f"{label}\n\nJSON:\n{json.dumps(payload, indent=2)}"


# ---------------- pipelines ----------------

async def _pipeline_eligibility(app, registry, message: str, *, scope: dict[str, Any] | None = None) -> AsyncIterator[str]:
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
        async for f in _stream_agent("OrchestratorAgent", registry["OrchestratorAgent"].agent,
                                     f"User question: {message}\n{scope_text}"):
            yield f

        # What the RUN concluded about this client, not a synthetic fixture.
        # `load_payroll_snapshot` read backend/data/payroll.csv and cited itself
        # as "not from a client feed", so the narration described 9,477 invented
        # employees while the question was about this client.
        #
        # No unscoped branch: `chat()` refuses a request without a client and a
        # tax year before dispatching, so both are always present here.
        context = chat_client_context(account_id=account_id, tax_year=tax_year)
        window = scope.get("window")
        snapshot = {
            "source": "tcc_gold — read from the run that computed it",
            "selected_client_id": account_id,
            "selected_tax_year": tax_year,
            "state": state,
            "calculated": context.get("calculated", False),
            "average_headcount": context.get("current_average"),
            "prior_year_average_headcount": context.get("prior_average"),
            "run_id": context.get("run_id"),
            "fiscal_window": {
                "begin": window.begin.isoformat() if window is not None else None,
                "end": window.end.isoformat() if window is not None else None,
            },
        }
        if not context.get("calculated"):
            snapshot["note"] = (
                f"No calculated run holds TY{tax_year} for this client. That is "
                f"not a zero — say so rather than reporting a figure."
            )
        async for f in _stream_agent("PayrollIngestAgent", registry["PayrollIngestAgent"].agent,
                                     _brief(f"Confirm the payroll snapshot in scope for state={state}.", snapshot)):
            yield f

        credit = chat_state_credit(
            state, tax_year=tax_year, account_id=account_id,
            current_average=context.get("current_average"),
            prior_average=context.get("prior_average"),
        )
        if not credit.get("no_state_pack"):
            async for f in _stream_agent("HeadcountAgent", registry["HeadcountAgent"].agent,
                                         _brief(f"Report the statutory headcount picture for {state} in one sentence.", {
                                             "state": state,
                                             "client_id": account_id,
                                             "tax_year": tax_year,
                                             "average_headcount": credit.get("average_headcount"),
                                             "prior_period_average_headcount": credit.get("prior_period_average_headcount"),
                                             "qualifying_jobs": credit.get("qualifying_jobs"),
                                         })):
                yield f


        if credit.get("no_state_pack"):
            async for f in _stream_agent("CreditRulesAgent", registry["CreditRulesAgent"].agent,
                                         _brief(
                                             f"Tell the user in one sentence that we have no state rule pack for {state}, "
                                             "and that federal credits like WOTC may still apply via the portfolio scan.",
                                             {"state": state, "message": credit["message"]},
                                         )):
                yield f
            async for f in _stream_agent("ReportingAgent", registry["ReportingAgent"].agent,
                                         _brief(
                                             f"Summarize for an exec in one sentence. Original question: {message}",
                                             {"state": state, "no_state_pack": True,
                                              "available_state_packs": ["GA", "NY", "SC", "NC", "TN", "FL", "OH", "CO", "VA"],
                                              "suggested_next_question": "Show me our full credit portfolio across every state."},
                                         )):
                yield f
        else:
            async for f in _stream_agent("CreditRulesAgent", registry["CreditRulesAgent"].agent,
                                         _brief(f"Report the {credit['credit_name']} result in one sentence.", credit)):
                yield f

            async for f in _stream_agent("ReportingAgent", registry["ReportingAgent"].agent,
                                         _brief(f"Summarize for an exec. Original question: {message}", {
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


async def _pipeline_portfolio(app, registry, message: str) -> AsyncIterator[str]:
    """Full multi-state portfolio scan. No exclusions — every pack, including GA.

    Answers the 'show me our complete credit picture across every state' question.
    """
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "portfolio"})
    recorder = TrailRecorder(title="Pending", citation="")
    token = set_recorder(recorder)
    try:
        yield _sse("status", {"phase": 3, "intent": "portfolio"})

        async for f in _stream_agent("OrchestratorAgent", registry["OrchestratorAgent"].agent,
                                     f"User question: {message}\nIntent: full multi-state portfolio across every rule pack."):
            yield f

        result = discover_credits()  # no exclusions — include GA + every other pack
        async for f in _stream_agent("CreditDiscoveryAgent", registry["CreditDiscoveryAgent"].agent,
                                     _brief(
                                         "List EVERY hit as a short bullet (jurisdiction, credit name, lifetime credit, citation). "
                                         "This is the full portfolio — do NOT exclude Georgia. "
                                         "Then call out which packs were considered but produced no hit, and why.",
                                         result,
                                     )):
            yield f

        total_lifetime = sum(h["lifetime_credit_usd"] for h in result["hits"])
        total_annual = sum(h["annual_credit_usd"] for h in result["hits"])
        async for f in _stream_agent("ReportingAgent", registry["ReportingAgent"].agent,
                                     _brief(
                                         f"Summarize the full multi-state portfolio for an exec. Original question: {message}",
                                         {"portfolio_total_annual_usd": total_annual,
                                          "portfolio_total_lifetime_usd": total_lifetime,
                                          "hit_count": len(result["hits"]),
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


async def _pipeline_discovery(app, registry, message: str) -> AsyncIterator[str]:
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "discovery"})
    recorder = TrailRecorder(title="Pending", citation="")
    token = set_recorder(recorder)
    try:
        yield _sse("status", {"phase": 3, "intent": "discovery"})

        async for f in _stream_agent("OrchestratorAgent", registry["OrchestratorAgent"].agent,
                                     f"User question: {message}\nIntent: discover additional credits across the rule library."):
            yield f

        # Exclude GA_JTC since the user's asking what *other* credits apply.
        result = discover_credits(exclude_codes=["GA_JTC"])
        async for f in _stream_agent("CreditDiscoveryAgent", registry["CreditDiscoveryAgent"].agent,
                                     _brief(
                                         "List each hit as a short bullet (jurisdiction, credit name, "
                                         "rough lifetime credit, citation). Mention which packs were considered.",
                                         result,
                                     )):
            yield f

        # Reporting closes with an exec line about the discovery total.
        total_lifetime = sum(h["lifetime_credit_usd"] for h in result["hits"])
        async for f in _stream_agent("ReportingAgent", registry["ReportingAgent"].agent,
                                     _brief(
                                         f"Summarize the discovery scan for an exec. Original question: {message}",
                                         {"total_other_credits_lifetime_usd": total_lifetime, "hit_count": len(result["hits"]), "hits": result["hits"]},
                                     )):
            yield f

        if recorder.steps:
            app.state.last_trail = recorder.to_dict()
            yield _sse("calculation_trail", recorder.to_dict())
        yield _sse("done", {})
    finally:
        reset_recorder(token)
        _TELEMETRY_CONTEXT.reset(ctx_token)


async def _pipeline_situation(app, registry, message: str, *, scope: dict[str, Any]) -> AsyncIterator[str]:
    """Why this client is worth calling. One brief, one narration.

    No engine and no payroll: the ranking is over recorded claims, so a per-row
    button on the book costs a query. The Orchestrator step is skipped — with a
    single deterministic brief there is no routing to acknowledge, and a second
    agent restating the scope would be narration for its own sake.
    """
    from application.queries.get_client_situation import GetClientSituationQuery

    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "situation"})
    try:
        account_id = scope.get("account_id")
        tax_year = scope.get("tax_year")
        yield _sse("status", {
            "phase": 3, "intent": "situation",
            "client_id": account_id, "tax_year": tax_year,
        })

        from application.wiring import get_mediator

        brief = get_mediator().send(
            GetClientSituationQuery(client_id=account_id, tax_year=tax_year)
        )
        async for f in _stream_agent("ClientSituationAgent", registry["ClientSituationAgent"].agent,
                                     _brief(f"User question: {message}", brief)):
            yield f
        yield _sse("done", {})
    finally:
        _TELEMETRY_CONTEXT.reset(ctx_token)


async def _pipeline_explain(app, registry, message: str) -> AsyncIterator[str]:
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "explain"})
    try:
        yield _sse("status", {"phase": 3, "intent": "explain"})

        cached = getattr(app.state, "last_trail", None)
        if not cached:
            async for f in _stream_agent("OrchestratorAgent", registry["OrchestratorAgent"].agent,
                                         "User asked you to walk through the calculation, but no prior eligibility "
                                         "result is cached. Reply in one sentence asking them to run an eligibility "
                                         "question first."):
                yield f
            yield _sse("done", {})
            return

        async for f in _stream_agent("ReportingAgent", registry["ReportingAgent"].agent,
                                     _brief(
                                         "Walk an exec through this calculation step by step in 3-5 sentences. "
                                         "Cite the statute. End by reminding them every number above is sourced from a JSON rule pack, not from the model.",
                                         cached,
                                     )):
            yield f

        yield _sse("calculation_trail", cached)
        yield _sse("done", {})
    finally:
        _TELEMETRY_CONTEXT.reset(ctx_token)


async def _pipeline_simulate(app, registry, message: str) -> AsyncIterator[str]:
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
        async for f in _stream_agent("OrchestratorAgent", registry["OrchestratorAgent"].agent, ack):
            yield f

        sim = simulate_hiring(location=city, new_hires=new_hires)

        async for f in _stream_agent("HeadcountAgent", registry["HeadcountAgent"].agent,
                                     _brief(
                                         f"Report the projected headcount shift for {city} in one sentence.",
                                         {"location": city, "headcount_change": new_hires, "direction": direction_verb,
                                          "baseline_net_new_headcount": sim["baseline"]["net_new_headcount"],
                                          "projected_net_new_headcount": sim["projected"]["net_new_headcount"]},
                                     )):
            yield f

        async for f in _stream_agent("CreditRulesAgent", registry["CreditRulesAgent"].agent,
                                     _brief("Report the projected credit in one sentence.", {
                                         "direction": direction_verb,
                                         "baseline_annual_credit_usd": sim["baseline"]["annual_credit_usd"],
                                         "projected_annual_credit_usd": sim["projected"]["annual_credit_usd"],
                                         "projected_lifetime_credit_usd": sim["projected"]["lifetime_credit_usd"],
                                         "citation": sim["citation"],
                                     })):
            yield f

        async for f in _stream_agent("ReportingAgent", registry["ReportingAgent"].agent,
                                     _brief(
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


#: How the page says each band. The chat reads it aloud beside the page, so it
#: must use the page's words — `lib/priority.js` — not the enum ids, which are
#: storage vocabulary ("unclaimed_at_scale" is labelled "Identified" on screen
#: precisely because no filing is held).
_BAND_LABEL = {
    "exposed": "Exposed",
    "on_the_line": "On the line",
    "declining": "Declining",
    "unclaimed_at_scale": "Identified",
    "not_assessed": "Not assessed",
    "settled": "Nothing found",
}


def _book_brief(limit: int = 8) -> dict[str, Any]:
    """The book exactly as the page ranks it, read from the page's own endpoint.

    It used to come from a second ranking over claim cells, filtered by the
    shell's year. The book has no year, and that ranking had no `declining`
    overlay — so the headline question answered "Northwind first" while the
    page behind the chat said Ironbridge. One ranking, one read.
    """
    from api.claims import portfolio_v2

    page = portfolio_v2(
        year=None, program=None, outcome=None, scope=None, near=None, status=None,
        sort="priority", order="asc", limit=limit, offset=0,
    )
    items = page.get("items") or []
    if not items:
        return {
            "calculated": False,
            "message": (
                "No client has been assessed yet. There is nothing to rank — "
                "that is not the same as nobody being worth calling."
            ),
        }
    clients = []
    for position, row in enumerate(items, start=1):
        band = row.get("priority_band")
        trend = row.get("trend") or {}
        clients.append({
            "position": position,
            "client_name": row.get("client_name") or f"Account {row.get('client_id')}",
            "reason": _BAND_LABEL.get(band, band),
            "program_code": row.get("program_code"),
            "tax_year": row.get("tax_year"),
            "identified_usd": row.get("identified_usd"),
            "jobs_margin": row.get("jobs_margin"),
            "credit_earned_on_trend_usd": trend.get("credit_earned_usd") if band == "declining" else None,
            "provenance_verified": row.get("provenance_verified"),
        })
    return {
        "calculated": True,
        "total_clients": page.get("total_clients"),
        "assessed_clients": page.get("assessed_clients"),
        "clients": clients,
        "ranking_note": (
            "Ordered by what inaction costs, not by size, and in the same order "
            "as the page. 'On the line' outranks 'Identified' because a threshold "
            "missed at year end is gone, while an unclaimed credit is recoverable "
            "retroactively. 'Declining' is a forecast about a year nobody has "
            "filed, not a finding against a filed return."
        ),
        "claimed_is_unverified": any(not c.get("provenance_verified", True) for c in clients),
    }


async def _pipeline_book(app, registry, message: str, *, scope: dict[str, Any]) -> AsyncIterator[str]:
    """Who to call across every client. The one brief that needs NO client."""
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "book"})
    try:
        # NO YEAR, whatever the shell sends. "Who do I call" is a question about
        # a client across every year they hold; the shell's year was flattening
        # the bands exactly as it once did on the page.
        yield _sse("status", {"phase": 3, "intent": "book"})

        brief = _book_brief()
        async for f in _stream_agent("ClientSituationAgent", registry["ClientSituationAgent"].agent,
                                     _brief(
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


async def _pipeline_at_risk(app, registry, message: str, *, scope: dict[str, Any]) -> AsyncIterator[str]:
    """Which counted jobs could fall out of the credit."""
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "at_risk"})
    try:
        account_id = scope.get("account_id")
        tax_year = scope.get("tax_year")
        state = scope.get("state")
        method = scope.get("method") or "min_max"
        if method == "both":
            method = "min_max"
        yield _sse("status", {
            "phase": 3, "intent": "at_risk",
            "client_id": account_id, "tax_year": tax_year,
        })

        brief = chat_jobs_at_risk(
            account_id=account_id, state=state, tax_year=tax_year, method=method,
        )
        async for f in _stream_agent("ClientSituationAgent", registry["ClientSituationAgent"].agent,
                                     _brief(
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


async def _pipeline_trend(app, registry, message: str, *, scope: dict[str, Any]) -> AsyncIterator[str]:
    """How a client has moved across years. One Gold read, one narration."""
    request_id = str(uuid.uuid4())
    ctx_token = _TELEMETRY_CONTEXT.set({"app": app, "request_id": request_id, "intent": "trend"})
    try:
        account_id = scope.get("account_id")
        yield _sse("status", {"phase": 3, "intent": "trend", "client_id": account_id})

        brief = chat_client_trend(account_id=account_id)
        async for f in _stream_agent("ClientSituationAgent", registry["ClientSituationAgent"].agent,
                                     _brief(
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


# ---------------- fallback (no Foundry) ----------------

async def _stub_stream(message: str) -> AsyncIterator[str]:
    yield _sse("status", {"phase": 1, "echo": message, "note": "Foundry not configured; scripted stream."})
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


# ---------------- endpoint ----------------

@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    app = request.app
    registry = getattr(app.state, "registry", None)
    needed = ("OrchestratorAgent", "PayrollIngestAgent", "HeadcountAgent",
              "CreditRulesAgent", "CreditDiscoveryAgent", "ReportingAgent",
              "ClientSituationAgent")

    # The scope refusal survives, and must not depend on Foundry being
    # configured — it is about answering for the wrong company, not about
    # routing. Checked with KEYWORDS so it needs no model: if every capability
    # the words suggest is client-scoped and no client is selected, decline
    # here. "Who should we reach out to?" is asked from the title bar where no
    # client is selected BY DESIGN, so it passes and `_dispatch` does the
    # authoritative per-capability check.
    no_client = req.client_id is None or req.tax_year is None
    keyword_plan = _keyword_intents(req.message)
    # Which client, BEFORE any model is involved. When every capability the
    # words suggest is about one client and that client is not unambiguous,
    # ask. `_dispatch` re-checks against the router's plan.
    clarify = (
        _referent(req) if all(i in _NEEDS_CLIENT for i in keyword_plan) else None
    )
    if clarify is not None:
        stream = _clarify_only(req, *clarify)
    elif no_client and all(i in _NEEDS_CLIENT for i in keyword_plan):
        stream = _missing_scope_stream(req.message)
    elif registry is None or any(name not in registry.by_name for name in needed):
        stream = _stub_stream(req.message)
    else:
        stream = _dispatch(app, registry, req, scope=None)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _run_intent(app, registry, intent: str, message: str, scope: dict[str, Any]):
    """One intent to one pipeline. The only place that mapping exists."""
    if intent == "discovery":
        return _pipeline_discovery(app, registry, message)
    if intent == "book":
        return _pipeline_book(app, registry, message, scope=scope)
    if intent == "multi_state":
        return _pipeline_portfolio(app, registry, message)
    if intent == "situation":
        return _pipeline_situation(app, registry, message, scope=scope)
    if intent == "trend":
        return _pipeline_trend(app, registry, message, scope=scope)
    if intent == "at_risk":
        return _pipeline_at_risk(app, registry, message, scope=scope)
    if intent == "explain":
        return _pipeline_explain(app, registry, message)
    if intent == "simulate":
        return _pipeline_simulate(app, registry, message)
    return _pipeline_eligibility(app, registry, message, scope=scope)


async def _dispatch(app, registry, req: ChatRequest, *, scope: dict[str, Any] | None = None) -> AsyncIterator[str]:
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
    intents = await _plan(registry, req.message, req.history, planning_scope)

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
            async for frame in _run_intent(app, registry, intent, req.message, planning_scope):
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
        async for frame in _run_intent(app, registry, intent, req.message, resolved or planning_scope):
            if frame.startswith("event: done") and position < len(intents) - 1:
                continue
            yield frame
