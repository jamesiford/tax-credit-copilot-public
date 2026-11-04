"""The sentences the orchestrator writes itself, and the only ones. [CH-08]

None carries a figure from the engine. They say what is needed (a client, a year), what
could not be done (and that nothing changed), or what to say next to confirm or drop a
prepared change. A refusal to run is stated plainly and early; it is never softened into
an answer.
"""
from __future__ import annotations

from collections.abc import Sequence

from app.core.tools import Clarification, Problem

CONFIRM_WORDS = ("confirm", "yes, apply", "yes apply")
CANCEL_WORDS = ("cancel",)
CONFIRM_HINT = "Reply **confirm** to apply this change, or **cancel** to drop it."

UNATTRIBUTED = (
    "I can't tell who you are in this conversation, so I won't run anything. "
    "Every answer and every change here is recorded against a named person."
)
NOTHING_PENDING = "There is nothing waiting for your confirmation."
CANCELLED = "Cancelled. Nothing was changed."
EXPIRED = "That preview has expired, so nothing was changed. Ask again to get a fresh preview."
INJECTION = "I can't act on that message as written. Ask the question again in plain terms."
MODEL_DOWN = "_The language model is unavailable, so this is the platform's own answer without commentary._"
GATEWAY_DOWN = "The calculation service did not answer, so I can't give a figure. Nothing has been changed."
TIMED_OUT = "That took too long, so I stopped. Nothing has been changed; try again."
DROPPED = "_The change I previewed earlier was dropped; nothing was changed. Ask again if you still want it._"
RATE_LIMITED = "You're asking quickly. Wait a moment and try again."
NOT_ENTITLED = "You are not entitled to do that from this channel."
CHANNEL_REFUSED = "The channel gateway refused this orchestrator's credentials, so I can't reach the calculation service."

_UNREACHABLE = ("gateway_unreachable", "timeout", "api_unreachable", "api_error", "bad_response")
_UNAUTHENTICATED = ("unauthenticated", "caller_not_allowed", "missing_scope", "mixed_token", "tenant_mismatch", "invalid_acting_user")

_COMMIT_FAILURES = {
    "confirmation_expired": EXPIRED,
    "confirmation_replayed": "That confirmation was already used, so nothing was repeated.",
    "confirmation_wrong_user": "That preview belongs to someone else, so nothing was changed.",
    "confirmation_unknown": "I could not find that preview, so nothing was changed. Ask again to get a fresh one.",
    "not_authorized": "You are not entitled to make changes from this channel, so nothing was changed.",
    "rate_limited": RATE_LIMITED + " Nothing was changed.",
}


def clarification(clarify: Clarification) -> str:
    """The question back. Candidates are numbered `1) Name`; the reader answers with the number."""
    if clarify.kind == "year":
        return "Which tax year do you mean?"
    if clarify.kind == "client":
        asked = "Which client do you mean?" + (f" ({clarify.reason})" if clarify.reason else "")
        lines = [f"{n}) {c.get('name') or 'Account ' + str(c.get('client_id'))}" for n, c in enumerate(clarify.candidates, 1)]
        return "\n\n".join(p for p in (asked, "\n".join(lines), "Reply with the number." if lines else "Tell me the client's name.") if p)
    return clarify.reason or "I need a little more to go on."


def failure(problems: Sequence[Problem]) -> str:
    """Why nothing could be answered, from the first problem; the platform's own message where it gave one."""
    if not problems:
        return "I couldn't answer that."
    first = problems[0]
    if first.code in _UNREACHABLE:
        return GATEWAY_DOWN
    if first.code in _UNAUTHENTICATED:
        return CHANNEL_REFUSED
    if first.code == "rate_limited":
        return RATE_LIMITED
    if first.code == "invalid_arguments":
        return f"I need a little more to run that: {first.message}"
    return f"I couldn't answer that: {(first.message or first.code.replace('_', ' ')).rstrip('.')}."


def commit_failure(code: str, message: str) -> str:
    """What to tell the owner when a confirmed change did not go through. Always says nothing was repeated or changed."""
    if code in _COMMIT_FAILURES:
        return _COMMIT_FAILURES[code]
    if code in _UNAUTHENTICATED:
        return CHANNEL_REFUSED + " Nothing was changed."
    if code in _UNREACHABLE:
        return ("The calculation service did not confirm the change, so I can't say whether it was made. "
                "Check the claim record before asking again; I won't retry on my own.")
    return f"The change was not made: {message or code.replace('_', ' ')}."
