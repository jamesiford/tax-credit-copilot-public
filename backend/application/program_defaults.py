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
        return derived
    message = (
        f"no state given and none could be derived for client {client_id} (payroll states {states or 'unknown'}); "
        f"falling back to {DEPRECATED_DEFAULT_STATE!r}. This default is deprecated: pass state explicitly."
    )
    warnings.warn(message, DeprecationWarning, stacklevel=2)
    logger.warning(message)
    return DEPRECATED_DEFAULT_STATE


def program_code_for_state(state: str) -> str | None:
    """The code of the program a state maps to in the registry, or None."""
    from tools.credit_math import PROGRAM_CODE_TO_PACK, STATE_TO_PACK

    pack_file = STATE_TO_PACK.get(state.upper())
    return next((code for code, name in PROGRAM_CODE_TO_PACK.items() if name == pack_file), None)
