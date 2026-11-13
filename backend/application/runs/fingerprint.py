"""The identity of a client-year run: what decides its answer, as the manifest records it. [ADR-012]

One derivation, used twice: by the run command when it stamps a manifest, and by the run orchestrator when it
asks "would this run produce the same thing as the last one?". Two implementations would be two opinions about
what "the same" means, and the second one would be found by a batch that skipped a client it should not have.

`source_snapshot_id` is deliberately absent: nothing populates it, so it cannot say anything about the data.
`calculation_id` digests the year's payroll rows (identifying and monetary fields), the floors and the
assumption ids, which is why it can stand in for a data version.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domain.runs import Fingerprint


@dataclass(frozen=True)
class RunIdentity:
    """The two manifest values every run derives from its inputs."""
    calculation_id: str
    rule_pack_version: str


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
    )
