"""A connection to the Lakehouse SQL analytics endpoint. [CH-16c]

The same T-SQL, the same managed identity and the same token as the Warehouse; what differs is
WHERE: the lakehouse's own endpoint database, which holds the source payroll tables
(`SOURCE_SCHEMA`). Settings follow the Warehouse pattern, and default to what the repo already
knows so a deployment sets nothing it does not have to:

- `LAKEHOUSE_SQL_SERVER` — the endpoint host; defaults to `WAREHOUSE_SERVER` (a workspace's
  Warehouse and lakehouse endpoints share one host).
- `LAKEHOUSE_SQL_DATABASE` — the lakehouse's endpoint database; defaults to `FABRIC_LAKEHOUSE`.
- The ODBC driver and connect timeout are the Warehouse's (`WAREHOUSE_ODBC_DRIVER`,
  `WAREHOUSE_CONNECT_TIMEOUT`).

It keeps its OWN small pool. The Warehouse pool is process-wide and keyed by nothing ("one
warehouse per process"), so borrowing from it here would hand a lakehouse link to a Gold read.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any

from infrastructure.persistence.fabric_warehouse import (
    _POOL_MAX_AGE_S,
    FabricWarehouseConnection,
    WarehouseNotConfigured,
    _close_quietly,
    _end_transaction,
)

_MAX_IDLE = 2


class LakehouseSqlConnection(FabricWarehouseConnection):
    """`FabricWarehouseConnection` pointed at the lakehouse endpoint, with a pool of its own."""

    def __init__(self, *, server: str | None = None, database: str | None = None, **kwargs: Any) -> None:
        super().__init__(
            server=server or os.getenv("LAKEHOUSE_SQL_SERVER") or os.getenv("WAREHOUSE_SERVER"),
            database=database or os.getenv("LAKEHOUSE_SQL_DATABASE") or os.getenv("FABRIC_LAKEHOUSE"),
            **kwargs,
        )
        self._idle: list[tuple[Any, float]] = []
        self._idle_lock = threading.Lock()

    def require_configuration(self) -> None:
        """Both the endpoint host and database are needed; say which setting to supply."""
        missing = [n for n, v in (("LAKEHOUSE_SQL_SERVER", self.server), ("LAKEHOUSE_SQL_DATABASE", self.database)) if not v]
        if missing:
            raise WarehouseNotConfigured(f"{', '.join(missing)} not set (or its Warehouse/lakehouse fallback).")

    def acquire(self) -> Any:
        """A pooled lakehouse connection, or a new one."""
        while True:
            with self._idle_lock:
                if not self._idle:
                    break
                connection, opened_at = self._idle.pop()
            if time.time() - opened_at <= _POOL_MAX_AGE_S:
                return connection
            _close_quietly(connection)
        return self.open()

    def release(self, connection: Any, *, reusable: bool = True) -> None:
        """Return a healthy connection to this endpoint's pool; close a suspect or surplus one."""
        if reusable and _end_transaction(connection):
            with self._idle_lock:
                if len(self._idle) < _MAX_IDLE:
                    self._idle.append((connection, time.time()))
                    return
        _close_quietly(connection)

    def prewarm(self, count: int = 0) -> int:
        """Not used: the endpoint is opened on demand, and the Warehouse's startup warm-up must not touch it."""
        return 0

    def keepalive(self) -> int:
        """Not used, for the same reason as `prewarm`."""
        return 0
