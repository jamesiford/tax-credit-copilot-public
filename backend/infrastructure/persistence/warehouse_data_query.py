"""Execute a built data query on a T-SQL endpoint: the Warehouse. [CH-16c]

The one place built statements reach a cursor for the Warehouse. It does four things and
nothing else:

- **Refuses anything but a single SELECT** before the statement is bound.
- **Binds the client through `TenantScopedQuery`**, the same helper every other Warehouse
  adapter uses, so the statement cannot run without the client predicate as its first term.
  `tests/test_architecture.py` holds this module under the same rule as `warehouse_*.py`.
- **Applies the time limit** with the driver's query timeout, set on the borrowed connection
  and put back to none before it returns to the pool (a pooled link is shared with every page
  read, and must not keep a data query's limit). A timeout is `QueryTimeout`; the connection is
  discarded, which also cancels the statement server-side. No rows are returned.
- **Fetches at most `max_rows + 1` rows** so the cap is reported without a COUNT.

`TsqlDataQueryExecutor` is the shared core; the Lakehouse SQL analytics endpoint is the same
T-SQL over a different connection (`lakehouse_data_query.py`). Connections, pooling and
managed identity are `FabricWarehouseConnection`'s: nothing here knows about credentials.
"""
from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

from application.data.dialect import Dialect
from application.data.errors import QueryError
from application.data.exec_errors import DataSourceUnavailable, QueryFailed, QueryTimeout
from application.data.executor import Rows, assert_read_only, read_capped
from infrastructure.persistence.fabric_warehouse import FabricWarehouseConnection, WarehouseNotConfigured
from infrastructure.persistence.tenant_sql import TenantScopeViolation, TenantScopedQuery

log = logging.getLogger("tcc.data_query")

#: SQLSTATEs a driver reports for an expired query (HYT00) or connection (HYT01) time limit.
_TIMEOUT_STATES = frozenset({"HYT00", "HYT01"})


def is_timeout(exc: BaseException) -> bool:
    """Whether a driver error means the time limit expired."""
    state = str(exc.args[0]) if exc.args else ""
    return state in _TIMEOUT_STATES or "timeout expired" in str(exc).lower()


class TsqlDataQueryExecutor:
    """Runs built T-SQL for one client on a `FabricWarehouseConnection`-shaped connection."""

    dialect = Dialect.TSQL
    label = "warehouse"

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def execute(self, sql: str, params: Sequence[Any], *, client_id: int, timeout_s: float, max_rows: int) -> Rows:
        """Rows for the statement, or a typed `QueryError`. Never partial."""
        assert_read_only(sql)
        try:
            self._connection.require_configuration()
            with self._connection.connect() as live:
                return self._read(live, sql, params, client_id, timeout_s, max_rows)
        except (QueryError, TenantScopeViolation):
            raise
        except WarehouseNotConfigured as exc:
            raise DataSourceUnavailable(f"the {self.label} connection is not configured") from exc
        except Exception as exc:  # noqa: BLE001 - classified: a timeout is typed, the rest is generic
            if is_timeout(exc):
                raise QueryTimeout(f"the query ran past its {timeout_s:g}s limit and was cancelled") from exc
            log.warning("data query failed on %s: %s", self.label, type(exc).__name__)
            raise QueryFailed("the data source could not run the query") from exc

    @staticmethod
    def _read(live: Any, sql: str, params: Sequence[Any], client_id: int, timeout_s: float, max_rows: int) -> Rows:
        live.timeout = max(1, int(timeout_s))
        cursor = live.cursor()
        try:
            TenantScopedQuery(client_id).execute(cursor, sql, list(params))
            return read_capped(cursor, max_rows)
        finally:
            live.timeout = 0
            cursor.close()


class WarehouseDataQueryExecutor(TsqlDataQueryExecutor):
    """The Warehouse (`tcc_gold`, `tcc_ops`), over the process's shared connection settings."""

    def __init__(self, connection: Any = None) -> None:
        super().__init__(connection or FabricWarehouseConnection())
