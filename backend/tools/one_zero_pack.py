"""Build a `OneZeroPack` (the eligibility floors) from a rule pack document. [ADR-013, F05]

The one place the pack's `one_zero` block becomes the engine's parameters. `credit_math.load_pack_one_zero` calls it after
resolving the year and applying any ingested overlay; the portal's draft preview calls it on a document held in memory. Two
copies of this mapping would be two readings of the same statute.
"""
from __future__ import annotations

from typing import Any

from domain.calculation.onezero import OneZeroMethodology, OneZeroPack


def build_one_zero_pack(
    pack: dict[str, Any], resolved: dict[str, Any], pay_codes: tuple[Any, Any], tax_year: int | None,
) -> OneZeroPack:
    """`resolved` is the pack's `one_zero` block after any year overlay; `pay_codes` is `(included, excluded)` or None each."""
    oz = pack["one_zero"]
    included, excluded = pay_codes
    pt_band = resolved.get("pt_band_hours")
    pt_weight = resolved.get("pt_weight")
    return OneZeroPack(
        min_weekly_hours=float(resolved["min_weekly_hours"]),
        min_weekly_wages=float(resolved.get("min_weekly_wages", 0.0)),
        wage_basis=str(resolved.get("wage_basis", oz.get("wage_basis", "regular"))),
        geographic_granularity=str(oz.get("geographic_granularity", "unit")),
        pt_aggregation=bool(oz.get("pt_aggregation", False)),
        headcount_unit_field=str(oz.get("headcount_unit_field", "Worksite_ID")),
        citation=str(pack.get("credit", {}).get("statutory_citation", "")),
        pt_band_hours=(float(pt_band[0]), float(pt_band[1])) if pt_band else None,   # [H2]
        pt_weight=float(pt_weight) if pt_weight else None,                           # [H2]
        measuring_date=str(resolved.get("measuring_date", oz.get("measuring_date", "last_day"))),  # [H3]
        entity_combination=str(oz.get("entity_combination", "permitted")),           # [I2]
        included_pay_codes=tuple(included) if included else None,                    # [L5]
        excluded_pay_codes=tuple(excluded) if excluded else None,                    # [L5]
        tax_year=tax_year,
        # Optional `methodology` block; absent means the certified v7 defaults, so existing packs need no edit.
        methodology=OneZeroMethodology.from_pack_json(oz.get("methodology")),
    )


def pack_from_document(pack: dict[str, Any], tax_year: int | None) -> OneZeroPack:
    """The parameters a year-resolved document carries, as the engine reads a materialised year pack (no overlays)."""
    oz = pack["one_zero"]
    policy = oz.get("pay_code_policy") or {}
    return build_one_zero_pack(pack, dict(oz), (policy.get("included_pay_codes"), policy.get("excluded_pay_codes")), tax_year)
