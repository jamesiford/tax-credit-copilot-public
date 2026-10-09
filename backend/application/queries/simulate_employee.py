"""What-if for a STACK of employees: each works differently for the rest of the year.

The partner, 24 September: "a picker of what's already available and putting them
into this what-if scenario, rather than creating it from thin air." The Near
the line cohort says what each person needs over the rest of the year; this
applies exactly that and re-runs the certified engine, so the verdict shown
flipping is the engine's, not an assertion.

28 September: one employee at a time was not the question. "Select a few and
stack them, so we can see the what-if for a multi-employee modification." So a
query carries a list of changes, every one is applied to the same client-year
payroll, and the engine runs ONCE over the result. Stacking is not the sum of
single-employee projections: two people who each fall short of moving a
location may move it together, and only one engine run can say so.

Each change has two levers, because the honest one differs by person:

- **more hours a week** for somebody failing the hours floor, and
- **a raise in $/hr** for somebody paid below the threshold rate, where more
  hours would take them to an implausible week.

The scenario, precisely: from the checkpoint to the end of the fiscal year the
employee works their year-to-date pace plus the extra hours, at their
year-to-date rate plus the raise. Periods closed by the checkpoint are left
exactly as paid. Nothing after the checkpoint is treated as known — on 31
August it has not happened — so the remaining periods are set to that pace
rather than having the extra added to whatever the payroll later recorded.

Each location a stacked employee works at is priced as the grid prices it (its
own frozen base, via `price_location_year`), and the client's change is the
sum of those locations' changes, because no other row moves.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from application.mediator import Query

_METHODS = ("min_max", "pay_period")
#: The most employees one projection stacks. A what-if is a conversation about
#: a handful of named people; a stack of hundreds is a different lever (Hours).
MAX_STACK = 25
MAX_EXTRA_WEEKLY_HOURS = 40.0
MAX_HOURLY_RAISE = 100.0


@dataclass(frozen=True)
class EmployeeChange:
    """One stacked employee, by record token — never an employee id."""

    record_token: str
    additional_weekly_hours: float = 0.0
    hourly_raise: float = 0.0

    def __post_init__(self) -> None:
        if not self.record_token:
            raise ValueError("record_token is required")
        if not 0 <= self.additional_weekly_hours <= MAX_EXTRA_WEEKLY_HOURS:
            raise ValueError(f"additional_weekly_hours must be between 0 and {MAX_EXTRA_WEEKLY_HOURS:g}")
        if not 0 <= self.hourly_raise <= MAX_HOURLY_RAISE:
            raise ValueError(f"hourly_raise must be between 0 and {MAX_HOURLY_RAISE:g}")


@dataclass(frozen=True)
class SimulateEmployeeQuery(Query):
    client_id: int
    tax_year: int
    changes: tuple[EmployeeChange, ...]
    state: str = "GA"
    method: str = "min_max"
    as_of: date | None = None

    def __post_init__(self) -> None:
        if self.method not in _METHODS:
            raise ValueError(f"method must be one of {_METHODS}, got {self.method!r}")
        if not self.changes:
            raise ValueError("at least one employee is required")
        if len(self.changes) > MAX_STACK:
            raise ValueError(f"at most {MAX_STACK} employees can be stacked")
        tokens = [c.record_token for c in self.changes]
        if len(set(tokens)) != len(tokens):
            raise ValueError("an employee appears twice in the stack")

    def resolved_as_of(self) -> date:
        # The progress view's checkpoint, so the row and the projection agree.
        return self.as_of or date(self.tax_year, 8, 31)


class EmployeeSimulationNotAvailable(LookupError):
    """The projection cannot be made for this employee, and why."""


def _day(value: Any) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def apply_rest_of_year(
    rows: list[dict[str, Any]], employee_id: str, *, as_of: date, extra_weekly_hours: float,
    window_end: date | None = None, hourly_raise: float = 0.0,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The client-year rows with ONE employee's remaining periods set to pace + extra.

    Pure. Returns the new rows and what was done, for the response to state.
    With `window_end`, an employee whose payroll stops at the checkpoint — an
    open year — has the remaining periods projected rather than refused.
    `hourly_raise` is added to their year-to-date rate for those periods only;
    periods already closed stay as paid.
    """
    mine = [r for r in rows if str(r["Employee_ID"]) == employee_id]
    closed = [r for r in mine if _day(r["Pay_Period_End"]) <= as_of]
    hours_to_date = sum(float(r.get("Hours_Worked") or 0) for r in closed)
    wages_to_date = sum(float(r.get("Gross_Wages") or 0) for r in closed)
    if not closed or hours_to_date <= 0:
        raise EmployeeSimulationNotAvailable("no hours closed by the checkpoint to take a pace from")
    first = min(_day(r["Pay_Period_Start"]) for r in closed)
    last = max(_day(r["Pay_Period_End"]) for r in closed)
    weeks_to_date = max((last - first).days / 7.0, 1 / 7.0)
    pace = hours_to_date / weeks_to_date
    rate = wages_to_date / hours_to_date

    # Group the open lines by period, so a period split across pay codes is
    # scaled as one period rather than given the extra once per line.
    open_periods: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in mine:
        if _day(r["Pay_Period_End"]) > as_of:
            open_periods.setdefault((str(r["Pay_Period_Start"]), str(r["Pay_Period_End"])), []).append(r)
    projected: list[dict[str, Any]] = []
    if not open_periods and window_end is not None and as_of < window_end:
        # An OPEN year (TY2026): the payroll stops at the checkpoint, because
        # the months after it have not happened. The remaining periods are
        # projected on the employee's own cadence, from their busiest line in
        # the last closed period — labelled, never mistaken for paid payroll.
        projected = _project_periods(closed, as_of=as_of, window_end=window_end)
        for line in projected:
            open_periods.setdefault((line["Pay_Period_Start"], line["Pay_Period_End"]), []).append(line)
    if not open_periods:
        raise EmployeeSimulationNotAvailable(
            "no pay periods after the checkpoint: the year is closed for this employee"
        )

    replaced: dict[int, dict[str, Any]] = {}
    new_rate = rate + hourly_raise
    for (start, end), lines in open_periods.items():
        weeks = ((_day(end) - _day(start)).days + 1) / 7.0
        target_hours = (pace + extra_weekly_hours) * weeks
        target_wages = target_hours * new_rate
        have_hours = sum(float(l.get("Hours_Worked") or 0) for l in lines)
        have_wages = sum(float(l.get("Gross_Wages") or 0) for l in lines)
        for index, line in enumerate(lines):
            copy = dict(line)
            if have_hours > 0:
                copy["Hours_Worked"] = float(line.get("Hours_Worked") or 0) * target_hours / have_hours
            else:
                copy["Hours_Worked"] = target_hours if index == 0 else 0.0
            if have_wages > 0:
                copy["Gross_Wages"] = float(line.get("Gross_Wages") or 0) * target_wages / have_wages
            else:
                copy["Gross_Wages"] = target_wages if index == 0 else 0.0
            replaced[id(line)] = copy

    moved = [replaced.get(id(r), r) for r in rows] + [replaced[id(line)] for line in projected]
    return moved, {
        "pace_weekly_hours": round(pace, 2),
        "projected_weekly_hours": round(pace + extra_weekly_hours, 2),
        "rate": round(rate, 2),
        "projected_rate": round(new_rate, 2),
        "periods_changed": len(open_periods),
        "periods_projected": len({(l["Pay_Period_Start"], l["Pay_Period_End"]) for l in projected}),
    }


def _project_periods(
    closed: list[dict[str, Any]], *, as_of: date, window_end: date,
) -> list[dict[str, Any]]:
    """The periods an open year has not reached yet, on this employee's cadence.

    One line per period, copied from the busiest line of the last closed period
    so the worksite, entity and pay code are the ones the employee is actually
    on. Hours and wages are placeholders; the caller sets them to the scenario.
    Only periods PAID inside the window are kept — the same Pay_Date trim the
    run applies.
    """
    from datetime import timedelta

    last_end = max(_day(r["Pay_Period_End"]) for r in closed)
    last = [r for r in closed if _day(r["Pay_Period_End"]) == last_end]
    template = max(last, key=lambda r: float(r.get("Hours_Worked") or 0))
    start, end = _day(template["Pay_Period_Start"]), _day(template["Pay_Period_End"])
    length = end - start
    lag = (_day(template["Pay_Date"]) - end) if template.get("Pay_Date") else timedelta(0)

    lines: list[dict[str, Any]] = []
    period_start = last_end + timedelta(days=1)
    while True:
        period_end = period_start + length
        pay_date = period_end + lag
        if pay_date > window_end:
            break
        if period_end > as_of:
            lines.append({
                **template,
                "Pay_Period_Start": period_start.isoformat(),
                "Pay_Period_End": period_end.isoformat(),
                "Pay_Date": pay_date.isoformat(),
                "Tax_Year": pay_date.year,
                "Hours_Worked": 0.0,
                "Gross_Wages": 0.0,
                "_Source_Payroll_Id": None,
                "_Projected": True,
            })
        period_start = period_end + timedelta(days=1)
    return lines


def _verdict(result: Any, employee_id: str) -> dict[str, Any]:
    row = next((a for a in result.all_averages if str(a["Employee_ID"]) == employee_id), None)
    eligible = any(str(e["Employee_ID"]) == employee_id for e in result.eligible_employees)
    return {
        "eligible": eligible,
        "avg_weekly_hours": round(float(row["avg_weekly_hours"]), 2) if row else None,
        "avg_weekly_wages": round(float(row["avg_weekly_wages"]), 2) if row else None,
    }


def _designation(grid: dict[str, Any] | None) -> dict[str, Any]:
    """The designation the grid shows for a location-year, in the grid's own fields."""
    grid = grid or {}
    return {
        "designation": grid.get("designation"),
        "tier": grid.get("tier"),
        "tier_source": grid.get("tier_source") or ("prototype" if grid.get("designation") else "unassigned"),
    }


def handle_simulate_employee(query: SimulateEmployeeQuery) -> dict[str, Any]:
    from application.queries._client_run import ClientRunNotAvailable, resolve_client_run
    from application.queries.simulate_unit import (
        _signed_margin, _unit_reading, location_series, open_year_months, price_location_year,
        run_rate_credit, RUN_RATE_BASIS,
    )
    from application.wiring import get_gold_reader
    from domain.calculation.onezero import run_min_max_method, run_pay_period_method
    from tools.tokens import record_token

    state = query.state.upper()
    as_of = query.resolved_as_of()
    try:
        run = resolve_client_run(account_id=query.client_id, state=state, tax_year=query.tax_year)
    except ClientRunNotAvailable as exc:
        raise EmployeeSimulationNotAvailable(str(exc)) from exc
    if as_of >= run.window.end:
        raise EmployeeSimulationNotAvailable("the year is closed — once it is, it is written in stone")

    # One pass over the population resolves every token in the stack.
    wanted = {c.record_token for c in query.changes}
    by_token: dict[str, str] = {}
    for emp in {str(r["Employee_ID"]) for r in run.rows}:
        token = record_token(query.client_id, run.program_code, query.tax_year, emp)
        if token in wanted:
            by_token[token] = emp
    missing = [c.record_token for c in query.changes if c.record_token not in by_token]
    if missing:
        raise EmployeeSimulationNotAvailable(
            f"{len(missing)} of the {len(query.changes)} stacked records match no employee "
            f"in this client-year"
        )

    # Every change lands on the SAME payroll before the engine runs once.
    moved = run.rows
    applied: dict[str, dict[str, Any]] = {}
    for change in query.changes:
        employee_id = by_token[change.record_token]
        try:
            moved, applied[change.record_token] = apply_rest_of_year(
                moved, employee_id, as_of=as_of,
                extra_weekly_hours=change.additional_weekly_hours,
                hourly_raise=change.hourly_raise, window_end=run.window.end,
            )
        except EmployeeSimulationNotAvailable as exc:
            raise EmployeeSimulationNotAvailable(f"employee {employee_id}: {exc}") from exc

    runner = run_min_max_method if query.method == "min_max" else run_pay_period_method
    kwargs = run.engine_kwargs()
    before_result = runner(run.rows, **kwargs)
    after_result = runner(moved, **kwargs)

    reader = get_gold_reader()
    with reader.scope():
        items, _total = reader.unit_years(query.client_id, method=query.method, limit=5000)

    # Where each stacked employee works, and the one they work at most: that
    # is the location the stack names them against.
    hours_at: dict[str, dict[str, float]] = {}
    stacked = set(by_token.values())
    for r in run.rows:
        emp = str(r["Employee_ID"])
        if emp in stacked:
            sites = hours_at.setdefault(emp, {})
            site = str(r["Worksite_ID"])
            sites[site] = sites.get(site, 0.0) + float(r.get("Hours_Worked") or 0)

    grid_rows: dict[str, dict[str, Any] | None] = {}
    locations = []
    for site in sorted({s for sites in hours_at.values() for s in sites}):
        rows_by_year, base_year = location_series(items, site)
        grid = rows_by_year.get(query.tax_year)
        grid_rows[site] = grid
        if grid is None or base_year is None or base_year == query.tax_year:
            continue
        # An open year is read on its closed months, both sides. Becoming
        # eligible counts the person in the months they have already worked;
        # the projected months stay out of a to-date average.
        closed_months = open_year_months(grid)
        before = _unit_reading(before_result, site, closed_months=closed_months)
        after = _unit_reading(after_result, site, closed_months=closed_months)
        if before is None or abs(before["average_headcount"] - float(grid["average_headcount"])) > 0.011:
            raise EmployeeSimulationNotAvailable(
                f"{site}'s payroll no longer reproduces the run that wrote the grid. "
                f"Re-run the calculation before projecting from it."
            )
        was, _ = price_location_year(rows_by_year, state=state, tax_year=query.tax_year, base_year=base_year)
        now, _ = price_location_year(
            rows_by_year, state=state, tax_year=query.tax_year, base_year=base_year,
            average=(after or {"average_headcount": 0.0})["average_headcount"],
        )
        run_rate = None
        if closed_months is not None:
            # An open year's credit, as the one labelled estimate: priced as if
            # the year closed at its pace so far. Both sides on the same basis.
            run_rate = {
                "before_usd": run_rate_credit(
                    rows_by_year, state=state, tax_year=query.tax_year, base_year=base_year,
                ),
                "after_usd": run_rate_credit(
                    rows_by_year, state=state, tax_year=query.tax_year, base_year=base_year,
                    average=now.average_headcount,
                ),
            }
            run_rate["delta_usd"] = run_rate["after_usd"] - run_rate["before_usd"]
        locations.append({
            "worksite_id": site,
            "base_year": base_year,
            **_designation(grid),
            # True for an open year: `qualified` below means on track to date.
            "in_progress": closed_months is not None,
            "threshold": was.threshold,
            "employees": sorted(
                emp for emp, sites in hours_at.items() if site in sites
            ),
            "before": {
                "average_headcount": round(was.average_headcount, 2),
                "net_new_vs_base": round(was.net_new, 2),
                "jobs_margin": _signed_margin(was),
                "qualified": bool(was.qualified),
                "annual_credit_usd": round(was.annual_credit_usd),
            },
            "after": {
                "average_headcount": round(now.average_headcount, 2),
                "net_new_vs_base": round(now.net_new, 2),
                "jobs_margin": _signed_margin(now),
                "qualified": bool(now.qualified),
                "annual_credit_usd": round(now.annual_credit_usd),
            },
            "run_rate": run_rate,
        })

    employees = []
    for change in query.changes:
        emp = by_token[change.record_token]
        sites = hours_at.get(emp, {})
        primary = max(sites, key=sites.get) if sites else None
        employees.append({
            "record_token": change.record_token,
            # Displayed after auth, like every row on the page. Never in a URL.
            "employee_id": emp,
            "worksite_id": primary,
            "worksites": sorted(sites),
            **_designation(grid_rows.get(primary) if primary else None),
            "additional_weekly_hours": change.additional_weekly_hours,
            "hourly_raise": change.hourly_raise,
            "applied": applied[change.record_token],
            "before": _verdict(before_result, emp),
            "after": _verdict(after_result, emp),
        })

    client_before = round(sum(
        float(row.get("annual_credit_usd") or 0) for row in items if int(row["tax_year"]) == query.tax_year
    ))
    client_delta = sum(l["after"]["annual_credit_usd"] - l["before"]["annual_credit_usd"] for l in locations)
    projected_periods = sum(a.get("periods_projected") or 0 for a in applied.values())
    became = sum(1 for e in employees if e["after"]["eligible"] and not e["before"]["eligible"])
    open_locations = [l for l in locations if l["run_rate"] is not None]
    # Only the locations the stack touches move, so the gain is their sum. No
    # client-wide run-rate TOTAL is stated: How am I doing projects the client
    # against its prior year, a different base, and two totals for one year
    # would disagree on screen.
    run_rate_gain = {
        "basis": RUN_RATE_BASIS,
        "delta_usd": sum(l["run_rate"]["delta_usd"] for l in open_locations),
        # Over the locations the stack touches, and only those — said so on screen.
        "before_usd": sum(l["run_rate"]["before_usd"] for l in open_locations),
        "after_usd": sum(l["run_rate"]["after_usd"] for l in open_locations),
        "locations": len(open_locations),
        "note": (
            f"Run-rate estimate: each location's TY{query.tax_year} priced as if the year "
            f"closed at its pace over the closed months, against its own base. Nothing is "
            f"claimable until the year closes."
        ),
    } if open_locations else None

    return {
        "scope": {
            "client_id": query.client_id, "state": state, "tax_year": query.tax_year,
            "method": query.method, "as_of": as_of.isoformat(),
        },
        "employees": employees,
        "locations": locations,
        "summary": {
            "employees": len(employees),
            "became_eligible": became,
            "lost_eligibility": sum(
                1 for e in employees if e["before"]["eligible"] and not e["after"]["eligible"]
            ),
            "locations_moved": sum(
                1 for l in locations if l["after"]["qualified"] != l["before"]["qualified"]
            ),
        },
        "client": {
            "annual_credit_usd_before": client_before,
            "annual_credit_usd_after": client_before + client_delta,
            "annual_credit_usd_delta": client_delta,
            "run_rate": run_rate_gain,
        },
        "eligibility_floors": {
            "min_weekly_hours": kwargs["pack"].min_weekly_hours,
            "min_weekly_wages": kwargs["pack"].min_weekly_wages,
        },
        "method_note": (
            f"From {as_of:%d %b} to the end of the fiscal year each stacked employee works "
            f"their pace to date plus the extra hours, at their own rate plus the raise; "
            f"periods already closed are left as paid. All {len(employees)} changes are "
            f"applied together and the certified engine re-decides everyone once, so two "
            f"people who could not move a location alone are seen moving it together. Each "
            f"location is priced against its own base year, as the grid prices it."
            + (
                f" TY{query.tax_year} is still open: the periods after {as_of:%d %b} are "
                f"projected on each employee's own cadence, and each location is read on "
                f"its closed months. The credit gained is a run-rate estimate: each "
                f"location priced as if the year closed at that pace."
                if projected_periods else ""
            )
        ),
    }