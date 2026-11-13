"""Export an approved draft: the bundle, the status change and the audit event; optionally, for developers, the rules folder. [F05.5]

Exporting changes the draft's status (approved -> exported) and appends an event, and nothing else: the app never writes into
the source tree in a deployed environment. In `ENVIRONMENT=local`, and only with `PROGRAM_EXPORT_ALLOW_LOCAL_WRITE=true`, a
developer may ask for the pack and year-pack files to be written into the rules folder; the registry entry is never edited (adding it
is the human step) and an existing file is never overwritten. A repeat export of an exported draft returns the same bytes.
"""
from __future__ import annotations

import io
import os
import shutil
import uuid
import zipfile
from datetime import datetime, timezone
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from application.program_drafts import customer_data
from application.program_drafts.bundle import Bundle, build_bundle
from application.program_drafts.lifecycle import load, validation_is_current
from config import get_settings
from domain.program_drafts import (
    CustomerDataInDraft, DraftConflict, DraftEvent, DraftInvalid, DraftStatus, InvalidTransition, ProgramDraft, ProgramDraftRepository, ReviewRefused,
)


class LocalWriteRefused(DraftInvalid):
    """Writing into the rules folder was asked for and is not allowed here."""

    code = "local_write_refused"


def _targets_inside(bundle: Bundle, root: Path) -> dict[str, Path]:
    """Where each pack file would land, refusing a path that resolves outside the rules folder (defence in depth)."""
    wanted = [f["path"] for f in bundle.manifest["files"] if f["path"].startswith("rules/")]
    targets = {name: root / name[len("rules/"):] for name in wanted}
    base = root.resolve()
    outside = [name for name, target in targets.items() if base not in target.resolve().parents]
    if outside:
        raise DraftInvalid(f"{outside[0]} is not a path inside the rules folder; nothing was written")
    return targets


def _make_parents(folder: Path, made: list[Path]) -> None:
    """Create the missing folders above a target, remembering each so a rollback can remove what this call made."""
    missing = []
    while not folder.exists():
        missing.append(folder)
        folder = folder.parent
    for path in reversed(missing):
        path.mkdir()
        made.append(path)


def _stage(bundle: Bundle, names: Iterable[str], staging: Path) -> None:
    """Write every file into the staging folder first, so a failure here has touched nothing that matters."""
    with zipfile.ZipFile(io.BytesIO(bundle.data)) as archive:
        for name in names:
            staged = staging / name
            staged.parent.mkdir(parents=True, exist_ok=True)
            staged.write_bytes(archive.read(name))


def _rollback(placed: list[Path], made: list[Path]) -> None:
    """Remove what this call placed and the folders it made; never anything that was there before."""
    for path in placed:
        path.unlink(missing_ok=True)
    for folder in reversed(made):
        try:
            folder.rmdir()
        except OSError:
            pass


def write_into_rules(bundle: Bundle, root: Path) -> list[str]:
    """Write only the pack and year-pack files, refusing any that already exist; return the paths written.

    All or nothing: every file is first written into a staging folder inside the rules folder (same volume, so a rename is a
    move), and only when all of them are staged are they moved into place. A failure while staging leaves the rules folder
    untouched; a failure part-way through the moves removes the files this call already placed and any folder it created.
    """
    targets = _targets_inside(bundle, root)
    clash = [str(p) for p in targets.values() if p.exists()]
    if clash:
        raise DraftConflict(f"{clash[0]} already exists; nothing was written (a bundle never overwrites a file)")
    staging = root / f".export-{uuid.uuid4().hex}"
    placed: list[Path] = []
    made: list[Path] = []
    try:
        _stage(bundle, targets, staging)
        for name, target in targets.items():
            _make_parents(target.parent, made)
            os.rename(staging / name, target)
            placed.append(target)
    except BaseException:
        _rollback(placed, made)
        raise
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return [str(p) for p in targets.values()]


def export(repo: ProgramDraftRepository, draft_id: str, actor: str, write_local: bool = False,
           at: datetime | None = None) -> tuple[ProgramDraft, Bundle, list[str]]:
    """The bundle for an approved or already exported draft, with the event that records who took it."""
    draft = load(repo, draft_id)
    if draft.status not in (DraftStatus.APPROVED_FOR_EXPORT, DraftStatus.EXPORTED):
        raise InvalidTransition(f"only an approved draft can be exported (this one is {draft.status.value})")
    if draft.approved_sha256 != draft.content_sha256 or not validation_is_current(draft):
        raise ReviewRefused("the documents differ from what was approved; it cannot be exported")
    if customer_data.scan_documents(draft):
        # Re-checked here, not only at validation: the book of client names can change after approval.
        raise CustomerDataInDraft("the documents look like they hold customer data; validate the draft to see where, remove it and ask for review again")
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
