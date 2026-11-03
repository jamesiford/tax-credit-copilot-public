"""Routing: what the chat can answer, and how one question becomes several.

The router is a language model, so the DETERMINISTIC half lives here — validation,
the keyword fallback and splitting. A model that invents `trend_analysis` must not
be able to dispatch it, and a model that is unavailable must not take the feature
down with it.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from api.chat.models import ChatTurn
from application.ai.requests import RouteQuestionQuery
from application.capabilities.catalog import CAPABILITIES

log = logging.getLogger(__name__)


#: Everything the chat can actually answer, and what each one costs, lives in
#: `application/capabilities/catalog.py` — `CAPABILITIES` and `_NEEDS_CLIENT`
#: are imported at the top of this module so there is one list. A plan is
#: validated against those names: the router is a language model and will invent
#: `trend_analysis`, and an unrecognised intent is DROPPED, never dispatched.

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


def _routing_prompt(message: str, history: list[ChatTurn], scope: dict[str, Any]) -> str:
    turns = "\n".join(f"{t.role}: {t.text}" for t in history[-6:])
    return (
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


async def _plan(message: str, history: list[ChatTurn], scope: dict[str, Any]) -> list[str]:
    """Ask the router which capabilities this question needs.

    The model chooses WHICH deterministic tool runs; it never produces a
    figure. That is the line ADR-004 draws, and routing sits on the safe side
    of it — the alternative is keyword matching, which cannot split "brief me
    and tell me what else they qualify for" into two answers.

    With no model available the keyword fallback answers; a router that errors
    must never fail the turn.
    """
    from application.wiring import get_mediator, get_narration_service
    from application.ai.handlers.route import ROUTER_AGENT

    if not get_narration_service().available([ROUTER_AGENT]):
        return _keyword_intents(message)

    text = ""
    try:
        async for event in get_mediator().stream(RouteQuestionQuery(prompt=_routing_prompt(message, history, scope))):
            text += getattr(event, "text", "") or ""
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
