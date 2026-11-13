"""Which program a run is for, when the caller did not say. [ADR-013]

The run request and the run command used to default to `state="GA"`, which silently priced any client under Georgia's
statute. The state is now derived from data: the states the client's payroll holds, narrowed to the states whose
registered program has an authored year pack for the year asked (a program that cannot be priced cannot be what a run
is for). A caller that names a state is never second-guessed.

When nothing can be derived (no payroll, or no calculable program in the client's states) the old default is kept as a
deprecated fallback with a warning, so an existing caller does not break. It is the last resort, not the design.
"""
from __future__ import annotations

import logging
import warnings
from typing import Sequence

logger = logging.getLogger(__name__)

#: Deprecated: the value every run used before the state was derived. Kept so a caller that depended on it still gets it.
DEPRECATED_DEFAULT_STATE = "GA"
DEPRECATED_DEFAULT_PROGRAM = "GA_JTC"


def calculable_states(tax_year: int | None = None) -> list[str]:
    """States, in registry order, whose program has an authored year pack (for `tax_year` when given)."""
    from tools.credit_math import authored_years
    from tools.program_registry import load_registry

    out: list[str] = []
    for entry in load_registry().active():
        if not entry.state or entry.state in out:
            continue
        years = authored_years(entry.pack_file)
        if years and (tax_year is None or tax_year in years):
            out.append(entry.state)
    return out


def pick_state(client_states: Sequence[str], tax_year: int | None) -> str | None:
    """The first calculable state, in registry order, that the client holds payroll in; None when there is none."""
    held = {s.upper() for s in client_states}
    candidates = [s for s in calculable_states(tax_year) if s in held]
    if len(candidates) > 1:
        logger.info("client holds payroll in several calculable states %s; using %s. Pass state to choose.", candidates, candidates[0])
    return candidates[0] if candidates else None


def derive_run_state(client_id: int, tax_year: int | None, requested: str | None = None) -> str:
    """The state a run is for: the caller's if given, else derived from the client's payroll, else the deprecated default."""
    if requested:
        return requested.upper()
    from application.source_ports import payroll_scope

    try:
        states = list(payroll_scope(client_id).states)
    except Exception:  # noqa: BLE001 - an unreadable footprint falls back to the deprecated default, below
        logger.exception("could not read client %s payroll states", client_id)
        states = []
    derived = pick_state(states, tax_year)
    if derived is not None:
        logger.info("client %s: state derived from payroll: %s (%s)", client_id, derived, program_code_for_state(derived))
        return derived
    message = (
        f"no state given and none could be derived for client {client_id} (payroll states {states or 'unknown'}); "
        f"falling back to {DEPRECATED_DEFAULT_STATE!r} ({DEPRECATED_DEFAULT_PROGRAM}). This default is deprecated: pass state explicitly."
    )
    warnings.warn(message, DeprecationWarning, stacklevel=2)
    logger.warning(message)
    return DEPRECATED_DEFAULT_STATE


def state_for_location(client_id: int, worksite_id: str, tax_year: int | None, requested: str | None = None) -> str:
    """The state for a location-level read: the caller's, else the location's own state prefix, else derived from payroll."""
    from tools.program_registry import load_registry

    if requested:
        return requested.upper()
    prefix = worksite_id.split("_", 1)[0].upper()
    return prefix if prefix in load_registry().state_to_pack() else derive_run_state(client_id, tax_year)


def calculable_programs_for_state(state: str, tax_year: int | None = None) -> list[str]:
    """Codes of a state's programs that have an authored year pack (for `tax_year` when given), in registry order.

    A program that cannot price the year asked cannot be what that year's run is for, which is the same narrowing
    `calculable_states` applies. When the year narrows the list to nothing the year-less list is returned, so the
    caller's own decline ("year not authored") names a real program instead of "no program". [F04c.2]
    """
    from tools.credit_math import authored_years
    from tools.program_registry import programs_for_state

    entries = [e for e in programs_for_state(state) if authored_years(e.pack_file)]
    for_year = [e for e in entries if tax_year is None or tax_year in authored_years(e.pack_file)]
    return [e.code for e in (for_year or entries)]


def derive_run_programs(client_id: int, tax_year: int | None) -> list[str]:
    """Every calculable program the client's payroll states hold, in registry order: the candidates `derive_run_state`
    narrows to one state. Empty when the footprint cannot be read or nothing is calculable."""
    from application.source_ports import payroll_scope
    from tools.program_registry import load_registry

    try:
        held = {s.upper() for s in payroll_scope(client_id).states}
    except Exception:  # noqa: BLE001 - an unreadable footprint means "cannot tell"
        logger.exception("could not read client %s payroll states", client_id)
        return []
    out: list[str] = []
    for entry in load_registry().active():
        if entry.state in held and entry.code in calculable_programs_for_state(entry.state, tax_year):
            out.append(entry.code)
    return out


class ProgramStateConflict(ValueError):
    """A request named a program and a state that are not the same program's. A caller error (422), not a coverage gap."""


class ProgramNotRunnable(LookupError):
    """The program exists but no run can be priced for it: it is unknown, retired, or has no state (federal). [F04c.5]"""


def check_program_state(state: str | None, program_code: str | None) -> None:
    """Raise `ProgramStateConflict` when both are given and the program's registry state is not that state."""
    if not (state and program_code):
        return
    from tools.program_registry import program_for_code

    entry = program_for_code(program_code)
    if entry is not None and entry.state and entry.state != state.upper():
        raise ProgramStateConflict(
            f"program {entry.code} is a {entry.state} program, not {state.upper()}: name the program or the state, "
            f"or make them agree"
        )


def program_state(program_code: str) -> str:
    """The state a program is priced in. Raises `ProgramNotRunnable` for an unknown, retired or federal program."""
    from tools.program_registry import program_for_code

    entry = program_for_code(program_code)
    if entry is None:
        raise ProgramNotRunnable(f"no active program has the code {program_code!r}")
    if not entry.state:
        raise ProgramNotRunnable(
            f"{entry.code} is a {entry.level} program with no state: a run prices a state's payroll rows, so "
            f"federal programs are described but not runnable"
        )
    return entry.state


def resolve_program(client_id: int | None, state: str | None, program_code: str | None, tax_year: int | None) -> tuple[str, str | None]:
    """`(state, program_code)` for a request: the program first, the state as a convenience that resolves to programs.

    An explicit program wins and fixes the state. A state alone resolves to its calculable program for the year; with
    several, the first in registry order is used (DEPRECATED, logged naming every candidate) and the caller must echo the
    chosen code. Neither given: the state is derived from payroll as before. The code is None only for a state that has
    no registered program, which the caller declines by name. [F04c.2]
    """
    if program_code:
        check_program_state(state, program_code)
        return program_state(program_code), program_code.upper()
    state = (state or derive_run_state(client_id, tax_year)).upper()
    candidates = calculable_programs_for_state(state, tax_year)
    if len(candidates) > 1:
        logger.warning(
            "state %s has several calculable programs %s; using %s. Naming a state alone is deprecated here: pass program_code.",
            state, candidates, candidates[0],
        )
    return state, (candidates[0] if candidates else program_code_for_state(state))


def program_code_for_state(state: str) -> str | None:
    """The code of the state's DEFAULT program (the first in registry order), or None. See `programs_for_state`."""
    from tools.program_registry import programs_for_state

    entries = programs_for_state(state)
    return entries[0].code if entries else None
