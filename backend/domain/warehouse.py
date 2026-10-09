"""Run provenance — the record of which calculation produced a figure.

A figure that lands on a filed return has to be reproducible years later against
the exact inputs, statute and code that produced it. The manifest is that
record: one row per run, naming the client-year it answered, the assumption sets
and rule pack it applied, and the commit that executed it.

The port is named for a capability, not for a database [ADR-002]. Implementations
live in `infrastructure/persistence/`; nothing above this layer may import
`pyodbc`. The domain never learns that the store is a warehouse.

Scope note: this declares WRITE and identity-read only. The query methods the
screens will need (latest non-superseded run for a client-year, and the Gold
tables it points at) arrive with the write path, not before — a port method with
no implementation behind it is a promise the caller cannot tell from a fact.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

#: `run_status` domain. The DDL records this as CONSTRAINT INTENT only, because
#: Fabric Warehouse accepts `CHECK` syntactically and does not enforce it. This
#: set is therefore the only place the values are actually policed.
#:
#: `running` is what makes an unfinished run visible. The manifest is written
#: when a run STARTS, so a run that dies without cleaning up stays `running`
#: with no completion stamp rather than claiming success it never reached.
RUN_STATUSES = frozenset({"running", "success", "failed", "superseded"})


@dataclass(frozen=True)
class RunManifest:
    """One calculation run, as `tcc_ops.run_manifest` stores it.

    Field names and nullability mirror the deployed DDL column for column, so a
    reader can hold this next to `docs/data/schema/tcc-schema.fabric.sql` and
    check them off. Renaming anything here means renaming a column there.
    """

    run_id: str
    client_id: int
    program_code: str
    tax_year: int
    fiscal_year_begin: date
    fiscal_year_end: date
    run_started_at: datetime
    run_status: str
    entity_id: int | None = None
    source_snapshot_id: str | None = None
    step1_assumption_set_id: str | None = None
    step1_assumption_sha256: str | None = None
    onezero_assumption_set_id: str | None = None
    onezero_assumption_sha256: str | None = None
    rule_pack_version: str | None = None
    code_commit: str | None = None
    calculation_id: str | None = None
    run_completed_at: datetime | None = None
    superseded_by_run_id: str | None = None
    triggered_by: str | None = None

    def __post_init__(self) -> None:
        if self.run_status not in RUN_STATUSES:
            raise ValueError(
                f"run_status={self.run_status!r} is not one of "
                f"{sorted(RUN_STATUSES)}. The warehouse will accept any string — "
                f"it does not enforce the constraint — so an unrecognised status "
                f"would sit in the manifest looking authoritative."
            )
        if self.fiscal_year_end <= self.fiscal_year_begin:
            raise ValueError(
                f"fiscal window {self.fiscal_year_begin}..{self.fiscal_year_end} "
                f"ends on or before it begins."
            )


class RunManifestRepository(Protocol):
    """The port. Implementations live in `infrastructure/`.

    `record` is append-only by design. A rerun does not overwrite its
    predecessor; it supersedes it, because the superseded figures may already be
    on a filed return.
    """

    def record(self, manifest: RunManifest) -> RunManifest:
        """Append one run. Returns what was stored."""

    def get(self, run_id: str) -> RunManifest | None:
        """One run by id, or None if it was never recorded."""

    def latest(self, client_id: int, *, program_code: str | None = None) -> RunManifest | None:
        """The live run for a client, or None if it has never been calculated.

        Live means `run_status = 'success'` and not yet superseded. None is a
        real answer — "not yet calculated" — and callers must not render it as
        a zero.
        """

    def count(self) -> int:
        """How many runs are recorded. The cheapest proof the store is reachable."""


# --- WI-21: a human-chosen base year ------------------------------------------

#: `tcc_ops.manual_override.scope` values the DDL declares (CONSTRAINT INTENT).
OVERRIDE_SCOPES = frozenset({"employee", "record", "unit"})


@dataclass(frozen=True)
class ManualOverride:
    """One human adjustment, as `tcc_ops.manual_override` records it.

    ADDITIVE, never destructive (DDL 4.2): the run that preceded it stays in
    Gold, so the machine result and the human one are both visible. Append-only
    too: clearing a base year is a new row whose `value_after` is None, never a
    delete, so the history of who chose what survives.
    """

    override_id: str
    run_id: str
    client_id: int
    scope: str
    target_key: str
    field_changed: str
    value_before: str | None
    value_after: str | None
    reason_code: str | None
    justification_text: str | None
    created_by: str
    created_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.scope not in OVERRIDE_SCOPES:
            raise ValueError(f"scope must be one of {sorted(OVERRIDE_SCOPES)}, got {self.scope!r}")


def base_year_key(program_code: str, worksite_id: str) -> str:
    """`target_key` for a location's base year: `GA_JTC:GA_GA-010`."""
    return f"{program_code}:{worksite_id}"


class ManualOverrideRepository(Protocol):
    """Where human adjustments are recorded. Append-only."""

    is_durable: bool

    def record(self, override: ManualOverride) -> ManualOverride:
        """Append one adjustment."""

    def base_years(self, client_id: int, program_code: str) -> dict[str, int]:
        """The base year currently chosen per location. Latest row wins; a row
        whose `value_after` is None means the choice was cleared."""

    def history(self, client_id: int) -> list[ManualOverride]:
        """Every adjustment for a client, oldest first."""
