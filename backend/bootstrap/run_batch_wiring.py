"""The run batch repository, composed. [ADR-012]

Follows `RUN_MANIFEST_STORE`, like the manual overrides: a batch is provenance about runs and lives where they are
recorded. `warehouse` (alias `fabric`, `azure_sql`) is the durable adapter; `sqlite` is a file shared by a local API
and a locally started worker; `memory` (the local default) is private to one process, so it suits tests and an
inline worker, and a separate worker process needs `RUN_MANIFEST_STORE=sqlite`.
"""
from __future__ import annotations

from typing import Any

from application.deployment import store_choice
from bootstrap.binding import bind

_repo: Any | None = None


def get_run_batch_repository() -> Any:
    """The repository the settings choose, built on first use."""
    global _repo
    if _repo is None:
        store = store_choice("RUN_MANIFEST_STORE")
        if store == "warehouse":
            from infrastructure.persistence.warehouse_run_batches import WarehouseRunBatchRepository

            _repo = WarehouseRunBatchRepository()
        elif store in ("sqlite", "memory"):
            from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository

            _repo = SqliteRunBatchRepository(":memory:" if store == "memory" else None)
        else:
            raise ValueError(
                f"RUN_MANIFEST_STORE={store!r} is not a known adapter for run batches. Use 'warehouse' "
                "(alias 'fabric'), 'sqlite' or 'memory'."
            )
    return _repo


def set_run_batch_repository(repo: Any) -> None:
    """Point the application at another adapter. Used by tests."""
    global _repo
    _repo = repo


bind(__name__, run_batch_repository="get_run_batch_repository")
