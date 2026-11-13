"""Export an approved program draft as a bundle for a human to commit. [F05.5]

A **command** (policy: writer): it moves the draft to `exported` and appends the audit event with who took it. It returns the
deterministic zip; the app never writes into the source tree unless a developer has enabled that in local development.
Exporting verifies nothing and activates nothing. [ADR-005]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.identity import Policy
from application.mediator import Command


@dataclass(frozen=True)
class ExportProgramDraftCommand(Command):
    """`write_local` asks for the pack files to be written into the rules folder (local development with the setting on only)."""
    draft_id: str = ""
    write_local: bool = False
    policy = Policy.WRITER


def handle_export_program_draft(command: ExportProgramDraftCommand) -> dict[str, Any]:
    from application.program_drafts import export
    from application.program_drafts.views import draft_view
    from application.services import get_program_draft_repository

    draft, bundle, written = export.export(get_program_draft_repository(), command.draft_id, command.actor, command.write_local)
    return {"draft": draft_view(draft), "bundle": bundle.data, "bundle_sha256": bundle.sha256, "manifest": bundle.manifest,
            "written_files": written}
