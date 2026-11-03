"""Name -> function, for every implemented capability.

The one module in this package that imports the others (and so the engine). The
catalog says what exists; this says where it lives, and a test holds the two
together so a tool cannot be catalogued without a body or implemented without a
catalog entry.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from application.capabilities import book, catalog, claims, client, findings, simulate, walkthrough, writes
from application.capabilities.envelope import ToolResult

FUNCTIONS: dict[str, Callable[..., ToolResult]] = {
    "book_rank": book.book_rank,
    "client_resolve": client.client_resolve,
    "client_situation": client.client_situation,
    "client_eligibility": client.client_eligibility,
    "client_trend": client.client_trend,
    "client_at_risk": client.client_at_risk,
    "client_discovery": client.client_discovery,
    "simulate": simulate.simulate,
    "calc_walkthrough": walkthrough.calc_walkthrough,
    "employee_drill": walkthrough.employee_drill,
    "findings_list": findings.findings_list,
    "claim_cell_history": claims.claim_cell_history,
    # Writes take `principal` first: who is asking, not part of the question.
    **{name: getattr(writes, name) for name in (
        "finding_resolve_prepare", "finding_resolve_commit",
        "finding_reopen_prepare", "finding_reopen_commit",
        "claim_transition_prepare", "claim_transition_commit",
        "claim_record_prepare", "claim_record_commit",
        "engagement_set_prepare", "engagement_set_commit",
        "base_year_set_prepare", "base_year_set_commit",
    )},
}


def get(name: str) -> Callable[..., ToolResult]:
    """The function behind a catalogued, implemented tool."""
    spec = catalog.get(name)
    if not spec.implemented:
        raise NotImplementedError(f"capability {name!r} is declared but not built yet")
    return FUNCTIONS[name]


def call(name: str, **arguments: Any) -> ToolResult:
    """Run a capability by name. Arguments are the catalog schema's properties."""
    return get(name)(**arguments)
