"""Build the export bundle: a deterministic zip and manifest for a human to commit. [F05.5, ADR-005, ADR-013]

The same draft always produces the same bytes: files are written in sorted order with a fixed timestamp and fixed compression,
JSON is canonical, and nothing in it comes from the clock or the environment (the review record carries the times the events
already stored). The bundle holds the pack and year-pack files at their final repository paths, the registry entry to add, the
stored validation, the review record and the commit checklist. It verifies nothing and activates nothing: a person commits it.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from typing import Any

from application.program_drafts.checklist import changelog_line, checklist
from application.program_drafts.naming import pack_file_name, registry_entry, year_file_name
from domain.program_drafts import DraftEvent, ProgramDraft

_FIXED_TIME = (1980, 1, 1, 0, 0, 0)
#: Events that belong to the reviewed history. The export itself is not one: a repeat export must reproduce the same bundle.
_HISTORY = ("created", "edited", "validated", "review_requested", "approved", "changes_requested")


@dataclass(frozen=True)
class Bundle:
    """The zip bytes, their SHA-256 and the manifest (which lists every file's hash; it is also inside the zip)."""

    data: bytes
    sha256: str
    manifest: dict[str, Any]


def _json(document: Any) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")


def _files(draft: ProgramDraft, events: list[DraftEvent]) -> dict[str, bytes]:
    pack_file = pack_file_name(draft)
    stem = pack_file[:-len(".json")]
    files: dict[str, bytes] = {f"rules/{pack_file}": _json(draft.pack)}
    for year, doc in draft.years.items():
        files[f"rules/{stem}/{year_file_name(year)}"] = _json(doc)
    files["registry-patch.json"] = _json({"add_to": "backend/rules/registry/programs.json", "programs": [registry_entry(draft)]})
    files["validation-report.json"] = _json({"note": "Valid means well-formed, not verified.", "result": draft.validation})
    files["review-record.json"] = _json({
        "requested_by": draft.review_requested_by, "reviewer": draft.reviewer, "decision": draft.decision, "comment": draft.decision_comment,
        "decided_at": draft.decided_at.isoformat() if draft.decided_at else None, "approved_content_sha256": draft.approved_sha256,
        "history": [{"seq": e.seq, "event": e.event_type, "actor": e.actor, "at": e.at.isoformat(), "to_status": e.to_status}
                    for e in events if e.event_type in _HISTORY]})
    names = sorted(files)
    files["COMMIT-CHECKLIST.md"] = checklist(draft, names, pack_file).encode("utf-8")
    return files


def _manifest(draft: ProgramDraft, files: dict[str, bytes]) -> dict[str, Any]:
    return {
        "kind": "program-draft-bundle", "schema_version": 1, "draft_id": draft.draft_id, "proposed_code": draft.proposed_code,
        "name": draft.name, "state": draft.state, "content_sha256": draft.content_sha256, "approved_sha256": draft.approved_sha256,
        "verification": "not_verified", "has_runtime_authority": False, "changelog_line": changelog_line(draft),
        "files": [{"path": p, "sha256": hashlib.sha256(files[p]).hexdigest(), "bytes": len(files[p])} for p in sorted(files)],
    }


def build_bundle(draft: ProgramDraft, events: list[DraftEvent]) -> Bundle:
    """The bundle for an approved draft. Deterministic: equal drafts give equal bytes."""
    files = _files(draft, events)
    manifest = _manifest(draft, files)
    files["manifest.json"] = _json(manifest)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=_FIXED_TIME)
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, files[name])
    data = buffer.getvalue()
    return Bundle(data=data, sha256=hashlib.sha256(data).hexdigest(), manifest=manifest)
