"""What `Account.IndustryTypeId` means.

The source schema carries the column and nothing populated it. The partner, 24
September: "To determine if a credit is there or not, you need to know the
industry and the tier." The id is the two-digit NAICS sector, so it is a
public classification rather than a code we invented.

DISPLAY-ONLY. Georgia restricts Tier 1 to eligible industries unless the county
is bottom-40 or a special zone, and the engine does not apply that rule yet. An
industry on screen changes no figure.
"""
from __future__ import annotations

#: NAICS sector -> the label a reader sees.
INDUSTRY_NAMES: dict[int, str] = {
    31: "Manufacturing",
    44: "Retail",
    48: "Transportation & warehousing",
    62: "Health care",
    72: "Food service",
}


def industry_name(industry_type_id: int | None) -> str | None:
    """The label for an id, or None — an unknown industry is not guessed."""
    if industry_type_id is None:
        return None
    try:
        return INDUSTRY_NAMES.get(int(industry_type_id))
    except (TypeError, ValueError):
        return None
