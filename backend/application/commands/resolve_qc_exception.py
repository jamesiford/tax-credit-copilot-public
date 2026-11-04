"""Record a human resolution for a QC exception (accept / drop / flag / assign / reopen).

A command: a `drop` or an `assign` flows into the calculation through
`application.qc_resolutions.apply_calc_drops`, so it changes a number. It declares no
policy because the route is withheld from the channel agent at the edge
(`AGENT_FORBIDDEN_WRITES`) and stays person-only; the named exception is recorded in
`test_every_registered_command_declares_a_policy_or_is_named_open`.
In-memory: it resets on restart, and production persists to the audit store.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from application.mediator import Command
from application.qc_resolutions import QC_RESOLUTIONS


@dataclass(frozen=True)
class ResolveQcExceptionCommand(Command):
    """`reopen` withdraws a resolution; `keep_worksite` is the unit that owns the head for `assign`."""

    exception_id: str = ""
    resolution: str = "accept"
    keep_worksite: str | None = None
    note: str | None = None


def handle_resolve_qc_exception(command: ResolveQcExceptionCommand) -> dict[str, Any]:
    if command.resolution == "reopen":
        QC_RESOLUTIONS.pop(command.exception_id, None)
        return {"ok": True, "exception_id": command.exception_id, "resolution": None}
    entry = {
        "exception_id": command.exception_id,
        "resolution": command.resolution,
        "keep_worksite": command.keep_worksite,
        "note": command.note,
        "reviewer": command.actor,
        "resolved_at": date.today().isoformat(),
    }
    QC_RESOLUTIONS[command.exception_id] = entry
    return {"ok": True, "exception_id": command.exception_id, "resolution": entry}
