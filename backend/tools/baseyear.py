"""[L1] CALC-07 — Georgia frozen-base-year tranche + backfill engine.

Source: June 11 2026 session with the partner. The statutory Georgia
Job Tax Credit is *not* a rolling prior-year net-new calc (that is what the demo
engine did). It is measured against a **frozen base year** with a **high-water
mark** that persists across years, evaluated in **5-year tranches**, and it
supports **backfill** — drop below the minimum-new-jobs threshold one year, climb
back the next, and you re-qualify.

> "Georgia says, okay, starting whatever year, that's your base… I start with 100,
>  go up to 105, I get credits on five people. The next year I'm at 104, so I lost
>  one, now four. But the next year I'm at 101 — now I'm kicked out, below the
>  threshold. The year after I go to 103, I can backfill 2 and I'm back in the
>  game… five-year tranches, each year is its own opportunity." — the partner

This module is a **defensible first cut** of those mechanics so we can show the partner
the direction and let them correct it against the actual GA Job Tax Credit form.
Every GA-specific assumption is flagged with `_prototype_verify` + `_disc_ref`
(DISC-8 base-year treatment, DISC-9 high-water-mark) until the partner confirms.

Pure functions only — no FastAPI, no I/O. Records steps into the active
calculation trail for audit defensibility (same boundary as the rest of `tools/`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from domain.calculation.trail import current_recorder

# This module models the statutory base-year mechanics described verbally by the
# SME; the exact GA form has not yet been shared. Flagged for SME verification.
_DISC_REF = "DISC-8"
_PROTOTYPE_VERIFY = True
DEFAULT_TRANCHE_YEARS = 5


@dataclass
class TrancheYear:
    """One year in the stair-step net-new-vs-frozen-base evaluation."""
    year: int
    average_headcount: float
    base_average_headcount: float
    net_new: float            # max(0, avg - base)
    threshold: float          # minimum_new_jobs for the designation
    qualified: bool           # net_new >= threshold
    eligible_jobs: float      # net_new if qualified else 0 (jobs claimable this year)
    high_water_mark: float    # running max average seen through this year (>= base)
    new_jobs_created: float   # increment over the prior high-water mark (a fresh tranche)
    backfilled: bool          # re-qualified this year after a prior non-qualifying year
    annual_credit_usd: float  # eligible_jobs * per_job (the stair-step annual claim)
    # The rate THIS year was priced at. On the year rather than on the series
    # because statute is versioned by tax year [ADR-005]: a series spanning six
    # years can span six rates, and a single scalar would report whichever one
    # happened to be read.
    per_job_usd: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "average_headcount": round(self.average_headcount, 2),
            "base_average_headcount": round(self.base_average_headcount, 2),
            "net_new": round(self.net_new, 2),
            "threshold": self.threshold,
            "qualified": self.qualified,
            "eligible_jobs": round(self.eligible_jobs, 2),
            "high_water_mark": round(self.high_water_mark, 2),
            "new_jobs_created": round(self.new_jobs_created, 2),
            "backfilled": self.backfilled,
            "annual_credit_usd": self.annual_credit_usd,
            "per_job_usd": self.per_job_usd,
        }


@dataclass
class TrancheEvent:
    """A job-creation event in `creation_year`, claimable over a 5-year window.

    Models the partner's "a job I created five years ago still throws a current-year
    installment" — the reason the retroactive scan (`[N1]`) must reach back
    `tranche_years` years.
    """
    creation_year: int
    jobs: float                       # new jobs created in that year (tranche size)
    per_job_usd: float
    tranche_years: int
    installments: list[dict] = field(default_factory=list)  # [{year, jobs_maintained, credit_usd}]

    @property
    def lifetime_usd(self) -> int:
        return sum(i["credit_usd"] for i in self.installments)

    def to_dict(self) -> dict[str, Any]:
        return {
            "creation_year": self.creation_year,
            "jobs": round(self.jobs, 2),
            "per_job_usd": self.per_job_usd,
            "tranche_years": self.tranche_years,
            "window": [self.creation_year, self.creation_year + self.tranche_years - 1],
            "installments": self.installments,
            "lifetime_usd": self.lifetime_usd,
        }


@dataclass
class BaseYearResult:
    state: str
    base_year: int
    base_average_headcount: float
    threshold: float
    per_job_usd: float
    tranche_years: int
    base_year_overridden: bool
    high_water_mark_overridden: bool
    years: list[TrancheYear]
    tranche_events: list[TrancheEvent]
    final_high_water_mark: float

    @property
    def total_annual_credit_usd(self) -> int:
        """Sum of the per-year stair-step claims (primary headline number)."""
        return sum(y.annual_credit_usd for y in self.years)

    @property
    def total_tranche_lifetime_usd(self) -> int:
        """Forecast ceiling: full 5-year value of every job created, if maintained."""
        return sum(e.lifetime_usd for e in self.tranche_events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "_roadmap_tag": "L1",
            "_story": "CALC-07",
            "_prototype_verify": _PROTOTYPE_VERIFY,
            "_disc_ref": _DISC_REF,
            "state": self.state,
            "base_year": self.base_year,
            "base_average_headcount": round(self.base_average_headcount, 2),
            "threshold": self.threshold,
            "per_job_usd": self.per_job_usd,
            "tranche_years": self.tranche_years,
            "base_year_overridden": self.base_year_overridden,
            "high_water_mark_overridden": self.high_water_mark_overridden,
            "years": [y.to_dict() for y in self.years],
            "tranche_events": [e.to_dict() for e in self.tranche_events],
            "final_high_water_mark": round(self.final_high_water_mark, 2),
            "total_annual_credit_usd": self.total_annual_credit_usd,
            "total_tranche_lifetime_usd": self.total_tranche_lifetime_usd,
        }


def compute_base_year_tranches(
    state: str,
    yearly_avg: dict[int, float],
    *,
    base_year: int,
    threshold: float,
    per_job_usd: float,
    tranche_years: int = DEFAULT_TRANCHE_YEARS,
    base_average_override: float | None = None,
    high_water_mark_override: float | None = None,
    benefit_by_year: Mapping[int, Mapping[str, float]] | None = None,
) -> BaseYearResult:
    """Evaluate the frozen-base-year stair-step with backfill + 5-year tranches.

    Args:
        state: two-letter state code (for trail labelling).
        yearly_avg: {tax_year: One/Zero Average Headcount} for the base year and
            every subsequent year to evaluate.
        base_year: the frozen base year. Net-new is measured against this year's
            Average Headcount (NOT the rolling prior year).
        threshold: the designation's `minimum_new_jobs`. A year qualifies only
            when net-new (above base) meets it; below it the year claims 0 but
            can **backfill** in a later qualifying year.
        per_job_usd: statutory dollars per qualifying job.
        tranche_years: benefit window per creation event (GA = 5).
        base_average_override: wipe/negotiate the base (DISC-8) — a long-present
            employer can negotiate the frozen base; an override replaces the
            base-year headcount.
        high_water_mark_override: seed the persistent high-water mark (DISC-9) —
            the "bad smell" baseline a long-present GA employer carries forward.
        benefit_by_year: `{tax_year: {threshold, per_job_usd}}`. Statute is
            versioned by tax year [ADR-005], so a six-year series can span six
            rates; the scalars above are the fallback for a caller that has only
            one. **A year absent from the map falls back to them rather than to
            a neighbouring year's**, because inheriting statute across years is
            the thing year packs exist to prevent.

    Returns a `BaseYearResult` with the per-year stair-step, the per-creation
    tranche schedule, and both the annual-claim total and the maintained-lifetime
    ceiling.
    """
    state_u = state.upper()
    base_avg = base_average_override if base_average_override is not None else float(yearly_avg.get(base_year, 0.0))

    eval_years = sorted(y for y in yearly_avg if y > base_year)
    running_hwm = high_water_mark_override if high_water_mark_override is not None else base_avg

    years: list[TrancheYear] = []
    tranche_events: list[TrancheEvent] = []
    prev_qualified = True  # the base year is, by definition, the qualifying baseline

    def _for(year: int, key: str, fallback: float) -> float:
        return float((benefit_by_year or {}).get(year, {}).get(key, fallback))

    for y in eval_years:
        year_threshold = _for(y, "threshold", threshold)
        year_rate = _for(y, "per_job_usd", per_job_usd)
        avg = float(yearly_avg[y])
        net_new = max(0.0, avg - base_avg)
        qualified = net_new >= year_threshold and net_new > 0
        eligible_jobs = net_new if qualified else 0.0
        new_jobs_created = max(0.0, avg - running_hwm)  # fresh creation = new high-water
        backfilled = qualified and not prev_qualified
        annual_credit = round(eligible_jobs * year_rate)

        years.append(TrancheYear(
            year=y,
            average_headcount=avg,
            base_average_headcount=base_avg,
            net_new=net_new,
            threshold=year_threshold,
            qualified=qualified,
            eligible_jobs=eligible_jobs,
            high_water_mark=max(running_hwm, avg),
            new_jobs_created=new_jobs_created,
            backfilled=backfilled,
            annual_credit_usd=annual_credit,
            per_job_usd=year_rate,
        ))

        # A fresh creation event opens a 5-year tranche, but only if this year
        # also clears the threshold (sub-threshold growth earns nothing).
        #
        # Priced at the CREATION year's rate and held there for the window: the
        # rate attaches to the job when it is created, so a later year's rate
        # must not reprice a tranche already running.
        if new_jobs_created > 0 and qualified:
            tranche_events.append(_build_tranche_event(
                creation_year=y, jobs=new_jobs_created, per_job_usd=year_rate,
                tranche_years=tranche_years, yearly_avg=yearly_avg, base_avg=base_avg,
            ))

        running_hwm = max(running_hwm, avg)
        prev_qualified = qualified

    result = BaseYearResult(
        state=state_u,
        base_year=base_year,
        base_average_headcount=base_avg,
        threshold=threshold,
        per_job_usd=per_job_usd,
        tranche_years=tranche_years,
        base_year_overridden=base_average_override is not None,
        high_water_mark_overridden=high_water_mark_override is not None,
        years=years,
        tranche_events=tranche_events,
        final_high_water_mark=running_hwm,
    )

    recorder = current_recorder()
    if recorder is not None:
        recorder.record(
            step=f"{state_u}: frozen base-year tranche evaluation",
            inputs={
                "base_year": base_year,
                "base_average_headcount": round(base_avg, 2),
                "threshold": threshold,
                "tranche_years": tranche_years,
                "years_evaluated": eval_years,
            },
            formula="net_new[y] = max(0, avg[y] - base_avg); qualify if net_new >= threshold (backfill auto); tranche = 5-yr window per new high-water",
            output={
                "total_annual_credit_usd": result.total_annual_credit_usd,
                "total_tranche_lifetime_usd": result.total_tranche_lifetime_usd,
                "final_high_water_mark": round(running_hwm, 2),
            },
            citation=f"GA JTC base-year mechanics (pending SME form — {_DISC_REF})",
        )

    return result


def _build_tranche_event(
    *,
    creation_year: int,
    jobs: float,
    per_job_usd: float,
    tranche_years: int,
    yearly_avg: dict[int, float],
    base_avg: float,
) -> TrancheEvent:
    """Project a creation event's installments over its 5-year window.

    A job is claimable in an out-year only if it is *maintained* — i.e. that
    year's Average Headcount still sits above the frozen base by at least the
    tranche size. Where an out-year has no data yet, the job is assumed
    maintained (carry-forward) so the forecast ceiling is visible.
    """
    installments: list[dict] = []
    for inst_year in range(creation_year, creation_year + tranche_years):
        future_avg = yearly_avg.get(inst_year)
        if future_avg is None:
            jobs_maintained = jobs  # no data yet → assume maintained (forecast)
        else:
            headroom = max(0.0, float(future_avg) - base_avg)
            jobs_maintained = min(jobs, headroom)
        installments.append({
            "year": inst_year,
            "jobs_maintained": round(jobs_maintained, 2),
            "credit_usd": round(jobs_maintained * per_job_usd),
        })
    return TrancheEvent(
        creation_year=creation_year, jobs=jobs, per_job_usd=per_job_usd,
        tranche_years=tranche_years, installments=installments,
    )
