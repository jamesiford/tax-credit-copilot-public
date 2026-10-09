"""The trend grid — headcount and qualification per location, across years.

One screen answers the question an operator opens the portal with: which of my
locations are growing, which slipped below the minimum, and what is claimable.
Thin [ADR-003] — the replay, the base-year mechanics and the tier lookup all
live in the application and tool layers.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from api.auth import attributed
from fastapi import Query as FastAPIQuery
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api", tags=["trend"])

#: Employee columns the unit drill may be ordered by. A whitelist, because the
#: value reaches SQL and arrives from a query string.
_UNIT_SORTS = (
    "avg_weekly_hours", "avg_weekly_wages", "employee_id", "weeks_worked", "total_hours",
)


def _run_is_fresh(completed: Any) -> bool:
    if not completed:
        return False
    when = completed
    if not isinstance(when, datetime):
        try:
            when = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
        except ValueError:
            return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - when).total_seconds() < 3600


def _program_code_for_state(state: str | None) -> str | None:
    """The programme a state maps to, so a `state` filter cannot cross one."""
    if not state:
        return None
    from tools.credit_math import PROGRAM_CODE_TO_PACK, STATE_TO_PACK

    pack_file = STATE_TO_PACK.get(state.upper())
    return next(
        (code for code, name in PROGRAM_CODE_TO_PACK.items() if name == pack_file), None
    )


@router.get("/v2/clients/{client_id}/units")
def v2_client_units(
    client_id: int,
    year: int | None = FastAPIQuery(None, description="tax year to read"),
    state: str | None = FastAPIQuery(None, description="optional state override"),
    method: str = FastAPIQuery("min_max", description="min_max | pay_period"),
    limit: int = FastAPIQuery(25, ge=1),
    offset: int = FastAPIQuery(0, ge=0),
) -> dict[str, object]:
    """Unit listing for one client-year, READ FROM `tcc_gold`.

    Returns the three Gold tables the grid needs, each as itself rather than
    pre-joined: `items` from `unit_year_master`, `months` from
    `unit_month_summary`, `installments` from `unit_credit_installment`. The
    tranche grain is creation-year x claimable-year and cannot be derived from
    the other two, so a response without it leaves the grid no credit columns.

    No calculation runs here. If the client has never been calculated the answer
    is `calculation_state: not_calculated` with an empty `items` and a null
    `run` — which a caller must render as an invitation to run the calculation,
    never as zero. A run that legitimately produced no rows looks different: the
    same empty `items`, but `run` populated.
    """
    from application.wiring import get_gold_reader
    from infrastructure.persistence.gold_reader import run_envelope

    if method not in ("min_max", "pay_period"):
        raise HTTPException(status_code=422, detail="method must be min_max | pay_period")

    reader = get_gold_reader()
    # One connection, and two round trips for the whole page. Six reads issued
    # separately was ~2.3s, almost all of it the per-trip floor.
    with reader.scope():
        program_code = _program_code_for_state(state)
        page = reader.unit_page(
            client_id, method=method, tax_year=year,
            program_code=program_code, limit=limit, offset=offset,
        )
        run = page["run"]
        # NOT gated on rows. A run that swept this client and found no qualifying
        # unit is a real answer, and tests defend that distinction; the drill is
        # where a year Gold never held has to say so.
        envelope = run_envelope(run, page["in_flight"])

        base = {
            **envelope,
            "client_id": client_id,
            "state": state,
            "year": year,
            "method": method,
            "limit": limit,
            "offset": offset,
        }
        if run is None:
            return {
                **base, "items": [], "total": 0,
                "months": [], "installments": [], "unit_totals": [], "units": [], "years": [],
            }

        items = page["items"]
        worksites = sorted({str(row["worksite_id"]) for row in items})
        return {
            **base,
            "items": items,
            "total": page["total"],
            "months": page["months"],
            "installments": page["installments"],
            "unit_totals": page["unit_totals"],
            # Dimension attributes are NOT duplicated into Gold — they stay with
            # their owner and join at read time. Blank where the registry has no
            # entry, which is honest: a guessed county changes a tier.
            "units": [_unit_dimension(worksite) for worksite in worksites],
            "years": sorted({int(row["tax_year"]) for row in items}),
        }


def _unit_dimension(worksite_id: str) -> dict[str, object]:
    from data.sites import SITES_BY_ID, worksite_name

    site = SITES_BY_ID.get(worksite_id)
    return {
        "worksite_id": worksite_id,
        "name": worksite_name(worksite_id),
        "county": site.county if site else "",
        "city": site.city if site else "",
    }


class BaseYearRequest(BaseModel):
    """Save (or, with null, clear) a location's base year."""

    base_year: int | None = None
    state: str = "GA"
    justification: str | None = Field(default=None, max_length=2000)
    triggered_by: str = "system"


@router.post("/v2/clients/{client_id}/units/{unit_id}/base-year")
def set_client_unit_base_year(
    client_id: int, unit_id: str, payload: BaseYearRequest, request: Request = None
) -> dict[str, Any]:
    """WI-21. Record the choice and start a recalculation. Thin [ADR-003]."""
    from application.commands.set_base_year import BaseYearNotAllowed, SetBaseYearCommand
    from application.wiring import get_mediator

    try:
        command = SetBaseYearCommand(
            client_id=client_id, worksite_id=unit_id, base_year=payload.base_year,
            state=payload.state.upper(), justification=payload.justification,
            actor=attributed(request, payload.triggered_by, default="system"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return get_mediator().send(command)
    except BaseYearNotAllowed as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/v2/clients/{client_id}/units/{unit_id}/rebase")
def rebase_client_unit(
    client_id: int,
    unit_id: str,
    base_year: int = FastAPIQuery(..., description="The base year the reader chose"),
    method: str = FastAPIQuery("min_max"),
    state: str = FastAPIQuery("GA"),
) -> dict[str, Any]:
    """WI-21. One location re-priced against a chosen base year. Thin [ADR-003].

    Declared before the unit drill so `/rebase` is not read as a unit id.
    """
    from application.queries.rebase_unit import RebaseNotAvailable, RebaseUnitQuery
    from application.wiring import get_mediator

    try:
        query = RebaseUnitQuery(
            client_id=client_id, worksite_id=unit_id, base_year=base_year,
            method=method, state=state,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return get_mediator().send(query)
    except RebaseNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/v2/clients/{client_id}/units/{unit_id}")
def v2_client_unit_detail(
    client_id: int,
    unit_id: str,
    year: int = FastAPIQuery(..., description="tax year to read"),
    month: int | None = FastAPIQuery(None, description="1-based month index"),
    state: str | None = FastAPIQuery(None, description="optional state override"),
    method: str = FastAPIQuery("min_max", description="min_max | pay_period"),
    sort: str = FastAPIQuery(
        "avg_weekly_hours", description="avg_weekly_hours | avg_weekly_wages | employee_id"
    ),
    order: str = FastAPIQuery("desc", description="asc | desc"),
    near_min_hours: float | None = FastAPIQuery(
        None,
        description=(
            "Narrow the near-threshold cohort to employees at or above this many "
            "weekly hours. An ABSOLUTE figure: the caller subtracts the band it "
            "wants from the statutory minimum this endpoint already returns in "
            "`thresholds`, so no jurisdiction's floor is baked into the query."
        ),
    ),
    limit: int | None = FastAPIQuery(None, ge=1, description="cap rows per cohort"),
    filter: str | None = FastAPIQuery(
        None,
        description=(
            "Narrow the counted cohort, as `col:expr;col:expr`. Compiled into "
            "SQL against a whitelist, so 10,236 employees are never fetched to "
            "be discarded in Python. Terms that do not parse are dropped and "
            "reported back in `filters_applied` rather than silently matching "
            "everything."
        ),
    ),
    near_filter: str | None = FastAPIQuery(
        None,
        description=(
            "The same grammar over the near-threshold cohort. SEPARATE from "
            "`filter` because the two are different questions about different "
            "populations: one narrowing must not move the other's count under "
            "a tab nobody is looking at."
        ),
    ),
) -> dict[str, object]:
    """One unit's employee drill, READ FROM `tcc_gold`.

    `month` NARROWS the employee list; it does not annotate it. The previous
    implementation returned every employee at the unit with a `month_value`
    attached and a total that counted all of them — 29 people under a heading
    that the statute answers with 25.

    Sorting, filtering and the near-threshold band are all applied in SQL.
    Candle Bottle holds 10,236 employees across 101 units, so narrowing them in
    Python after fetching them is the same problem one layer down.
    """
    from application.wiring import get_gold_reader
    from infrastructure.persistence.gold_reader import (
        EMPLOYEE_FILTERS,
        NEAR_FILTERS,
        run_envelope,
    )
    from tools.grid_filter import compile_filters

    if method not in ("min_max", "pay_period"):
        raise HTTPException(status_code=422, detail="method must be min_max | pay_period")
    if month is not None and (month < 1 or month > 12):
        raise HTTPException(status_code=422, detail="month must be between 1 and 12")
    if sort not in _UNIT_SORTS:
        raise HTTPException(
            status_code=422, detail=f"sort must be one of {', '.join(sorted(_UNIT_SORTS))}"
        )
    if order.lower() not in ("asc", "desc"):
        raise HTTPException(status_code=422, detail="order must be asc | desc")

    reader = get_gold_reader()
    # Echoed back rather than reflected from the request: a term the compiler
    # dropped must not appear on screen as an active filter, or the page claims
    # a narrowing the total does not have.
    _, _, applied = compile_filters(filter, EMPLOYEE_FILTERS)
    _, _, near_applied = compile_filters(near_filter, NEAR_FILTERS)
    # Six reads on one connection. See v2_client_units.
    with reader.scope():
        drill = reader.unit_drill(
            client_id, unit_id, tax_year=year, method=method, month=month,
            sort=sort, order=order, near_min_hours=near_min_hours, limit=limit,
            employee_filters=filter, near_filters=near_filter,
        )
        run = drill["run"]
        # Same rule as the grid: whether THIS year was calculated is a question
        # about the rows Gold holds, not about the year the run was asked for.
        year_held = drill.get("year_held", drill["unit"] is not None)
        envelope = run_envelope(run, drill["in_flight"], has_rows=year_held)

        base = {
            **envelope,
            "client_id": client_id,
            "state": state,
            "year": year,
            "method": method,
            "month_filter": {"month_index": month},
            "filters_applied": applied,
            "near_filters_applied": near_applied,
        }
        if run is None or not year_held:
            return {
                **base, "unit": None, "employees": [], "near_threshold": [],
                "thresholds": _unit_thresholds(None, year), "total": 0,
                "total_unfiltered": 0, "near_total_unfiltered": 0,
            }

        unit = drill["unit"]
        if unit is None:
            # Gold HOLDS this client-year, so an absent unit is a bad id rather
            # than an uncalculated year.
            raise HTTPException(
                status_code=404,
                detail=f"unit {unit_id!r} is not in the live run for client {client_id} / TY{year}",
            )

        employees = drill["employees"]
        near = _with_lever(drill["near_threshold"], run.get("program_code"), year)
        _with_rest_of_year(near, client_id=client_id, state=state, tax_year=year, run=run)
        return {
            **base,
            "unit": unit,
            "months": drill["months"],
            "employees": employees,
            # The near miss is a SEPARATE cohort, never merged into the qualified
            # list. `onezero_matrix` holds only people already above the floor, so
            # a cusp count taken from it is structurally zero.
            "near_threshold": near,
            "thresholds": _unit_thresholds(run.get("program_code"), year),
            "total": len(employees),
            # What each cohort holds BEFORE its filter, so the grid can say
            # "12 of 37" rather than presenting 12 as the population.
            "total_unfiltered": drill.get("employees_total", len(employees)),
            "near_total_unfiltered": drill.get("near_total", len(drill["near_threshold"])),
        }


def _with_rest_of_year(
    rows: list[dict[str, Any]], *, client_id: int, state: str | None, tax_year: int,
    run: dict[str, Any],
) -> None:
    """What each near-the-floor person needs over the REST of the year.

    29 Sep: a location's near-the-floor list feeds the What-if stack, and the
    stack is pre-filled with this figure — the same one Near the line uses, via
    the same function. Only an open year has a rest of it; a closed year is left
    as it was, and its rows offer no lever.
    """
    if not rows:
        return
    from datetime import date

    from application.queries._client_run import resolve_statute
    from application.queries.get_proximity import attach_rest_of_year

    try:
        resolved = resolve_statute(account_id=client_id, state=state or "GA", tax_year=tax_year)
    except LookupError:
        return
    as_of = date(tax_year, 8, 31)
    if as_of >= resolved.window.end:
        return
    attach_rest_of_year(
        rows, client_id=client_id, tax_year=tax_year, run_id=run["run_id"],
        resolved=resolved, as_of=as_of,
    )


def _with_lever(
    rows: list[dict[str, Any]], program_code: str | None, tax_year: int
) -> list[dict[str, Any]]:
    """"How many more hours a week would Sally have to work?"

    The grid already shows the hours gap, and for most people that IS the
    answer. It is not the answer for everybody: somebody clearing the hours
    floor and failing the wage floor needs extra hours priced at their OWN
    rate, and the binding requirement is the larger of the two. Showing the
    hours gap alone tells that person they are fine.

    The arithmetic is `assess_employee`'s, called rather than copied. A second
    implementation of the lever is a second answer to the one question this
    column exists to answer.

    Deliberately NO dollar figure per person. What a location's credit is worth
    is a function of its job count against a threshold, not of any one
    employee — the marginal person is worth the whole tranche if they cross the
    threshold and nothing at all if they do not, and there is no honest way to
    attribute that to a row. So the column says the hours.
    """
    from domain.calculation.proximity import assess_employee
    from tools.credit_math import resolve_statutory_floors

    if not rows or not program_code:
        return rows
    try:
        floors = resolve_statutory_floors(program_code, tax_year)
    except Exception:  # noqa: BLE001 - an unauthored year has no lever to state
        return rows

    out: list[dict[str, Any]] = []
    for row in rows:
        lever = assess_employee({**row, "Employee_ID": row.get("employee_id")}, floors=floors)
        out.append({
            **row,
            "additional_weekly_hours": lever["additional_weekly_hours"],
            "projected_weekly_hours": lever["projected_weekly_hours"],
            # A lever that needs a 90-hour week is not a lever. Saying so is
            # the difference between a work list and a list of impossibilities.
            "exceeds_plausible_week": lever["exceeds_plausible_week"],
            # Which floor is binding, so the column can say WHY the answer is
            # bigger than the visible hours gap.
            "failure_mode": lever["failure_mode"],
            "hourly_rate_to_qualify": lever["hourly_rate_to_qualify"],
        })
    return out


def _unit_thresholds(program_code: str | None, tax_year: int) -> dict[str, object]:
    """The statutory floor as NUMBERS a marker can be drawn at.

    `rule_pack_version` identifies the statute but cannot be plotted, and a page
    that hardcodes 35 has quietly taken Georgia's floor as everyone's.
    """
    from tools.credit_math import resolve_statutory_floors

    if not program_code:
        return {"min_weekly_hours": None, "min_weekly_wages": None, "resolved": False}
    try:
        floors = resolve_statutory_floors(program_code, tax_year)
    except Exception:  # noqa: BLE001 - an unauthored year has no floor to state
        return {"min_weekly_hours": None, "min_weekly_wages": None, "resolved": False}
    return {
        "min_weekly_hours": float(floors.min_weekly_hours),
        "min_weekly_wages": float(floors.min_weekly_wages),
        "resolved": True,
    }


@router.get("/v2/employees/{record_token}")
def v2_employee_detail(
    record_token: str,
    client_id: int | None = FastAPIQuery(None, description="client scope"),
    year: int | None = FastAPIQuery(None, description="tax year"),
    state: str | None = FastAPIQuery(None, description="optional state override"),
    method: str = FastAPIQuery("min_max", description="min_max | pay_period"),
) -> dict[str, object]:
    """One employee's derivation, READ FROM `tcc_gold` and keyed by the token."""
    from application.wiring import get_gold_reader
    from infrastructure.persistence.gold_reader import run_envelope

    if year is None:
        raise HTTPException(status_code=422, detail="year is required")
    if client_id is None:
        raise HTTPException(status_code=422, detail="client_id is required")

    reader = get_gold_reader()
    with reader.scope():
        run = reader.latest_run(client_id)
        envelope = run_envelope(run, reader.run_in_flight(client_id))

        base = {
            **envelope,
            "client_id": client_id,
            "state": state,
            "tax_year": year,
            "record_token": record_token,
        }
        if run is None:
            return {**base, "eligibility": [], "units": []}

        eligibility = reader.employee(
            record_token, client_id=client_id, tax_year=year, run_id=run["run_id"]
        )
        if not eligibility:
            raise HTTPException(
                status_code=404,
                detail=f"handle {record_token!r} is not in the live run for client {client_id} / TY{year}",
            )

        return {
            **base,
            "employee_id": eligibility[0]["employee_id"],
            "eligibility": eligibility,
            "units": reader.employee_units(
                record_token, client_id=client_id, tax_year=year,
                run_id=run["run_id"], method=method,
            ),
        }


class ClientRunRequest(BaseModel):
    """Run metadata for one client-year."""

    year: int
    state: str = "GA"
    triggered_by: str = "system"
    #: Omitted means assess every year the payroll covers. Name the years for a
    #: targeted recalculation of one.
    assess_years: list[int] | None = None


@router.post("/v2/clients/{client_id}/runs")
def create_client_run(client_id: int, payload: ClientRunRequest, request: Request = None) -> dict[str, Any]:
    """Execute a client-year calculation and persist every row it implies.

    Thin [ADR-003]: the engine call, the projection onto the Gold schema, the
    write and the section 9 validation sweep all live in the command.
    """
    from application.commands.run_client_calculation import (
        RunClientCalculationCommand,
    )
    from application.queries._client_run import ClientRunNotAvailable
    from application.wiring import get_mediator

    try:
        command = RunClientCalculationCommand(
            client_id=client_id,
            tax_year=payload.year,
            state=payload.state.upper(),
            actor=attributed(request, payload.triggered_by, default="system"),
            assess_tax_years=tuple(payload.assess_years or ()),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return get_mediator().send(command)
    except ClientRunNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/v2/clients/{client_id}/runs/latest")
def latest_client_run(client_id: int) -> dict[str, Any]:
    """The live run for a client, read from the warehouse manifest.

    A 404 here means NOT YET CALCULATED, which is a real state and not a zero.
    """
    from application.wiring import get_run_manifest_repository

    manifest = get_run_manifest_repository().latest(client_id)
    if manifest is None:
        raise HTTPException(
            status_code=404,
            detail=f"client {client_id} has not been calculated yet",
        )

    return {
        "run_id": manifest.run_id,
        "client_id": manifest.client_id,
        "tax_year": manifest.tax_year,
        "program_code": manifest.program_code,
        "run_status": manifest.run_status,
        "run_started_at": manifest.run_started_at.isoformat(),
        "run_completed_at": (
            manifest.run_completed_at.isoformat() if manifest.run_completed_at else None
        ),
        "calculation_id": manifest.calculation_id,
        "code_commit": manifest.code_commit,
        "rule_pack_version": manifest.rule_pack_version,
        "triggered_by": manifest.triggered_by,
        "fresh": _run_is_fresh(manifest.run_completed_at),
    }


class EmployeeDrillRequest(BaseModel):
    """The handle stays in the body; an employee never appears in a URL path."""

    record_token: str = Field(min_length=8, max_length=128)
    tax_year: int
    state: str = "GA"
    account_id: int | None = None


@router.post("/employee/drill")
def employee_drill(payload: EmployeeDrillRequest) -> dict[str, Any]:
    """One employee's derivation for the SELECTED client-year, not the sealed run."""
    from application.queries._client_run import ClientRunNotAvailable
    from application.queries.get_employee_drill import GetEmployeeDrillQuery
    from application.wiring import get_mediator

    try:
        query = GetEmployeeDrillQuery(
            record_token=payload.record_token,
            tax_year=payload.tax_year,
            state=payload.state,
            account_id=payload.account_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        return get_mediator().send(query)
    except ClientRunNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
