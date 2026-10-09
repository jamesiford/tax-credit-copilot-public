"""Tenant-scoped SQL: the only way Warehouse statements are executed. [DATA-4]

The retired document store partitioned by tenant, so a query could not reach another client's
documents. The Warehouse has no partitions: one forgotten predicate returns
every client's rows, and the screen renders them under the wrong name. This
module replaces the partition with a rule the code cannot route around:

- **A `TenantScopedQuery` binds `client_id` itself.** A statement carries the
  marker `{tenant}` (or `{tenant:alias}`) as the FIRST term of its `WHERE` or
  `ON` clause; the helper rewrites it to `client_id = ?` and inserts the bound
  value at the right position. A statement without the marker, or with it
  anywhere but directly after `WHERE`/`ON`, is refused before it reaches a
  cursor.
- **Inserts are checked row by row.** `insert()` requires a `client_id` column
  and refuses a row for any other client, so a write cannot land on the wrong
  tenant either.
- **Crossing tenants is explicit and logged.** `tenant_exempt(reason)` is the
  one way past the rule — the portfolio matrix spans clients by design, and a
  connection keep-alive has no tenant at all. Every use logs its reason, so an
  exemption is a line someone can read rather than a predicate someone forgot.

`tests/test_architecture.py` fails the build if a Warehouse adapter calls
`execute` anywhere but here.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Iterable, Sequence

log = logging.getLogger("tcc.tenant_sql")

_MARKER = re.compile(r"\{tenant(?::([A-Za-z_][A-Za-z0-9_]*))?\}")
#: The marker must be the first term of a WHERE or ON clause.
_ANCHORED = re.compile(r"\b(WHERE|ON)\s+$", re.IGNORECASE)


class TenantScopeViolation(ValueError):
    """A statement that could return or write another client's rows."""


def _count_params(sql: str) -> int:
    """Count `?` placeholders outside string literals."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql).count("?")


class TenantScopedQuery:
    """Statements bound to ONE client. Construct per request; it holds no connection."""

    def __init__(self, client_id: int) -> None:
        if client_id is None or isinstance(client_id, bool) or not isinstance(client_id, int):
            raise TenantScopeViolation(f"client_id must be an int, got {client_id!r}")
        self.client_id = client_id

    # ------------------------------------------------------------ building

    def bind(self, sql: str, params: Sequence[Any] = ()) -> tuple[str, list[Any]]:
        """Rewrite every `{tenant}` marker and splice in the bound client_id.

        Returns the statement and its full parameter list. Raises
        `TenantScopeViolation` if there is no marker, or one is not the first
        term of a WHERE/ON clause.
        """
        markers = list(_MARKER.finditer(sql))
        if not markers:
            raise TenantScopeViolation(
                "statement has no {tenant} predicate; every tcc_ops/tcc_gold read "
                "or update must be scoped to one client:\n" + sql
            )
        given = list(params)
        expected = _count_params(_MARKER.sub("", sql))
        if len(given) != expected:
            raise TenantScopeViolation(
                f"statement takes {expected} parameter(s) besides the tenant; got {len(given)}"
            )
        out_sql: list[str] = []
        out_params: list[Any] = []
        cursor = 0
        consumed = 0
        for marker in markers:
            before = sql[cursor: marker.start()]
            if not _ANCHORED.search(sql[: marker.start()]):
                raise TenantScopeViolation(
                    "the {tenant} predicate must be the FIRST term of a WHERE or ON clause"
                )
            n = _count_params(before)
            out_params.extend(given[consumed: consumed + n])
            consumed += n
            alias = marker.group(1)
            out_sql.append(before)
            out_sql.append(f"{alias + '.' if alias else ''}client_id = ?")
            out_params.append(self.client_id)
            cursor = marker.end()
        out_sql.append(sql[cursor:])
        out_params.extend(given[consumed:])
        return "".join(out_sql), out_params

    # ----------------------------------------------------------- executing

    def execute(self, cursor: Any, sql: str, params: Sequence[Any] = ()) -> Any:
        statement, values = self.bind(sql, params)
        return cursor.execute(statement, values)

    def insert(
        self,
        cursor: Any,
        table: str,
        columns: Sequence[str],
        rows: Iterable[Sequence[Any]],
        *,
        multirow: bool = False,
    ) -> int:
        """Insert rows that all belong to this client. Returns the row count.

        `multirow=True` sends ONE `INSERT ... VALUES (...), (...)` with every
        value bound — the Gold writer's batching, which measured 24x faster than
        `executemany` on Fabric. The caller keeps the batch under the 2100
        parameter ceiling.
        """
        columns = list(columns)
        if "client_id" not in columns:
            raise TenantScopeViolation(f"insert into {table} has no client_id column")
        position = columns.index("client_id")
        batch = [list(r) for r in rows]
        for row in batch:
            if len(row) != len(columns):
                raise TenantScopeViolation(f"row has {len(row)} values for {len(columns)} columns")
            if row[position] != self.client_id:
                raise TenantScopeViolation(
                    f"refusing to write client_id={row[position]!r} under tenant {self.client_id}"
                )
        if not batch:
            return 0
        one_row = "(" + ", ".join("?" for _ in columns) + ")"
        head = f"INSERT INTO {table} ({', '.join(columns)}) VALUES "
        if multirow:
            flat = [value for row in batch for value in row]
            cursor.execute(head + ", ".join(one_row for _ in batch), flat)
        elif len(batch) == 1:
            cursor.execute(head + one_row, batch[0])
        else:
            cursor.executemany(head + one_row, batch)
        return len(batch)


class TenantExemptQuery:
    """The explicit, logged way past the tenant rule. Use `tenant_exempt(reason)`."""

    def __init__(self, reason: str) -> None:
        if not (reason or "").strip():
            raise TenantScopeViolation("a tenant exemption needs a reason")
        self.reason = reason.strip()

    def _log(self, sql: str) -> None:
        head = " ".join(sql.split())[:120]
        log.info("tenant-exempt SQL (%s): %s", self.reason, head)

    def execute(self, cursor: Any, sql: str, params: Sequence[Any] = ()) -> Any:
        self._log(sql)
        if params:
            return cursor.execute(sql, list(params))
        return cursor.execute(sql)

    def executemany(self, cursor: Any, sql: str, rows: Iterable[Sequence[Any]]) -> Any:
        self._log(sql)
        return cursor.executemany(sql, [list(r) for r in rows])


def tenant_exempt(reason: str) -> TenantExemptQuery:
    """A query that may span tenants, for the stated reason. Logged on every use."""
    return TenantExemptQuery(reason)


# --------------------------------------------------------------------------
# Write-conflict retry (Fabric snapshot isolation)
# --------------------------------------------------------------------------

#: Native error numbers meaning "another transaction changed this table first".
#: 24556 is Fabric Warehouse's snapshot-isolation update conflict; 3960 is SQL
#: Server's; 1205 is a deadlock victim. All are safe to retry from the top.
CONFLICT_ERROR_NUMBERS = frozenset({24556, 3960, 1205})
_CONFLICT_TEXT = re.compile(
    r"snapshot isolation transaction aborted|update conflict|deadlock", re.IGNORECASE
)
_NATIVE_NUMBER = re.compile(r"\((\d{3,6})\)")

MAX_ATTEMPTS = 5
_BASE_DELAY_S = 0.2
_MAX_DELAY_S = 3.2


def is_write_conflict(exc: BaseException) -> bool:
    """True when the error is a retryable write-write conflict."""
    text = " ".join(str(a) for a in getattr(exc, "args", ()) or ()) or str(exc)
    numbers = {int(n) for n in _NATIVE_NUMBER.findall(text)}
    return bool(numbers & CONFLICT_ERROR_NUMBERS) or bool(_CONFLICT_TEXT.search(text))


def run_in_transaction(
    connection: Any,
    work: Callable[[Any], Any],
    *,
    attempts: int = MAX_ATTEMPTS,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Run `work(cursor)` in ONE explicit transaction, retrying on a conflict.

    Rolls back on any failure. A write-write conflict is retried with capped
    exponential backoff, up to `attempts` tries in total; anything else is
    raised at once. The caller's statements must be safe to re-run from the
    top, which close-then-insert is: the close re-reads the live row.
    """
    previous = getattr(connection, "autocommit", False)
    connection.autocommit = False
    try:
        for attempt in range(1, attempts + 1):
            cursor = connection.cursor()
            try:
                result = work(cursor)
                connection.commit()
                return result
            except Exception as exc:  # noqa: BLE001 - classified below
                try:
                    connection.rollback()
                except Exception:  # noqa: BLE001 - the original error matters more
                    pass
                if not is_write_conflict(exc) or attempt == attempts:
                    raise
                delay = min(_MAX_DELAY_S, _BASE_DELAY_S * (2 ** (attempt - 1)))
                log.warning("write conflict (attempt %d/%d); retrying in %.1fs: %s", attempt, attempts, delay, exc)
                sleep(delay)
            finally:
                try:
                    cursor.close()
                except Exception:  # noqa: BLE001
                    pass
    finally:
        connection.autocommit = previous
    raise RuntimeError("unreachable")  # pragma: no cover
