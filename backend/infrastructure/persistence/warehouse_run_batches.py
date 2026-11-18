"""The run batch queue over the Fabric Warehouse or Azure SQL: `tcc_ops.run_batch` and `run_batch_item` (migration 0004). [ADR-012]

All statements run through one tenant exemption: the queue is the cross-client control plane (claiming,
leasing and counting span clients by design), and its rows are work items, not a client's figures. Writes go
through `run_in_transaction`, so a snapshot-isolation conflict (24556, 3960, 1205) re-runs the transaction.
Not exercised against a live Warehouse in this repository's tests (LIVE-CHECK-REQUIRED).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

from infrastructure.persistence.fabric_warehouse import names, FabricWarehouseConnection
from infrastructure.persistence.run_batch_queue import RunBatchRepository
from infrastructure.persistence.tenant_sql import run_in_transaction, tenant_exempt
from infrastructure.persistence.warehouse_claims import from_db_instant, rows_as_dicts, to_db_instant

T = TypeVar("T")
_QUEUE = tenant_exempt("run batch queue: claiming, leasing and counting items span clients by design")


class _Result:
    def __init__(self, rows: list[dict[str, Any]], rowcount: int) -> None:
        self.rows, self.rowcount = rows, rowcount


class _Tx:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def execute(self, sql: str, params: list[Any] | tuple = ()) -> _Result:
        _QUEUE.execute(self._cursor, sql, list(params))
        rows = rows_as_dicts(self._cursor) if self._cursor.description else []
        return _Result(rows, self._cursor.rowcount if self._cursor.rowcount is not None else -1)


class WarehouseBackend:
    """Warehouse transactions with conflict retry, and naive-UTC instants."""
    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    def table(self, name: str) -> str:
        return f"{names.ops(name)}"

    def bind(self, value: datetime | None) -> datetime | None:
        return to_db_instant(value)

    def parse(self, value: Any) -> datetime | None:
        parsed = from_db_instant(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed is not None and parsed.tzinfo is None else parsed

    def page(self, limit: int, offset: int) -> tuple[str, list[int]]:
        return "OFFSET ? ROWS FETCH NEXT ? ROWS ONLY", [offset, limit]

    def transact(self, work: Callable[[_Tx], T]) -> T:
        with self._connection.connect() as connection:
            return run_in_transaction(connection, lambda cursor: work(_Tx(cursor)))


class WarehouseRunBatchRepository(RunBatchRepository):
    """The whole queue port over the Warehouse or Azure SQL."""
    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        super().__init__(WarehouseBackend(connection))
