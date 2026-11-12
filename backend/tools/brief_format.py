"""Pre-formatting helpers the page briefs share: a number, a dollar figure, a plural, the band wording. [03b]

Pure. A brief states a figure only as these helpers format it, which is what lets `unsupported_figures`
check a finished summary against the brief at the precision it was written to.
"""
from __future__ import annotations

from typing import Any

BAND_LABEL = {
    "exposed": "Exposed",
    "on_the_line": "On the line",
    "declining": "Declining",
    "unclaimed_at_scale": "Identified",
    "not_assessed": "Not assessed",
    "settled": "Nothing found",
    "unavailable": "Unavailable",
}




def num(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def usd(value: Any) -> str:
    n = num(value)
    return "—" if n is None else f"${n:,.0f}"


def one(value: Any) -> str:
    n = num(value)
    return "—" if n is None else f"{n:.1f}"


def plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"
