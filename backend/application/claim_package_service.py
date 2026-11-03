"""Build a claim package and store it: the one place that does both. [BLOB-4, CH-06]

The portal's `POST /api/clients/{id}/packages` and the channel's
`claim_package_create` commit both end in "build the workbook from what the run
wrote, put it in the artifact store, register it". Two copies would drift on the
one thing that must not: the blob path, which is never reused.

Reads Gold and the claim store; never runs the engine.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from application.artifacts import OUTPUTS, Artifact
from application.claim_package import XLSX, ClaimPackage, build_claim_package


@dataclass(frozen=True)
class StoredPackage:
    """The registered artifact, and the workbook's per-sheet row counts."""

    artifact: Artifact
    rows: dict[str, int]


def store_claim_package(client_id: int, tax_year: int, author: str) -> StoredPackage:
    """Build one client-year's package and register it. Raises `NoRunForClient` with no run."""
    from application.wiring import get_artifact_service, get_claim_package_source

    package: ClaimPackage = build_claim_package(
        client_id, tax_year, get_claim_package_source(), generated_by=author,
    )
    # Blob paths are never reused, so each generation gets its own segment.
    generation = uuid.uuid4().hex[:12]
    artifact = get_artifact_service().put(
        package.data,
        kind="claim_package",
        client_id=client_id,
        program_code=package.program_code,
        tax_year=tax_year,
        run_id=package.run_id,
        container_name=OUTPUTS,
        blob_path=f"{client_id}/{package.run_id}/{generation}/{package.file_name}",
        file_name=package.file_name,
        content_type=XLSX,
        created_by=author,
    )
    return StoredPackage(artifact, package.rows)


def latest_package(client_id: int, tax_year: int) -> Artifact | None:
    """The newest live claim package for a client-year, or None if none was built."""
    from application.wiring import get_artifact_service

    found = get_artifact_service().repository.live(client_id, kind="claim_package", tax_year=tax_year)
    return max(found, key=lambda a: a.created_at, default=None)


def download_path(client_id: int, artifact_id: str) -> str:
    """The API-relative path a package is served from. Never a storage URL."""
    return f"/api/clients/{client_id}/artifacts/{artifact_id}"
