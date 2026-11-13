"""Base classes that make a pyodbc test double refuse what the real driver refuses.

Why this exists: the footprint guard once set `cursor.timeout = 20`. A real
`pyodbc.Cursor` has no such attribute (the timeout belongs to the CONNECTION), but
the hand-written double accepted any assignment, so every test passed while every
live read returned 500. A double that is looser than the library proves nothing
about the code that talks to the library.

What is modelled, from the installed driver's own surface (the test in
`test_driver_fidelity.py` compares these sets with `dir(pyodbc.Cursor)` and
`dir(pyodbc.Connection)` when pyodbc is importable):

- a cursor accepts writes only to `arraysize`, `fast_executemany`, `noscan` and
  `messages`; `description`, `rowcount` and `connection` are read-only;
- a connection accepts writes only to `autocommit` and `timeout`; `closed`,
  `maxwrite` and `searchescape` are read-only;
- names that start with an underscore are the double's own bookkeeping and are free.

A double exposes what a test needs to observe through underscore attributes and
read-only properties, never through a public attribute the real class lacks.
"""

from __future__ import annotations

from typing import Any

CURSOR_WRITABLE = frozenset({"arraysize", "fast_executemany", "noscan", "messages"})
CURSOR_READ_ONLY = frozenset({"description", "rowcount", "connection"})
CONNECTION_WRITABLE = frozenset({"autocommit", "timeout"})
CONNECTION_READ_ONLY = frozenset({"closed", "maxwrite", "searchescape"})


def _refuse(owner: object, name: str, real: str) -> None:
    raise AttributeError(f"'{real}' object has no writable attribute '{name}' (the double matches the driver)")


class PyodbcCursorModel:
    """Subclass this; set `_description` and `_rowcount` for the read-only properties."""

    _description: Any = None
    _rowcount: int = -1

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or name in CURSOR_WRITABLE:
            object.__setattr__(self, name, value)
            return
        _refuse(self, name, "pyodbc.Cursor")

    @property
    def description(self) -> Any:
        return self._description

    @property
    def rowcount(self) -> int:
        return self._rowcount

    def __enter__(self) -> "PyodbcCursorModel":
        return self

    def __exit__(self, *exc: object) -> None:
        close = getattr(self, "close", None)
        if close:
            close()


class PyodbcConnectionModel:
    """Subclass this; `autocommit` and `timeout` are the only public writes, `closed` is read-only."""

    _closed: bool = False
    _autocommit: bool = False
    _timeout: int = 0

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_") or name in CONNECTION_WRITABLE:
            object.__setattr__(self, name, value)
            return
        _refuse(self, name, "pyodbc.Connection")

    @property
    def closed(self) -> bool:
        return self._closed
