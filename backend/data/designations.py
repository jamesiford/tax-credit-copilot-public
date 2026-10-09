"""[L2] CALC-08 — Georgia county/designation history per worksite.

The partner (June 11): a Georgia location's tier/designation can change year to year,
and when a designation change coincides with net-new job creation you run TWO
concurrent calcs for the same location — each designation is its own analysis,
each with its own minimum-new-jobs threshold and benefit window.

> "If last year it was a tier one bottom 40, and this year it's a tier one but I
>  create enough jobs to trigger new jobs under a tier one, I'm running a whole
>  separate calculation. Each designation has to be its own analysis." — the partner

This registry is a synthetic first cut (one GA site changes designation mid-
window) so we can show the partner the structure; the exact GA tier rules + minimums
need the GA Job Tax Credit form (DISC-10). Tier → minimum-new-jobs mapping
follows the publicly documented GA pattern (Tier 1 = 2, Tier 2 = 10,
Tier 3 = 15, Tier 4 = 25) and is flagged for SME verification.

Registry shape: worksite_id -> [{year, tier, designation, min_new_jobs}].
"""
from __future__ import annotations

from typing import Any

_PROTOTYPE_VERIFY = True
_DISC_REF = "DISC-10"

# Tier → statutory minimum-new-jobs (publicly documented GA pattern; verify).
TIER_MIN_JOBS = {1: 2, 2: 10, 3: 15, 4: 25}

# Per-worksite designation timeline. Most GA sites are stable Tier 1; GA_MAC_OPS
# is re-designated for 2025 (a tier change that, combined with net-new jobs,
# spawns a parallel calc) so the L2 concept is demonstrable.
_DESIGNATION_HISTORY: dict[str, list[dict[str, Any]]] = {
    "GA_ATL_HQ": [
        {"year": 2021, "tier": 1, "designation": "Tier 1 — Standard", "min_new_jobs": 2},
        {"year": 2025, "tier": 1, "designation": "Tier 1 — Standard", "min_new_jobs": 2},
    ],
    "GA_SAV_DC": [
        {"year": 2021, "tier": 1, "designation": "Tier 1 — Standard", "min_new_jobs": 2},
        {"year": 2025, "tier": 1, "designation": "Tier 1 — Standard", "min_new_jobs": 2},
    ],
    "GA_MAC_OPS": [
        {"year": 2021, "tier": 2, "designation": "Tier 2 — Less Developed Census Tract", "min_new_jobs": 10},
        # 2025 re-designation: county moves to Tier 1 (lower minimum). A net-new
        # year under the NEW designation runs a separate analysis from the
        # surviving Tier 2 tranches.
        {"year": 2025, "tier": 1, "designation": "Tier 1 — Standard", "min_new_jobs": 2},
    ],
    "GA_CUM_OPS": [
        {"year": 2021, "tier": 1, "designation": "Tier 1 — Standard", "min_new_jobs": 2},
        {"year": 2025, "tier": 1, "designation": "Tier 1 — Standard", "min_new_jobs": 2},
    ],
}

# --- Source-schema units (WI-17, 24 Sep) ------------------------------------
#
# The partner's "golden report": "Each tax year has its own designation... T1, T1,
# T1B40, T1." Codes are the ones the partner uses: T1, T1 B40, T2..T4, plus MZ (military
# zone), OZ (opportunity zone) and LDCT (less developed census tract).
#
# DISPLAY-ONLY FOR 1 OCTOBER, and deliberately so. In the partner's rules designation
# changes eligibility (retailers qualify only in T1 B40) and the minimum (T2 =
# 10, T3 = 15, T4 = 25). The engine applies neither. Every synthetic location is
# therefore kept on T1 or T1 B40, whose two-job minimum equals the rule pack's,
# so a registry entry cannot move a figure. `test_designations.py` fails if one
# ever would. Wiring designation into eligibility is the first post-demo item.

#: Clients 2000+ are generated (synth.py). Their Georgia locations sit on T1
#: unless a story below says otherwise.
_SYNTHETIC_GA_DEFAULT = [
    {"year": 2020, "tier": 1, "designation": "T1", "min_new_jobs": 2},
]

_SOURCE_DESIGNATIONS: dict[tuple[int, str], list[dict[str, Any]]] = {
    # WI-18. Cascade is a retailer — the partner's own example. GA-013 created about
    # seven jobs in TY2021 and held them, and TY2021 was a bottom-40 year:
    # "We created jobs, but we're in the wrong tier... no — in this year you
    # were in an eligible tier." Not GA-016 or GA-007, which carry WI-11.
    (2001, "GA_GA-013"): [
        {"year": 2020, "tier": 1, "designation": "T1", "min_new_jobs": 2},
        {"year": 2021, "tier": 1, "designation": "T1 B40", "min_new_jobs": 2},
        {"year": 2022, "tier": 1, "designation": "T1", "min_new_jobs": 2},
    ],
}


def _is_synthetic(client_id: int) -> bool:
    return int(client_id) >= 2000


def designation_history(worksite_id: str, client_id: int | None = None) -> list[dict[str, Any]]:
    """The designation timeline for a location, oldest first.

    With a `client_id` this reads the source-schema registry, keyed by client
    AND unit, because source unit ids repeat across clients: every synthetic
    client has a `GA_GA-001`, and a registry keyed on the id alone would hand
    one client's designation to another. Without one it reads the legacy
    worksite registry.
    """
    if client_id is not None:
        key = (int(client_id), worksite_id)
        if key in _SOURCE_DESIGNATIONS:
            return [dict(d) for d in _SOURCE_DESIGNATIONS[key]]
        if _is_synthetic(client_id) and worksite_id.startswith("GA_"):
            return [dict(d) for d in _SYNTHETIC_GA_DEFAULT]
        # A real client's designation is a fact we do not hold. Unassigned is
        # the honest answer; a guessed tier would move its minimum.
        return []
    return list(_DESIGNATION_HISTORY.get(worksite_id, []))


def all_designations() -> dict[str, list[dict[str, Any]]]:
    return {k: list(v) for k, v in _DESIGNATION_HISTORY.items()}


def disc_meta() -> dict[str, Any]:
    return {"_prototype_verify": _PROTOTYPE_VERIFY, "_disc_ref": _DISC_REF}
