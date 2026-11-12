"""The portfolio footprint read, with the guard that keeps it from scanning what it should not. [03b.2]

`footprint()` answers "which states does each client hold payroll in" with one `GROUP BY` over the whole
`Payroll` table, untenanted. At a few hundred thousand rows that is a fraction of a second. At billions it
is a scan that never lets the page load, and a client that merely waits and then abandons it leaves the
statement running on the server. So, before and while running it:

- `auto` (default) asks for a **row estimate that does not scan**: the Delta log's per-file statistics, else
  the SQL catalogue's partition statistics. Above `PORTFOLIO_FOOTPRINT_MAX_ROWS` it does not run, and says
  so as a typed `DependencyUnavailable` (the page reports it as degraded: the map and state filters are
  empty, and why). With no estimate it runs under the timeout.
- `on` always runs it, under the timeout. `off` never does.
- The timeout is the ODBC statement timeout (`SQL_ATTR_QUERY_TIMEOUT`), which makes the driver cancel the
  statement on the server; it is not a client that stops waiting.

Below the limit the result is exactly what `SourceSqlReader.footprint` always returned.
"""
from __future__ import annotations

import logging
from typing import Any

from application.errors import DependencyUnavailable

log = logging.getLogger(__name__)

_IMPACT = "where each client operates is unknown, so the footprint map and the state filters are empty"


def _unavailable(reason: str, remedy: str) -> DependencyUnavailable:
    return DependencyUnavailable("source_sql", reason, remedy, impact=_IMPACT)


def _catalogue_rows(reader: Any) -> int | None:
    """The SQL catalogue's row count for the payroll table, or None when the endpoint cannot say."""
    from data.source.onelake import physical_table

    table = reader._table("Payroll")
    catalogue = f"[{reader.lakehouse}].sys.dm_db_partition_stats"
    try:
        rows = reader._query(
            f"SELECT SUM(CAST(row_count AS BIGINT)) FROM {catalogue} WHERE object_id = OBJECT_ID(?) AND index_id IN (0, 1)",
            [table],
        )
    except Exception as exc:  # noqa: BLE001 - an endpoint without the catalogue view simply has no estimate
        log.info("no catalogue row estimate for %s (%s)", physical_table("Payroll"), type(exc).__name__)
        return None
    value = rows[0][0] if rows and rows[0] else None
    return int(value) if value else None


def _delta_rows() -> int | None:
    """The Delta log's row count for the payroll table (file statistics, no data read), or None."""
    from data.source.from_fabric import FabricLakehouseReader

    delta = FabricLakehouseReader()
    if not delta.is_configured():
        return None
    try:
        return delta.table_row_estimate("Payroll")
    except Exception as exc:  # noqa: BLE001 - no OneLake access (a SQL-only identity) just means no estimate
        log.info("no Delta row estimate for Payroll (%s)", type(exc).__name__)
        return None


def estimated_payroll_rows(reader: Any) -> int | None:
    """The cheapest row estimate that does not scan the table, or None when there is none."""
    estimate = _delta_rows()
    return estimate if estimate is not None else _catalogue_rows(reader)


def _check_allowed(reader: Any, mode: str, max_rows: int) -> None:
    """Raise `DependencyUnavailable` when the mode or the size estimate says the scan must not run."""
    if mode == "off":
        raise _unavailable("the footprint read is switched off (PORTFOLIO_FOOTPRINT_MODE=off).",
                           "Set PORTFOLIO_FOOTPRINT_MODE=auto to read it where the table is small enough.")
    if mode != "auto":
        return
    estimate = estimated_payroll_rows(reader)
    if estimate is not None and estimate > max_rows:
        raise _unavailable(
            f"the payroll table is estimated at {estimate:,} rows, over PORTFOLIO_FOOTPRINT_MAX_ROWS ({max_rows:,}); "
            "the footprint is not scanned.",
            "Raise PORTFOLIO_FOOTPRINT_MAX_ROWS, set PORTFOLIO_FOOTPRINT_MODE=on to run it under the timeout, "
            "or use the pre-aggregated read once it is available.",
        )


def _scan(reader: Any, timeout_seconds: int) -> list[tuple]:
    """The one `GROUP BY` over payroll, under the statement timeout. A timeout becomes `DependencyUnavailable`."""
    from infrastructure.persistence import source_sql as s

    payroll, location, address, zips = (reader._table(t) for t in ("Payroll", "Location", "Address", "StateCountyZip"))
    sql = f"""
        SELECT p.AccountId AS account_id, {s._STATE} AS work_state
        FROM {payroll} p
        LEFT JOIN {location} l ON l.LocationId = {s._LOCATION}
        LEFT JOIN {address} a ON a.AddressId = l.AddressId
        LEFT JOIN {zips} s
               ON s.StateCountyZipId = a.StateCountyZipId
        WHERE {s._HAS_SPAN}
        GROUP BY p.AccountId, {s._STATE}
        """
    try:
        return reader._query(sql, [], **({"timeout": timeout_seconds} if timeout_seconds else {}))
    except Exception as exc:  # noqa: BLE001 - only a statement timeout is translated here; the caller classifies the rest
        if "HYT00" not in str(exc) and "timeout expired" not in str(exc).lower():
            raise
        raise _unavailable(
            f"the footprint query exceeded PORTFOLIO_FOOTPRINT_TIMEOUT_SECONDS ({timeout_seconds}s) and was cancelled "
            "on the server.", "Raise the timeout, or set PORTFOLIO_FOOTPRINT_MODE=off until the pre-aggregated read exists.",
        ) from exc


def read_footprint(reader: Any, *, mode: str, max_rows: int, timeout_seconds: int) -> dict[int, list[str]]:
    """Which states each client holds payroll in, subject to the guard. See the module docstring."""
    from infrastructure.persistence import source_sql as s

    cached = s._FOOTPRINT_CACHE.get(reader.lakehouse)
    if cached is not None:
        return cached
    _check_allowed(reader, mode, max_rows)
    out: dict[int, list[str]] = {}
    for account_id, state in _scan(reader, timeout_seconds):
        if account_id is not None and state:
            out.setdefault(int(account_id), []).append(str(state))
    result = {key: sorted(set(states)) for key, states in out.items()}
    s._FOOTPRINT_CACHE[reader.lakehouse] = result
    return result
