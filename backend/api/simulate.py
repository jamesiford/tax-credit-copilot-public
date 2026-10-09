"""What-if: move a lever and re-run the statutory engine.

Split out of `api/onezero.py`. A projection is still a statutory figure -
somebody will act on it - so it runs under the same rules as an actual
calculation and refuses a year with no authored statute rather than borrowing a
neighbouring year's [ADR-005].
"""
from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api._payperiods import require_pay_periods

from application.queries.simulate_portfolio import (
    PortfolioSimulationNotAvailable,
    SimulatePortfolioQuery,
)
from application.queries.simulate_unit import SimulateUnitQuery, UnitSimulationNotAvailable
from application.queries.simulate_employee import (
    EmployeeChange,
    EmployeeSimulationNotAvailable,
    SimulateEmployeeQuery,
)
from application.wiring import get_mediator

router = APIRouter(prefix="/api", tags=["simulation"])


@router.get("/simulate/portfolio/{tax_year}")
def simulate_portfolio(
    tax_year: int,
    state: str,
    action: str = "add_headcount",
    magnitude: float = 5.0,
    limit: int = 50,
) -> dict[str, Any]:
    """One lever, applied across every client operating in this state-year.

    The single-client what-if asks what one client would get. This asks who
    **crosses the threshold** if we act — which is the portfolio question, and
    the one a client one hire short is invisible to when results are ranked by
    dollar value.
    """
    try:
        query = SimulatePortfolioQuery(
            tax_year=tax_year,
            state=state,
            action=action,
            magnitude=magnitude,
            limit=limit,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return get_mediator().send(query)
    except PortfolioSimulationNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class UnitSimulateRequest(BaseModel):
    """What-if at one location, priced the way the location grid prices it."""

    client_id: int
    worksite_id: str
    tax_year: int
    state: str = "GA"
    method: str = Field("min_max", pattern="^(min_max|pay_period)$")
    action: str = Field(
        "add_headcount",
        pattern="^(add_headcount|remove_headcount|adjust_hours|adjust_wages)$",
    )
    magnitude: float = 1.0
    hire_weekly_hours: float | None = Field(default=None, gt=0, le=80)
    hire_hourly_rate: float | None = Field(default=None, gt=0, le=500)


@router.post("/simulate/unit")
def run_unit_simulation(payload: UnitSimulateRequest) -> dict[str, Any]:
    """One lever at one location. Thin [ADR-003]: the query owns the pricing."""
    try:
        query = SimulateUnitQuery(**payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return get_mediator().send(query)
    except UnitSimulationNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class EmployeeChangeRequest(BaseModel):
    """One stacked employee: more hours a week, a raise in $/hr, or both."""

    record_token: str = Field(min_length=1, max_length=64)
    additional_weekly_hours: float = Field(0.0, ge=0, le=40)
    hourly_raise: float = Field(0.0, ge=0, le=100)


class EmployeeSimulateRequest(BaseModel):
    """A stack of employees, each working differently for the rest of the year."""

    client_id: int
    tax_year: int
    employees: list[EmployeeChangeRequest] = Field(min_length=1, max_length=25)
    state: str = "GA"
    method: str = Field("min_max", pattern="^(min_max|pay_period)$")


@router.post("/simulate/employee")
def run_employee_simulation(payload: EmployeeSimulateRequest) -> dict[str, Any]:
    """Thin [ADR-003]. Record tokens, never employee ids, cross the wire."""
    try:
        query = SimulateEmployeeQuery(
            client_id=payload.client_id,
            tax_year=payload.tax_year,
            state=payload.state,
            method=payload.method,
            changes=tuple(EmployeeChange(**e.model_dump()) for e in payload.employees),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return get_mediator().send(query)
    except EmployeeSimulationNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


class OneZeroSimulateRequest(BaseModel):
    """[J2] UX-02 — entity-level what-if against the statutory One/Zero engine."""
    tax_year: int = 2025
    state: str
    fein: str | None = None  # scope to a single legal entity (cost-center proxy)
    # Which tenant. Scope is a dimension of the request, so a what-if run while
    # looking at one client must not silently evaluate another's payroll.
    client_id: int | None = None
    action: str = Field(
        "adjust_hours",
        pattern="^(add_headcount|remove_headcount|adjust_hours|adjust_wages)$",
    )
    # adjust_hours -> hrs/wk delta (e.g. +2); adjust_wages -> percent (e.g. +5);
    # add/remove_headcount -> integer count of full-time heads.
    magnitude: float = 0.0
    label: str | None = None
    # WI-22. What a hired role is. Absent: a full-time role clear of both floors.
    hire_weekly_hours: float | None = Field(default=None, gt=0, le=80)
    hire_hourly_rate: float | None = Field(default=None, gt=0, le=500)


@router.post("/simulate/onezero")
def run_onezero_simulation(payload: OneZeroSimulateRequest) -> dict[str, Any]:
    """[J2] UX-02 — what-if simulator at the legal-entity level, run against the
    statutory One/Zero engine. Levers: headcount add/remove, wage adjustment,
    hours adjustment — scoped to a state and optional FEIN.

    A projection is still a statutory figure: it says what the credit WOULD be,
    and somebody will act on it. So it obeys the same two rules as an actual
    calculation — it runs against the requested tenant's payroll, and it refuses
    a programme-year with no authored statute rather than quietly using a
    neighbouring year's rules [ADR-005].
    """
    from tools.credit_math import STATE_TO_PACK, authored_years, load_pack_one_zero
    from tools.simulation import onezero_snapshot, apply_onezero_lever
    from api._assess import _client_window, average_headcount, rows_for_state_year

    st = payload.state.upper()
    pack_file = STATE_TO_PACK.get(st)
    if pack_file is None:
        raise HTTPException(status_code=400, detail=f"No rule pack for state {st}")

    # Same source of truth the scope selector and the assessment path use, so
    # all three agree about what can be priced. Without this the simulator
    # happily returns a figure for a programme the UI has disabled.
    priceable = authored_years(pack_file)
    if not priceable:
        raise HTTPException(
            status_code=422,
            detail=(
                f"{st} has no year-scoped rule packs, so a projection would run "
                f"under no particular year's statute. ADR-005."
            ),
        )
    if payload.tax_year not in priceable:
        raise HTTPException(
            status_code=422,
            detail=(
                f"No rule pack for {st} tax year {payload.tax_year}. "
                f"Authored: {', '.join(str(y) for y in priceable)}."
            ),
        )

    pack = load_pack_one_zero(st, tax_year=payload.tax_year)
    if pack is None:
        raise HTTPException(status_code=400, detail=f"State {st} has no one_zero block")

    all_rows = require_pay_periods(account_id=payload.client_id)
    # One definition of "the rows for this state-year", shared with the
    # assessment path — INCLUDING the client's own fiscal window. Leaving this
    # on the calendar year while the assessment moved to the real window is how
    # Position and Plan came to quote different figures for one client-year.
    window = _client_window(payload.client_id, st, payload.tax_year)
    base_rows = rows_for_state_year(all_rows, st, payload.tax_year, window)
    if payload.fein:
        base_rows = [r for r in base_rows if r.get("Entity_FEIN") == payload.fein]
    if not base_rows:
        raise HTTPException(status_code=404, detail="No pay-period rows for that scope.")

    # The frozen base the credit is measured against — the SAME base the
    # coverage matrix used. Without it the simulator treats an established
    # employer's whole workforce as net-new, and Position and Plan then quote
    # different figures for the same client-year.
    prior_average = 0.0
    prior_year = payload.tax_year - 1
    if prior_year in priceable:
        prior_rows = all_rows
        if payload.fein:
            prior_rows = [r for r in prior_rows if r.get("Entity_FEIN") == payload.fein]
        prior_average = average_headcount(
            prior_rows, st, prior_year, load_pack_one_zero(st, tax_year=prior_year),
            _client_window(payload.client_id, st, prior_year),
        )

    baseline = onezero_snapshot(
        base_rows, tax_year=payload.tax_year, state=st, pack=pack,
        prior_average_headcount=prior_average,
    )
    sim_rows, detail = apply_onezero_lever(
        base_rows, action=payload.action, magnitude=payload.magnitude,
        pack=pack, state=st, fein=payload.fein,
        hire_weekly_hours=payload.hire_weekly_hours, hire_hourly_rate=payload.hire_hourly_rate,
    )
    projected = onezero_snapshot(
        sim_rows, tax_year=payload.tax_year, state=st, pack=pack,
        prior_average_headcount=prior_average,
    )

    delta = {
        "average_headcount": round(projected["average_headcount"] - baseline["average_headcount"], 2),
        "eligible_employee_count": projected["eligible_employee_count"] - baseline["eligible_employee_count"],
        "annual_credit_usd": projected["annual_credit_usd"] - baseline["annual_credit_usd"],
        "lifetime_credit_usd": projected["lifetime_credit_usd"] - baseline["lifetime_credit_usd"],
    }

    return {
        "as_of": date.today().isoformat(),
        "scope": {
            "state": st,
            "fein": payload.fein,
            "tax_year": payload.tax_year,
            "client_id": payload.client_id,
        },
        "action": payload.action,
        "magnitude": payload.magnitude,
        "detail": detail,
        # Disclosed so a reader can see what the credit was measured against.
        # Zero means we found no prior year, which is the establishment case —
        # legitimate, but it makes the whole workforce look net-new, so it must
        # not be silent.
        "base_average_headcount": prior_average,
        "base_year": payload.tax_year - 1 if prior_average else None,
        "eligibility_floors": {
            "min_weekly_hours": pack.min_weekly_hours,
            "min_weekly_wages": pack.min_weekly_wages,
            "pt_band_hours": list(pack.pt_band_hours) if pack.pt_band_hours else None,
            "pt_weight": pack.pt_weight,
        },
        "baseline": baseline,
        "projected": projected,
        "delta": delta,
        "_roadmap_tag": "J2",
    }
