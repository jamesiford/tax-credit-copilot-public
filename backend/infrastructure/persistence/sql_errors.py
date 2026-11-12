"""Native SQL Server error numbers the adapters treat as expected outcomes. [09]

The Fabric Warehouse does not enforce keys, so the code checks "does this row exist" first. Azure SQL
enforces them: a race between that check and the insert surfaces as 2627 (primary key / unique
constraint) or 2601 (unique index). Those are the SAME answer the pre-check gives, so they are
reported as one deliberate error instead of leaking a driver message.
"""
from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

DUPLICATE_KEY_NUMBERS = frozenset({2627, 2601})
_NATIVE_NUMBER = re.compile(r"\((\d{3,6})\)")


class DuplicateKey(ValueError):
    """The row is already there; the store refused to hold it twice."""


def is_duplicate_key(exc: BaseException) -> bool:
    """True when the driver error carries a unique-key violation number."""
    text = " ".join(str(a) for a in getattr(exc, "args", ()) or ()) or str(exc)
    return bool({int(n) for n in _NATIVE_NUMBER.findall(text)} & DUPLICATE_KEY_NUMBERS)


@contextmanager
def duplicate_key_as(message: str) -> Iterator[None]:
    """Re-raise a unique-key violation as `DuplicateKey(message)`; anything else passes through."""
    try:
        yield
    except Exception as exc:
        if is_duplicate_key(exc):
            raise DuplicateKey(message) from exc
        raise
