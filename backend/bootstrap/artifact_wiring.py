"""The artifact service, composed: bytes in a store, rows in a repository. [BLOB-3, BLOB-6]

Split out of `bootstrap.wiring`, which re-exports both names, to keep that module to the
bindings the mediator needs.
"""
from __future__ import annotations

import os
from typing import Any

from bootstrap.auth_wiring import get_client_authorizer

_artifact_service: Any | None = None


def get_artifact_service() -> Any:
    """Bytes (ARTIFACT_STORE local|blob) + rows (ARTIFACT_REPOSITORY sqlite|warehouse)."""
    global _artifact_service
    if _artifact_service is None:
        from application.artifacts import ArtifactService
        from application.deployment import artifact_repository, artifact_store

        if artifact_store() == "blob":
            from infrastructure.storage.blob_store import BlobArtifactStore

            store: Any = BlobArtifactStore()
        else:
            from infrastructure.storage.local_store import LocalArtifactStore

            store = LocalArtifactStore()
        if artifact_repository() == "warehouse":
            from infrastructure.persistence.warehouse_artifacts import WarehouseArtifactRepository

            repository: Any = WarehouseArtifactRepository()
        else:
            from infrastructure.persistence.sqlite_artifacts import SqliteArtifactRepository

            repository = SqliteArtifactRepository()
        _artifact_service = ArtifactService(
            store, repository, get_client_authorizer(),
            retention_days=int(os.getenv("OUTPUTS_RETENTION_DAYS", "2555")),
        )
    return _artifact_service


def set_artifact_service(service: Any) -> None:
    global _artifact_service
    _artifact_service = service
