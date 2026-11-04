"""SSE chat endpoint with intent routing.

Nine intents, each driving a different agent pipeline:

| Intent      | Trigger phrases                                   | Pipeline |
| ----------- | ------------------------------------------------- | -------- |
| eligibility | 'eligibility', 'jobs tax credit', default         | Orchestrator -> PayrollIngest -> Headcount -> CreditRules -> Reporting |
| multi_state | 'portfolio', 'all our states', 'every state'      | Orchestrator -> CreditDiscovery (no excludes) -> Reporting |
| discovery   | 'other credits', 'what else', 'discover'          | Orchestrator -> CreditDiscovery (excludes GA_JTC) -> Reporting |
| explain     | 'walk me through', 'how did you', 'explain'       | Reporting only, re-narrating the cached trail |
| situation   | 'situation', 'why would I call', 'brief me'       | ClientSituation only, over a deterministic claims brief |
| simulate    | 'what if', 'hired', 'simulate'                    | Orchestrator -> Headcount -> CreditRules -> Reporting |
| book, at_risk, trend | see `application/capabilities/catalog.py`  | ClientSituation over one deterministic brief |

All numbers come from Python tools; agents only narrate the JSON they're handed.
The latest calculation trail is cached on app.state.last_trail so the 'explain'
intent can re-emit it without rerunning the whole pipeline.

Model access goes through the mediator (`NarrateBriefQuery`, `RouteQuestionQuery`)
— no SDK type is visible here [AI-02]. The package is split by responsibility:

    models        the request       scope       whose answer this is, clarification
    routing       intents and plan  narration   one agent's stream as SSE frames
    sse           framing, spans    dispatch    route, split, delegate, bundle
    pipelines_*   the pipelines
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.chat.dispatch import _dispatch, _run_intent, _stub_stream
from api.chat.models import ChatRequest, ChatTurn, _normalise_chat_method
from api.chat.narration import _brief, _record_agent_action, _stream_agent
from api.chat.pipelines_briefs import _book_brief
from api.chat.routing import _KEYWORDS, _detect_intent, _keyword_intents, _plan, _validate_plan
from api.chat.scope import (
    _candidate_year, _chat_clients, _clarify_only, _detect_state, _missing_scope_stream, _referent,
    _request_scope,
)
from api.chat.sse import _ACTOR, _AUTHENTICATED, _TELEMETRY_CONTEXT, _sse
from application.capabilities.catalog import CAPABILITIES, CHAT_INTENT_TOOL, NEEDS_CLIENT as _NEEDS_CLIENT

__all__ = [
    "CAPABILITIES", "CHAT_INTENT_TOOL", "ChatRequest", "ChatTurn", "router", "chat",
    "_ACTOR", "_KEYWORDS", "_NEEDS_CLIENT", "_TELEMETRY_CONTEXT", "_book_brief", "_brief",
    "_candidate_year", "_chat_clients", "_detect_intent", "_detect_state", "_dispatch",
    "_keyword_intents", "_normalise_chat_method", "_plan", "_record_agent_action", "_request_scope",
    "_run_intent", "_sse", "_stream_agent", "_validate_plan",
]

router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat")
async def chat(req: ChatRequest, request: Request) -> StreamingResponse:
    from api.auth import current_principal
    from application.ai.specs import CHAT_PIPELINE_AGENTS
    from application.services import get_narration_service

    principal = current_principal(request)
    _ACTOR.set(principal.actor if principal.authenticated else None)
    _AUTHENTICATED.set(bool(principal.authenticated))
    app = request.app

    # The scope refusal survives, and must not depend on a model being configured —
    # it is about answering for the wrong company, not about routing. Checked
    # with KEYWORDS so it needs no model: if every capability the words suggest
    # is client-scoped and no client is selected, decline here. "Who should we
    # reach out to?" is asked from the title bar where no client is selected BY
    # DESIGN, so it passes and `_dispatch` does the authoritative per-capability
    # check.
    no_client = req.client_id is None or req.tax_year is None
    keyword_plan = _keyword_intents(req.message)
    # Which client, BEFORE any model is involved. When every capability the
    # words suggest is about one client and that client is not unambiguous,
    # ask. `_dispatch` re-checks against the router's plan.
    clarify = _referent(req) if all(i in _NEEDS_CLIENT for i in keyword_plan) else None
    if clarify is not None:
        stream = _clarify_only(req, *clarify)
    elif no_client and all(i in _NEEDS_CLIENT for i in keyword_plan):
        stream = _missing_scope_stream(req.message)
    elif not get_narration_service().available(CHAT_PIPELINE_AGENTS):
        stream = _stub_stream(req.message)
    else:
        stream = _dispatch(app, req, scope=None)
    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
