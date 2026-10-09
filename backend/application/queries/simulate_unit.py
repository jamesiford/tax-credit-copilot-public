"""What-if at ONE location, priced exactly the way the location grid prices it.

Georgia's Job Tax Credit is tested per location, and the grid shows each
location against its OWN frozen base year. The client-wide simulator measures
the whole client against the PRIOR year, which is a different base — at
Cascade GA-016 in TY2025 that is 13.67 jobs against the grid's 7.33. A
location-scoped projection opened from a "Below minimum" pill and priced the
client-wide way would tell the reader that hiring two people does nothing, while
the grid that sent them there says it clears the minimum. Two screens
disagreeing about one location is the defect, whichever is right.

So this does no statutory math of its own:

1. The lever is applied to this location's pay-period rows only, and the
   certified engine re-runs over the WHOLE client-year. An employee who works at
   two locations keeps every row, so their eligibility verdict is not changed by
   the scoping.
2. The location's average is read out of the engine's allocation, the same
   aggregation the write path uses.
3. That average replaces ONE year in the location's series from Gold, and the
   series is priced by `unit_trend` — the function that wrote the grid.

Before projecting it proves the baseline: the unmoved engine must reproduce the
grid's average and credit for that year. If the payroll has moved since the run
that wrote Gold, it declines rather than projecting from a base nobody can see.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query

_ACTIONS = ("add_headcount", "remove_headcount", "adjust_hours", "adjust_wages")
_METHODS = ("min_max", "pay_period")
# Gold stores averages to two places, so anything inside a cent of a job agrees.
_AVERAGE_TOLERANCE = 0.011
_CREDIT_TOLERANCE_USD = 1.0


@dataclass(frozen=True)
class SimulateUnitQuery(Query):
    """One lever, applied at one location, in one client-year, under one method."""

    client_id: int
    worksite_id: str
    tax_year: int
    state: str = "GA"
    method: str = "min_max"
    action: str = "add_headcount"
    magnitude: float = 1.0
    #: WI-22. What a hired role is: hours a week and pay. Both optional.
    hire_weekly_hours: float | None = None
    hire_hourly_rate: float | None = None

    def __post_init__(self) -> None:
        if self.action not in _ACTIONS:
            raise ValueError(f"action must be one of {_ACTIONS}, got {self.action!r}")
        if self.method not in _METHODS:
            raise ValueError(f"method must be one of {_METHODS}, got {self.method!r}")
        if self.hire_weekly_hours is not None and not 0 < self.hire_weekly_hours <= 80:
            raise ValueError("hire_weekly_hours must be between 0 and 80")
        if self.hire_hourly_rate is not None and not 0 < self.hire_hourly_rate <= 500:
            raise ValueError("hire_hourly_rate must be between 0 and 500")


class UnitSimulationNotAvailable(LookupError):
    """The projection cannot be made for this location-year, and why."""


def _unit_reading(result: Any, worksite_id: str, *, closed_months: int | None = None) -> dict[str, Any] | None:
    """This location's average from an engine result, aggregated like the write path.

    `closed_months` reads an OPEN year the way the write path writes one: the
    average of its first N months, not of twelve. The months after the
    checkpoint have not happened, and dividing by them would invent a decline.
    """
    from domain.calculation.rollups import rollup_matrix_by_two_fields
    from tools.unit_trend import aggregate_units

    summary = [
        {"unit_id": row["Worksite_ID"], "fein": row["Entity_FEIN"], **row}
        for row in rollup_matrix_by_two_fields(
            result.employee_unit_matrix, "Worksite_ID", "Entity_FEIN"
        )
    ]
    unit = next((u for u in aggregate_units(summary) if u["unit_id"] == worksite_id), None)
    if unit is not None and closed_months:
        # The first N months — the closed ones — over N. Before a lever that is
        # the write path's total / closed exactly, because the months after the
        # checkpoint hold nothing yet. A rest-of-year lever FILLS those months,
        # and summing them in would put the forecast into a to-date average.
        closed = [float(v) for v in unit["month_totals"][:closed_months]]
        unit = {**unit, "average_headcount": round(sum(closed) / closed_months, 2)}
    return unit


def open_year_months(row: dict[str, Any] | None) -> int | None:
    """The closed months of an open Gold row, or None for a closed year."""
    if row and row.get("status") == "in_progress":
        return int(row.get("months_reachable") or 0) or None
    return None


def _signed_margin(stair: Any) -> float:
    """Jobs over (+) or short of (-) the minimum, measured from the base itself."""
    gap = float(stair.average_headcount) - float(stair.base_average_headcount)
    return round(gap - float(stair.threshold), 2)


def _num(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _reading(
    stair: Any, *, tax_year: int, base_year: int, months: int, reachable: int,
    in_progress: bool = False,
) -> dict[str, Any]:
    from tools.unit_trend import STATUS_IN_PROGRESS, unit_status

    return {
        "average_headcount": round(stair.average_headcount, 2),
        "base_average_headcount": round(stair.base_average_headcount, 2),
        "net_new_vs_base": round(stair.net_new, 2),
        "threshold": stair.threshold,
        # Signed, unlike net new: one job over and fifty over must not read alike.
        # Against the BASE, not the clamped net new: GA-016 in TY2026 once sat at
        # 3.0 against 7.33, and "2.00 short" understated the gap by 4.33 jobs.
        "jobs_margin": _signed_margin(stair),
        # For an open year this is ON TRACK, not qualified: nothing is decided
        # until the year closes.
        "qualified": bool(stair.qualified),
        "status": STATUS_IN_PROGRESS if in_progress else unit_status(
            tax_year=tax_year, base_year=base_year, qualified=bool(stair.qualified),
            months_with_headcount=months, months_reachable=reachable,
        ),
        "eligible_jobs": round(stair.eligible_jobs, 2),
        "annual_credit_usd": round(stair.annual_credit_usd),
    }


def location_series(items: list[dict[str, Any]], site: str) -> tuple[dict[int, dict[str, Any]], int | None]:
    """One location's Gold rows by year, and the base year the grid measured it from."""
    rows_by_year = {int(row["tax_year"]): row for row in items if row.get("worksite_id") == site}
    if not rows_by_year:
        return {}, None
    base_year = next(
        (year for year, row in rows_by_year.items() if row.get("is_base_year")),
        min(rows_by_year),
    )
    return rows_by_year, base_year


def location_trend(
    rows_by_year: dict[int, dict[str, Any]], *, state: str, base_year: int,
    averages: dict[int, float] | None = None,
) -> Any:
    """The whole series priced by `unit_trend` — the function the write path used.

    Gold's own averages and per-year statute; `averages` replaces a year's
    headcount first, which is a what-if. Any `base_year` the series holds can be
    passed: yearly average headcount does not depend on the base, so moving it
    re-prices exactly what the write path would have produced.
    """
    from tools.unit_trend import unit_trend

    # An open year is not part of the priced series: the write path priced the
    # closed years alone, so re-pricing must too or a TY2025 check would read
    # TY2026's partial average into the tranches.
    rows_by_year = {
        year: row for year, row in rows_by_year.items() if open_year_months(row) is None
    } or rows_by_year
    latest = rows_by_year[max(rows_by_year)]
    threshold = _num(latest.get("threshold"))
    per_year = {
        year: {
            "threshold": _num(row.get("threshold")) if row.get("threshold") is not None else threshold,
            "per_job_usd": _num(row.get("per_job_usd")),
        }
        for year, row in rows_by_year.items()
    }
    series = {
        year: {"average_headcount": _num(row.get("average_headcount"))}
        for year, row in rows_by_year.items()
    }
    for year, average in (averages or {}).items():
        if year in series:
            series[year] = {"average_headcount": float(average)}
    return unit_trend(
        series, state=state, base_year=base_year, threshold=threshold,
        per_job_usd=_num(latest.get("per_job_usd")),
        tranche_years=int(latest.get("tranche_years") or 5),
        benefit_by_year=per_year,
    )


def price_location_year(
    rows_by_year: dict[int, dict[str, Any]], *, state: str, tax_year: int, base_year: int,
    average: float | None = None,
) -> tuple[Any, Any]:
    """Price one year of a location's series exactly as the grid priced it.

    The series is Gold's, with its per-year statute, so this is `unit_trend` —
    the function the write path used — and no statutory math of its own. With
    `average`, that one year's headcount is replaced first; that is a what-if.
    """
    trend = location_trend(
        rows_by_year, state=state, base_year=base_year,
        averages={tax_year: average} if average is not None else None,
    )
    row = rows_by_year.get(tax_year)
    if open_year_months(row) is not None:
        # An open year is read, not priced: on its closed months, against the
        # closed series' base, with no credit until it closes. The same
        # function the write path used to write the row.
        from application.open_year import open_year_reading

        statute = {"threshold": _num(row.get("threshold")), "per_job_usd": _num(row.get("per_job_usd"))}
        stair = open_year_reading(
            average if average is not None else _num(row.get("average_headcount")),
            trend, statute, statute["threshold"],
        )
        return stair, trend
    return next(y for y in trend.years if y.year == tax_year), trend


#: An open year's credit is not claimable until it closes. A run-rate is the
#: one labelled estimate the product makes of it, and every figure produced
#: here travels under this name so no screen can render it as a calculation.
RUN_RATE_BASIS = "run_rate"


def run_rate_credit(
    rows_by_year: dict[int, dict[str, Any]], *, state: str, tax_year: int, base_year: int,
    average: float | None = None,
) -> int | None:
    """What an OPEN year would earn if it closed at its pace so far.

    The to-date average stands in for the full year and the series is priced by
    `unit_trend` — the function that wrote the grid — exactly as a closed year
    would be: new tranches at this year's rate, and earlier tranches lost if
    the jobs behind them are not maintained. No statutory math of its own; the
    only assumption is that the remaining months run at the closed months'
    pace, which is what "run-rate" says. None for a year that is not open.
    """
    row = rows_by_year.get(tax_year)
    if open_year_months(row) is None:
        return None
    as_if_closed = {**rows_by_year, tax_year: {**row, "status": RUN_RATE_BASIS}}
    trend = location_trend(
        as_if_closed, state=state, base_year=base_year,
        averages={tax_year: average if average is not None else _num(row.get("average_headcount"))},
    )
    year = next(y for y in trend.years if y.year == tax_year)
    return round(year.annual_credit_usd)


def handle_simulate_unit(query: SimulateUnitQuery) -> dict[str, Any]:
    from application.queries._client_run import ClientRunNotAvailable, resolve_client_run
    from application.wiring import get_gold_reader
    from domain.calculation.onezero import run_min_max_method, run_pay_period_method
    from tools.simulation import apply_onezero_lever

    state = query.state.upper()
    site = query.worksite_id

    reader = get_gold_reader()
    with reader.scope():
        run = reader.latest_run(query.client_id)
        items, _total = reader.unit_years(query.client_id, method=query.method, limit=5000)
    rows_by_year = {
        int(row["tax_year"]): row for row in items if row.get("worksite_id") == site
    }
    if not rows_by_year:
        raise UnitSimulationNotAvailable(
            f"no calculated run holds location {site} for account {query.client_id}"
        )
    target = rows_by_year.get(query.tax_year)
    if target is None:
        raise UnitSimulationNotAvailable(
            f"the run holds no TY{query.tax_year} for location {site}"
        )
    base_year = next(
        (year for year, row in rows_by_year.items() if row.get("is_base_year")),
        min(rows_by_year),
    )
    if query.tax_year == base_year:
        # Moving the base year moves every later year's net new. That is a
        # restatement of the baseline, not a projection of one year.
        raise UnitSimulationNotAvailable(
            f"TY{query.tax_year} is {site}'s base year — the figure every later year "
            f"is measured against, so a lever there is not a what-if about that year"
        )

    try:
        client_run = resolve_client_run(
            account_id=query.client_id, state=state, tax_year=query.tax_year,
        )
    except ClientRunNotAvailable as exc:
        raise UnitSimulationNotAvailable(str(exc)) from exc

    at_site = [r for r in client_run.rows if r.get("Worksite_ID") == site]
    if not at_site:
        raise UnitSimulationNotAvailable(
            f"no TY{query.tax_year} payroll at {site} inside the client's fiscal window"
        )
    elsewhere = [r for r in client_run.rows if r.get("Worksite_ID") != site]

    runner = run_min_max_method if query.method == "min_max" else run_pay_period_method
    kwargs = client_run.engine_kwargs()
    # TY2026. An open year is read on its closed months on BOTH sides, so the
    # lever moves the same average the grid shows.
    closed_months = open_year_months(target)

    before = _unit_reading(runner(client_run.rows, **kwargs), site, closed_months=closed_months)
    gold_average = _num(target.get("average_headcount"))
    if before is None or abs(before["average_headcount"] - gold_average) > _AVERAGE_TOLERANCE:
        raise UnitSimulationNotAvailable(
            f"{site}'s payroll no longer reproduces the run that wrote the grid "
            f"(grid {gold_average:.2f}, payroll "
            f"{before['average_headcount'] if before else 0:.2f}). Re-run the "
            f"calculation before projecting from it."
        )

    moved, detail = apply_onezero_lever(
        at_site, action=query.action, magnitude=query.magnitude,
        pack=kwargs["pack"], state=state,
        hire_weekly_hours=query.hire_weekly_hours, hire_hourly_rate=query.hire_hourly_rate,
    )
    after = _unit_reading(runner(elsewhere + moved, **kwargs), site, closed_months=closed_months) or {
        "average_headcount": 0.0, "months_with_headcount": 0,
    }

    baseline_stair, baseline_trend = price_location_year(
        rows_by_year, state=state, tax_year=query.tax_year, base_year=base_year,
    )
    if (
        bool(baseline_stair.qualified) != bool(target.get("qualified"))
        or abs(baseline_stair.annual_credit_usd - _num(target.get("annual_credit_usd")))
        > _CREDIT_TOLERANCE_USD
    ):
        raise UnitSimulationNotAvailable(
            f"re-pricing {site}'s series does not reproduce the grid's TY{query.tax_year} "
            f"credit, so a projection from it would not be comparable. Re-run the calculation."
        )

    projected_stair, projected_trend = price_location_year(
        rows_by_year, state=state, tax_year=query.tax_year, base_year=base_year,
        average=after["average_headcount"],
    )

    reachable = int(target.get("months_reachable") or 12)
    in_progress = closed_months is not None
    baseline = _reading(
        baseline_stair, tax_year=query.tax_year, base_year=base_year,
        months=int(target.get("months_with_headcount") or before["months_with_headcount"]),
        reachable=reachable, in_progress=in_progress,
    )
    projected = _reading(
        projected_stair, tax_year=query.tax_year, base_year=base_year,
        months=int(after["months_with_headcount"]), reachable=reachable,
        in_progress=in_progress,
    )

    def series_credit(trend: Any) -> int:
        return round(sum(year.annual_credit_usd for year in trend.years))

    baseline["series_credit_usd"] = series_credit(baseline_trend)
    projected["series_credit_usd"] = series_credit(projected_trend)
    run_rate = None
    if in_progress:
        was = run_rate_credit(rows_by_year, state=state, tax_year=query.tax_year, base_year=base_year)
        now = run_rate_credit(
            rows_by_year, state=state, tax_year=query.tax_year, base_year=base_year,
            average=after["average_headcount"],
        )
        run_rate = {
            "basis": RUN_RATE_BASIS,
            "before_usd": was,
            "after_usd": now,
            "delta_usd": now - was,
            "note": (
                f"Run-rate estimate: TY{query.tax_year} priced as if it closed at its "
                f"pace over the {closed_months} closed months, against {site}'s "
                f"TY{base_year} base. Nothing is claimable until the year closes."
            ),
        }

    return {
        "scope": {
            "client_id": query.client_id,
            "worksite_id": site,
            "state": state,
            "program_code": client_run.program_code,
            "tax_year": query.tax_year,
            "method": query.method,
        },
        "action": query.action,
        "magnitude": query.magnitude,
        "detail": detail.replace(f"in {state}", f"at {site}").replace(f"from {state}", f"at {site}")
        .replace(f"across all {state} pay periods", f"across {site}'s pay periods"),
        "base_year": base_year,
        "series_years": [min(rows_by_year), max(rows_by_year)],
        "eligibility_floors": {
            "min_weekly_hours": kwargs["pack"].min_weekly_hours,
            "min_weekly_wages": kwargs["pack"].min_weekly_wages,
        },
        "baseline": baseline,
        "projected": projected,
        "delta": {
            key: round(projected[key] - baseline[key], 2)
            for key in ("average_headcount", "net_new_vs_base", "annual_credit_usd", "series_credit_usd")
        },
        "open_year": {
            "months_closed": closed_months,
            "note": (
                f"TY{query.tax_year} is still open. Both sides are read on its "
                f"{closed_months} closed months, against {site}'s TY{base_year} base: "
                f"'qualified' means on track to date, and the only credit shown is a "
                f"labelled run-rate estimate — nothing is claimable until the year "
                f"closes. A hire here is counted as if on payroll for those "
                f"months."
            ),
        } if in_progress else None,
        "run_rate": run_rate,
        "run_id": (run or {}).get("run_id"),
        "method_note": (
            f"Priced as the location grid prices it: {site} against its own TY{base_year} "
            f"base, under TY{query.tax_year} statute. The lever changes only this "
            f"location's payroll; everyone's eligibility is re-decided by the same engine."
        ),
    }
