"""[L4] CALC-10 — negotiated-incentive wage-standard overrides.

Some incentives are NEGOTIATED, not statutory: an agreement might require
"create 100 jobs paying an average of $18/hr" — a wage standard and minimum
that come from the contract, not the rule pack. The live example is a Tractor
Supply New York deal whose wage base is written into the agreement.

This is a service, not a route. It was previously `api/negotiated.py`, which
put a mutable calculation input behind an HTTP surface that nothing in the
portal ever called — the writer was reachable only by hand. The resolver stays
because the One/Zero engine depends on it; the router is gone.

`register_override` is the seam a real agreement store plugs into. Until one
exists the store is empty, so `resolve_override` returns `None` and the
statutory pack values stand unaltered.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

#: key = "STATE" or "STATE:WORKSITE_ID" -> override dict
_OVERRIDES: dict[str, dict[str, Any]] = {}


def _key(state: str, worksite: str | None) -> str:
    return f"{state.upper()}:{worksite}" if worksite else state.upper()


def resolve_override(state: str, worksite: str | None = None) -> dict[str, Any] | None:
    """[L4] Return the negotiated override for a state (worksite-specific wins).

    Used by the One/Zero route to prefer a negotiated wage standard + minimum
    over the statutory pack values. Worksite-specific overrides take precedence
    over state-wide ones.
    """
    su = state.upper()
    if worksite and _key(su, worksite) in _OVERRIDES:
        return _OVERRIDES[_key(su, worksite)]
    return _OVERRIDES.get(su)


def register_override(
    state: str,
    *,
    worksite_id: str | None = None,
    wage_standard_weekly: float | None = None,
    min_jobs: float | None = None,
    source: str = "self_service",
    effective_years: int | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """[L4] CALC-10 — record a negotiated override.

    `source` is `self_service` when a client operator enters their own
    agreement terms, or `agreement` when compliance supplies them from the
    signed deal. The distinction is recorded so the calculation trail shows
    which negotiated number was applied and where it came from.
    """
    if wage_standard_weekly is None and min_jobs is None:
        raise ValueError("provide wage_standard_weekly and/or min_jobs")
    if source not in ("self_service", "agreement"):
        raise ValueError("source must be self_service or agreement")

    record = {
        "_roadmap_tag": "L4",
        "_story": "CALC-10",
        "_disc_ref": "DISC-13",
        "state": state.upper(),
        "worksite_id": worksite_id,
        "wage_standard_weekly": wage_standard_weekly,
        "min_jobs": min_jobs,
        "source": source,
        "effective_years": effective_years,
        "note": note,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    _OVERRIDES[_key(state, worksite_id)] = record
    return record


def list_overrides() -> dict[str, dict[str, Any]]:
    """[L4] Every override currently on file, keyed by state or state:worksite."""
    return dict(_OVERRIDES)


def _reset_for_tests() -> None:
    """Test hook — clear the in-memory store."""
    _OVERRIDES.clear()
