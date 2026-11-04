"""Build a client-year's claim package and register it. [CH-06]

A **command**: it adds a governed file to the client's record and somebody has to
be responsible for it, so it carries `actor` and demands the writer policy like
every other thing the channel can do that outlives the conversation.

Nothing here computes a figure. The workbook is read from what the run already
wrote, so this never triggers a calculation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.capabilities.errors import NotCalculated
from application.claim_package import NoRunForClient
from application.claim_package_service import download_path, store_claim_package
from application.identity import Policy
from application.mediator import Command


@dataclass(frozen=True)
class CreateClaimPackageCommand(Command):
    """Package one client-year. The writer policy applies; `actor` is whoever asked."""
    client_id: int = 0
    tax_year: int = 0
    policy = Policy.WRITER

    def validate(self) -> None:
        """A package is for one client and one year."""
        if self.client_id <= 0 or not 1900 <= self.tax_year <= 2100:
            raise ValueError("client_id and tax_year are required")


def handle_create_claim_package(command: CreateClaimPackageCommand) -> dict[str, Any]:
    """Store the package; return what a caller needs to find it again."""
    try:
        stored = store_claim_package(command.client_id, command.tax_year, command.actor)
    except NoRunForClient as exc:
        raise NotCalculated(str(exc)) from exc
    artifact = stored.artifact
    return {
        "artifact_id": artifact.artifact_id,
        "client_id": artifact.client_id,
        "tax_year": artifact.tax_year,
        "run_id": artifact.run_id,
        "file_name": artifact.file_name,
        "sha256": artifact.sha256,
        "size_bytes": artifact.size_bytes,
        "download_path": download_path(artifact.client_id, artifact.artifact_id),
        "rows": stored.rows,
    }
