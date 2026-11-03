"""Which client is a chat question about — or is that genuinely unclear?

The 23 Sep call caught the chat answering a follow-up about Halloway Foods when
the room was talking about Cascade. Nothing had failed: a client WAS in scope,
so the refusal never fired, and the question's "their" was resolved against the
scope rather than the conversation. A wrong-client answer in front of an
executive is worse than no answer, so the rule is: when the client is not
unambiguous, ASK — never pick one.

Deterministic on purpose. This decides whose payroll an answer describes, so it
must not depend on a model being up, and the same question must get the same
response every time it is rehearsed.

It only ever applies to capabilities that are about ONE client. "Who should we
call?" names nobody and asks about everybody, and needs no clarification.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: A leading word too common to stand for a client on its own.
_GENERIC_WORDS = frozenset({
    "the", "first", "national", "american", "united", "general", "global",
    "north", "south", "east", "west", "new", "great", "account", "client",
})

#: Words that refer back to a client named earlier rather than naming one.
_REFERENT = re.compile(
    r"\b(their|theirs|them|they|they'?re|this client|that client|this one|that one|"
    r"these|those|the client|same client)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ClientName:
    client_id: int
    name: str


@dataclass(frozen=True)
class Referent:
    """The outcome. `client_id` is set when the question resolves to one client."""

    client_id: int | None
    clarify: bool = False
    candidates: tuple[int, ...] = ()
    reason: str = ""
    named: tuple[int, ...] = field(default=())


def aliases(client: ClientName) -> list[str]:
    """How a client can be named in a sentence: in full, or by a distinctive first word."""
    full = client.name.strip().lower()
    out = [full]
    first = full.split()[0] if full.split() else ""
    if len(first) >= 4 and first not in _GENERIC_WORDS and first != full:
        out.append(first)
    return out


def clients_named(text: str, clients: Sequence[ClientName]) -> list[int]:
    """Client ids named in `text`, in the order they first appear."""
    if not text:
        return []
    lowered = text.lower()
    found: list[tuple[int, int]] = []
    for client in clients:
        positions = [
            match.start()
            for alias in aliases(client)
            for match in re.finditer(rf"\b{re.escape(alias)}\b", lowered)
        ]
        if positions:
            found.append((min(positions), client.client_id))
    return [client_id for _, client_id in sorted(found)]


def _last_named(history: Iterable[Mapping[str, Any]], clients: Sequence[ClientName]) -> list[int]:
    """The clients named by the most recent turn that named any."""
    for turn in reversed(list(history)):
        named = clients_named(str(turn.get("text") or ""), clients)
        if named:
            return named
    return []


def _union(*groups: Iterable[int]) -> tuple[int, ...]:
    seen: list[int] = []
    for group in groups:
        for client_id in group:
            if client_id not in seen:
                seen.append(client_id)
    return tuple(seen)


def resolve_referent(
    message: str,
    history: Iterable[Mapping[str, Any]],
    scope_client_id: int | None,
    clients: Sequence[ClientName],
) -> Referent:
    """Decide whose answer this is, or that the reader must say.

    The rules, in order:

    1. **Two clients named at once** — a one-client answer cannot be both. Ask.
    2. **One client named**:
       - it is the client in scope: answer.
       - a DIFFERENT client is in scope: ask. The page and the sentence disagree,
         and picking either silently is the defect this module exists to stop.
       - nothing is in scope: ask, with that one client offered, so the year
         the answer is for is on the button rather than assumed.
    3. **No client named, but a word pointing back** ("their", "them") — it
       points at the last turn that named anyone. If that turn named only the
       client in scope, answer; otherwise ask among them (and the scope client).
    4. **No client named, nothing pointing back** — it is about the page. With a
       client in scope, answer. With none, ask.
    """
    named = clients_named(message, clients)
    known = {c.client_id for c in clients}
    everyone = tuple(c.client_id for c in clients)
    in_scope = scope_client_id if scope_client_id in known else None

    if len(named) >= 2:
        return Referent(None, True, tuple(named), "names more than one client", tuple(named))

    if len(named) == 1:
        only = named[0]
        if in_scope == only:
            return Referent(only, named=(only,))
        if in_scope is not None:
            return Referent(
                None, True, (only, in_scope),
                "names a different client from the one this chat is about", (only,),
            )
        return Referent(None, True, (only,), "no client is selected", (only,))

    if _REFERENT.search(message or ""):
        earlier = _last_named(history, clients)
        if earlier and set(earlier) != {in_scope}:
            return Referent(
                None, True, _union(earlier, [in_scope] if in_scope is not None else []),
                "does not say which client it means",
            )
        if in_scope is not None:
            return Referent(in_scope)
        return Referent(None, True, everyone, "does not say which client it means")

    if in_scope is not None:
        return Referent(in_scope)
    earlier = _last_named(history, clients)
    return Referent(None, True, tuple(earlier) or everyone, "no client is selected")
