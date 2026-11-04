"""The port every data-query adapter implements, and what they share. [CH-16c]

`DataQueryExecutor.execute(sql, params, *, client_id, timeout_s, max_rows)` runs ONE built,
tenant-marked statement for ONE client and returns `Rows`. It takes `client_id` beside the
statement because the client scope is bound by `TenantScopedQuery` inside the adapter, the only
place allowed to touch a cursor; the statement itself carries a marker, never an id.

What every adapter must do, and what is shared here so they cannot differ:

- **Refuse anything but a single SELECT** (`assert_read_only`) before the statement is bound.
  The builder cannot emit anything else, so this is the second lock, not the first.
- **Fetch at most `max_rows + 1` rows** (`read_capped`). The extra row is the probe: it says the
  result was capped without a second COUNT, and is dropped.
- **A timeout is `QueryTimeout`, never a partial result.**

Standard library only; adapters live in `infrastructure/persistence/`.
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from application.data.dialect import Dialect
from application.data.exec_errors import NotReadOnly

_SELECT = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_COMMENT = re.compile(r"--|/\*")


@dataclass(frozen=True, slots=True)
class Rows:
    """A capped result: column names, the rows kept, and whether more existed beyond the cap."""

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    truncated: bool = False

    @property
    def row_count(self) -> int:
        """Rows actually returned, never counting the dropped probe row."""
        return len(self.rows)


class DataQueryExecutor(Protocol):
    """Runs a built statement read-only, for one client, within a time and row limit."""

    dialect: Dialect

    def execute(self, sql: str, params: Sequence[Any], *, client_id: int, timeout_s: float, max_rows: int) -> Rows:
        """Rows for the statement, or a typed `QueryError`; never a partial result."""
        ...


def assert_read_only(sql: str) -> None:
    """A single SELECT with no comment: the only statement shape an adapter will run.

    `;` is refused anywhere because every value is bound, so a legitimate statement has no
    reason to contain one; a comment marker is refused for the same reason.
    """
    if not isinstance(sql, str) or not _SELECT.match(sql):
        raise NotReadOnly("only a SELECT statement may be run")
    if ";" in sql or _COMMENT.search(sql):
        raise NotReadOnly("a statement may not contain ';' or a comment")


def read_capped(cursor: Any, max_rows: int) -> Rows:
    """Read up to `max_rows` rows from an executed DB-API cursor and say whether more existed."""
    columns = tuple(str(d[0]) for d in cursor.description or ())
    fetched = cursor.fetchmany(max_rows + 1)
    kept = tuple(tuple(r) for r in fetched[:max_rows])
    return Rows(columns=columns, rows=kept, truncated=len(fetched) > max_rows)
