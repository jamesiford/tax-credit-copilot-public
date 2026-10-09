"""Per-unit multi-year trend — the shape the statute is actually tested in.

Everything multi-year in this codebase so far has been per-state or per-client:
`api/retroactive.py` replays whole years, `tools/baseyear.py` freezes one base
year for an entire state. Georgia's Job Tax Credit is a per-LOCATION test, so a
client with one growing store and one shrinking store has two different answers
and a single state-wide average shows neither.

This module does no statutory math of its own. The frozen base year, the
backfill rule and the five-year tranches all come from `tools/baseyear.py`; here
the engine's per-(unit, FEIN) monthly summary is reshaped into a per-unit yearly
series and each unit's series is handed to that engine separately.

Pure functions. No I/O, no framework.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from tools.baseyear import DEFAULT_TRANCHE_YEARS, BaseYearResult, compute_base_year_tranches

MONTHS_IN_YEAR = 12

# A unit-year's reading, before any colour is chosen for it. Presentation maps
# these to a tone; the decision of which one applies is made once, here.
STATUS_BASE = "base"
STATUS_ABOVE = "above_minimum"
STATUS_BELOW = "below_minimum"
STATUS_PARTIAL = "partial"
STATUS_NO_DATA = "no_data"
#: A year before the base (WI-21). Not measured against it, so not a reading:
#: before a saved base existed, the base was always the earliest complete year
#: and only partial years could precede it.
STATUS_BEFORE_BASE = "before_base"
#: An open year (TY2026), read on its closed months and not yet priced.
STATUS_IN_PROGRESS = "in_progress"


def aggregate_units(summary_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Collapse the engine's (unit x FEIN) summary to unit grain.

    Georgia tests headcount at the location, and one location can host more than
    one legal entity. Summing the monthly columns is the aggregation the statute
    asks for; the FEINs are carried along so the drill can still name them.
    """
    by_unit: dict[str, dict[str, Any]] = {}

    for row in summary_rows:
        unit_id = str(row.get("unit_id") or row.get("Worksite_ID") or "")
        fein = str(row.get("fein") or row.get("Entity_FEIN") or "")
        months = [float(v) for v in (row.get("month_totals") or [])]

        bucket = by_unit.setdefault(
            unit_id,
            {"unit_id": unit_id, "feins": [], "month_totals": [0.0] * MONTHS_IN_YEAR},
        )
        if fein and fein not in bucket["feins"]:
            bucket["feins"].append(fein)
        for index, value in enumerate(months[:MONTHS_IN_YEAR]):
            bucket["month_totals"][index] += value

    units: list[dict[str, Any]] = []
    for bucket in by_unit.values():
        totals = [round(v, 2) for v in bucket["month_totals"]]
        total = round(sum(totals), 2)
        units.append(
            {
                "unit_id": bucket["unit_id"],
                "feins": sorted(bucket["feins"]),
                "month_totals": totals,
                "total": total,
                "average_headcount": round(total / MONTHS_IN_YEAR, 2),
                "months_with_headcount": sum(1 for v in totals if v > 0),
            }
        )
    return sorted(units, key=lambda u: u["unit_id"])


def build_unit_series(
    per_year_units: Mapping[int, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[int, dict[str, Any]]]:
    """Pivot {tax_year: [unit rows]} into {unit_id: {tax_year: unit row}}.

    A unit missing from a year is genuinely absent — the location had no payroll
    inside that year's window — and is left out rather than zero-filled, because
    a zero average would flow into the base-year comparison as a real reading.
    """
    series: dict[str, dict[int, dict[str, Any]]] = {}
    for tax_year, units in per_year_units.items():
        for unit in units:
            series.setdefault(str(unit["unit_id"]), {})[int(tax_year)] = dict(unit)
    return series


def infer_base_year(
    unit_years: Mapping[int, Mapping[str, Any]],
    *,
    reachable_by_year: Mapping[int, int] | None = None,
) -> int | None:
    """The unit's own base year: its earliest year of complete payroll.

    A partial year makes a flattering base — fewer months of headcount averaged
    over twelve reads as a lower baseline, and every later year then looks like
    growth that never happened.

    **Completeness is measured against the months that are REACHABLE**, not
    against twelve. A calendar-year client whose last December period ends on
    the 15th has no measuring date in December at all, so its best possible year
    is eleven months. Judging it against twelve rejected a complete year and
    pushed the base a year later — on Cascade that moved the base from TY2020 to
    TY2021 and, because the base is the most leveraged input in the model,
    changed every net-new figure and every dollar downstream.
    """
    if not unit_years:
        return None

    reachable = reachable_by_year or {}
    complete = [
        year
        for year, unit in sorted(unit_years.items())
        if int(unit.get("months_with_headcount") or 0)
        >= reachable.get(year, MONTHS_IN_YEAR)
    ]
    if complete:
        return complete[0]
    return min(unit_years)


def unit_status(
    *,
    tax_year: int,
    base_year: int | None,
    qualified: bool,
    months_with_headcount: int,
    months_reachable: int = MONTHS_IN_YEAR,
) -> str:
    """One reading per unit-year, decided in a single place.

    `partial` means the client's payroll does not cover the year. A month whose
    measuring date no pay period reaches is a different fact — the year is
    complete and the calendar is the problem — so it must not be reported as a
    short year.
    """
    if months_with_headcount <= 0:
        return STATUS_NO_DATA
    if base_year is not None and tax_year == base_year:
        return STATUS_BASE
    if base_year is not None and tax_year < base_year and months_with_headcount >= months_reachable:
        # A complete year before a chosen base. It was never measured, and
        # calling it "below minimum" would paint a shortfall that did not happen.
        return STATUS_BEFORE_BASE
    if months_with_headcount < months_reachable:
        return STATUS_PARTIAL
    return STATUS_ABOVE if qualified else STATUS_BELOW


def unit_trend(
    unit_years: Mapping[int, Mapping[str, Any]],
    *,
    state: str,
    base_year: int,
    threshold: float,
    per_job_usd: float,
    tranche_years: int = DEFAULT_TRANCHE_YEARS,
    benefit_by_year: Mapping[int, Mapping[str, float]] | None = None,
) -> BaseYearResult:
    """Run the frozen-base-year engine over one unit's yearly averages."""
    yearly_avg = {
        int(year): float(unit.get("average_headcount") or 0.0)
        for year, unit in unit_years.items()
    }
    return compute_base_year_tranches(
        state,
        yearly_avg,
        base_year=base_year,
        threshold=threshold,
        per_job_usd=per_job_usd,
        tranche_years=tranche_years,
        benefit_by_year=benefit_by_year,
    )


def tranche_columns(result: BaseYearResult, years: Sequence[int]) -> list[dict[str, Any]]:
    """The YR1..YRn credit stream, one column per year on the grid.

    Each creation year opens its own window, so a year's column is the sum of
    every live tranche's installment for it. Reported as `claimable_usd` rather
    than `credit`, because a tranche installment in a year with no payroll yet
    is a forecast on the assumption the job is maintained.
    """
    installment_by_year: dict[int, float] = {}
    creations_by_year: dict[int, list[int]] = {}

    for event in result.tranche_events:
        for installment in event.installments:
            year = int(installment["year"])
            installment_by_year[year] = installment_by_year.get(year, 0.0) + float(
                installment["credit_usd"]
            )
            creations_by_year.setdefault(year, []).append(event.creation_year)

    return [
        {
            "tax_year": year,
            "claimable_usd": round(installment_by_year.get(year, 0.0)),
            "from_creation_years": sorted(set(creations_by_year.get(year, []))),
            # No payroll for the year yet: the installment assumes the job is
            # still there, which is a projection and has to read as one.
            "projected": year not in {y.year for y in result.years} and year != result.base_year,
        }
        for year in years
    ]
