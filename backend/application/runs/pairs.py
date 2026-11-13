"""Which programs each client is run for: one item per (client, program). [ADR-012, F04b.4]

A client with payroll in several states that each have a calculable program must be assessed for each, not only for
the first in registry order. The set is derived from the client book's footprint (one read of the states each
client holds payroll in, the same source the portfolio page uses) and the registry, with no payroll scan.

A client with no calculable program gets a single item with no program: the executor then declines it with the reason,
exactly as before. When the footprint cannot be read the planner does the same for every client rather than guess.
"""
from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

log = logging.getLogger("tcc.runs")


def _footprint() -> Mapping[int, list[str]]:
    from application.source_ports import new_source_reader

    return new_source_reader().footprint()


def calculable_programs() -> list[tuple[str, str]]:
    """`(state, program_code)` for every active registry program that has an authored year pack, in registry order."""
    from tools.credit_math import authored_years
    from tools.program_registry import load_registry

    return [(e.state, e.code) for e in load_registry().active() if e.state and authored_years(e.pack_file)]


def programs_by_client(
    ids: Iterable[int], footprint: Callable[[], Mapping[int, list[str]]] | None = None,
) -> dict[int, tuple[str, ...]]:
    """Calculable program codes per client, in registry order. A client with none, or an unreadable footprint, is absent."""
    try:
        held = (footprint or _footprint)()
    except Exception as exc:  # noqa: BLE001 - an unreadable footprint means "cannot tell": every client keeps one program-less item
        log.warning("could not read the client footprint (%s); planning one item per client", type(exc).__name__)
        return {}
    options = calculable_programs()
    out: dict[int, tuple[str, ...]] = {}
    for client_id in ids:
        states = {s.upper() for s in held.get(client_id) or []}
        codes = tuple(code for state, code in options if state in states)
        if codes:
            out[client_id] = codes
    return out


def client_pairs(
    ids: tuple[int, ...], program_code: str | None, footprint: Callable[[], Mapping[int, list[str]]] | None = None,
) -> list[tuple[int, str | None]]:
    """The `(client, program)` pairs a batch runs: the named program for everyone, else each client's calculable programs."""
    if program_code:
        return [(i, program_code) for i in ids]
    found = programs_by_client(ids, footprint)
    return [(i, code) for i in ids for code in (found.get(i) or (None,))]


def pair_summary(pairs: list[tuple[int, str | None]]) -> dict[str, Any]:
    """How many pairs per program, and how many clients are run for more than one program."""
    per_program: dict[str, int] = {}
    per_client: dict[int, int] = {}
    for client_id, code in pairs:
        per_program[code or "none"] = per_program.get(code or "none", 0) + 1
        per_client[client_id] = per_client.get(client_id, 0) + 1
    return {"programs": per_program, "multi_program_clients": sum(1 for n in per_client.values() if n > 1)}
