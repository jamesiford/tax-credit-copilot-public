"""Who qualifies — the eligible population for one client, programme and year.

A thin router [ADR-003]. It validates input, dispatches a query, and maps a
domain failure onto a status code.

The name is reused deliberately. `api/eligibility.py` previously served a
synthetic single-tenant surface and was removed in the 30 August cleanup; this
is the per-client replacement, and it holds no rules of its own.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi import Query as QueryParam

from application.queries.get_eligibility import (
    EligibilityNotAvailable,
    GetEligibilityQuery,
)
from application.wiring import get_mediator

router = APIRouter(prefix="/api/eligibility", tags=["eligibility"])


@router.get("/{tax_year}")
def eligibility(
    tax_year: int,
    state: str = QueryParam(..., description="Two-letter state code, e.g. GA"),
    account_id: int | None = QueryParam(None, description="Client; defaults to the tenant"),
    status: str = QueryParam("all", description="all | both | min_max_only | pay_period_only | neither"),
    near_floor: bool = QueryParam(False, description="Only employees within 5% of a floor"),
    q: str = QueryParam("", description="Employee id substring"),
    limit: int = QueryParam(50, ge=1, le=500),
    offset: int = QueryParam(0, ge=0),
    sort: str = QueryParam("employee_id", description="column to order by, before paging"),
    order: str = QueryParam("asc", description="asc | desc"),
) -> dict[str, Any]:
    """Both certified methods, per employee, for the selected client-year.

    Two independent denominators produce two independently validated lists. The
    response carries both verdicts for every employee rather than a single
    number with a caveat attached.
    """
    try:
        query = GetEligibilityQuery(
            tax_year=tax_year,
            state=state,
            account_id=account_id,
            status=status,
            near_floor=near_floor,
            q=q,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order.lower(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return get_mediator().send(query)
    except EligibilityNotAvailable as exc:
        # Well-formed but unanswerable: no statute for that year, or no payroll
        # for that client-state-year. Never an empty population, which would
        # read as "nobody qualifies".
        raise HTTPException(status_code=404, detail=str(exc)) from exc
