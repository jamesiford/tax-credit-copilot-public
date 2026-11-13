"""Export an approved draft: the bundle, the status change and the audit event; optionally, for developers, the rules folder. [F05.5]

Exporting changes the draft's status (approved -> exported) and appends an event, and nothing else: the app never writes into
the source tree in a deployed environment. In `ENVIRONMENT=local`, and only with `PROGRAM_EXPORT_ALLOW_LOCAL_WRITE=true`, a
developer may ask for the pack and year-pack files to be written into the rules folder; the registry entry is never edited (adding it
is the human step) and an existing file is never overwritten. A repeat export of an exported draft returns the same bytes.
"""
from __future__ import annotations

import io
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from application.program_drafts.bundle import Bundle, build_bundle
from application.program_drafts.lifecycle import load, validation_is_current
from config import get_settings
from domain.program_drafts import (
    DraftConflict, DraftEvent, DraftInvalid, DraftStatus, InvalidTransition, ProgramDraft, ProgramDraftRepository, ReviewRefused,
)


class LocalWriteRefused(DraftInvalid):
    """Writing into the rules folder was asked for and is not allowed here."""

    code = "local_write_refused"


def write_into_rules(bundle: Bundle, root: Path) -> list[str]:
    """Write only the pack and year-pack files, refusing any that already exist; return the paths written."""
    wanted = [f["path"] for f in bundle.manifest["files"] if f["path"].startswith("rules/")]
    targets = {name: root / name[len("rules/"):] for name in wanted}
    clash = [str(p) for p in targets.values() if p.exists()]
    if clash:
        raise DraftConflict(f"{clash[0]} already exists; nothing was written (a bundle never overwrites a file)")
    with zipfile.ZipFile(io.BytesIO(bundle.data)) as archive:
        for name, target in targets.items():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(name))
    return [str(p) for p in targets.values()]


def export(repo: ProgramDraftRepository, draft_id: str, actor: str, write_local: bool = False,
           at: datetime | None = None) -> tuple[ProgramDraft, Bundle, list[str]]:
    """The bundle for an approved or already exported draft, with the event that records who took it."""
    draft = load(repo, draft_id)
    if draft.status not in (DraftStatus.APPROVED_FOR_EXPORT, DraftStatus.EXPORTED):
        raise InvalidTransition(f"only an approved draft can be exported (this one is {draft.status.value})")
    if draft.approved_sha256 != draft.content_sha256 or not validation_is_current(draft):
        raise ReviewRefused("the documents differ from what was approved; it cannot be exported")
    if write_local and not get_settings().programs.export_allow_local_write:
        raise LocalWriteRefused("writing into the rules folder is off (ENVIRONMENT=local and PROGRAM_EXPORT_ALLOW_LOCAL_WRITE=true enable it for developers)")
    bundle = build_bundle(draft, repo.events(draft_id))
    written = write_into_rules(bundle, get_settings().programs.rules_dir) if write_local else []
    now = at or datetime.now(timezone.utc)
    first = draft.status is DraftStatus.APPROVED_FOR_EXPORT
    changed = draft.with_changes(status=DraftStatus.EXPORTED, exported_at=draft.exported_at or now, export_sha256=bundle.sha256,
                                 version=draft.version + 1, updated_by=actor, updated_at=now)
    event = DraftEvent(draft_id=draft_id, seq=0, event_type="exported", actor=actor, at=now, from_status=draft.status.value,
                       to_status=DraftStatus.EXPORTED.value,
                       detail={"bundle_sha256": bundle.sha256, "first_export": first, "wrote_local_files": written})
    repo.save(changed, draft.version, event)
    return changed, bundle, written


def manifest(repo: ProgramDraftRepository, draft_id: str) -> dict[str, Any]:
    """The manifest of the bundle an approved or exported draft would produce, with no status change and no event."""
    draft = load(repo, draft_id)
    if draft.status not in (DraftStatus.APPROVED_FOR_EXPORT, DraftStatus.EXPORTED):
        raise InvalidTransition(f"a manifest exists once a draft is approved (this one is {draft.status.value})")
    bundle = build_bundle(draft, repo.events(draft_id))
    return {**bundle.manifest, "bundle_sha256": bundle.sha256, "bundle_bytes": len(bundle.data)}
