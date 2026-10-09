"""The artifact service: files in Blob, governed by rows in the Warehouse. [BLOB-3, BLOB-6, D24]

Two stores, two jobs:

- an `ArtifactStore` holds the BYTES (Blob Storage when deployed, a local
  directory in development and CI);
- an `ArtifactRepository` holds the ROWS — `tcc_ops.artifact` (what the file is,
  whose it is, its SHA-256) and `tcc_ops.artifact_access` (who downloaded it).

The row is the authorization record, not an index. `get` authorizes the caller
for the requested client, looks the row up, checks the artifact belongs to that
client, and only then streams the blob — so a blob with no row cannot be
downloaded, and no SAS ever reaches a browser. Every attempt on a registered
artifact is written down: `served`, `denied`, or `missing` (registered, but the
bytes are gone). A request for an id nobody registered is a 404 and is logged,
not recorded, because `artifact_access` rows must point at a real artifact
(DDL validation 9.13).
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

from application.identity import Principal

log = logging.getLogger("tcc.artifacts")

KINDS = ("rule_source", "claim_package")
OUTCOMES = ("served", "denied", "missing")
OUTPUTS = "outputs"
ARTIFACTS = "artifacts"


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Artifact:
    kind: str
    container_name: str
    blob_path: str
    file_name: str
    content_type: str
    size_bytes: int
    sha256: str
    created_by: str
    client_id: int | None = None
    program_code: str | None = None
    tax_year: int | None = None
    run_id: str | None = None
    rule_pack_version: str | None = None
    retain_until: date | None = None
    created_at: datetime = field(default_factory=_now)
    superseded_at: datetime | None = None
    artifact_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"artifact kind {self.kind!r} is not one of {KINDS}")
        if self.kind == "claim_package" and (self.client_id is None or not self.run_id):
            raise ValueError("a claim package belongs to one client and one run")
        if self.container_name == OUTPUTS and not self.blob_path.startswith(f"{self.client_id}/"):
            raise ValueError("an output blob must live under its client's prefix")

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "client_id": self.client_id,
            "program_code": self.program_code,
            "tax_year": self.tax_year,
            "run_id": self.run_id,
            "file_name": self.file_name,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }


@dataclass(frozen=True)
class ArtifactAccess:
    artifact_id: str
    client_id: int | None
    user_upn: str
    outcome: str
    user_oid: str | None = None
    accessed_at: datetime = field(default_factory=_now)
    access_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        if self.outcome not in OUTCOMES:
            raise ValueError(f"access outcome {self.outcome!r} is not one of {OUTCOMES}")


class ArtifactStore(Protocol):
    """The bytes. Paths are container-relative; containers are `outputs` and `artifacts`."""

    is_durable: bool

    def put(self, container: str, path: str, data: bytes, content_type: str) -> None: ...

    def get(self, container: str, path: str) -> bytes | None: ...


class ArtifactRepository(Protocol):
    """The rows: `tcc_ops.artifact` and `tcc_ops.artifact_access`."""

    is_durable: bool

    def record(self, artifact: Artifact) -> Artifact: ...

    def find(self, artifact_id: str) -> Artifact | None:
        """By id, across clients: the authorization lookup."""

    def live(self, client_id: int, *, kind: str | None = None, tax_year: int | None = None) -> list[Artifact]: ...

    def record_access(self, access: ArtifactAccess) -> ArtifactAccess: ...

    def accesses(self, client_id: int) -> list[ArtifactAccess]: ...


@dataclass(frozen=True)
class Download:
    outcome: str                  # served | denied | missing | not_found
    artifact: Artifact | None = None
    data: bytes | None = None


class ArtifactService:
    def __init__(self, store: ArtifactStore, repository: ArtifactRepository, authorizer: Any,
                 *, retention_days: int = 2555) -> None:
        self.store = store
        self.repository = repository
        self.authorizer = authorizer
        self.retention_days = retention_days

    def put(self, data: bytes, **fields: Any) -> Artifact:
        """Write the blob, then register it. A row never points at missing bytes."""
        digest = hashlib.sha256(data).hexdigest()
        artifact = Artifact(
            size_bytes=len(data), sha256=digest,
            retain_until=(_now() + timedelta(days=self.retention_days)).date(),
            **fields,
        )
        self.store.put(artifact.container_name, artifact.blob_path, data, artifact.content_type)
        return self.repository.record(artifact)

    def get(self, principal: Principal, client_id: int, artifact_id: str) -> Download:
        """Authorize, look up, check ownership, stream — recording the outcome."""
        artifact = self.repository.find(artifact_id)
        if artifact is None:
            log.warning("download of unregistered artifact %s for client %s by %s",
                        artifact_id, client_id, principal.actor)
            return Download("not_found")

        owner_ok = artifact.client_id == client_id
        allowed = (
            owner_ok
            and self.authorizer.is_authorized(principal, client_id)
            and (artifact.client_id is None or self.authorizer.is_authorized(principal, artifact.client_id))
        )
        if not allowed:
            self._audit(principal, artifact, "denied")
            return Download("denied", artifact)

        data = self.store.get(artifact.container_name, artifact.blob_path)
        if data is None:
            self._audit(principal, artifact, "missing")
            return Download("missing", artifact)

        self._audit(principal, artifact, "served")
        return Download("served", artifact, data)

    def _audit(self, principal: Principal, artifact: Artifact, outcome: str) -> None:
        self.repository.record_access(ArtifactAccess(
            artifact_id=artifact.artifact_id,
            client_id=artifact.client_id,
            user_upn=principal.actor,
            user_oid=principal.oid,
            outcome=outcome,
        ))

