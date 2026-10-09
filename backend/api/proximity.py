"""Threshold proximity — who is near the statutory line.

A thin router [ADR-003]. It validates input, dispatches a query, and maps a
domain failure onto a status code. It holds no business rules, because rules in
routers is how one statutory quantity ended up with three implementations that
disagreed.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Query as QueryParam

from application.queries.get_proximity import GetProximityQuery, ProximityNotAvailable
from application.wiring import get_mediator

router = APIRouter(prefix="/api/proximity", tags=["proximity"])


@router.get("/{tax_year}")
def proximity(
    tax_year: int,
    state: str = QueryParam(..., description="Two-letter state code, e.g. GA"),
    method: str = QueryParam("min_max", description="min_max | pay_period"),
    within: float = QueryParam(5.0, ge=0.0, le=40.0, description="Band, extra hrs/week"),
    limit: int = QueryParam(100, ge=1, le=1000),
    account_id: int | None = QueryParam(None, description="Client; defaults to the tenant"),
    rest_of_year: bool = QueryParam(False, description="Add what the rest of the year needs"),
) -> dict[str, Any]:
    """Employees within `within` additional hours per week of qualifying.

    Ranked by that figure rather than by either raw gap: an employee half an hour
    short and an employee $40 short are not comparable until both are expressed
    as the same lever.
    """
    try:
        query = GetProximityQuery(
            tax_year=tax_year,
            state=state,
            method=method,
            within_weekly_hours=within,
            limit=limit,
            account_id=account_id,
            rest_of_year=rest_of_year,
        )
    except ValueError as exc:
        # The request itself is malformed — the caller can fix this.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return get_mediator().send(query)
    except ProximityNotAvailable as exc:
        # Well-formed but unanswerable: no statute for that year, or no payroll
        # for that client-state-year. Never an empty cohort, which would read as
        # "nobody is near the line".
        raise HTTPException(status_code=404, detail=str(exc)) from exc
