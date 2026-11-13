"""A fictional program pack, for the draft and catalog tests. [F05]

Every number is invented and flagged `_prototype_verify`; nothing here is law. `draft_documents` returns what a draft holds: a
base pack and its year packs, complete and non-inherited. Customer-neutral by construction.
"""
from __future__ import annotations

import copy
from typing import Any

CODE, STATE = "ZY_DRAFT_JTC", "ZY"
FLAG = {"_prototype_verify": True}


def pack(code: str = CODE, state: str = STATE, year: int | None = None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "_prototype_verification": "FICTIONAL draft for tests. Every value is invented and flagged; it is not law.",
        "rule_pack_version": "0.0.1" if year is None else f"0.0.1+ty{year}",
        "jurisdiction": {"level": "state", "code": state, "name": "Zedland Two (fictional)"},
        "credit": {"code": code, "name": f"{code} (fictional)", "statutory_citation": "Fictional Code § 0-0-0"},
        "tax_year_convention": {"label": "begins", **FLAG},
        "filing": {"window": "Fictional filing window", "cycle": "annual", **FLAG},
        "thresholds": {"minimum_new_jobs": 1, "minimum_hours_per_week_full_time": 30, **FLAG},
        "benefit": {"amount_per_qualifying_job_usd": 1200, "benefit_period_years": 3, "carryforward_years": 5, "currency": "USD", **FLAG},
        "one_zero": {
            "min_weekly_hours": 30.0, "min_weekly_wages": 400.0, "wage_basis": "regular", "geographic_granularity": "statewide",
            "pt_aggregation": False, "headcount_unit_field": "Worksite_ID", "entity_combination": "permitted", **FLAG,
            "wage_floor_basis": {"note": "invented for tests", **FLAG},
        },
    }
    if year is not None:
        doc["tax_year"] = year
        doc["_year_provenance"] = {"source": "invented for tests", "adr": "ADR-005"}
    return doc


def documents(years: tuple[int, ...] = (2024, 2025)) -> dict[str, Any]:
    """The `documents` a draft holds: `{"pack": {...}, "years": {"2024": {...}}}`."""
    return {"pack": pack(), "years": {str(y): pack(year=y) for y in years}}


def broken(docs: dict[str, Any]) -> dict[str, Any]:
    """A copy whose benefit is a percentage of wages: valid JSON, an unsupported credit model once a year is authored."""
    out = copy.deepcopy(docs)
    for doc in (out["pack"], *out["years"].values()):
        doc["benefit"] = {"amount_per_qualifying_job_pct_of_wages": 0.05, **FLAG}
    return out
