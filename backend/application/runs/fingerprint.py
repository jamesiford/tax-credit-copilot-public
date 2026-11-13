"""The identity of a client-year run: what decides its answer, as the manifest records it. [ADR-012]

One derivation, used twice: by the run command when it stamps a manifest, and by the run orchestrator when it
asks "would this run produce the same thing as the last one?". Two implementations would be two opinions about
what "the same" means, and the second one would be found by a batch that skipped a client it should not have.

`calculation_id` digests ONE year's payroll, but a run replays and writes every authored year, so a restated prior
year would go unseen. `source_snapshot_id` (F04b.1) is therefore a digest of ALL the client's payroll inside any
authored year's fiscal window, stored in the manifest when a run completes. Payroll outside every authored window
does not move it, because no run reads it into a figure. A manifest without it means "cannot tell, so run".
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from domain.runs import Fingerprint


_ROW_FIELDS = (
    "Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date",
    "Hours_Worked", "Gross_Wages", "Pay_Code",
)


def client_data_fingerprint(state_rows: list[dict[str, Any]], windows: list[tuple[str, str]]) -> str | None:
    """A digest of the client's payroll rows paid inside any authored year's window, independent of row order.

    None when there are no windows to judge by (nothing authored): that is "cannot tell", never a digest of nothing.
    """
    if not windows:
        return None
    lines = sorted(
        "\0".join(str(row.get(f) or "") for f in _ROW_FIELDS)
        for row in state_rows
        if any(begin <= str(row.get("Pay_Date") or "")[:10] <= end for begin, end in windows)
    )
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def authored_windows(account_id: int | None, state: str, program_code: str) -> list[tuple[str, str]]:
    """`(begin, end)` ISO dates of each authored year's fiscal window for this client, where one resolves."""
    from application.source_ports import fiscal_window_for_state_year
    from tools.credit_math import PROGRAM_CODE_TO_PACK, authored_years

    pack_file = PROGRAM_CODE_TO_PACK.get(program_code)
    out = []
    for year in authored_years(pack_file) if pack_file else []:
        window = fiscal_window_for_state_year(account_id, state, year)
        if window is not None:
            out.append((window.begin.isoformat(), window.end.isoformat()))
    return out


@dataclass(frozen=True)
class RunIdentity:
    """The manifest values every run derives from its inputs."""
    calculation_id: str
    rule_pack_version: str
    source_snapshot_id: str | None = None

    def manifest_fields(self) -> dict[str, str | None]:
        """The three values as `RunManifest` fields, so the run command adds them in one place."""
        return {"calculation_id": self.calculation_id, "rule_pack_version": self.rule_pack_version,
                "source_snapshot_id": self.source_snapshot_id}


def run_identity(run: Any, assumptions: list[dict[str, str]]) -> RunIdentity:
    """The calculation id and rule pack version for a resolved client run."""
    from tools import gold_projection as gp

    return RunIdentity(
        calculation_id=gp.calculation_id(
            client_id=run.account_id,
            program_code=run.program_code,
            tax_year=run.tax_year,
            window_begin=run.window.begin,
            window_end=run.window.end,
            floors=run.floors.as_dict(),
            assumption_ids=[a["set_id"] for a in assumptions],
            rows=run.rows,
        ),
        rule_pack_version=str(run.floors.as_dict().get("source") or ""),
        source_snapshot_id=client_data_fingerprint(
            run.state_rows, authored_windows(run.account_id, run.state, run.program_code)),
    )


def current_fingerprint(run: Any, assumptions: list[dict[str, str]], code_commit: str) -> Fingerprint:
    """What a run started now would record, without running the engine."""
    identity = run_identity(run, assumptions)
    return Fingerprint(
        calculation_id=identity.calculation_id,
        step1_assumption_sha256=assumptions[0]["sha256"] if assumptions else None,
        onezero_assumption_sha256=assumptions[1]["sha256"] if len(assumptions) > 1 else None,
        rule_pack_version=identity.rule_pack_version or None,
        code_commit=code_commit or None,
        tax_year=run.tax_year,
        source_snapshot_id=identity.source_snapshot_id,
    )


def current_assumptions() -> list[dict[str, str]]:
    """The active assumption sets with their content hashes, as a run would stamp them."""
    from application.commands.run_client_calculation import _assumption_identity

    return _assumption_identity()


def current_code_commit() -> str:
    from application.commands.run_client_calculation import _code_commit

    return _code_commit()


def manifest_fingerprint(manifest: Any | None) -> Fingerprint | None:
    """The fingerprint recorded on a manifest, or None when there is no earlier run."""
    if manifest is None:
        return None
    return Fingerprint(
        calculation_id=manifest.calculation_id or None,
        step1_assumption_sha256=manifest.step1_assumption_sha256 or None,
        onezero_assumption_sha256=manifest.onezero_assumption_sha256 or None,
        rule_pack_version=manifest.rule_pack_version or None,
        code_commit=manifest.code_commit or None,
        tax_year=manifest.tax_year,
        source_snapshot_id=getattr(manifest, "source_snapshot_id", None) or None,
    )
