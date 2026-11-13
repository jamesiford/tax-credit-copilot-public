"""The program draft repository, composed. [F05.2]

Follows `RUN_MANIFEST_STORE`, like the run batches: a draft is provenance about how a program came to exist and lives where the
platform records its decisions. `warehouse` (alias `fabric`, `azure_sql`) is the durable adapter; `sqlite` is a file; `memory`
(the local default) is private to one process. A draft has no runtime authority, so the choice affects durability only.
"""
from __future__ import annotations

from typing import Any

from application.deployment import store_choice
from bootstrap.binding import bind

_repo: Any | None = None


def get_program_draft_repository() -> Any:
    """The repository the settings choose, built on first use."""
    global _repo
    if _repo is None:
        store = store_choice("RUN_MANIFEST_STORE")
        if store == "warehouse":
            from infrastructure.persistence.warehouse_program_drafts import WarehouseProgramDraftRepository

            _repo = WarehouseProgramDraftRepository()
        elif store in ("sqlite", "memory"):
            from infrastructure.persistence.sqlite_program_drafts import SqliteProgramDraftRepository

            _repo = SqliteProgramDraftRepository(":memory:" if store == "memory" else None)
        else:
            raise ValueError(f"RUN_MANIFEST_STORE={store!r} is not a known adapter for program drafts. Use 'warehouse' (alias 'fabric'), 'sqlite' or 'memory'.")
    return _repo


def set_program_draft_repository(repo: Any) -> None:
    """Point the application at another adapter. Used by tests."""
    global _repo
    _repo = repo


bind(__name__, program_draft_repository="get_program_draft_repository")
