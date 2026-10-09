"""Which employees are near the statutory line, and what would close the gap.

The partner, 27 August 2026, twice and unprompted:

> "People are either going to be solidly in or solidly out. It's just those ones
> that are on the edge that if we can scoop more in, that's always good."

> "Uh-oh, you're at 9, and these are the people that are almost part-time or
> almost full-time, because maybe you can work them a little bit more to get them
> over the edge."

The engine already knows this and never says it. `OneZeroResult.all_averages`
carries `avg_weekly_hours` and `avg_weekly_wages` for every employee including
the ineligible; the floors resolve per year from the rule pack. The gap between
the two is arithmetic we were throwing away.

**This module reads an eligibility result. It must never alter one.** Nothing
here feeds back into `run_min_max_method` or `run_pay_period_method`, and the
parity gate (10,236 / 539 / 656) is the proof.

Two distinctions that make the difference between an instruction and a number:

**The tests fail independently.** An employee can miss on hours, on wages, or on
both, and conflating them produces a wrong instruction — "work them more hours"
is useless advice for someone already at 40 hours who is simply paid too little.
The failure modes are counted and reported separately throughout.

**Extra hours pay at the employee's own rate.** Adding hours moves *both*
averages, so the hours needed to clear the wage floor depend on what the
employee earns. Below the threshold rate — `min_wages / min_hours`, $18.17/hour
for Georgia in 2023 — the wage test binds harder than the hours test, and the
honest instruction is a raise rather than a longer week. Those employees are
flagged `rate_limited` rather than being handed an implausible hours figure.
"""
from __future__ import annotations

from typing import Any

from domain.calculation.floors import StatutoryFloors
from domain.calculation.onezero import _round_half_up

# A working week beyond which "just give them more hours" stops being a
# scheduling decision and becomes an overtime conversation. Not statutory —
# it exists so the UI can separate a realistic instruction from an arithmetic
# one, and it is reported rather than applied as a filter.
PLAUSIBLE_WEEKLY_HOURS = 40.0

#: The notches the band curve reports. Named because a caller bounding which
#: rows it fetches has to reach the widest of them — a bound and a curve that
#: disagree empty the outer notches without saying so.
BAND_CURVE_HOURS = (1.0, 2.0, 5.0, 10.0)


def _rate(total_hours: float, total_wages: float) -> float | None:
    """Implied hourly rate, or None when it cannot be known.

    Zero-hour rows are real: BA-05 keeps wages paid against no hours (bonuses,
    severance, corrections) in the numerator. Such an employee has no rate, and
    inventing one would produce a confident instruction from nothing.
    """
    if total_hours <= 0:
        return None
    return total_wages / total_hours


def assess_employee(
    average: dict[str, Any], *, floors: StatutoryFloors, decimals: int = 2
) -> dict[str, Any]:
    """One employee's distance from the two floors, and the lever that closes it.

    `average` is a row of `OneZeroResult.all_averages`.
    """
    weeks = float(average.get("weeks_worked") or 0.0)
    total_hours = float(average.get("total_hours") or 0.0)
    total_wages = float(average.get("total_wages") or 0.0)
    avg_hours = float(average.get("avg_weekly_hours") or 0.0)
    avg_wages = float(average.get("avg_weekly_wages") or 0.0)

    min_hours = float(floors.min_weekly_hours)
    min_wages = float(floors.min_weekly_wages)

    passed_hours = avg_hours >= min_hours
    passed_wages = avg_wages >= min_wages

    failed: list[str] = []
    if not passed_hours:
        failed.append("hours")
    if not passed_wages:
        failed.append("wages")

    # The two floors are the DISPLAY halves of the verdict, not the verdict.
    # `_eligibility_filter` sets `eligible = weight > 0`, and a part-time band
    # (South Carolina, 20-32 hrs at 0.5) carries a non-zero weight for someone
    # who failed the hours floor — so deriving eligibility from the floors
    # misclassifies every SC part-timer as out. Where the caller carries a
    # recorded verdict, that verdict wins; Georgia has no band, so nothing moves.
    recorded = average.get("eligible")
    derived = not failed
    eligible = bool(recorded) if recorded is not None else derived

    hours_gap = 0.0 if passed_hours else _round_half_up(min_hours - avg_hours, decimals)
    wages_gap = 0.0 if passed_wages else _round_half_up(min_wages - avg_wages, decimals)

    rate = _rate(total_hours, total_wages)
    threshold_rate = min_wages / min_hours if min_hours else None
    rate_limited = bool(rate is not None and threshold_rate is not None and rate < threshold_rate)

    # Additional hours per week that clear every failing test at the employee's
    # own rate. The wage requirement is divided by the rate because the extra
    # hours are what pay it; both requirements must be met, so the binding one
    # is the maximum.
    additional_weekly_hours: float | None
    if not failed:
        additional_weekly_hours = 0.0
    elif weeks <= 0:
        additional_weekly_hours = None
    else:
        needs = [hours_gap] if not passed_hours else []
        if not passed_wages:
            if rate is None or rate <= 0:
                needs = None  # type: ignore[assignment]
            else:
                needs.append(wages_gap / rate)
        additional_weekly_hours = (
            None if needs is None else _round_half_up(max(needs), decimals)
        )

    # The alternative lever: leave the schedule alone and pay more. Only
    # meaningful when the hours test already passes — otherwise a raise cannot
    # fix an employee who is not working enough hours to qualify at any rate.
    hourly_rate_to_qualify: float | None = None
    if passed_hours and not passed_wages and total_hours > 0:
        hourly_rate_to_qualify = _round_half_up((min_wages * weeks) / total_hours, decimals)

    projected_weekly_hours = (
        _round_half_up(avg_hours + additional_weekly_hours, decimals)
        if additional_weekly_hours is not None
        else None
    )

    return {
        "employee_id": average.get("Employee_ID"),
        "weeks_worked": _round_half_up(weeks, decimals),
        "total_hours": total_hours,
        "total_wages": total_wages,
        "avg_weekly_hours": avg_hours,
        "avg_weekly_wages": avg_wages,
        "eligible": eligible,
        "verdict_source": "recorded" if recorded is not None else "derived",
        "verdict_disagrees": recorded is not None and bool(recorded) != derived,
        "failed": failed,
        "failure_mode": (
            "none" if not failed
            else "both" if len(failed) == 2
            else f"{failed[0]}_only"
        ),
        "hours_gap_per_week": hours_gap,
        "wages_gap_per_week": wages_gap,
        "implied_hourly_rate": None if rate is None else _round_half_up(rate, decimals),
        "threshold_hourly_rate": (
            None if threshold_rate is None else _round_half_up(threshold_rate, decimals)
        ),
        "rate_limited": rate_limited,
        "additional_weekly_hours": additional_weekly_hours,
        "projected_weekly_hours": projected_weekly_hours,
        "exceeds_plausible_week": (
            projected_weekly_hours is not None
            and projected_weekly_hours > PLAUSIBLE_WEEKLY_HOURS
        ),
        "hourly_rate_to_qualify": hourly_rate_to_qualify,
        # Carried through so a row can be opened (or sent to What-if) without an
        # employee id ever entering a URL.
        "record_token": average.get("record_token"),
    }


def rest_of_year(
    periods: list[dict[str, Any]],
    *,
    floors: StatutoryFloors,
    as_of: Any,
    year_end: Any,
    method: str = "min_max",
    decimals: int = 2,
) -> dict[str, Any]:
    """What it takes over the REST of the year, as of a checkpoint.

    The partner, 24 September: "We know her year-to-date hours, and we know how much
    further in the year we have to go. In order to get her over the hurdle for
    the remaining year, she has to work this many hours per week."

    The full-year gap understates this once most of the year is gone: 0.13 hrs
    short on the year is several hours a week over the last four months. So the
    requirement is re-spread over the weeks that remain:

        needed pace = (floor x weeks in year - to date) / weeks remaining
        extra       = needed pace - current pace

    for hours, and for wages converted to hours at the employee's own rate. Both
    floors must clear, so the larger binds. The periods are what closed by
    `as_of`; nothing after the checkpoint is read, because the question is asked
    on 31 August and the rest of the year has not happened.

    Pure: data in, reading out. It never touches an eligibility verdict.
    """
    from datetime import date as _date

    def _d(value: Any) -> _date:
        return value if isinstance(value, _date) else _date.fromisoformat(str(value)[:10])

    checkpoint = _d(as_of)
    end = _d(year_end)
    min_hours = float(floors.min_weekly_hours)
    min_wages = float(floors.min_weekly_wages)

    closed = sorted(
        (
            (_d(p["pay_period_start"]), _d(p["pay_period_end"]),
             float(p.get("hours") or 0.0), float(p.get("wages") or 0.0))
            for p in periods
            if _d(p["pay_period_end"]) <= checkpoint
        ),
        key=lambda p: (p[1], p[0]),
    )
    # Days from period end to pay date. A period counts toward the year only if
    # it is PAID inside the window (the Pay_Date trim), so the last period the
    # year holds is decided by this lag, not by the calendar.
    lags = sorted(
        (_d(p["pay_date"]) - _d(p["pay_period_end"])).days
        for p in periods
        if p.get("pay_date") and _d(p["pay_period_end"]) <= checkpoint
    )
    if checkpoint >= end:
        return {"state": "closed", "note": "The year is closed."}
    if not closed:
        return {
            "state": "no_payroll_to_date",
            "note": "Hired after the checkpoint",
        }

    first_start = closed[0][0]
    last_end = closed[-1][1]
    if method == "pay_period":
        weeks_to_date = sum(((e - s).days + 1) / 7.0 for s, e, _h, _w in closed)
    else:
        # BA-11: Min-Max spans first PPS to last PPE, exclusive of the end day.
        weeks_to_date = (last_end - first_start).days / 7.0

    # The rest of the year is the whole pay periods still to be PAID inside
    # it, on this employee's own cadence — not the calendar days to the window
    # end. Spreading the need over the calendar asked for too little per week:
    # a biweekly employee whose December period is paid in January has sixteen
    # weeks left, not eighteen, and "+0.92 hrs/wk" then left them 1.25 hours
    # short of the floor in the engine that decides.
    from datetime import timedelta as _timedelta

    period_days = sorted((e - s).days + 1 for s, e, _h, _w in closed)
    period_length = period_days[len(period_days) // 2]
    lag = _timedelta(days=lags[len(lags) // 2] if lags else 0)
    step_days = _timedelta(days=period_length)
    remaining_periods = 0
    while last_end + step_days * (remaining_periods + 1) + lag <= end:
        remaining_periods += 1
    weeks_remaining = remaining_periods * period_length / 7.0
    if weeks_to_date <= 0 or weeks_remaining <= 0:
        return {"state": "closed", "note": "The year is closed."}

    hours_to_date = sum(h for _s, _e, h, _w in closed)
    wages_to_date = sum(w for _s, _e, _h, w in closed)
    weeks_in_year = weeks_to_date + weeks_remaining
    pace_hours = hours_to_date / weeks_to_date
    pace_wages = wages_to_date / weeks_to_date
    rate = _rate(hours_to_date, wages_to_date)
    threshold_rate = min_wages / min_hours if min_hours else None

    needed_hours_pace = (min_hours * weeks_in_year - hours_to_date) / weeks_remaining
    needed_wages_pace = (min_wages * weeks_in_year - wages_to_date) / weeks_remaining
    extra_for_hours = max(0.0, needed_hours_pace - pace_hours)
    extra_wages = max(0.0, needed_wages_pace - pace_wages)
    extra_for_wages = (extra_wages / rate) if (extra_wages > 0 and rate) else 0.0
    if extra_wages > 0 and not rate:
        return {"state": "no_rate", "note": "No hours on record to price extra hours at."}

    extra = max(extra_for_hours, extra_for_wages)
    period_weeks = period_length / 7.0

    if extra <= 0:
        return {
            "state": "on_pace",
            "weeks_remaining": _round_half_up(weeks_remaining, decimals),
            "remaining_pay_periods": remaining_periods,
            "pace_weekly_hours": _round_half_up(pace_hours, decimals),
            "note": "On pace to clear both floors if the year continues as it has.",
        }

    # Rounded UP, so the figure offered actually clears the line.
    import math

    step = 10 ** decimals
    extra_up = math.ceil(extra * step - 1e-9) / step
    rate_limited = bool(
        extra_for_wages > extra_for_hours and rate is not None
        and threshold_rate is not None and rate < threshold_rate
    )
    # The pair a What-if stack pre-fills (hours AND pay), so it closes the gap
    # with the lever that actually applies. Hours-bound: the extra hours, no
    # raise. Rate-limited: only the hours the HOURS floor needs, plus the raise
    # that clears the wage floor at that week — not an implausible 60-hour week.
    if rate_limited:
        suggested_hours = math.ceil(extra_for_hours * step - 1e-9) / step
        week = pace_hours + suggested_hours
        needed_rate = needed_wages_pace / week if week > 0 else 0.0
        suggested_raise = max(0.0, math.ceil((needed_rate - rate) * 100 - 1e-9) / 100)
    else:
        suggested_hours, suggested_raise = extra_up, 0.0
    return {
        "state": "open",
        "as_of": checkpoint.isoformat(),
        "weeks_to_date": _round_half_up(weeks_to_date, decimals),
        "weeks_remaining": _round_half_up(weeks_remaining, decimals),
        "remaining_pay_periods": remaining_periods,
        "pay_period_weeks": _round_half_up(period_weeks, decimals),
        "hours_to_date": _round_half_up(hours_to_date, decimals),
        "pace_weekly_hours": _round_half_up(pace_hours, decimals),
        "needed_weekly_hours": _round_half_up(pace_hours + extra_up, decimals),
        "additional_weekly_hours": extra_up,
        # The partner's other framing: "an extra 10 hours the next pay period, or maybe
        # an extra hour for the next 10 pay periods."
        "additional_hours_total": _round_half_up(extra_up * weeks_remaining, decimals),
        "binding": "wages" if extra_for_wages > extra_for_hours else "hours",
        "rate_limited": rate_limited,
        # For a rate-limited employee the honest lever is pay, at current hours.
        "hourly_rate_to_qualify": (
            _round_half_up(needed_wages_pace / pace_hours, decimals)
            if rate_limited and pace_hours > 0 else None
        ),
        "exceeds_plausible_week": pace_hours + extra_up > PLAUSIBLE_WEEKLY_HOURS,
        "suggested_additional_weekly_hours": suggested_hours,
        "suggested_hourly_raise": suggested_raise,
    }


def near_miss_cohort(
    averages: list[dict[str, Any]],
    *,
    floors: StatutoryFloors,
    within_weekly_hours: float = 5.0,
    limit: int | None = None,
    decimals: int = 2,
    population: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """The ineligible population, ranked by how little it would take to qualify.

    `within_weekly_hours` bands on the single actionable number — the additional
    hours per week that clear every failing test. Ranking on that rather than on
    either raw gap is deliberate: an employee 0.5 hours short and an employee $40
    short are not comparable until both are expressed as the same lever.

    Counts cover the whole ineligible population, not the band, so a UI can say
    how many were considered as well as how many are reachable.

    `population` supplies those counts when the caller has bounded `averages` to
    the rows that could reach the band — the counts are then a fact about the
    whole client-year that the passed rows can no longer see. Overriding rather
    than deriving is the point: a count silently taken over a filtered set is
    the failure mode this parameter exists to prevent.
    """
    assessed = [assess_employee(a, floors=floors, decimals=decimals) for a in averages]
    ineligible = [a for a in assessed if not a["eligible"]]

    modes = {"hours_only": 0, "wages_only": 0, "both": 0}
    for row in ineligible:
        modes[row["failure_mode"]] = modes.get(row["failure_mode"], 0) + 1

    reachable = [
        r for r in ineligible
        if r["additional_weekly_hours"] is not None
        and r["additional_weekly_hours"] <= within_weekly_hours
    ]
    reachable.sort(key=lambda r: (r["additional_weekly_hours"], str(r["employee_id"])))

    cohort = reachable[:limit] if limit else reachable

    return {
        "floors": {
            "program_code": floors.program_code,
            "tax_year": floors.tax_year,
            "minimum_average_weekly_hours": floors.min_weekly_hours,
            "minimum_average_weekly_wages_usd": floors.min_weekly_wages,
            "threshold_hourly_rate": _round_half_up(
                float(floors.min_weekly_wages) / float(floors.min_weekly_hours), decimals
            ) if floors.min_weekly_hours else None,
            "source": f"rules/{floors.program_code.lower()}/{floors.tax_year}.json",
        },
        "band_weekly_hours": within_weekly_hours,
        "evaluated": int(population["evaluated"]) if population else len(assessed),
        "eligible": (
            int(population["eligible"]) if population
            else len(assessed) - len(ineligible)
        ),
        "ineligible": int(population["ineligible"]) if population else len(ineligible),
        # Rows where the RECORDED verdict and today's floors disagree. Expected
        # only where the pack has a part-time band; anywhere else it means the
        # statute was re-authored after the run, and the band on screen is being
        # drawn with a different ruler than the verdict beside it.
        "verdict_disagreements": sum(1 for r in assessed if r["verdict_disagrees"]),
        "failure_modes": dict(population["failure_modes"]) if population else modes,
        "within_band": len(reachable),
        "rate_limited_in_band": sum(1 for r in reachable if r["rate_limited"]),
        "exceeds_plausible_week_in_band": sum(
            1 for r in reachable if r["exceeds_plausible_week"]
        ),
        "returned": len(cohort),
        "cohort": cohort,
        "method_note": (
            "Additional hours are priced at each employee's own implied hourly "
            "rate (total wages / total hours), so the figure reflects the wages "
            "those hours would also earn. Employees paid below the effective "
            "hourly floor are flagged: for them the wage test binds harder than "
            "the hours test, and a pay rise rather than a longer week is the lever."
        ),
    }


def fragility(
    average: dict[str, Any], *, floors: StatutoryFloors, decimals: int = 2
) -> dict[str, Any]:
    """How much cushion a QUALIFYING employee has before they stop qualifying.

    The mirror of `assess_employee`, and a different question. That one asks
    what it would take to bring somebody in; this asks what it would take to
    lose somebody already counted — the jobs a client is relying on for the
    credit they have.

    **The SMALLER cushion binds, where the larger gap binds on the way in.**
    Eligibility needs BOTH floors cleared, so an employee falls out the moment
    either is breached: `min`, not `max`. Somebody at twice the hours floor and
    a dollar over the wage floor is one bad week from falling out, and taking
    the hours cushion alone would call them safe.
    """
    weeks = float(average.get("weeks_worked") or 0.0)
    total_hours = float(average.get("total_hours") or 0.0)
    total_wages = float(average.get("total_wages") or 0.0)
    avg_hours = float(average.get("avg_weekly_hours") or 0.0)
    avg_wages = float(average.get("avg_weekly_wages") or 0.0)

    min_hours = float(floors.min_weekly_hours)
    min_wages = float(floors.min_weekly_wages)

    hours_headroom = _round_half_up(avg_hours - min_hours, decimals)
    wages_headroom = _round_half_up(avg_wages - min_wages, decimals)

    rate = _rate(total_hours, total_wages)
    # The wage cushion expressed in the same unit as the hours cushion, so the
    # two are comparable. Without a rate it cannot be converted, and the hours
    # cushion is then all we can honestly report.
    wages_headroom_hours = (
        _round_half_up(wages_headroom / rate, decimals)
        if rate and rate > 0 else None
    )
    cushions = [hours_headroom] + (
        [wages_headroom_hours] if wages_headroom_hours is not None else []
    )
    weekly_hours_to_lose = min(cushions) if cushions else None

    binding = "hours"
    if wages_headroom_hours is not None and wages_headroom_hours < hours_headroom:
        binding = "wages"

    return {
        "employee_id": average.get("Employee_ID"),
        "record_token": average.get("record_token"),
        "weeks_worked": _round_half_up(weeks, decimals),
        "avg_weekly_hours": avg_hours,
        "avg_weekly_wages": avg_wages,
        "hours_headroom": hours_headroom,
        "wages_headroom_usd": wages_headroom,
        "weekly_hours_to_lose": weekly_hours_to_lose,
        "binding_floor": binding,
        "implied_hourly_rate": None if rate is None else _round_half_up(rate, decimals),
        # A part-time band carries a fractional weight, so losing this employee
        # does not always cost a whole job.
        "weight": float(average.get("weight") or 1.0),
    }


def fragile_cohort(
    averages: list[dict[str, Any]],
    *,
    floors: StatutoryFloors,
    within_weekly_hours: float = 5.0,
    limit: int | None = None,
    decimals: int = 2,
    population: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Qualifying employees ranked by how little it would take to lose them.

    `averages` must already be the ELIGIBLE population — this ranks cushions,
    it does not re-decide who qualified. Re-deciding here would be a second
    opinion about a certified verdict.
    """
    assessed = [fragility(a, floors=floors, decimals=decimals) for a in averages]
    reachable = [
        a for a in assessed
        if a["weekly_hours_to_lose"] is not None
        and a["weekly_hours_to_lose"] <= within_weekly_hours
    ]
    reachable.sort(key=lambda r: (r["weekly_hours_to_lose"], str(r["employee_id"])))
    cohort = reachable[:limit] if limit else reachable

    return {
        "band_weekly_hours": within_weekly_hours,
        "eligible": int(population["eligible"]) if population else len(assessed),
        "evaluated": int(population["evaluated"]) if population else len(assessed),
        "within_band": len(reachable),
        "jobs_at_risk": _round_half_up(
            sum(r["weight"] for r in reachable), decimals
        ),
        "binding_floors": {
            "hours": sum(1 for r in reachable if r["binding_floor"] == "hours"),
            "wages": sum(1 for r in reachable if r["binding_floor"] == "wages"),
        },
        "returned": len(cohort),
        "cohort": cohort,
        "floors": {
            "program_code": floors.program_code,
            "tax_year": floors.tax_year,
            "minimum_average_weekly_hours": floors.min_weekly_hours,
            "minimum_average_weekly_wages_usd": floors.min_weekly_wages,
            "source": f"rules/{floors.program_code.lower()}/{floors.tax_year}.json",
        },
        "method_note": (
            "Cushion is the SMALLER of the two floors' headroom, because "
            "eligibility needs both cleared — an employee falls out the moment "
            "either is breached. This describes a completed year: it is what "
            "would have to change to lose these jobs, not a forecast that they "
            "will be lost."
        ),
    }


def band_curve(
    averages: list[dict[str, Any]],
    *,
    floors: StatutoryFloors,
    bands: tuple[float, ...] = BAND_CURVE_HOURS,
    decimals: int = 2,
) -> list[dict[str, Any]]:
    """How many become eligible at each band — the shape of the opportunity.

    One pass over the assessment, reused across bands. A UI showing a band
    control needs this to answer "and if I widen it?" without a round trip per
    notch.
    """
    assessed = [assess_employee(a, floors=floors, decimals=decimals) for a in averages]
    ineligible = [
        a for a in assessed
        if not a["eligible"] and a["additional_weekly_hours"] is not None
    ]
    return [
        {
            "within_weekly_hours": band,
            "employees": sum(1 for r in ineligible if r["additional_weekly_hours"] <= band),
            "plausible": sum(
                1 for r in ineligible
                if r["additional_weekly_hours"] <= band and not r["exceeds_plausible_week"]
            ),
        }
        for band in bands
    ]
