"""Client-scoped capabilities: resolve, situation, eligibility, trend, at-risk, discovery.

Each returns the brief the portal's narrator agents already received — the same
tools, called the same way — wrapped in an envelope with platform-rendered
blocks and provenance. Nothing here computes a figure of its own.

`client_resolve` and `client_situation` live here; the rest were split out by size
(`client_eligibility`, `client_analysis`) and are re-exported below, so every import
of `application.capabilities.client` is unchanged.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from application import client_book
from application.capabilities import _support as s
from application.capabilities.book import BAND_LABEL
from application.capabilities.client_analysis import client_at_risk, client_discovery, client_trend  # noqa: F401
from application.capabilities.client_eligibility import client_eligibility  # noqa: F401
from application.capabilities.envelope import Provenance, ToolResult
from application.capabilities.errors import Ambiguous, ClientNotFound
from application.chat_scope import ClientName, resolve_referent


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
    [`chat_scope`]. When the client is not unambiguous the result says so and
    lists candidates; with `strict` it raises `Ambiguous` instead.
    """
    book = client_book.clients_or_empty()
    if not book:
        raise ClientNotFound("The client book could not be read, so no client can be resolved.")
    names = {int(c["account_id"]): str(c["name"]) for c in book}
    clients = [ClientName(client_id, name) for client_id, name in names.items()]

    referent = resolve_referent(name_or_text, list(history), current_client_id, clients)
    candidates = [
        {"client_id": cid, "name": names.get(cid, f"Account {cid}")} for cid in referent.candidates
    ]
    facts = {
        "client_id": referent.client_id,
        "client_name": names.get(referent.client_id) if referent.client_id is not None else None,
        "clarify": referent.clarify,
        "candidates": candidates,
        "reason": referent.reason,
        "named": list(referent.named),
    }
    if referent.clarify and strict:
        raise Ambiguous(referent.reason or "the question does not name one client", tuple(candidates))

    if referent.clarify:
        asked = "Which client do you mean?" + (f" ({referent.reason})" if referent.reason else "")
        blocks = [s.paragraph(asked), s.bullets([c["name"] for c in candidates])]
    else:
        blocks = [s.paragraph(f"Answering for {facts['client_name']}.")]
    return s.result("client_resolve", facts, blocks, provenance=Provenance(source="client book"))


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
