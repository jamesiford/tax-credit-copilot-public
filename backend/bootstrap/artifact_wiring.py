"""The artifact service, composed: bytes in a store, rows in a repository. [BLOB-3, BLOB-6]

Split out of `bootstrap.wiring`, which re-exports both names, to keep that module to the
bindings the mediator needs.
"""
from __future__ import annotations

from typing import Any

from bootstrap.auth_wiring import get_client_authorizer
from config import get_settings

_artifact_service: Any | None = None


def get_artifact_service() -> Any:
    """Bytes (ARTIFACT_STORE local|blob) + rows (ARTIFACT_REPOSITORY sqlite|warehouse)."""
    global _artifact_service
    if _artifact_service is None:
        from application.artifacts import ArtifactService
        from application.deployment import artifact_repository, artifact_store

        stores = get_settings().stores
        if artifact_store() == "blob":
            from infrastructure.storage.blob_store import BlobArtifactStore

            store: Any = BlobArtifactStore(account_url=stores.artifact_blob_account_url)
        else:
            from infrastructure.storage.local_store import LocalArtifactStore

            store = LocalArtifactStore(root=stores.artifact_local_root)
        if artifact_repository() == "warehouse":
            from infrastructure.persistence.warehouse_artifacts import WarehouseArtifactRepository

            repository: Any = WarehouseArtifactRepository()
        else:
            from infrastructure.persistence.sqlite_artifacts import SqliteArtifactRepository

            repository = SqliteArtifactRepository()
        _artifact_service = ArtifactService(
            store, repository, get_client_authorizer(),
            retention_days=stores.outputs_retention_days,
        )
    return _artifact_service


def set_artifact_service(service: Any) -> None:
    global _artifact_service
    _artifact_service = service
