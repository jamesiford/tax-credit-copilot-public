"""[L2] CALC-08 — detect designation changes that spawn parallel calculations.

When a Georgia location's designation changes between the base year and the
analysis year AND the location created net-new jobs, two analyses run for that
location at once: the surviving jobs continue under their original designation's
tranches, while the new net-new is tested under the new designation's minimum.

This tool reads the synthetic designation registry (`data/designations.py`) and
flags such locations, emitting the two parallel "calc streams" as metadata.
Pure tool — records into the calculation trail; the credit math itself is the
existing One/Zero engine (the exact two-stream credit split needs the GA form,
DISC-10).
"""
from __future__ import annotations

from typing import Any

from data.designations import all_designations, disc_meta
from domain.calculation.trail import current_recorder


def detect_designation_splits(state: str, tax_year: int, base_year: int = 2021) -> dict[str, Any]:
    """[L2] Return per-worksite designation timelines for `state`, flagging the
    sites whose designation changed between `base_year` and `tax_year` (a
    parallel-calc trigger).
    """
    state_u = state.upper()
    sites: list[dict[str, Any]] = []
    split_count = 0
    for wsid, history in sorted(all_designations().items()):
        if not wsid.startswith(f"{state_u}_"):
            continue
        base = next((h for h in history if h["year"] <= base_year), history[0] if history else None)
        current = next((h for h in reversed(history) if h["year"] <= tax_year), None)
        changed = bool(base and current and base["designation"] != current["designation"])
        parallel_calcs: list[dict[str, Any]] = []
        if changed:
            split_count += 1
            parallel_calcs = [
                {
                    "stream": "surviving_base_designation",
                    "designation": base["designation"],
                    "tier": base["tier"],
                    "min_new_jobs": base["min_new_jobs"],
                    "window": [base_year, tax_year],
                    "note": "Jobs created under the original designation continue their tranches.",
                },
                {
                    "stream": "new_designation_net_new",
                    "designation": current["designation"],
                    "tier": current["tier"],
                    "min_new_jobs": current["min_new_jobs"],
                    "window": [tax_year, tax_year + 4],
                    "note": "Net-new created in the change year is a separate analysis under the new minimum.",
                },
            ]
        sites.append({
            "worksite_id": wsid,
            "base_designation": base,
            "current_designation": current,
            "designation_changed": changed,
            "parallel_calcs": parallel_calcs,
        })

    recorder = current_recorder()
    if recorder is not None:
        recorder.record(
            step=f"{state_u}: detect designation changes ({base_year}->{tax_year})",
            inputs={"sites": len(sites)},
            formula="flag site where designation(base_year) != designation(tax_year)",
            output={"parallel_calc_sites": split_count},
            citation=f"GA designation-change parallel-calc rule (pending GA form — {disc_meta()['_disc_ref']})",
        )

    return {
        "_roadmap_tag": "L2",
        "_story": "CALC-08",
        **disc_meta(),
        "state": state_u,
        "tax_year": tax_year,
        "base_year": base_year,
        "site_count": len(sites),
        "parallel_calc_site_count": split_count,
        "sites": sites,
    }
