"""Save a location's base year, then recalculate the client (WI-21).

A write, so a command: it changes which baseline every later year's net-new is
measured from, and that lands on a filed return. It goes through the mediator
pipeline like any other write and is recorded in `tcc_ops.manual_override`,
append-only, with who chose it, when, the base it replaced and why.

The recalculation is what makes the choice real. The replay reads saved base
years (`run_client_calculation._base_year_for`), so the new run writes Gold
with `base_year_source = 'override'` and every figure measured from the chosen
year. The run it replaces stays in Gold, not current, which is how the machine
result and the human one both stay visible (DDL 4.2).

A run takes minutes, so it is started in the background and the command
returns once the choice is recorded. The grid already reads
`newer_run_in_flight` from the manifest and says a run is on its way; when it
lands, the grid re-reads. Two saves for one client while a run is going start
ONE more run afterwards, not one each: the second run reads every saved choice.

Only a complete year can be saved. A partial year makes a flattering base.
"""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from application.mediator import Command

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SetBaseYearCommand(Command):
    client_id: int = 0
    worksite_id: str = ""
    #: None clears a saved choice: the run goes back to inferring one.
    base_year: int | None = None
    state: str = "GA"
    program_code: str = "GA_JTC"
    justification: str | None = None
    #: False in tests, so the command can be checked without starting a run.
    recalculate: bool = True

    def __post_init__(self) -> None:
        if self.client_id <= 0:
            raise ValueError("client_id is required and must be positive")
        if not self.worksite_id:
            raise ValueError("worksite_id is required")
        if self.justification and len(self.justification) > 2000:
            raise ValueError("justification is limited to 2,000 characters")


class BaseYearNotAllowed(ValueError):
    """This base year cannot be saved for this location, and why."""


# One background recalculation per client at a time; a save during a run asks
# for one more afterwards rather than starting a second concurrent one.
_RUNNING: dict[int, bool] = {}
_AGAIN: dict[int, bool] = {}
_LOCK = threading.Lock()


def _recalculate_in_background(client_id: int, tax_year: int, state: str, actor: str) -> bool:
    """Start (or queue) a recalculation. True if a new thread was started."""
    with _LOCK:
        if _RUNNING.get(client_id):
            _AGAIN[client_id] = True
            return False
        _RUNNING[client_id] = True

    def work() -> None:
        from application.commands.run_client_calculation import RunClientCalculationCommand
        from application.wiring import get_mediator

        while True:
            try:
                get_mediator().send(RunClientCalculationCommand(
                    client_id=client_id, tax_year=tax_year, state=state, actor=actor,
                ))
            except Exception:  # noqa: BLE001 - logged; the manifest records the failed run
                logger.exception("base-year recalculation failed for client %s", client_id)
            with _LOCK:
                if _AGAIN.pop(client_id, False):
                    continue
                _RUNNING[client_id] = False
                return

    threading.Thread(target=work, name=f"rebase-recalc-{client_id}", daemon=True).start()
    return True


def recalculation_running(client_id: int) -> bool:
    with _LOCK:
        return bool(_RUNNING.get(client_id))


def handle_set_base_year(command: SetBaseYearCommand) -> dict[str, Any]:
    from application.queries.simulate_unit import location_series
    from application.wiring import get_gold_reader, get_override_repository, get_run_manifest_repository
    from domain.warehouse import ManualOverride, base_year_key

    reader = get_gold_reader()
    with reader.scope():
        run = reader.latest_run(command.client_id)
        items, _total = reader.unit_years(command.client_id, method="min_max", limit=5000)
    if run is None:
        raise BaseYearNotAllowed(f"account {command.client_id} has no calculated run to change")
    rows_by_year, current_base = location_series(items, command.worksite_id)
    if not rows_by_year:
        raise BaseYearNotAllowed(f"the run holds no location {command.worksite_id}")

    repo = get_override_repository()
    saved = repo.base_years(command.client_id, command.program_code).get(command.worksite_id)

    if command.base_year is not None:
        row = rows_by_year.get(command.base_year)
        if row is None:
            raise BaseYearNotAllowed(f"the run holds no TY{command.base_year} for {command.worksite_id}")
        if int(row.get("months_with_headcount") or 0) < int(row.get("months_reachable") or 12):
            raise BaseYearNotAllowed(
                f"TY{command.base_year} is a partial year at {command.worksite_id}, and a "
                f"partial year makes a flattering base"
            )
        if row.get("status") == "in_progress":
            raise BaseYearNotAllowed(
                f"TY{command.base_year} is still open at {command.worksite_id}; a base is "
                f"measured on a year that has finished"
            )
    if command.base_year == saved:
        return {"recorded": False, "reason": "unchanged", "base_year": saved, "recalculation": "not_needed"}
    if command.base_year is None and saved is None:
        return {"recorded": False, "reason": "no saved base year to clear", "recalculation": "not_needed"}

    override = ManualOverride(
        override_id=uuid.uuid4().hex,
        run_id=str(run["run_id"]),
        client_id=command.client_id,
        scope="unit",
        target_key=base_year_key(command.program_code, command.worksite_id),
        field_changed="base_year",
        value_before=str(saved if saved is not None else current_base) if (saved or current_base) else None,
        value_after=str(command.base_year) if command.base_year is not None else None,
        reason_code="base_year_set" if command.base_year is not None else "base_year_cleared",
        justification_text=command.justification,
        created_by=command.actor,
        created_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    repo.record(override)

    recalculation = "not_requested"
    if command.recalculate:
        manifest = get_run_manifest_repository().latest(command.client_id)
        tax_year = int(manifest.tax_year) if manifest is not None else max(rows_by_year)
        started = _recalculate_in_background(command.client_id, tax_year, command.state, command.actor)
        recalculation = "started" if started else "queued"

    return {
        "recorded": True,
        "override_id": override.override_id,
        "worksite_id": command.worksite_id,
        "base_year": command.base_year,
        "replaced": override.value_before,
        "recalculation": recalculation,
        "durable": bool(getattr(repo, "is_durable", False)),
        "note": (
            "Saved. The client is being recalculated from the chosen base; the grid "
            "updates when the new run lands. The previous run stays in Gold as history."
            if command.base_year is not None else
            "Cleared. The client is being recalculated with the run choosing its own base."
        ),
    }
