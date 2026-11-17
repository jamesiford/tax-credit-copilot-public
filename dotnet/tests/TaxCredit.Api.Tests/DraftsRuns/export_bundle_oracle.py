"""Generate member-byte evidence from the approved CPython oracle, never from .NET."""
from __future__ import annotations

import io
import json
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

if sys.version_info[:2] != (3, 12):
    raise SystemExit("The bundle oracle requires CPython 3.12.")

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "backend"))

from application.program_drafts.bundle import build_bundle
from domain.program_drafts import DraftEvent, DraftStatus, ProgramDraft, documents_hash

records = {
    r["id"]: r for line in (ROOT / "contract" / "recordings" / "p1_program_drafts.jsonl").read_text(encoding="utf-8").splitlines()
    if "request" in (r := json.loads(line))
}
created = records["create"]["request"]["body"]["value"]
documents = records["second-fill"]["request"]["body"]["value"]
pack, years = documents["pack"], documents["years"]
pack["_bundle_fixture"] = {
    "text": "caf\u00e9 \u00a7 \U0001f600 \u0000 \u007f \u2028",
    "numbers": [-0.0, 1e-7, 1e20, 2**70],
}
digest = documents_hash(pack, years)
validation = {
    "valid": True, "content_sha256": digest, "errors": 0, "warnings": 0, "infos": 0,
    "findings": [], "truncated": False, "verification": "not_verified",
}
at = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
draft = ProgramDraft(
    draft_id="4000000000004000800000000000f00d", proposed_code=created["code"], name=created["name"],
    jurisdiction_level="state", state=created["state"], status=DraftStatus.APPROVED_FOR_EXPORT, version=1,
    created_by="ann", created_at=at, updated_by="bob", updated_at=at, pack=pack, years=years,
    validation=validation, review_requested_by="ann", reviewer="bob", decision="approve",
    decided_at=at, approved_sha256=digest,
)
event = DraftEvent(
    draft_id=draft.draft_id, seq=1, event_type="approved", actor="bob", at=at,
    from_status="ready_for_review", to_status="approved_for_export",
)
bundle = build_bundle(draft, [event])
with zipfile.ZipFile(io.BytesIO(bundle.data)) as archive:
    members = {name: archive.read(name).decode("utf-8") for name in archive.namelist()}
fixture = {
    "oracle": "CPython 3.12; application.program_drafts.bundle.build_bundle",
    "input": {
        "id": draft.draft_id, "code": draft.proposed_code, "name": draft.name, "state": draft.state,
        "at": at.isoformat(), "pack": pack, "years": years, "validation": validation,
        "content_sha256": digest,
    },
    "members": members,
}
Path(__file__).with_name("bundle-oracle.json").write_text(json.dumps(fixture, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
