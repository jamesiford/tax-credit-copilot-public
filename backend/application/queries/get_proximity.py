"""Who is near the statutory line, and what would close the gap.

A query: it computes and returns, and changes nothing. The eligibility verdicts
it reads were produced by the certified engine at write time — the same run that
yields 10,236 / 539 / 656 — so this handler cannot move those figures. It reads
them; it does not re-derive them.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query

_METHODS = ("min_max", "pay_period")


@dataclass(frozen=True)
class GetProximityQuery(Query):
    """Employees within `within_weekly_hours` of qualifying, ranked.

    `state` and `tax_year` together select the statute [ADR-005]. A cohort
    spanning two programme-years would rank employees against different rulers,
    so the pair is required rather than defaulted.
    """

    tax_year: int
    state: str
    method: str = "min_max"
    within_weekly_hours: float = 5.0
    limit: int = 100
    account_id: int | None = None
    #: WI-19. Add what each person needs over the REST of the year, as of the
    #: in-year checkpoint (31 August unless `as_of` says otherwise).
    rest_of_year: bool = False
    as_of: Any = None

    def __post_init__(self) -> None:
        if self.method not in _METHODS:
            raise ValueError(f"method must be one of {_METHODS}, got {self.method!r}")
        if self.within_weekly_hours < 0:
            raise ValueError("within_weekly_hours cannot be negative")

    def resolved_as_of(self) -> Any:
        from datetime import date

        return self.as_of or date(self.tax_year, 8, 31)


class ProximityNotAvailable(LookupError):
    """The question cannot be answered, and why.

    A domain-level failure with a reason, so the router can choose a status code
    without re-deriving what went wrong. Returning an empty cohort instead would
    be indistinguishable from 'nobody is near the line', which is a different and
    far more dangerous answer.
    """


def handle_get_proximity(query: GetProximityQuery) -> dict[str, Any]:
    """Who is near the line, read from the run that decided who was over it.

    This used to replay a certified method over the client's whole payroll on
    every page load — 61 seconds for the reference client, and ClientPage fired
    it alongside two more replays behind the forecast. Every field the
    assessment needs (`weeks_worked`, the two totals, the two averages) was
    already written to `employee_eligibility` by the run.

    Two things change with the source, and both are corrections:

    - **The population is the client's FISCAL window, not the calendar year.**
      The old filter was `Pay_Date[:4] == tax_year` with a hardcoded December
      year end, so this screen and `get_eligibility` disagreed about which
      payroll TY2023 contains for any client that is not a calendar filer.
    - **The verdict is READ.** `assess_employee` prefers the recorded
      `eligible`, so a part-time-band employee is no longer reported as a near
      miss that the run had already counted.
    """
    from application.queries._client_run import resolve_statute
    from application.wiring import get_gold_reader
    from domain.calculation.proximity import BAND_CURVE_HOURS, band_curve, near_miss_cohort

    # Statute first. An unauthored year and an unmapped state are facts about
    # the programme, not about the client, and they decline by name whether or
    # not a client was named.
    try:
        resolved = resolve_statute(
            account_id=query.account_id, state=query.state, tax_year=query.tax_year
        )
    except LookupError as exc:
        raise ProximityNotAvailable(str(exc)) from exc

    if query.account_id is None:
        raise ProximityNotAvailable(
            "a client is required — the cohort is read from that client's run"
        )

    # The widest question the response answers. `band_curve` reports out to ten
    # hours, so the rows must reach at least that far even when the caller asked
    # for five — a bound taken from the query alone would silently empty the
    # outer notches of the curve.
    widest_band = max(float(query.within_weekly_hours), max(BAND_CURVE_HOURS))

    population = get_gold_reader().proximity_candidates(
        query.account_id,
        tax_year=query.tax_year,
        method=query.method,
        min_weekly_hours=float(resolved.floors.min_weekly_hours),
        min_weekly_wages=float(resolved.floors.min_weekly_wages),
        widest_band_hours=widest_band,
    )
    run = population["run"]
    rows = population["rows"]
    counts = population["counts"]
    if run is None or counts is None or not int(counts.get("evaluated") or 0):
        # "No run has reached this client-year" is not "nobody is near the
        # line". The caller renders the first as a statement and the second as
        # a result, so they must not arrive as the same shape.
        return {
            "state": resolved.state,
            "program_code": resolved.program_code,
            "tax_year": query.tax_year,
            "method": query.method,
            "account_id": query.account_id,
            "calculation_state": "not_calculated",
            "run": run,
            "cohort": [],
            "bands": [],
        }

    averages = [
        {
            "Employee_ID": row["employee_id"],
            "record_token": row["record_token"],
            "weeks_worked": float(row["weeks_worked"] or 0),
            "total_hours": float(row["total_hours"] or 0),
            "total_wages": float(row["total_wages"] or 0),
            "avg_weekly_hours": float(row["avg_weekly_hours"] or 0),
            "avg_weekly_wages": float(row["avg_weekly_wages"] or 0),
            "eligible": bool(row["eligible"]),
        }
        for row in rows
    ]

    cohort = near_miss_cohort(
        averages,
        floors=resolved.floors,
        within_weekly_hours=query.within_weekly_hours,
        limit=query.limit,
        population={
            "evaluated": int(counts["evaluated"] or 0),
            "eligible": int(counts["eligible_count"] or 0),
            "ineligible": int(counts["ineligible_count"] or 0),
            "failure_modes": {
                "hours_only": int(counts["hours_only"] or 0),
                "wages_only": int(counts["wages_only"] or 0),
                "both": int(counts["both"] or 0),
            },
        },
    )
    cohort.update(
        {
            "state": resolved.state,
            "program_code": resolved.program_code,
            "tax_year": query.tax_year,
            "method": query.method,
            "account_id": query.account_id,
            "calculation_state": "calculated",
            "run": run,
            "fiscal_window": {
                "begin": str(resolved.window.begin),
                "end": str(resolved.window.end),
            },
            "bands": band_curve(averages, floors=resolved.floors),
        }
    )
    cohort["statute_matches_run"] = _statute_matches_run(cohort, resolved)
    if query.rest_of_year and cohort["cohort"]:
        _attach_rest_of_year(cohort, query=query, resolved=resolved, run=run)
    return cohort


def _attach_rest_of_year(cohort: dict[str, Any], *, query: Any, resolved: Any, run: dict[str, Any]) -> None:
    """Add `rest_of_year` to each row, read from the periods the run wrote.

    A failure costs the column, never the cohort: the full-year answer stands.
    """
    as_of = query.resolved_as_of()
    cohort["rest_of_year_as_of"] = as_of.isoformat()
    attach_rest_of_year(
        cohort["cohort"], client_id=query.account_id, tax_year=query.tax_year,
        run_id=run["run_id"], resolved=resolved, as_of=as_of, method=query.method,
    )


def attach_rest_of_year(
    rows: list[dict[str, Any]], *, client_id: int, tax_year: int, run_id: str,
    resolved: Any, as_of: Any, method: str = "min_max",
) -> None:
    """Give each row what the rest of the year needs, and where they work.

    Shared by Near the line, a location's near-the-floor list and the employee
    walk (29 Sep), so all three pre-fill a What-if stack with the same figure.
    Rows are changed in place; a failed read leaves them as they were.
    """
    import logging

    from application.wiring import get_gold_reader
    from domain.calculation.proximity import rest_of_year

    try:
        tokens = [row.get("record_token") for row in rows if row.get("record_token")]
        periods = get_gold_reader().cohort_periods(
            client_id, tax_year=tax_year, run_id=run_id, tokens=tokens,
        ) if tokens else {}
    except Exception:  # noqa: BLE001
        logging.getLogger(__name__).warning("rest-of-year unavailable", exc_info=True)
        return
    for row in rows:
        token = row.get("record_token")
        if token in periods:
            row["rest_of_year"] = rest_of_year(
                periods[token], floors=resolved.floors, as_of=as_of,
                year_end=resolved.window.end, method=method,
            )
            row.update(_where_they_work(periods[token], client_id=client_id, tax_year=tax_year))


def _where_they_work(periods: list[dict[str, Any]], *, client_id: int, tax_year: int) -> dict[str, Any]:
    """The location an employee works at most, and its designation that year.

    A What-if stack names each person against a location, so the row carries
    it. Designation is the same registry the grid was written from — shown,
    not applied by the engine (DISC-10).
    """
    from application.queries.get_unit_trend import _designation_at

    hours: dict[str, float] = {}
    for p in periods:
        site = str(p.get("worksite_id") or "")
        if site:
            hours[site] = hours.get(site, 0.0) + float(p.get("hours") or 0.0)
    if not hours:
        return {}
    primary = max(hours, key=hours.get)
    designation = _designation_at(primary, tax_year, client_id)
    return {
        "worksite_id": primary,
        "worksites": sorted(hours),
        "designation": (designation or {}).get("designation"),
        "tier": (designation or {}).get("tier"),
        "tier_source": "prototype" if designation else "unassigned",
    }


def _statute_matches_run(cohort: dict[str, Any], resolved: Any) -> dict[str, Any]:
    """Whether the band is drawn with the ruler the verdict was decided by.

    `eligible` is read from the run; the near-floor band and the two `passed_*`
    halves are drawn from the floors resolved NOW. They agree only while the
    rule pack has not been re-authored since the run.

    `run_manifest.rule_pack_version` cannot answer this — it stores the pack's
    PATH, and re-authoring a materialised year pack changes its contents but not
    its filename. `calculation_id` hashes the floors but also the payroll, so
    recomputing it would cost the engine pass this whole change removes.

    The stored rows answer it directly instead. Absent a part-time band,
    `eligible` must equal "passed both floors"; any row where it does not means
    the floors moved after the run.

    `run_manifest.rule_pack_version` is deliberately NOT reported here. It is
    stamped once per RUN from the commanded year's floors, while a run replays
    many years — so for account 2001 it reads `2025.json` beside a TY2023
    answer, which looks like a contradiction and is merely the wrong grain.
    """
    disagreements = int(cohort.get("verdict_disagreements") or 0)
    has_band = bool(
        getattr(resolved.pack, "pt_band_hours", None)
        and getattr(resolved.pack, "pt_weight", None)
    )
    return {
        "matches": disagreements == 0 or has_band,
        "verdict_disagreements": disagreements,
        "programme_has_part_time_band": has_band,
        "resolved_rule_pack_source": str(
            resolved.floors.as_dict().get("source") or ""
        ) or None,
    }
