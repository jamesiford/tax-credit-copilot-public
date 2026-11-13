"""The sentence that names the lever for a borderline (yellow) employee. [J3 UX-03]

Lifted out of `api/forecast.py` so the route stays thin and the wording has one home. The numbers come from the engine's
performance dashboard; this only phrases them.
"""
from __future__ import annotations

from typing import Any


def lever_sentence(employee: dict[str, Any], state: str, pack: Any) -> str | None:
    """What this employee would have to change to clear the floors, or None when nothing is short."""
    parts = []
    if employee["hours_gap_per_week"] > 0:
        parts.append(f"add {employee['hours_gap_per_week']:.1f} hrs/wk to clear the {state} {pack.min_weekly_hours:.0f}-hr threshold")
    if pack.min_weekly_wages > 0 and employee["wages_gap_per_week"] > 0:
        parts.append(
            f"raise weekly wages by ${employee['wages_gap_per_week']:,.0f} to clear the {state} ${pack.min_weekly_wages:,.0f}/wk floor"
        )
    if not parts:
        return None
    return (
        f"{employee['Employee_ID']} ({employee['Worksite_ID']}) is at {employee['avg_weekly_hours']:.1f} hrs/wk "
        f"and ${employee['avg_weekly_wages']:,.0f}/wk avg — " + "; ".join(parts) + "."
    )
