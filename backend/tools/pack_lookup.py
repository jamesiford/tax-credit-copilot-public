"""Which pack file a state or a program code names. [ADR-013, F04c]

A state names its DEFAULT program's pack (the first registered for it); a program code names its own, whether or not it is
its state's default; a pack's `credit.code` and a federal entry's code are found last. Kept out of `credit_math` so the
program-first resolution has one small home and `credit_math` does not grow.
"""
from __future__ import annotations

from tools.program_registry import load_registry


def pack_file_for(state_or_code: str) -> str | None:
    """The pack file for a state (its default program) or a program code; None when neither is registered.

    A state is tried first, which is safe because no program code is two letters long.
    """
    from tools.credit_math import PROGRAM_CODE_TO_PACK, STATE_TO_PACK, _load_pack

    key = (state_or_code or "").upper()
    if key in STATE_TO_PACK:
        return STATE_TO_PACK[key]
    registry = load_registry()
    entry = registry.get(key)
    if entry is not None and entry.lifecycle != "retired":
        return entry.pack_file
    # A pack whose `credit.code` is what was asked for, then federal entries (no state key, so not in either view).
    for filename in PROGRAM_CODE_TO_PACK.values():
        if _load_pack(filename).get("credit", {}).get("code") == key:
            return filename
    return next((e.pack_file for e in registry.federal() if e.code == key), None)
