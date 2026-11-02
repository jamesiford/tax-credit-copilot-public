"""`claim_cell_history` — one claim cell and everything that ever happened to it.

"What did you believe on the day you filed?" is the question an audit asks, and a
current-state-only store cannot answer it. The history is the point.
"""
from __future__ import annotations

from application.capabilities import _support as s
from application.capabilities.errors import NotCalculated
from application.capabilities.envelope import Provenance, ToolResult


def claim_cell_history(client_id: int, program_code: str, tax_year: int) -> ToolResult:
    """The current claim and its full history, in the order the store returns it.

    A cell nobody has recorded is `NotCalculated`, not an empty history: "no
    claim" and "a claim worth nothing" are different statements.
    """
    from application.queries.get_coverage import ClaimNotFound, GetCellHistoryQuery
    from application.wiring import get_mediator

    try:
        facts = get_mediator().send(
            GetCellHistoryQuery(client_id=client_id, program_code=program_code, tax_year=tax_year)
        )
    except ClaimNotFound as exc:
        raise NotCalculated(str(exc)) from exc

    current = facts["current"]
    rows = [
        (
            s.cell(entry["effective_from"], "date"),
            str(entry["status"]),
            s.cell(entry["identified_usd"], "money"),
            s.cell(entry["claimed_usd"], "money"),
            str(entry["decided_by"] or s.ABSENT),
        )
        for entry in facts["history"]
    ]
    blocks = [
        s.heading(f"{current['program_code']} · TY{s.cell(current['tax_year'], 'year')}"),
        s.table(("From", "Status", "Identified", "Claimed", "Decided by"), rows),
    ]
    warnings = []
    if not current.get("provenance_verified"):
        warnings.append("The claimed figure is an unverified assertion, not a filing.")
    return s.result(
        "claim_cell_history", facts, blocks,
        provenance=Provenance(
            run_id=current.get("identified_run_id"),
            rule_pack_version=current.get("rule_pack_version"),
            assumption_set_id=current.get("assumption_set_id"),
            source="recorded claims",
        ),
        warnings=warnings,
    )
