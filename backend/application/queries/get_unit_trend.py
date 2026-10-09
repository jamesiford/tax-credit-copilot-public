"""The per-unit multi-year trend behind the grid.

One question, asked of every location a client operates: how has headcount moved
since this location's base year, did each year clear the minimum-new-jobs
threshold, and what does that make claimable.

Every year resolves through `_client_run`, so the window this reads is the same
window `/api/eligibility` and `/api/onezero/matrix` read for the same client and
year. Payroll is loaded once and handed to the resolver rather than reloaded per
year — seven round trips to the lakehouse for one screen is not a detail the
operator should pay for.

A year the statute cannot price is DECLINED by name. A trend with a silent hole
in it reads as a flat year, and a flat year is a finding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query
from application.queries._client_run import ClientRunNotAvailable, resolve_client_run

_METHODS = ("min_max", "pay_period")

# A twelve-month average needs enough measuring dates to be an average. Candle
# Bottle's payroll stops 2024-08-09 while TY2024's window runs to 2025-08-02, so
# one of the twelve targets is reachable and the other eleven are not — the year
# was being "priced" at an average of 0.0 across 101 locations. `_client_run`
# only declines on ZERO rows, which is too weak a test. Half is a judgement, not
# a statute; it sits far from both observed cases (1 of 12, and 11 of 12).
_MIN_REACHABLE_MONTHS = 6


@dataclass(frozen=True)
class GetUnitTrendQuery(Query):
    """Headcount and qualification per unit, across every priceable year."""

    state: str
    account_id: int | None = None
    method: str = "min_max"
    base_year: int | None = None

    def __post_init__(self) -> None:
        if self.method not in _METHODS:
            raise ValueError(f"method must be one of {_METHODS}, got {self.method!r}")


def _candidate_years(state: str) -> list[int]:
    from tools.credit_math import STATE_TO_PACK, authored_years

    pack_file = STATE_TO_PACK.get(state.upper())
    return authored_years(pack_file) if pack_file else []


def _year_benefit(program_code: str, tax_year: int) -> dict[str, Any]:
    """The statutory threshold and per-job amount for one year. [ADR-005]"""
    from tools.credit_math import PROGRAM_CODE_TO_PACK, load_year_pack

    pack_file = PROGRAM_CODE_TO_PACK[program_code]
    pack, year_resolved = load_year_pack(pack_file, tax_year)
    benefit = pack.get("benefit") or {}
    return {
        "threshold": float((pack.get("thresholds") or {}).get("minimum_new_jobs") or 0.0),
        "per_job_usd": float(benefit.get("amount_per_qualifying_job_usd") or 0.0),
        "benefit_period_years": int(benefit.get("benefit_period_years") or 5),
        "year_resolved": year_resolved,
    }


def _designation_at(unit_id: str, tax_year: int, client_id: int | None = None) -> dict[str, Any] | None:
    """The designation in force for a unit in a year, or None if unregistered.

    Prototype data (DISC-10). Most units are not in the registry at all, and
    returning None for them is the honest answer — a guessed tier changes the
    minimum-new-jobs threshold and therefore whether the year qualifies.

    Pass `client_id` for a source-schema unit: its id is only unique within a
    client.
    """
    from data.designations import designation_history

    history = [d for d in designation_history(unit_id, client_id) if int(d["year"]) <= tax_year]
    return dict(history[-1]) if history else None


def _counties(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Work county per unit. Blank under `csv`, which has no county column."""
    out: dict[str, str] = {}
    for row in rows:
        unit_id = str(row.get("Worksite_ID") or "")
        county = str(row.get("Work_County") or "").strip()
        if unit_id and county and unit_id not in out:
            out[unit_id] = county
    return out


# The replay costs one engine run per authored year, and the landing screen is
# the first thing opened for every client. Payroll is immutable for a run and
# both methods are deterministic, so the result is a pure function of the key —
# which includes the data source, because pointing at a different one must not
# return the previous one's answer.
_REPLAY_CACHE: dict[tuple, tuple[dict, dict, str]] = {}
_REPLAY_CACHE_MAX = 24


def _replay_years(query: GetUnitTrendQuery, payroll: list[dict[str, Any]], candidates: list[int]):
    """Run one certified method over every year the statute can price."""
    from domain.calculation.onezero import (
        run_min_max_method, run_pay_period_method, unreachable_months,
    )
    from domain.calculation.rollups import rollup_matrix_by_two_fields
    from tools.fabric_source import active_data_source
    from tools.unit_trend import aggregate_units

    key = (query.account_id, query.state.upper(), query.method, active_data_source(), tuple(candidates))
    cached = _REPLAY_CACHE.get(key)
    if cached is not None:
        return (*cached, [])

    runner = run_min_max_method if query.method == "min_max" else run_pay_period_method
    per_year_units: dict[int, list[dict[str, Any]]] = {}
    per_year_meta: dict[int, dict[str, Any]] = {}
    declined: list[dict[str, str]] = []
    program_code = ""

    for tax_year in candidates:
        try:
            run = resolve_client_run(
                account_id=query.account_id,
                state=query.state.upper(),
                tax_year=tax_year,
                rows=payroll,
            )
        except ClientRunNotAvailable as exc:
            declined.append({"tax_year": str(tax_year), "reason": str(exc)})
            continue

        program_code = run.program_code
        result = runner(run.rows, **run.engine_kwargs())
        unreached = unreachable_months(run.rows, result.months)
        reachable = len(result.months) - len(unreached)
        if reachable < _MIN_REACHABLE_MONTHS:
            first, last = result.months[0], result.months[-1]
            declined.append({
                "tax_year": str(tax_year),
                "reason": (
                    f"payroll reaches {reachable} of {len(result.months)} monthly "
                    f"measuring dates in {first}..{last}; a twelve-month average "
                    f"would be mostly zeroes"
                ),
            })
            continue

        summary = [
            {"unit_id": row["Worksite_ID"], "fein": row["Entity_FEIN"], **row}
            for row in rollup_matrix_by_two_fields(
                result.employee_unit_matrix, "Worksite_ID", "Entity_FEIN"
            )
        ]
        per_year_units[tax_year] = aggregate_units(summary)
        per_year_meta[tax_year] = {
            "tax_year": tax_year,
            "fiscal": run.window.as_dict(),
            "months": [month.isoformat() for month in result.months],
            # Positions no pay period reaches. Their zero is a calendar fact,
            # not a headcount, and the grid must not colour it as a loss.
            "unreachable_months": unreached,
            "months_reachable": reachable,
            "thresholds": run.floors.as_dict(),
            "eligible_employees": len(result.eligible_employees),
            "annual_average": result.annual_average,
            "benefit": _year_benefit(run.program_code, tax_year),
        }

    if per_year_units:
        if len(_REPLAY_CACHE) >= _REPLAY_CACHE_MAX:
            _REPLAY_CACHE.pop(next(iter(_REPLAY_CACHE)))
        _REPLAY_CACHE[key] = (per_year_units, per_year_meta, program_code)

    return per_year_units, per_year_meta, program_code, declined


def reset_replay_cache() -> None:
    """Drop the memoised replays. For tests, and for a data-source switch."""
    _REPLAY_CACHE.clear()


def handle_get_unit_trend(query: GetUnitTrendQuery) -> dict[str, Any]:
    """Replay every priceable year for one client at unit grain."""
    from data.sites import SITES_BY_ID, worksite_name
    from infrastructure.payroll.pay_period_source import load_pay_periods
    from tools.unit_trend import (
        build_unit_series,
        infer_base_year,
        tranche_columns,
        unit_status,
        unit_trend,
    )

    state = query.state.upper()
    candidates = _candidate_years(state)
    if not candidates:
        raise ClientRunNotAvailable(
            f"no year-scoped rule packs authored for {state}; a trend would have "
            f"no statute to test each year against"
        )

    payroll = load_pay_periods(query.account_id)
    if not payroll:
        raise ClientRunNotAvailable(
            f"no payroll for account {query.account_id} in the active data source"
        )

    per_year_units, per_year_meta, program_code, declined = _replay_years(
        query, payroll, candidates
    )

    if not per_year_units:
        raise ClientRunNotAvailable(
            f"no {state} year could be resolved for account {query.account_id}: "
            + "; ".join(d["reason"] for d in declined)
        )

    years = sorted(per_year_units)
    latest_benefit = per_year_meta[years[-1]]["benefit"]
    counties = _counties(payroll)
    series = build_unit_series(per_year_units)
    reachable_by_year = {y: per_year_meta[y]["months_reachable"] for y in years}

    units: list[dict[str, Any]] = []
    for unit_id, unit_years in sorted(series.items()):
        base_year = query.base_year or infer_base_year(
            unit_years, reachable_by_year=reachable_by_year
        )
        if base_year is None or base_year not in unit_years:
            base_year = min(unit_years)
        base_source = "override" if query.base_year else "inferred"

        latest_year = max(unit_years)
        designation = _designation_at(unit_id, latest_year, query.account_id)
        threshold = (
            float(designation["min_new_jobs"]) if designation else latest_benefit["threshold"]
        )

        trend = unit_trend(
            unit_years,
            state=state,
            base_year=base_year,
            threshold=threshold,
            per_job_usd=latest_benefit["per_job_usd"],
            tranche_years=latest_benefit["benefit_period_years"],
        )
        by_year = {y.year: y for y in trend.years}

        rows: list[dict[str, Any]] = []
        for tax_year in years:
            unit = unit_years.get(tax_year)
            if unit is None:
                continue
            stair = by_year.get(tax_year)
            year_designation = _designation_at(unit_id, tax_year, query.account_id)
            rows.append(
                {
                    "tax_year": tax_year,
                    "month_totals": unit["month_totals"],
                    "total": unit["total"],
                    "average_headcount": unit["average_headcount"],
                    "months_with_headcount": unit["months_with_headcount"],
                    "feins": unit["feins"],
                    "tier": (year_designation or {}).get("tier"),
                    "designation": (year_designation or {}).get("designation"),
                    "tier_source": "prototype" if year_designation else "unassigned",
                    "net_new": round(stair.net_new, 2) if stair else 0.0,
                    "threshold": threshold,
                    "qualified": bool(stair.qualified) if stair else False,
                    "backfilled": bool(stair.backfilled) if stair else False,
                    "eligible_jobs": round(stair.eligible_jobs, 2) if stair else 0.0,
                    # Distinct from eligible_jobs and both are required. eligible_jobs
                    # is net-new above the FROZEN BASE and sizes the annual credit;
                    # new_jobs_created is the increment above the RUNNING HIGH-WATER
                    # MARK and is what opens a tranche. In a recovery year the first
                    # is positive while the second is zero — claimable, but not fresh
                    # creation. Dropping either collapses that distinction.
                    "new_jobs_created": round(stair.new_jobs_created, 2) if stair else 0.0,
                    "high_water_mark": round(stair.high_water_mark, 2) if stair else 0.0,
                    "annual_credit_usd": stair.annual_credit_usd if stair else 0,
                    "is_base_year": tax_year == base_year,
                    "status": unit_status(
                        tax_year=tax_year,
                        base_year=base_year,
                        qualified=bool(stair.qualified) if stair else False,
                        months_with_headcount=unit["months_with_headcount"],
                        months_reachable=reachable_by_year.get(tax_year, 12),
                    ),
                }
            )

        site = SITES_BY_ID.get(unit_id)
        units.append(
            {
                "unit_id": unit_id,
                "worksite_id": unit_id,
                "name": worksite_name(unit_id),
                "feins": sorted({f for row in rows for f in row["feins"]}),
                "county": counties.get(unit_id) or (site.county if site else ""),
                "city": site.city if site else "",
                # Not held anywhere in the system. Rendered blank rather than
                # inferred from the county, which would be a fabricated tract.
                "census_tract": "",
                "base_year": base_year,
                "base_year_source": base_source,
                "base_average_headcount": round(trend.base_average_headcount, 2),
                "threshold": threshold,
                "threshold_source": "designation" if designation else "rule_pack",
                "rows": rows,
                "credit_years": tranche_columns(
                    trend, list(range(base_year, base_year + len(years) + 1))
                ),
                "total_annual_credit_usd": trend.total_annual_credit_usd,
                "total_tranche_lifetime_usd": trend.total_tranche_lifetime_usd,
                "final_high_water_mark": round(trend.final_high_water_mark, 2),
            }
        )

    thresholds_by_year = {y: per_year_meta[y]["benefit"]["threshold"] for y in years}
    per_job_by_year = {y: per_year_meta[y]["benefit"]["per_job_usd"] for y in years}
    unreached = {
        y: per_year_meta[y]["unreachable_months"]
        for y in years if per_year_meta[y]["unreachable_months"]
    }

    return {
        "account_id": query.account_id,
        "state": state,
        "program_code": program_code,
        "method": query.method,
        "years": years,
        "declined_years": declined,
        "units": units,
        "year_meta": [per_year_meta[y] for y in years],
        "totals": {
            "units": len(units),
            "annual_credit_usd": sum(u["total_annual_credit_usd"] for u in units),
            "tranche_lifetime_usd": sum(u["total_tranche_lifetime_usd"] for u in units),
        },
        "disclosures": _disclosures(thresholds_by_year, per_job_by_year, units, unreached),
    }


def _disclosures(
    thresholds_by_year: dict[int, float],
    per_job_by_year: dict[int, float],
    units: list[dict[str, Any]],
    unreached: dict[int, list[int]],
) -> list[dict[str, str]]:
    """What a reader has to know before quoting a number off this screen."""
    out = [
        {
            "code": "DISC-8",
            "subject": "base year",
            "text": (
                "The frozen base year and its high-water-mark treatment are read "
                "from a verbal SME description and are not yet confirmed against "
                "the Georgia Job Tax Credit form."
            ),
        },
        {
            "code": "DISC-10",
            "subject": "tier",
            "text": (
                "Tier designations are prototype data covering four worksites. "
                "Units outside that registry are shown unassigned and fall back "
                "to the rule pack's minimum-new-jobs threshold."
            ),
        },
        {
            "code": "TIER-FLAT",
            "subject": "credit amount",
            "text": (
                "Claimable dollars use one statutory amount per qualifying job. "
                "Tier-varied amounts are not authored in any rule pack, so a "
                "Tier 2 location is priced at the Tier 1 rate."
            ),
        },
    ]
    if len({round(v, 2) for v in thresholds_by_year.values()}) > 1 or len(
        {round(v, 2) for v in per_job_by_year.values()}
    ) > 1:
        out.append(
            {
                "code": "STATUTE-DRIFT",
                "subject": "threshold",
                "text": (
                    "The minimum-new-jobs threshold or per-job amount changed "
                    "across this window. The tranche engine applies a single "
                    "value; per-year statute is shown on each row."
                ),
            }
        )
    if any(u["census_tract"] == "" for u in units):
        out.append(
            {
                "code": "NO-TRACT",
                "subject": "census tract",
                "text": "Census tract is not held anywhere in the system and is left blank.",
            }
        )
    if unreached:
        named = ", ".join(
            f"TY{year} month{'s' if len(idx) > 1 else ''} "
            + "/".join(str(i + 1) for i in idx)
            for year, idx in sorted(unreached.items())
        )
        out.append(
            {
                "code": "NO-MEASURING-DATE",
                "subject": "month coverage",
                "text": (
                    f"No pay period reaches the measuring date in {named}. Those "
                    f"months read zero as a fact about the pay calendar, not about "
                    f"headcount, and are marked rather than counted as a decline."
                ),
            }
        )
    return out
