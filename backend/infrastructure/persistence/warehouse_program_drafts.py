"""Program drafts over the Fabric Warehouse or Azure SQL: `tcc_ops.program_draft*` (migration 0005). [F05.2]

The tables hold proposals about the platform, not a client's figures, so every statement runs under one named tenant
exemption. Writes go through `run_in_transaction`, so a snapshot-isolation conflict (24556, 3960, 1205) re-runs the
transaction. Not exercised against a live Warehouse in this repository's tests (LIVE-CHECK-REQUIRED).
"""
from __future__ import annotations

from typing import Any, Callable, TypeVar

from infrastructure.persistence.fabric_warehouse import FabricWarehouseConnection
from infrastructure.persistence.program_draft_store import ProgramDraftStore
from infrastructure.persistence.tenant_sql import run_in_transaction, tenant_exempt
from infrastructure.persistence.warehouse_claims import rows_as_dicts
from infrastructure.persistence.warehouse_run_batches import WarehouseBackend, _Result

T = TypeVar("T")
_DRAFTS = tenant_exempt("program drafts: proposals about the platform's programs, not a client's data; they carry no client key")


class _Tx:
    def __init__(self, cursor: Any) -> None:
        self._cursor = cursor

    def execute(self, sql: str, params: list[Any] | tuple = ()) -> _Result:
        _DRAFTS.execute(self._cursor, sql, list(params))
        rows = rows_as_dicts(self._cursor) if self._cursor.description else []
        return _Result(rows, self._cursor.rowcount if self._cursor.rowcount is not None else -1)


class _DraftBackend(WarehouseBackend):
    """The run queue's Warehouse backend (names, instants, paging) with this store's own exemption and transaction."""

    def transact(self, work: Callable[[_Tx], T]) -> T:  # type: ignore[override]
        with self._connection.connect() as connection:
            return run_in_transaction(connection, lambda cursor: work(_Tx(cursor)))


class WarehouseProgramDraftRepository(ProgramDraftStore):
    """The draft repository over the Warehouse or Azure SQL."""

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        super().__init__(_DraftBackend(connection))
