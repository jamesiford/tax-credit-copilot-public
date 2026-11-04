"""The portfolio page: one row per client, filtered and ranked by what inaction costs.

`GET /api/v2/portfolio`. The ranking and the paging are `get_portfolio.portfolio_page`;
this request exists so the router reaches it through the mediator like every other read.
`book`, `states` and `priceable` are the seams the client book, the footprint and the
priceable-states reads come in through; a caller that supplies none gets the real ones.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from application.mediator import Query
from application.queries import get_portfolio


@dataclass(frozen=True)
class GetPortfolioPageQuery(Query):
    """Filter and sort one row per client; every filter is optional."""

    year: int | None = None
    program: str | None = None
    outcome: str | None = None
    scope: str | None = None
    near: bool | None = None
    status: str | None = None
    sort: str = "priority"
    order: str = "asc"
    limit: int = 25
    offset: int = 0
    book: Callable[[], list[dict[str, Any]]] | None = None
    states: Callable[[], dict[int, list[str]]] | None = None
    priceable: Callable[[], set[str]] | None = None


def handle_get_portfolio_page(query: GetPortfolioPageQuery) -> dict[str, Any]:
    """The page, ranked by `PriorityBand`, with the unassessed clients after the ranked ones."""
    seams = {
        name: supplied
        for name, supplied in (("book", query.book), ("states", query.states), ("priceable", query.priceable))
        if supplied is not None
    }
    return get_portfolio.portfolio_page(
        year=query.year, program=query.program, outcome=query.outcome, scope=query.scope,
        near=query.near, status=query.status, sort=query.sort, order=query.order,
        limit=query.limit, offset=query.offset, **seams,
    )
