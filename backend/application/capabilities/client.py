"""Client-scoped capabilities: resolve, situation, eligibility, trend, at-risk, discovery.

Each returns the brief the portal's narrator agents already received — the same
tools, called the same way — wrapped in an envelope with platform-rendered
blocks and provenance. Nothing here computes a figure of its own.

`client_resolve` and `client_situation` live here; the rest were split out by size
(`client_eligibility`, `client_analysis`) and are re-exported below, so every import
of `application.capabilities.client` is unchanged.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from application import client_book
from application.capabilities import _support as s
from application.capabilities.book import BAND_LABEL
from application.capabilities.client_analysis import client_at_risk, client_discovery, client_trend  # noqa: F401
from application.capabilities.client_eligibility import client_eligibility  # noqa: F401
from application.capabilities.envelope import Provenance, ToolResult
from application.capabilities.errors import Ambiguous, ClientNotFound
from application.chat_scope import ClientName, Referent, clients_named, resolve_referent


def _exact_single_name(referent: Referent, text: str, clients: Sequence[ClientName]) -> Referent:
    """One client named in full or by an exact alias is the answer, whatever is selected.

    The portal asks here because a page selection can contradict the sentence; a channel
    has no page, so the reader's own words are the whole signal, and a second question
    about a name they already gave is the friction CH-15e removes. Partial text never
    reaches this (`clients_named` matches whole words only) and two names still ask.

    A full name beats a first-word alias that other clients share: "Cascade Retail
    Partners" also contains "cascade", which would name both Cascade clients. So when
    exactly one FULL name is present, the text left after removing it must name nobody
    else.
    """
    if not (referent.clarify and referent.named):
        return referent
    if len(referent.named) == 1:
        return Referent(referent.named[0], named=referent.named)
    lowered = text.lower()
    in_full = [c for c in clients if re.search(rf"\b{re.escape(c.name.strip().lower())}\b", lowered)]
    if len(in_full) != 1:
        return referent
    only = in_full[0]
    remainder = re.sub(rf"\b{re.escape(only.name.strip().lower())}\b", " ", lowered)
    if set(clients_named(remainder, clients)) <= {only.client_id}:
        return Referent(only.client_id, named=(only.client_id,))
    return referent


def client_resolve(
    name_or_text: str,
    history: Sequence[Mapping[str, Any]] = (),
    current_client_id: int | None = None,
    *,
    strict: bool = False,
) -> ToolResult:
    """Whose answer this is — or the choices to ask about.

    Deterministic and model-free: it decides whose payroll an answer describes,
    so it must give the same response every time the same question is asked
    [`chat_scope`]. `facts.resolved` says whether one client was settled. When it is
    not unambiguous the result lists candidates; with `strict` (the portal's rule,
    where the page selection can disagree with the words) it raises `Ambiguous`
    instead and a single name is not promoted.
    """
    book = client_book.clients_or_empty()
    if not book:
        raise ClientNotFound("The client book could not be read, so no client can be resolved.")
    names = {int(c["account_id"]): str(c["name"]) for c in book}
    clients = [ClientName(client_id, name) for client_id, name in names.items()]

    referent = resolve_referent(name_or_text, list(history), current_client_id, clients)
    if not strict:
        referent = _exact_single_name(referent, name_or_text, clients)
    facts = _resolution_facts(referent, names)
    if referent.clarify and strict:
        raise Ambiguous(referent.reason or "the question does not name one client", tuple(facts["candidates"]))
    return s.result(
        "client_resolve", facts, _resolution_blocks(referent, facts), provenance=Provenance(source="client book"),
    )


def _resolution_facts(referent: Referent, names: Mapping[int, str]) -> dict[str, Any]:
    """The wire facts of a resolution; `resolved` is the one flag a caller needs."""
    chosen = referent.client_id
    return {
        "resolved": chosen is not None,
        "client_id": chosen,
        "client_name": names.get(chosen) if chosen is not None else None,
        "clarify": referent.clarify,
        "candidates": [{"client_id": cid, "name": names.get(cid, f"Account {cid}")} for cid in referent.candidates],
        "reason": referent.reason,
        "named": list(referent.named),
    }


def _resolution_blocks(referent: Referent, facts: Mapping[str, Any]) -> list[Any]:
    """Either the question to ask back with its choices, or the one-line statement of whose answer this is."""
    if not referent.clarify:
        return [s.paragraph(f"Answering for {facts['client_name']}.")]
    asked = "Which client do you mean?" + (f" ({referent.reason})" if referent.reason else "")
    return [s.paragraph(asked), s.bullets([c["name"] for c in facts["candidates"]])]


def _situation_rows(facts: dict[str, Any]) -> list[tuple[str, ...]]:
    """One row per recorded cell, grouped by the band that ranks it."""
    return [
        (
            BAND_LABEL.get(band, band),
            str(c["program_code"]),
            s.cell(c["tax_year"], "year"),
            s.cell(c["identified_usd"], "money"),
            s.cell(c["jobs_margin"], "number"),
        )
        for band, cells in facts["by_band"].items()
        for c in cells
    ]


def client_situation(client_id: int, year: int | None = None) -> ToolResult:
    """Why you would call this client, ranked, from recorded claims alone.

    No payroll and no engine: the brief is an ordering of claims by
    `PriorityBand`. `facts` equals the REST endpoint's body, display name
    included; the portal narrator is handed the same object without
    `client_name`, which it never received.
    """
    from application.queries.get_client_situation import (
        GetClientSituationQuery,
        SituationNotAvailable,
        with_client_name,
    )
    from application.wiring import get_mediator

    try:
        body = get_mediator().send(GetClientSituationQuery(client_id=client_id, tax_year=year))
    except SituationNotAvailable as exc:
        raise ClientNotFound(str(exc)) from exc
    facts = with_client_name(body, client_id)

    name = facts["client_name"] or f"Account {client_id}"
    if not facts.get("assessed"):
        blocks = [s.heading(name), s.paragraph(facts["message"])]
        return s.result(
            "client_situation", facts, blocks, provenance=Provenance(source="recorded claims; no run"),
        )

    blocks = [
        s.heading(name),
        s.paragraph(
            f"{s.cell(facts['cells'], 'count')} recorded cells. "
            f"Identified credit: {s.cell(facts['identified_usd'], 'money')}."
        ),
        s.table(("Reason", "Programme", "Tax year", "Identified", "Jobs margin"), _situation_rows(facts)),
    ]
    warnings = []
    if facts.get("claimed_is_unverified"):
        warnings.append(
            "The claimed side of this book is an unverified assertion; do not read "
            "recoverable or exposure figures as findings against a filed return."
        )
    return s.result(
        "client_situation", facts, blocks,
        provenance=Provenance(source="recorded claims; no run"), warnings=warnings,
    )
