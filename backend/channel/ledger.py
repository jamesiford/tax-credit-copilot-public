"""The facts a conversation has been told, and `verify_figures`. [CH-06, ADR-008]

Cowork's model writes its own prose, so the platform cannot stop a figure being
misquoted. It can keep a record of every `facts` block it returned in a
conversation and let the author check a draft against exactly those: the numeric
guard, zero tolerance, over the union of the conversation's facts.

PER PROCESS, bounded and expiring: an LRU of conversations (`MAX_CONVERSATIONS`),
each holding its most recent results (`MAX_RESULTS`), forgotten after `TTL`. A
restart, or a second worker, loses it — and the answer to "is this figure in the
conversation's results" then becomes "no", which is the strict direction: a figure
that cannot be traced is reported, never waved through. Documented in the runbook.

Not recorded: the results of `verify_figures` and `channel_ping` (their numbers
are positions and counts, not the engine's), the download ticket, and a write's
confirmation token (digits inside a secret are not a licence to quote digits).
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any

from application.capabilities.verify import verify_figures
from application.capabilities.envelope import ToolResult

TTL_SECONDS = 8 * 3600
MAX_CONVERSATIONS = 1000
MAX_RESULTS = 200
UNRECORDED_TOOLS = frozenset({"verify_figures", "channel_ping", "claim_package_link", "claim_package_redeem"})
UNRECORDED_KEYS = frozenset({"confirmation", "ticket"})


def _scrub(facts: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in facts.items() if k not in UNRECORDED_KEYS}


class FactLedger:
    """What each conversation has been told, keyed by conversation id."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._items: OrderedDict[str, tuple[float, list[dict[str, Any]]]] = OrderedDict()
        self._lock = threading.Lock()

    def record(self, conversation_id: str, tool: str, facts: Mapping[str, Any]) -> bool:
        """Keep `facts` for this conversation. False when the tool's results are never kept."""
        if tool in UNRECORDED_TOOLS:
            return False
        now = self._clock()
        with self._lock:
            self._expire(now)
            _, held = self._items.pop(conversation_id, (now, []))
            held.append(_scrub(facts))
            del held[:-MAX_RESULTS]
            self._items[conversation_id] = (now, held)
            while len(self._items) > MAX_CONVERSATIONS:
                self._items.popitem(last=False)
        return True

    def facts_for(self, conversation_id: str) -> list[dict[str, Any]]:
        """Every recorded result of the conversation, oldest first; empty if forgotten."""
        with self._lock:
            self._expire(self._clock())
            return list(self._items.get(conversation_id, (0.0, []))[1])

    def _expire(self, now: float) -> None:
        while self._items:
            key, (stamp, _) = next(iter(self._items.items()))
            if now - stamp < TTL_SECONDS:
                break
            del self._items[key]


def verify_against(ledger: FactLedger, conversation_id: str, draft_text: str, allowed_context: list[str]) -> ToolResult:
    """The numeric guard over `draft_text`, against this conversation's recorded facts."""
    return verify_figures(draft_text, allowed_context, facts=ledger.facts_for(conversation_id))
