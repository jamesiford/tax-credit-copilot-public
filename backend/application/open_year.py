"""Is a tax year still open? One answer, used everywhere a year is priced.

A year is OPEN while its fiscal window has not ended. TY2026 is the first one
the product holds (24 Sep 2026): payroll through the 31 August checkpoint, and
four months still to come.

An open year is not a small year, and treating it as one is the defect this
exists to prevent. Its months after the checkpoint are zero because they have
not happened, so an average over twelve reads as a location that shrank by a
third. The partner's own framing is the fix: "change the denominator from 12 months to
8 or 9". An open year is read on its closed months, is never claimed, and is
never fed into the priced credit series until it closes.

`today()` is the one seam: tests pin it, so a test written today still means
the same thing next year.
"""
from __future__ import annotations

from datetime import date
from typing import Any

#: The fewest closed months an open year is read on. Fewer is too early to
#: state a pace anyone should repeat; the year is declined with that reason.
MIN_OPEN_MONTHS = 3


def today() -> date:
    return date.today()


def is_open(window_end: Any, *, on: date | None = None) -> bool:
    """True while the fiscal window ending `window_end` is still running."""
    end = window_end if isinstance(window_end, date) else date.fromisoformat(str(window_end)[:10])
    return end > (on or today())


def open_year_reading(
    average_headcount: float, trend: Any, statute: dict[str, Any], threshold: float,
) -> Any:
    """Where an open year stands against the base, read on its closed months.

    Not a priced year: `annual_credit_usd` and `eligible_jobs` are zero because
    nothing is claimable until the year closes. `qualified` is the on-track
    reading — net new to date against the minimum — which is what How am I
    doing asks. `trend` is the CLOSED series, so the base and the high-water
    mark are the ones the grid measured the finished years against.

    The write path and the What-if both call this, so the grid and a projection
    from it cannot disagree about what "on track" means.
    """
    from types import SimpleNamespace

    average = float(average_headcount or 0.0)
    net_new = max(0.0, average - float(trend.base_average_headcount))
    year_threshold = float(statute.get("threshold", threshold))
    return SimpleNamespace(
        average_headcount=average,
        base_average_headcount=float(trend.base_average_headcount),
        net_new=net_new, threshold=year_threshold,
        qualified=net_new >= year_threshold and net_new > 0,
        eligible_jobs=0.0, new_jobs_created=0.0,
        high_water_mark=max(float(trend.final_high_water_mark), average),
        backfilled=False, annual_credit_usd=0.0,
        per_job_usd=float(statute.get("per_job_usd") or trend.per_job_usd),
    )
