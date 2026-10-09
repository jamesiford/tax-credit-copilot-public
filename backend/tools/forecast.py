"""[N2] FCST-01 — "How am I doing" trajectory + provision number.

The forecast the partner's Tractor Supply pitch lit up: as the year progresses, project
the year-end credit from year-to-date actuals toward the finish line (the
statutory threshold), and surface a single "estimated credit as of now = $X"
number a tax department can drop into its provision / quarterly estimate.

Method (per the June-17 decision): **linear run-rate** from YTD actuals to the
measuring date — NO seasonality, NO ML. The same no-extrapolation discipline the
rule packs follow: every projection records its inputs + method note into the
calculation trail. The run-rate is the YTD Average Monthly Headcount (sum of the
elapsed months' unit headcounts ÷ months elapsed); the projection assumes that
run-rate holds through year-end.

Pure tool layer — no FastAPI. Reuses the statutory One/Zero engine
(`run_pay_period_method`) so the trajectory is grounded in the same Average
Headcount math as every other surface.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from domain.calculation.onezero import run_pay_period_method, fiscal_window_start, _twelve_month_ends
from tools.credit_math import load_pack_one_zero, apply_one_zero_state_credit
from domain.calculation.trail import current_recorder

_ROADMAP_TAG = "N2"
_STORY = "FCST-01"


def _months_elapsed(analysis_start: date, as_of: date) -> int:
    """How many of the 12 fiscal months have closed on/after `as_of`.

    Counts a month as elapsed once its measuring (month-end) date is <= as_of.
    Clamped to 1..12 so a forecast always has at least one month of actuals and
    never claims more than a full year.
    """
    month_ends = _twelve_month_ends(analysis_start)
    elapsed = sum(1 for me in month_ends if me <= as_of)
    return max(1, min(elapsed, 12))


def _ytd_average_headcount(summary: list[dict], months_elapsed: int) -> float:
    """Run-rate YTD Average Monthly Headcount from the engine's per-unit summary.

    `summary` rows carry `month_totals[12]`. Sum the first `months_elapsed`
    months across all units and divide by months elapsed — the run-rate the
    projection assumes holds for the remaining months.
    """
    if months_elapsed <= 0:
        return 0.0
    total = 0.0
    for unit in summary:
        total += sum(unit["month_totals"][:months_elapsed])
    return round(total / months_elapsed, 2)


def project_state_year_end(
    state: str,
    tax_year: int,
    rows: list[dict],
    prior_rows: list[dict],
    *,
    as_of: date,
    fiscal_year_end_month: int = 12,
    months_elapsed: int | None = None,
    ytd_average_headcount: float | None = None,
    prior_average_headcount: float | None = None,
) -> dict[str, Any] | None:
    """Project a state's year-end One/Zero credit from YTD actuals.

    Returns None if the state has no rule pack. `rows` / `prior_rows` are the
    pay-period rows already bucketed into `tax_year` / `tax_year - 1` by the
    caller (same fiscal-year-by-pay-date rule as `/api/onezero`).

    Both averages may be supplied by a caller that has already READ them from
    the run that computed them, in which case no payroll is replayed and `rows`
    / `prior_rows` are unused. They are parameters rather than a lookup because
    this module is deterministic compute: data in, data out, no I/O.

    `months_elapsed` travels WITH `ytd_average_headcount` and is not optional in
    practice: the average is a sum over N months, and reporting a different N
    beside it makes the denominator note describe a calculation nobody did.
    """
    state_u = state.upper()
    pack = load_pack_one_zero(state_u, tax_year=tax_year)
    if pack is None:
        return None

    analysis_start = fiscal_window_start(tax_year, fiscal_year_end_month)
    if months_elapsed is None:
        months_elapsed = _months_elapsed(analysis_start, as_of)

    if ytd_average_headcount is None:
        full = run_pay_period_method(
            rows, tax_year=tax_year, analysis_start_month=analysis_start,
            pack=pack, fiscal_year_end_month=fiscal_year_end_month,
        )
        ytd_avg = _ytd_average_headcount(full.summary, months_elapsed)
    else:
        ytd_avg = round(float(ytd_average_headcount), 2)
    # Linear run-rate: the projected full-year Average Headcount == the YTD
    # run-rate (the current monthly headcount, assumed to hold through year-end).
    projected_avg = ytd_avg

    # Prior-year Average Headcount (the frozen comparison base for net-new).
    if prior_average_headcount is not None:
        prior_avg = float(prior_average_headcount)
    else:
        prior_avg = 0.0
        prior_pack = load_pack_one_zero(state_u, tax_year=tax_year - 1)
        state_prior_rows = [r for r in prior_rows if str(r["Worksite_ID"]).startswith(f"{state_u}_")]
        if prior_pack is not None and state_prior_rows:
            prior_res = run_pay_period_method(
                state_prior_rows, tax_year=tax_year - 1,
                analysis_start_month=fiscal_window_start(tax_year - 1, fiscal_year_end_month),
                pack=prior_pack, fiscal_year_end_month=fiscal_year_end_month,
            )
            prior_avg = prior_res.annual_average

    credit = apply_one_zero_state_credit(state_u, projected_avg, prior_period_average_headcount=prior_avg)
    threshold = float(credit.get("threshold") or 0.0)
    # The "finish line" = the Average Headcount at which net-new first clears the
    # statutory minimum (prior-year base + threshold).
    finish_line = round(prior_avg + threshold, 2)
    gap_to_finish = round(max(0.0, finish_line - projected_avg), 2)
    projected_net_new = round(max(0.0, projected_avg - prior_avg), 2)
    on_track = projected_avg + 1e-9 >= finish_line

    method_note = (
        f"Linear run-rate from {months_elapsed} month(s) of {tax_year} actuals "
        f"(YTD Average Monthly Headcount {ytd_avg}); assumes the current run-rate "
        f"holds through year-end. No seasonality applied."
    )

    recorder = current_recorder()
    if recorder is not None:
        recorder.record(
            step=f"{state_u}: project {tax_year} year-end credit (run-rate as of {as_of.isoformat()})",
            inputs={
                "months_elapsed": months_elapsed,
                "ytd_average_headcount": ytd_avg,
                "prior_year_average_headcount": prior_avg,
                "threshold": threshold,
            },
            formula="projected_avg = ytd_avg (run-rate); net_new = max(0, projected_avg - prior_avg); finish_line = prior_avg + threshold",
            output={
                "projected_average_headcount": projected_avg,
                "projected_credit_usd": credit.get("annual_credit_usd", 0),
                "gap_to_finish": gap_to_finish,
            },
            citation=f"{_STORY} run-rate forecast (no extrapolation beyond run-rate)",
        )

    return {
        "_roadmap_tag": _ROADMAP_TAG,
        "_story": _STORY,
        "state": state_u,
        "tax_year": tax_year,
        "as_of": as_of.isoformat(),
        "months_elapsed": months_elapsed,
        "ytd_average_headcount": ytd_avg,
        "projected_average_headcount": projected_avg,
        "prior_year_average_headcount": prior_avg,
        "threshold": threshold,
        "finish_line_headcount": finish_line,
        "gap_to_finish": gap_to_finish,
        "projected_net_new": projected_net_new,
        "on_track": on_track,
        "projected_annual_credit_usd": credit.get("annual_credit_usd", 0),
        "projected_lifetime_credit_usd": credit.get("lifetime_credit_usd", 0),
        "credit_code": credit.get("credit_code"),
        "credit_name": credit.get("credit_name"),
        "method_note": method_note,
    }
