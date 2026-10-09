"""Claim packages and governed downloads. [BLOB-3, BLOB-4, D16, D24]

Thin [ADR-003]: the workbook is built by `application.claim_package` from what
the run already wrote, and every byte moves through `ArtifactService`, which
authorizes, checks ownership and records the access. No SAS URL is ever
returned; the API streams the file.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response

from api.auth import attributed, current_principal

router = APIRouter(prefix="/api/clients", tags=["artifacts"])


@router.post("/{client_id}/packages", status_code=201)
def create_claim_package(client_id: int, request: Request, tax_year: int = Query(...)) -> dict[str, Any]:
    """Build one client-year's claim package, store it, and return its id."""
    from application.artifacts import OUTPUTS
    from application.claim_package import XLSX, NoRunForClient, build_claim_package
    from application.wiring import get_artifact_service, get_claim_package_source

    author = attributed(request, None, default="system:claim-package")
    try:
        package = build_claim_package(client_id, tax_year, get_claim_package_source(), generated_by=author)
    except NoRunForClient as exc:
        # "Not calculated" is a state, not an empty workbook.
        raise HTTPException(status_code=409, detail=str(exc)) from exc

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
    return {**artifact.to_dict(), "rows": package.rows}


@router.get("/{client_id}/artifacts/{artifact_id}")
def download_artifact(client_id: int, artifact_id: str, request: Request) -> Response:
    """Stream an artifact the caller may see, recording served/denied/missing."""
    from application.wiring import get_artifact_service

    result = get_artifact_service().get(current_principal(request), client_id, artifact_id)
    if result.outcome == "not_found":
        raise HTTPException(status_code=404, detail="no such artifact")
    if result.outcome == "denied":
        raise HTTPException(status_code=403, detail=f"not authorized for this artifact under client {client_id}")
    if result.outcome == "missing":
        raise HTTPException(status_code=404, detail="the artifact is registered but its file is missing")
    artifact = result.artifact
    return Response(
        content=result.data,
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{artifact.file_name}"',
            "Cache-Control": "no-store",
            "X-Content-SHA256": artifact.sha256,
        },
    )
