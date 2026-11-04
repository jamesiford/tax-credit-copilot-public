"""Name -> function, for every implemented capability.

The one module in this package that imports the others (and so the engine). The
catalog says what exists; this says where it lives, and a test holds the two
together so a tool cannot be catalogued without a body or implemented without a
catalog entry.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from application.capabilities import (
    book, catalog, claims, client, data_catalog, data_query, findings, package, simulate, verify, walkthrough, writes,
)
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
    "verify_figures": verify.verify_figures,
    # Data tools take `principal` first: it picks the budget a query is spent against and decides
    # whether Copilot Cowork may be handed employee-level rows.
    "data_catalog": data_catalog.data_catalog,
    "data_query": data_query.data_query,
    "data_distinct_values": data_query.data_distinct_values,
    # Downloads are bound to a person, so these take `principal` first as well.
    "claim_package_link": package.claim_package_link,
    "claim_package_redeem": package.claim_package_redeem,
    # Writes take `principal` first: who is asking, not part of the question.
    **{name: getattr(writes, name) for name in (
        "finding_resolve_prepare", "finding_resolve_commit",
        "finding_reopen_prepare", "finding_reopen_commit",
        "claim_transition_prepare", "claim_transition_commit",
        "claim_record_prepare", "claim_record_commit",
        "engagement_set_prepare", "engagement_set_commit",
        "base_year_set_prepare", "base_year_set_commit",
        "claim_package_create_prepare", "claim_package_create_commit",
    )},
}

#: The tools whose first argument is the caller. Named, not inferred from a
#: signature: what a function is handed is part of its contract.
NEEDS_PRINCIPAL = frozenset(
    {"claim_package_link", "claim_package_redeem", "data_catalog", "data_query", "data_distinct_values"}
    | {n for n in FUNCTIONS if n.endswith(("_prepare", "_commit"))}
)


def get(name: str) -> Callable[..., ToolResult]:
    """The function behind a catalogued, implemented tool."""
    spec = catalog.get(name)
    if not spec.implemented:
        raise NotImplementedError(f"capability {name!r} is declared but not built yet")
    return FUNCTIONS[name]


def call(name: str, **arguments: Any) -> ToolResult:
    """Run a capability by name. Arguments are the catalog schema's properties."""
    return get(name)(**arguments)
