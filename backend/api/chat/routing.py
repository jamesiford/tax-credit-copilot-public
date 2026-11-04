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
from application.chat_keywords import KEYWORDS as _KEYWORDS  # noqa: F401 - re-exported
from application.chat_keywords import keyword_intents as _keyword_intents

log = logging.getLogger(__name__)


#: Everything the chat can actually answer, and what each one costs, lives in
#: `application/capabilities/catalog.py` — `CAPABILITIES` and `_NEEDS_CLIENT`
#: are imported at the top of this module so there is one list. A plan is
#: validated against those names: the router is a language model and will invent
#: `trend_analysis`, and an unrecognised intent is DROPPED, never dispatched.

#: Keyword routing lives in `application/chat_keywords.py` (standard library only, so the
#: channel orchestrator shares the exact table). The names are imported above.


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
    from application.ai.safety.untrusted import UntrustedText

    # "copilot", not "assistant": a line starting `assistant:` is how a forged turn looks.
    labels = {"assistant": "copilot"}
    turns = "\n".join(f"{labels.get(t.role, t.role)}: {t.text}" for t in history[-6:])
    return (
        "Route this question to one or more capabilities.\n\n"
        f"CAPABILITIES:\n{json.dumps(CAPABILITIES, indent=2)}\n\n"
        f"CONVERSATION SO FAR:\n{UntrustedText(turns, 'conversation').fenced() if turns else '(none)'}\n\n"
        f"SELECTED SCOPE: client_id={scope.get('account_id')}, "
        f"tax_year={scope.get('tax_year')}, state={scope.get('state')}\n\n"
        f"QUESTION:\n{UntrustedText(message, 'reader question').fenced()}\n\n"
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
    from application.services import get_mediator, get_narration_service
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
