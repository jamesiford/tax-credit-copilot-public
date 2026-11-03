"""The chat request, as the browser sends it."""
from __future__ import annotations

from pydantic import BaseModel


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
