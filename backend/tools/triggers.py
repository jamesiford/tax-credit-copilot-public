"""Trigger detection engine: diff two pay-period snapshots and emit the
opportunity flags the partner called out in the stakeholder meeting:

  - headcount_spike    -> a unit gained >= N employees year-over-year
  - wage_increase      -> a unit's avg weekly wage increased >= pct YoY
  - new_fein           -> a new Entity_FEIN appeared in the latest snapshot
  - new_jurisdiction   -> a state appeared that wasn't in the prior snapshot

This replaces the static `data/alerts.py` registry with a real diff engine.
The static alerts stay in place as the workflow-state store (ack / resolve /
snooze targets); triggers feed into that registry rather than mutating it.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any


def _aggregate(rows: list[dict], *, group_by: tuple[str, ...]) -> dict[tuple, dict]:
    """Group rows by `group_by` keys, summing hours/wages and counting employees."""
    agg: dict[tuple, dict] = {}
    for r in rows:
        key = tuple(r.get(k, "") for k in group_by)
        slot = agg.setdefault(key, {
            "employees": set(),
            "total_hours": 0.0,
            "total_wages": 0.0,
            "feins": set(),
            "states": set(),
        })
        slot["employees"].add(r["Employee_ID"])
        slot["total_hours"] += float(r.get("Hours_Worked", 0) or 0)
        slot["total_wages"] += float(r.get("Gross_Wages", 0) or 0)
        slot["feins"].add(r.get("Entity_FEIN", ""))
        # Worksite_ID is `XX_*`; first 2 chars = state.
        unit = r.get("Worksite_ID", "")
        if len(unit) >= 2:
            slot["states"].add(unit[:2])
    return agg


def detect_triggers(
    prior_rows: list[dict],
    current_rows: list[dict],
    *,
    headcount_spike_min: int = 5,
    wage_increase_min_pct: float = 0.10,
) -> list[dict[str, Any]]:
    """Return a list of trigger dicts comparing `current_rows` to `prior_rows`.

    Each trigger has:
        - type           one of headcount_spike, wage_increase, new_fein, new_jurisdiction
        - jurisdiction   state code (two letters) when applicable
        - unit           Worksite_ID when applicable
        - delta          the magnitude of the change
        - message        human-readable summary
        - severity       'high' | 'medium' | 'low'
    """
    triggers: list[dict[str, Any]] = []

    prior_by_unit = _aggregate(prior_rows, group_by=("Worksite_ID",))
    curr_by_unit = _aggregate(current_rows, group_by=("Worksite_ID",))

    # ----- headcount_spike + wage_increase per unit -----
    for unit_key, curr_slot in curr_by_unit.items():
        unit = unit_key[0]
        if not unit:
            continue
        state = unit[:2]
        prior_slot = prior_by_unit.get(unit_key)
        curr_emp = len(curr_slot["employees"])
        prior_emp = len(prior_slot["employees"]) if prior_slot else 0
        delta_emp = curr_emp - prior_emp
        if delta_emp >= headcount_spike_min:
            triggers.append({
                "type": "headcount_spike",
                "jurisdiction": state,
                "unit": unit,
                "prior_headcount": prior_emp,
                "current_headcount": curr_emp,
                "delta": delta_emp,
                "severity": "high" if delta_emp >= 10 else "medium",
                "message": (
                    f"Headcount spike at {unit}: {prior_emp} -> {curr_emp} employees "
                    f"(+{delta_emp}). Eligible for One/Zero recompute against {state} rule pack."
                ),
            })

        # Wage increase (only meaningful when prior_slot existed and had hours)
        if prior_slot and prior_slot["total_hours"] > 0 and curr_slot["total_hours"] > 0:
            prior_avg = prior_slot["total_wages"] / prior_slot["total_hours"]
            curr_avg = curr_slot["total_wages"] / curr_slot["total_hours"]
            if prior_avg > 0:
                pct = (curr_avg - prior_avg) / prior_avg
                if pct >= wage_increase_min_pct:
                    triggers.append({
                        "type": "wage_increase",
                        "jurisdiction": state,
                        "unit": unit,
                        "prior_avg_hourly": round(prior_avg, 2),
                        "current_avg_hourly": round(curr_avg, 2),
                        "delta_pct": round(pct, 3),
                        "severity": "medium",
                        "message": (
                            f"Avg hourly wage at {unit} rose from ${prior_avg:,.2f} to "
                            f"${curr_avg:,.2f} (+{pct:.1%}); may push borderline employees "
                            f"over the One/Zero weekly-wage floor."
                        ),
                    })

    # ----- new_fein -----
    prior_feins = {r.get("Entity_FEIN", "") for r in prior_rows} - {""}
    curr_feins = {r.get("Entity_FEIN", "") for r in current_rows} - {""}
    new_feins = curr_feins - prior_feins
    for fein in sorted(new_feins):
        # Find a state hint for the new FEIN.
        states = sorted({
            r.get("Worksite_ID", "")[:2]
            for r in current_rows
            if r.get("Entity_FEIN") == fein and r.get("Worksite_ID")
        })
        triggers.append({
            "type": "new_fein",
            "jurisdiction": states[0] if states else None,
            "fein": fein,
            "severity": "high",
            "message": (
                f"New legal entity FEIN {fein} appeared in {states[0] if states else 'the latest snapshot'}; "
                f"may require a new rule-pack pinning and a separate compliance filing per entity."
            ),
        })

    # ----- new_jurisdiction -----
    prior_states = {r.get("Worksite_ID", "")[:2] for r in prior_rows if len(r.get("Worksite_ID", "")) >= 2}
    curr_states = {r.get("Worksite_ID", "")[:2] for r in current_rows if len(r.get("Worksite_ID", "")) >= 2}
    new_states = curr_states - prior_states - {""}
    for st in sorted(new_states):
        triggers.append({
            "type": "new_jurisdiction",
            "jurisdiction": st,
            "severity": "high",
            "message": (
                f"New jurisdiction {st} appeared in the latest snapshot; rule-pack "
                f"discovery should evaluate any {st} state credits that may apply."
            ),
        })

    return triggers
