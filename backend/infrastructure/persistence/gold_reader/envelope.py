"""The provenance block above every Gold-read screen."""
from __future__ import annotations

from typing import Any



def run_envelope(
    run: dict[str, Any] | None,
    in_flight: dict[str, Any] | None,
    *,
    has_rows: bool = True,
) -> dict[str, Any]:
    """The provenance block every screen shows above its figures.

    `produced_at` answers "when was this true"; `in_flight` answers "is a newer
    answer coming". A figure with neither is a number with no date on it.

    `has_rows` is what keeps the year honest. The run is resolved per client, so
    a client with any current run would otherwise report every year as
    calculated — including years its payroll never covered. Candle Bottle holds
    TY2023 only, and its TY2024 must still say nobody has looked.
    """
    calculated = bool(run) and has_rows
    return {
        "calculation_state": "calculated" if calculated else "not_calculated",
        "run": {
            "run_id": run["run_id"],
            "produced_at": run["run_completed_at"],
            "started_at": run["run_started_at"],
            "calculation_id": run["calculation_id"],
            "code_commit": run["code_commit"],
            "rule_pack_version": run["rule_pack_version"],
            "step1_assumption_set_id": run["step1_assumption_set_id"],
            "onezero_assumption_set_id": run["onezero_assumption_set_id"],
            "triggered_by": run["triggered_by"],
            # What the run was ASKED FOR. Provenance, not the set of years it
            # produced — see `_stmt_latest_run`.
            "tax_year": run["tax_year"],
            "program_code": run["program_code"],
        } if run else None,
        "newer_run_in_flight": bool(in_flight),
        "in_flight": in_flight,
        "message": None if calculated else (
            "Not yet calculated. Run the calculation to see figures."
        ),
    }
