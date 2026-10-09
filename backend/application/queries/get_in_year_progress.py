"""In-year progress: are we on track, and who is on the edge.

The partner's named first operational test, 27 August 2026:

> "We are going to run their calcs starting when the dust settles on their
> August payroll, and say — yep, as of the end of August you've still got 10 or
> 11 or 12 and you're good. Or, uh-oh, you're at 9, and these are the people
> that are almost part-time or almost full-time, because maybe you can work them
> a little bit more to get them over the edge."

> "All we have to do is be able to change the denominator from 12 months to 8
> months or nine months."

Two halves, in that order: **are we on track**, then **who moves the needle**.
The second half is what makes this actionable rather than a report — and it is
answered by the proximity query rather than reimplemented here, so the two views
can never disagree about who is near the line.

A projection is not a calculation, and this says so. The run-rate assumes the
current monthly headcount holds to year end, applies no seasonality, and is
labelled an estimate everywhere it surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from application.mediator import Query


@dataclass(frozen=True)
class GetInYearProgressQuery(Query):
    """Where a client stands part-way through a tax year.

    `as_of` defaults to 31 August — the partner's own checkpoint, chosen because that
    is when the dust settles on the August payroll and there is enough of the
    year to project from.
    """

    tax_year: int
    state: str
    as_of: date | None = None
    account_id: int | None = None
    proximity_band_hours: float = 5.0

    def resolved_as_of(self) -> date:
        return self.as_of or date(self.tax_year, 8, 31)


class ProgressNotAvailable(LookupError):
    """No statute, or no payroll, for this client-state-year."""


def handle_get_in_year_progress(query: GetInYearProgressQuery) -> dict[str, Any]:
    from application.queries.get_proximity import (
        GetProximityQuery,
        ProximityNotAvailable,
        handle_get_proximity,
    )
    from application.wiring import get_gold_reader
    from tools.forecast import project_state_year_end

    state = query.state.upper()
    as_of = query.resolved_as_of()

    if query.account_id is None:
        raise ProgressNotAvailable(
            "a client is required — progress is read from that client's run"
        )

    # Both halves of the projection were computed by the run and written to
    # Gold: the monthly headcount series for the year being projected, and the
    # prior year's annual average. This handler replayed the payroll twice to
    # re-derive them, on every page load, on top of the proximity replay.
    reader = get_gold_reader()
    current = reader.headcount_series(
        query.account_id, tax_year=query.tax_year, method="pay_period"
    )
    prior = reader.headcount_series(
        query.account_id, tax_year=query.tax_year - 1, method="pay_period"
    )
    if current["run"] is None or not any(current["months"]):
        raise ProgressNotAvailable(
            f"no calculated run holds {state} tax year {query.tax_year} "
            f"for account {query.account_id}"
        )

    months_elapsed = _closed_months(
        current["month_ends"], current.get("unreachable_months") or [], as_of,
    )
    ytd_average = (
        round(sum(current["months"][:months_elapsed]) / months_elapsed, 2)
        if months_elapsed else 0.0
    )
    has_prior_payroll = any(prior["months"])
    prior_average = float(prior["annual_average"] or 0.0) if has_prior_payroll else 0.0

    projection = project_state_year_end(
        state, query.tax_year, [], [], as_of=as_of, fiscal_year_end_month=12,
        months_elapsed=months_elapsed,
        ytd_average_headcount=ytd_average,
        prior_average_headcount=prior_average,
    )
    if projection is None:
        raise ProgressNotAvailable(
            f"{state} has no authored statute for tax year {query.tax_year}"
        )

    # A base of zero is not the same fact as a base that happens to be small.
    # With no prior-year payroll the ENTIRE workforce counts as net-new, so
    # "on track" becomes trivially true — 73 net-new against a threshold of 2 —
    # and the verdict stops meaning anything. Disclosed rather than rendered as
    # a result, because a trivially-true yes is worse than an honest "cannot
    # tell": one of them gets acted on.
    base_is_meaningful = has_prior_payroll and projection["prior_year_average_headcount"] > 0

    # The actionable half. Reuses the proximity query rather than recomputing,
    # so "who is on the edge" cannot differ between this view and that one.
    cohort: dict[str, Any] | None = None
    try:
        cohort = handle_get_proximity(
            GetProximityQuery(
                tax_year=query.tax_year,
                state=state,
                method="min_max",
                within_weekly_hours=query.proximity_band_hours,
                limit=10,
                account_id=query.account_id,
                # WI-19: the same checkpoint the verdict above uses.
                rest_of_year=True,
                as_of=as_of,
            )
        )
    except ProximityNotAvailable:
        # A missing cohort is not a missing answer — the on-track half still
        # stands, and saying so beats failing the whole view.
        cohort = None


    return {
        **projection,
        "account_id": query.account_id,
        "has_prior_year_payroll": has_prior_payroll,
        "base_is_meaningful": base_is_meaningful,
        "base_caveat": (
            None
            if base_is_meaningful
            else (
                f"No {state} payroll held for TY{query.tax_year - 1}, so the "
                f"base is zero and every employee counts as net-new. The "
                f"net-new figure is an upper bound, not a position."
            )
        ),
        "near_the_line": (
            {
                "band_weekly_hours": cohort["band_weekly_hours"],
                "within_band": cohort["within_band"],
                "ineligible": cohort["ineligible"],
                "evaluated": cohort["evaluated"],
                "failure_modes": cohort["failure_modes"],
                "cohort": cohort["cohort"],
                "floors": cohort["floors"],
            }
            if cohort
            else None
        ),
        # Stated on the payload, not left to the view, so an export or a report
        # carries the same caveat the screen does.
        "is_estimate": True,
        "denominator_note": (
            f"Average headcount over {projection['months_elapsed']} closed "
            f"month(s), not 12. Projected to year end at the current run-rate "
            f"with no seasonality applied."
        ),
    }


def _closed_months(month_ends: list[str], unreachable: list[int], as_of: date) -> int:
    """Months elapsed by `as_of`, less any the payroll has not reached yet.

    A measuring date on or before the checkpoint that NO pay period spans has
    not happened in the payroll: an open year's payroll stops at the
    checkpoint, so its 31 August month end is spanned by nothing. Counting it
    put a zero into the to-date average — Cascade TY2026 read 96 jobs against a
    TY2025 base of 120.68, a shrinking client that is in fact growing.

    Only TRAILING months are dropped, and only in an OPEN year: in a closed one
    an unreachable month is a fact about the pay calendar, not about the future.
    """
    from application.open_year import is_open

    elapsed = _months_elapsed_from(month_ends, as_of)
    unreached = set(unreachable)
    year_open = bool(month_ends) and is_open(month_ends[-1])
    while year_open and elapsed > 1 and (elapsed - 1) in unreached:
        elapsed -= 1
    return elapsed


def _months_elapsed_from(month_ends: list[str], as_of: date) -> int:
    """How many of the run's twelve measuring months have closed by `as_of`.

    Counted against the run's OWN month ends. The old path counted from
    1 January, which for a client whose fiscal year opens in August put the
    denominator several months out — and the denominator is the whole point of
    this view: "change it from 12 months to 8 or 9".
    """
    if not month_ends:
        return 1
    elapsed = sum(1 for end in month_ends if date.fromisoformat(str(end)[:10]) <= as_of)
    return max(1, min(elapsed, len(month_ends)))
