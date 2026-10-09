"""Rolling a One/Zero matrix up to a coarser grain.

The matrix is one row per (employee, unit, segment). Every view above that -
by state, by worksite, by state and month - is an aggregation of it, and doing
those aggregations in the router is how two screens end up disagreeing about
the same total.

Presentation of a result, not part of computing one: nothing in the engine
calls these.
"""
from __future__ import annotations

from collections import defaultdict



def rollup_matrix_by_field(matrix: list[dict], field: str) -> dict[str, dict]:
    """[I1] CALC-06 — roll the One/Zero matrix up by an arbitrary grouping
    field (e.g. `Entity_FEIN` for legal-entity slicing, or `Worksite_ID`).

    Returns {field_value: {month_totals[12], total, average_headcount}}.
    Mirrors `_build_summary` math but groups by the requested field so the
    same monthly 1/0.5/0 values can be presented at unit OR legal-entity grain.
    """
    by_key: dict[str, list[float]] = defaultdict(lambda: [0.0] * 12)
    for row in matrix:
        key = row.get(field, "") or "(unattributed)"
        for m in range(12):
            by_key[key][m] += row["months"][m]
    out: dict[str, dict] = {}
    for key in sorted(by_key.keys()):
        cols = [round(c, 2) for c in by_key[key]]
        total = round(sum(cols), 2)
        out[key] = {
            "month_totals": cols,
            "total": total,
            "average_headcount": round(total / 12.0, 2),
        }
    return out


def rollup_matrix_by_two_fields(matrix: list[dict], field_a: str, field_b: str) -> list[dict]:
    """[L3] CALC-09 — roll the One/Zero matrix up by TWO grouping fields at once
    (e.g. `Worksite_ID` × `Entity_FEIN` for the per-site-per-legal-entity drill).

    The GA Job Tax Credit is a per-location test, and a single site can host
    multiple legal entities — so the credible drill is site × FEIN, not just one
    or the other. Returns a sorted list of
    {field_a, field_b, month_totals[12], total, average_headcount} so the UI can
    render one row per (site, entity) pair.
    """
    by_key: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0] * 12)
    for row in matrix:
        a = row.get(field_a, "") or "(unattributed)"
        b = row.get(field_b, "") or "(unattributed)"
        for m in range(12):
            by_key[(a, b)][m] += row["months"][m]
    out: list[dict] = []
    for (a, b) in sorted(by_key.keys()):
        cols = [round(c, 2) for c in by_key[(a, b)]]
        total = round(sum(cols), 2)
        out.append({
            field_a: a,
            field_b: b,
            "month_totals": cols,
            "total": total,
            "average_headcount": round(total / 12.0, 2),
        })
    return out
