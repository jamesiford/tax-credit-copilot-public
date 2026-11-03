"""Per-conversation state, in memory, with a time to live. [CH-08]

A hosted agent's replicas are interchangeable and its filesystem is not durable across
restarts, so nothing here is a record of anything: it is a convenience ("their" means
the client we were just talking about) and one safety device (a pending write waits for
a word from the SAME person). Losing it costs a repeated question, never a wrong answer
and never a silent write: a pending confirmation that is lost simply cannot be confirmed,
and the person asks again.

The key is the person AND the conversation. In a group chat somebody else's `confirm`
looks in their own slot, finds nothing, and is told so.
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

HISTORY_LIMIT = 6


@dataclass
class PendingWrite:
    """A prepared change waiting for its owner's `confirm`. The token is held here and never shown."""

    tool: str
    args: dict[str, Any]
    token: str
    expires_at: float
    summary: str = ""


@dataclass
class ConversationState:
    """What the next turn may rely on."""

    client_id: int | None = None
    tax_year: int | None = None
    pending: PendingWrite | None = None
    candidates: list[dict[str, Any]] = field(default_factory=list)
    question: str = ""
    history: list[dict[str, str]] = field(default_factory=list)
    touched: float = 0.0

    def remember(self, role: str, text: str) -> None:
        self.history.append({"role": role, "text": text[:500]})
        del self.history[:-HISTORY_LIMIT]


class StateStore:
    """Holds `ConversationState` per `(oid, conversation)` until it has been idle for `ttl_seconds`."""

    def __init__(self, ttl_seconds: int, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl, self._clock = ttl_seconds, clock
        self._items: dict[tuple[str, str], ConversationState] = {}

    def get(self, key: tuple[str, str]) -> ConversationState:
        """The live state for `key`, or a fresh one. Idle states are dropped here, so nothing runs in the background."""
        now = self._clock()
        for stale in [k for k, s in self._items.items() if now - s.touched > self._ttl]:
            del self._items[stale]
        state = self._items.setdefault(key, ConversationState())
        state.touched = now
        return state

    def forget(self, key: tuple[str, str]) -> None:
        self._items.pop(key, None)

    def __len__(self) -> int:
        return len(self._items)
