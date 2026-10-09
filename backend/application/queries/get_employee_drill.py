"""One employee's derivation, for whichever client-year is on screen.

The sealed workspace has served this since the beginning, and only ever for the
certified run: its `token_to_employee` index is built once, for account 1001 in
TY2023. `record_token` is a SHA-256 and cannot be reversed, so a token minted by
a per-client view for any other client-year was a valid handle that resolved
nowhere — every row the trend grid and the per-client One/Zero render opened a
404.

Resolution here is by re-minting: run the client-year, mint a token for each
employee in the population, and match. That is not a trick to get around the
one-way hash; it is the same thing the sealed service does, over a run that
follows the selector.

**What this deliberately cannot answer**, rather than answering emptily:

- **Access differences.** There is one partner reconciliation and it is for the
  reference client. An empty panel would read as "we checked and found none".
- **Source file and row lineage.** The sealed path reads four CSVs it can name a
  line in. Payroll from the lakehouse has no such coordinate.
- **Assumption-set and calculation ids.** Those identify the certified artifact.
  Minting new ones per request would make a hash that proves nothing.

What it does carry instead is the run's own identity: the programme, the
statutory year, the resolved fiscal window and the floors actually applied.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from application.mediator import Query
from application.queries._client_run import ClientRunNotAvailable

_MONTHS_IN_YEAR = 12


@dataclass(frozen=True)
class GetEmployeeDrillQuery(Query):
    """One employee within one client-programme-year, keyed by opaque handle."""

    record_token: str
    tax_year: int
    state: str
    account_id: int | None = None

    def __post_init__(self) -> None:
        if not self.record_token.strip():
            raise ValueError("record_token is required")


def _verdict(row: dict[str, Any] | None, floors) -> dict[str, Any] | None:
    """The shape the drill's method card reads, from one method's averages."""
    if row is None:
        return None
    hours = float(row["avg_weekly_hours"])
    wages = float(row["avg_weekly_wages"])
    weeks = float(row["weeks_worked"])
    passed_hours = hours >= float(floors.min_weekly_hours)
    passed_wages = wages >= float(floors.min_weekly_wages)
    return {
        "denominator_weeks": weeks,
        "avg_weekly_hours": hours,
        "avg_weekly_wages": wages,
        # The sealed path carries full-precision and rounded side by side to
        # reconcile against Access. There is no Access output here, so both
        # columns would be the same number twice.
        "rounded_avg_weekly_hours": hours,
        "rounded_avg_weekly_wages": wages,
        "passed_hours": passed_hours,
        "passed_wages": passed_wages,
        "eligible": passed_hours and passed_wages,
        "denominator_detail": {
            "weeks_worked": weeks,
            "total_hours": float(row.get("total_hours") or 0.0),
            "total_wages": float(row.get("total_wages") or 0.0),
        },
    }


def _month_ends(read: dict[str, Any]) -> list[str]:
    """The run's twelve measuring month-ends, as ISO strings, READ.

    Taken from `run_method_summary.month_ends`, the list the matrix beside this
    panel renders. Deriving them from `fiscal_year_begin` put the drill a month
    out for any window opening mid-month: Candle Bottle opens 2023-07-28 on a
    stub no pay period spans, so the derivation began at 2023-07-31 while the
    run measured from 2023-08-31. No stored list means no months, not a guess.
    """
    return [str(month)[:10] for month in read.get("month_ends") or []]


def _segments(rows: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    """One method's unit segments for this employee, from the stored matrix."""
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if str(row.get("method")) != method:
            continue
        months = [float(row.get(f"month_{i:02d}") or 0) for i in range(1, 13)]
        out.append({
            "segment_id": f"{row.get('worksite_id')}-{row.get('first_pps')}-{index}",
            "unit_id": row.get("worksite_id"),
            "fein": row.get("entity_fein") or "",
            "period_start": str(row.get("first_pps") or ""),
            "period_end": str(row.get("last_ppe") or ""),
            "source_refs": [],
            "months": months,
            # The stored matrix IS the resolved one; the pre-tie-break cells are
            # not kept, so raw and final are the same numbers here.
            "raw_months": months,
        })
    return out


def handle_get_employee_drill(query: GetEmployeeDrillQuery) -> dict[str, Any]:
    """Resolve an opaque handle against the run that minted it, from Gold."""
    from application.queries._client_run import resolve_statute
    from application.wiring import get_gold_reader
    from tools.fabric_source import active_data_source

    if query.account_id is None:
        raise ClientRunNotAvailable(
            "a client is required — a handle only resolves where it was minted"
        )

    resolved = resolve_statute(
        account_id=query.account_id, state=query.state, tax_year=query.tax_year
    )
    read = get_gold_reader().employee_drill(
        query.account_id, tax_year=query.tax_year, record_token=query.record_token
    )
    verdicts = read["verdicts"]
    if read["run"] is None or not verdicts:
        raise ClientRunNotAvailable(
            f"no employee in account {query.account_id} {resolved.program_code} "
            f"{query.tax_year} matches that handle"
        )

    by_method = {str(row["method"]): row for row in verdicts}
    employee_id = str(verdicts[0]["employee_id"])
    floors = resolved.floors

    mm_verdict = _verdict(by_method.get("min_max"), floors)
    pp_verdict = _verdict(by_method.get("pay_period"), floors)
    totals = by_method.get("min_max") or by_method.get("pay_period") or {}

    source_rows = [
        {
            "source_file": "",
            "source_row": index,
            "job_title": row.get("job_title") or "",
            "unit_id": row.get("worksite_id") or "",
            "fein": row.get("entity_fein") or "",
            "pay_period_start": str(row.get("pay_period_start") or ""),
            "pay_period_end": str(row.get("pay_period_end") or ""),
            "pay_date": str(row.get("pay_date") or ""),
            "pay_frequency_code": str(row.get("pay_frequency_code") or ""),
            "hours": str(row.get("hours") or 0),
            "wages": str(row.get("wages") or 0),
            # Gold records WHY a row was selected (`fiscal_window`); the panel
            # asks WHETHER it was. Everything held here was consumed by the run,
            # and the rows the window excluded are named in `not_available`
            # rather than appearing as a silently shorter list.
            "selection_decision": "included",
        }
        for index, row in enumerate(read["periods"])
    ]

    months = _month_ends(read)
    weeks_delta = None
    if mm_verdict and pp_verdict:
        weeks_delta = round(
            pp_verdict["denominator_weeks"] - mm_verdict["denominator_weeks"], 2
        )

    # 29 Sep: the walk can add this person to a What-if stack, pre-filled with
    # what the rest of the year needs — the same reading Near the line shows.
    from application.queries.get_proximity import _where_they_work
    from domain.calculation.proximity import rest_of_year

    as_of = date(query.tax_year, 8, 31)
    periods = list(read["periods"])
    rest = (
        rest_of_year(periods, floors=floors, as_of=as_of, year_end=resolved.window.end)
        if periods and as_of < resolved.window.end else {"state": "closed", "note": "The year is closed."}
    )
    where = _where_they_work(periods, client_id=query.account_id, tax_year=query.tax_year)

    return {
        "basis": "per_client",
        "record_token": query.record_token,
        "employee_id": employee_id,
        "account_id": query.account_id,
        "state": resolved.state,
        "program_code": resolved.program_code,
        "tax_year": query.tax_year,
        "run": {
            "program_code": resolved.program_code,
            "tax_year": query.tax_year,
            "fiscal_begin": resolved.window.begin.isoformat(),
            "fiscal_end": resolved.window.end.isoformat(),
            "data_source": active_data_source(),
            "months": months,
            "run_id": (read["run"] or {}).get("run_id"),
        },
        "thresholds": {
            "minimum_average_weekly_hours": str(floors.min_weekly_hours),
            "minimum_average_weekly_wages_usd": str(floors.min_weekly_wages),
        },
        "raw_source_rows": source_rows,
        "rest_of_year": rest,
        "where": where,
        "step1": {
            "totals": {
                "total_hours": str(totals.get("total_hours") or 0),
                "total_wages": str(totals.get("total_wages") or 0),
            },
            "min_max": mm_verdict,
            "pay_period": pp_verdict,
            "denominator_invariant": {
                "pay_period_minus_min_max_weeks": weeks_delta,
                "pay_period_gt_min_max": bool(weeks_delta is not None and weeks_delta > 0),
                "over_review_tolerance": bool(
                    weeks_delta is not None and abs(weeks_delta) > 1.5
                ),
                "pay_period_over_52_weeks": bool(
                    pp_verdict and pp_verdict["denominator_weeks"] > 52.0
                ),
            },
        },
        "onezero": {
            "months": months,
            "min_max": _segments(read["segments"], "min_max"),
            "pay_period": _segments(read["segments"], "pay_period"),
            # Not empty — ABSENT. The matrix is deduped before it is written, so
            # a contest leaves no trace in the rows it produced; only the
            # per-run count survives, in `run_method_summary.contested_months`.
            # An empty list here would read as "we checked and found none".
            "overlap_flags": [],
        },
        "exceptions": {"step1": [], "onezero": []},
        # Named, not omitted. A reader has to know the difference between a
        # question we answered and one this path cannot ask.
        "not_available": [
            "Access reconciliation — there is one partner comparison and it is "
            "for the certified reference client.",
            "Source file and row lineage — lakehouse payroll has no such coordinate.",
            "Assumption-set and calculation hashes — those identify the certified "
            "artifact, and minting new ones here would prove nothing.",
            "Per-employee contested months — the matrix is deduped before it is "
            "stored, so the contest leaves no trace in the rows it produced.",
            "Pay periods the fiscal window EXCLUDED — the run writes only the "
            "rows it consumed, so a paycheck that fell outside the window is not "
            "held here.",
        ],
    }
