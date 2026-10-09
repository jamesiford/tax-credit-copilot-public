"""Coverage reads: what a client claims, and what the portfolio looks like.

Queries. They compute and return; nothing here changes what the business
believes. The reading rules — how a cell is interpreted in the light of the
engagement we hold, and how totals are summed — live in `domain/coverage.py`,
so a report and a screen cannot disagree about what an opportunity is.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from application.mediator import Query
from domain.coverage import group_by_client, matrix, totals, totals_by_program


class ClaimNotFound(LookupError):
    """No claim recorded for that client, programme and year.

    A domain-level absence. The router turns it into a 404; a batch job might
    reasonably skip it. Neither decision belongs in the handler.
    """


@dataclass(frozen=True)
class GetClientCoverageQuery(Query):
    """One client's programme x year grid.

    `tax_years` narrows to a window — the retroactive audit's natural shape. The
    totals describe exactly the cells returned, so a headline figure can never
    cover years the grid beneath it is not showing.
    """

    client_id: int
    program_code: str | None = None
    tax_years: tuple[int, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class GetPortfolioCoverageQuery(Query):
    """Every client's coverage — the portfolio matrix.

    Totals are per client *and* overall, because a headline that mixed one
    client's exposure into another's opportunity would be useless for the thing
    this view exists to do: decide who to call.
    """

    tax_year: int | None = None


@dataclass(frozen=True)
class GetCellHistoryQuery(Query):
    """One cell and everything that ever happened to it.

    The history is the point. "What did you believe on the day you filed?" is
    the question an audit asks, and a current-state-only store cannot answer it.
    """

    client_id: int
    program_code: str
    tax_year: int


def handle_get_client_coverage(query: GetClientCoverageQuery) -> dict[str, Any]:
    from application.wiring import get_claim_repository as get_repository

    repo = get_repository()
    years = list(query.tax_years) or None
    claims = repo.coverage(
        query.client_id,
        program_codes=[query.program_code] if query.program_code else None,
        tax_years=years,
    )
    engagements = repo.engagements(query.client_id)
    scopes = {e.program_code: e.scope for e in engagements}
    return {
        "client_id": query.client_id,
        "tax_years": years,
        "cells": matrix(claims, scopes),
        "totals": totals(claims),
        # The grid's row totals. Summed as Decimal here so the browser never
        # adds money — see `totals_by_program`.
        "program_totals": totals_by_program(claims),
        "engagements": [e.to_dict() for e in engagements],
    }


def handle_get_portfolio_coverage(query: GetPortfolioCoverageQuery) -> dict[str, Any]:
    from application.wiring import get_claim_repository as get_repository

    repo = get_repository()
    claims = repo.portfolio_coverage(
        tax_years=[query.tax_year] if query.tax_year else None
    )
    return {
        "clients": [
            {
                "client_id": client_id,
                "cells": matrix(
                    rows, {e.program_code: e.scope for e in repo.engagements(client_id)}
                ),
                "totals": totals(rows),
            }
            for client_id, rows in sorted(group_by_client(claims).items())
        ],
        "totals": totals(claims),
    }


def handle_get_cell_history(query: GetCellHistoryQuery) -> dict[str, Any]:
    from application.wiring import get_claim_repository as get_repository

    repo = get_repository()
    current = repo.current(query.client_id, query.program_code, query.tax_year)
    if current is None:
        raise ClaimNotFound(
            f"No claim recorded for client {query.client_id}, "
            f"{query.program_code.upper()}, TY{query.tax_year}."
        )
    return {
        "current": current.to_dict(),
        "history": [
            c.to_dict()
            for c in repo.history(query.client_id, query.program_code, query.tax_year)
        ],
    }
