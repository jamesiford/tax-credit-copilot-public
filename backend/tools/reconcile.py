"""[P1] PILOT-04 — parallel-calculation reconciliation harness.

The June 11 plan: run our One/Zero output side-by-side with the partner's Access /
Copilot calcs on the SAME data, and document row-for-row matches + discrepancies
within tolerance. The partner offered a few of their GA clients for the comparison; that real-data run happens INSIDE the partner's
environment (payroll never leaves the partner). Until then this harness runs against
a synthetic benchmark fixture so the reconciliation machinery is proven.

Pure tool — given a benchmark (the partner's numbers) and our computed numbers, emit a
per-row match/diff report within an agreed tolerance. The endpoint wires our live
engine output into it.
"""
from __future__ import annotations

from typing import Any

DEFAULT_TOLERANCE = 0.5  # Average Headcount units


def reconcile(
    benchmark: list[dict[str, Any]],
    computed: list[dict[str, Any]],
    *,
    key: str = "key",
    value: str = "average_headcount",
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    """Row-for-row reconcile a benchmark against computed values.

    Each row carries a `key` (e.g. state or worksite) and a `value`
    (Average Headcount). Returns per-row {benchmark, computed, diff, status}
    where status ∈ {match, within_tolerance, mismatch, missing_computed,
    missing_benchmark} plus a summary.
    """
    comp_by_key = {str(r[key]): float(r[value]) for r in computed if key in r and value in r}
    bench_by_key = {str(r[key]): float(r[value]) for r in benchmark if key in r and value in r}

    rows: list[dict[str, Any]] = []
    matches = within = mismatches = 0
    for k in sorted(set(bench_by_key) | set(comp_by_key)):
        b = bench_by_key.get(k)
        c = comp_by_key.get(k)
        if b is None:
            rows.append({"key": k, "benchmark": None, "computed": c, "diff": None, "status": "missing_benchmark"})
            continue
        if c is None:
            rows.append({"key": k, "benchmark": b, "computed": None, "diff": None, "status": "missing_computed"})
            continue
        diff = round(c - b, 4)
        if abs(diff) < 1e-9:
            status = "match"
            matches += 1
        elif abs(diff) <= tolerance:
            status = "within_tolerance"
            within += 1
        else:
            status = "mismatch"
            mismatches += 1
        rows.append({"key": k, "benchmark": b, "computed": c, "diff": diff, "status": status})

    return {
        "_roadmap_tag": "P1",
        "_story": "PILOT-04",
        "tolerance": tolerance,
        "rows": rows,
        "summary": {
            "row_count": len(rows),
            "exact_matches": matches,
            "within_tolerance": within,
            "mismatches": mismatches,
            "reconciled": mismatches == 0
            and not any(r["status"].startswith("missing") for r in rows),
        },
    }
