"""What `Account.IndustryTypeId` means. [07: an app-owned lookup, seeded]

DISPLAY-ONLY. The id is documented as a two-digit NAICS sector; the labels come from the versioned seed
`backend/rules/lookups/industry_type.v1.json`, flagged `inferred` until the data owner confirms the ids. An id the
seed does not hold has no name (the raw id is kept by the caller), never a guess. Georgia restricts Tier 1 to
eligible industries unless the county is bottom-40 or a special zone, and the engine does not apply that rule yet:
an industry on screen changes no figure.
"""
from __future__ import annotations

from data.lookups.model import Provenance
from data.lookups.seeds import load_seed


def industry_name(industry_type_id: int | None) -> str | None:
    """The label for an id, or None; an unknown industry is not guessed."""
    seed = load_seed("industry_type")
    if industry_type_id is None or seed is None:
        return None
    try:
        return seed.entries.get(str(int(industry_type_id)))
    except (TypeError, ValueError):
        return None


def industry_provenance() -> Provenance:
    seed = load_seed("industry_type")
    if seed is None:
        return Provenance("industry_type", "none", policy="assume", note="no seed; industries show no name")
    return Provenance("industry_type", "seed", str(seed.version), seed.inferred, policy="assume")
