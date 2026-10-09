"""One location's series, re-priced against a base year the reader chose (WI-21).

The partner, 24 September: "Maybe this screen would have the ability for the user to
pull down a drop down and say, this is going to be a base year... everything
above that kind of grayed out... each subsequent year... year one, year two,
year three... if I drop below the requisite number... DNQ."

A READ, and a derivation rather than a restatement. Yearly average headcount
does not depend on the base, so moving the base re-prices the run's own
averages through `unit_trend` — the function the write path used — and answers
exactly what that run would have produced with this base. No engine replay, no
payroll, nothing written. The certified figures stay what they are; this is a
view of what they WOULD be, and the response says so.

Only a complete year can be a base. A partial year makes a flattering base —
fewer months averaged over twelve reads as a lower baseline, and every later
year then looks like growth that never happened (see `infer_base_year`).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query

_METHODS = ("min_max", "pay_period")


@dataclass(frozen=True)
class RebaseUnitQuery(Query):
    client_id: int
    worksite_id: str
    base_year: int
    method: str = "min_max"
    state: str = "GA"

    def __post_init__(self) -> None:
        if self.method not in _METHODS:
            raise ValueError(f"method must be one of {_METHODS}, got {self.method!r}")


class RebaseNotAvailable(LookupError):
    """This base year cannot be used for this location, and why."""


def _complete(row: dict[str, Any]) -> bool:
    return int(row.get("months_with_headcount") or 0) >= int(row.get("months_reachable") or 12)


def handle_rebase_unit(query: RebaseUnitQuery) -> dict[str, Any]:
    from application.open_year import open_year_reading
    from application.queries.simulate_unit import (
        _num, location_series, location_trend, open_year_months,
    )
    from application.wiring import get_gold_reader
    from tools.unit_trend import unit_status

    reader = get_gold_reader()
    with reader.scope():
        run = reader.latest_run(query.client_id)
        items, _total = reader.unit_years(query.client_id, method=query.method, limit=5000)

    rows_by_year, inferred = location_series(items, query.worksite_id)
    if not rows_by_year:
        raise RebaseNotAvailable(
            f"no calculated run holds location {query.worksite_id} for account {query.client_id}"
        )
    candidates = sorted(
        y for y, row in rows_by_year.items() if _complete(row) and open_year_months(row) is None
    )
    if query.base_year not in rows_by_year:
        raise RebaseNotAvailable(f"the run holds no TY{query.base_year} for {query.worksite_id}")
    if open_year_months(rows_by_year[query.base_year]) is not None:
        raise RebaseNotAvailable(
            f"TY{query.base_year} is still open at {query.worksite_id}; a base is measured "
            f"on a year that has finished"
        )
    if query.base_year not in candidates:
        raise RebaseNotAvailable(
            f"TY{query.base_year} is a partial year at {query.worksite_id}, and a partial "
            f"year makes a flattering base: fewer months averaged over twelve reads as "
            f"a lower baseline"
        )

    trend = location_trend(rows_by_year, state=query.state.upper(), base_year=query.base_year)
    stairs = {y.year: y for y in trend.years}

    years = []
    for year in sorted(rows_by_year):
        row = rows_by_year[year]
        entry: dict[str, Any] = {
            "tax_year": year,
            "average_headcount": round(_num(row.get("average_headcount")), 2),
        }
        if year < query.base_year:
            entry.update({"role": "before_base", "status": "before_base"})
        elif year == query.base_year:
            entry.update({"role": "base", "status": "base"})
        elif open_year_months(row) is not None:
            # Still open: read against the new base on its closed months, never priced.
            stair = open_year_reading(
                _num(row.get("average_headcount")), trend,
                {"threshold": _num(row.get("threshold")), "per_job_usd": _num(row.get("per_job_usd"))},
                _num(row.get("threshold")),
            )
            entry.update({
                "role": "evaluated",
                "year_number": year - query.base_year,
                "net_new_vs_base": round(stair.net_new, 2),
                "threshold": stair.threshold,
                "qualified": bool(stair.qualified),
                "eligible_jobs": 0.0,
                "annual_credit_usd": 0,
                "backfilled": False,
                "status": "in_progress",
            })
        else:
            stair = stairs[year]
            entry.update({
                "role": "evaluated",
                "year_number": year - query.base_year,
                "net_new_vs_base": round(stair.net_new, 2),
                "threshold": stair.threshold,
                "qualified": bool(stair.qualified),
                "eligible_jobs": round(stair.eligible_jobs, 2),
                "annual_credit_usd": round(stair.annual_credit_usd),
                "backfilled": bool(stair.backfilled),
                "status": unit_status(
                    tax_year=year, base_year=query.base_year, qualified=bool(stair.qualified),
                    months_with_headcount=int(row.get("months_with_headcount") or 0),
                    months_reachable=int(row.get("months_reachable") or 12),
                ),
            })
        years.append(entry)

    rebased_total = round(sum(y.annual_credit_usd for y in trend.years))
    run_total = round(sum(_num(row.get("annual_credit_usd")) for row in rows_by_year.values()))
    return {
        "client_id": query.client_id,
        "worksite_id": query.worksite_id,
        "method": query.method,
        "base_year": query.base_year,
        "inferred_base_year": inferred,
        "candidate_base_years": candidates,
        "base_average_headcount": round(trend.base_average_headcount, 2),
        "years": years,
        "total_annual_credit_usd": rebased_total,
        "run_total_annual_credit_usd": run_total,
        "delta_annual_credit_usd": rebased_total - run_total,
        "run_id": (run or {}).get("run_id"),
        "saved": False,
        "note": (
            f"Re-priced against TY{query.base_year} from the run's own averages. Not saved, "
            f"and not the certified figures — those are measured from TY{inferred}."
        ),
    }
