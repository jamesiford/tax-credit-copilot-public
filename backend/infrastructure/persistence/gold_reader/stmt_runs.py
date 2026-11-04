"""Which run is live for a client, and whether one is still in flight."""
from __future__ import annotations

from infrastructure.persistence.fabric_warehouse import OPS_SCHEMA, STRANDED_RUN_MINUTES
from infrastructure.persistence.gold_reader.columns import Statement


_MANIFEST_COLUMNS: tuple[str, ...] = (
    "run_id", "client_id", "program_code", "tax_year", "fiscal_year_begin",
    "fiscal_year_end", "step1_assumption_set_id", "onezero_assumption_set_id",
    "rule_pack_version", "code_commit", "calculation_id", "run_started_at",
    "run_completed_at", "run_status", "superseded_by_run_id", "triggered_by",
)


def _stmt_latest_run(client_id: int) -> Statement:
    """The live run for a CLIENT. Deliberately not narrowed by tax year.

    A run writes every year the payroll covers, so `run_manifest.tax_year` is
    the year the run was COMMANDED for, not the set of years it produced.
    Filtering on it made a client's other years read as `not_calculated` while
    their rows sat in Gold. Supersession already answers "which run is current",
    and it answers it per client.

    The year belongs on the `tcc_gold` read instead, where `tax_year` and
    `is_current` already live.
    """
    return (
        f"SELECT TOP 1 {', '.join(_MANIFEST_COLUMNS)} FROM {OPS_SCHEMA}.run_manifest "
        f"WHERE client_id = ? AND run_status = 'success' "
        f"AND superseded_by_run_id IS NULL AND run_completed_at IS NOT NULL "
        f"ORDER BY run_started_at DESC",
        [client_id],
    )


def _stmt_run_in_flight(client_id: int) -> Statement:
    # The age guard is what stops a process that died mid-run from advertising
    # itself as in flight forever. The reaper closes those rows durably, but a
    # run can strand at any moment and the next read must not repeat the lie.
    return (
        f"SELECT TOP 1 run_id, run_started_at, triggered_by, tax_year "
        f"FROM {OPS_SCHEMA}.run_manifest "
        f"WHERE client_id = ? AND run_completed_at IS NULL "
        f"AND run_status = 'running' "
        f"AND run_started_at >= DATEADD(minute, ?, SYSUTCDATETIME()) "
        f"ORDER BY run_started_at DESC",
        [client_id, -abs(STRANDED_RUN_MINUTES)],
    )
