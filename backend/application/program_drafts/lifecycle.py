"""The draft lifecycle: create, edit, validate, request review, review, withdraw. [F05.3, ADR-013, ADR-005]

Plain functions over a `ProgramDraftRepository`, so the rules live in one place and the commands stay thin. Every change is
one `save` that names the version it read and appends its audit event in the same transaction. Nothing here touches the rules
folder or the registry: a draft is a proposal, and statute only arrives when a human commits the exported files. [ADR-005]
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from application.program_drafts.validation import for_storage, validate_draft
from config import get_settings
from domain.program_drafts import (
    CODE_PATTERN, EDITABLE, MAX_DOCUMENT_CHARS, DraftConflict, DraftEvent, DraftInvalid, DraftNotFound, DraftStatus,
    InvalidTransition, ProgramDraft, ProgramDraftRepository, ReviewRefused, canonical_json,
)

_STATE = re.compile(r"^[A-Z]{2}$")
_YEAR = re.compile(r"^\d{4}$")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def load(repo: ProgramDraftRepository, draft_id: str) -> ProgramDraft:
    draft = repo.get(draft_id)
    if draft is None:
        raise DraftNotFound(f"no draft {draft_id!r}")
    return draft


def _event(draft: ProgramDraft, kind: str, actor: str, at: datetime, to: DraftStatus | None = None, **detail: Any) -> DraftEvent:
    return DraftEvent(draft_id=draft.draft_id, seq=0, event_type=kind, actor=actor, at=at, from_status=draft.status.value,
                      to_status=(to or draft.status).value, detail=detail)


def _check_documents(pack: Any, years: Any) -> None:
    """Refuse a document that is not an object or will not fit, by name, before the store sees it."""
    if pack is not None and not isinstance(pack, dict):
        raise DraftInvalid("the base pack must be a JSON object")
    if not isinstance(years, dict) or any(not _YEAR.match(str(k)) or not isinstance(v, dict) for k, v in years.items()):
        raise DraftInvalid("years must be an object of four-digit tax years, each a JSON object")
    for key, doc in (("pack", pack), *years.items()):
        if doc is not None and len(canonical_json(doc)) > MAX_DOCUMENT_CHARS:
            raise DraftInvalid(f"document {key!r} is larger than {MAX_DOCUMENT_CHARS} characters; split the notes out or shorten it")


def create(repo: ProgramDraftRepository, *, code: str, name: str, state: str, years: list[int], actor: str,
           at: datetime | None = None) -> ProgramDraft:
    """A new draft from the scaffold template: every statutory value `null` and flagged, so it fails validation until filled in."""
    from tools.program_registry import load_registry
    from tools.program_scaffold import base_pack, year_pack

    code, state, name = code.strip().upper(), state.strip().upper(), name.strip()
    if not CODE_PATTERN.match(code):
        raise DraftInvalid("a program code is upper case letters, digits and underscores, starting with a letter (for example ZZ_DEMO_JTC)")
    if not _STATE.match(state):
        raise DraftInvalid("a state is its two-letter code; a federal program is not runnable yet and cannot be drafted")
    if not name:
        raise DraftInvalid("a program needs a name")
    if load_registry().get(code) is not None:
        raise DraftConflict(f"{code} is already registered; a draft proposes a NEW program")
    if repo.live_for_code(code) is not None:
        raise DraftConflict(f"a draft for {code} is already open")
    now = at or _now()
    pack = base_pack(code, state, name)
    skeletons = {str(y): year_pack(pack, int(y)) for y in sorted(set(years))}
    draft = ProgramDraft(draft_id=uuid.uuid4().hex, proposed_code=code, name=name, jurisdiction_level="state", state=state,
                         status=DraftStatus.DRAFT, version=1, created_by=actor, created_at=now, updated_by=actor, updated_at=now,
                         pack=pack, years=skeletons)
    _check_documents(draft.pack, draft.years)
    repo.create(draft, _event(draft, "created", actor, now, years=sorted(skeletons)))
    return draft


def edit(repo: ProgramDraftRepository, draft_id: str, expected_version: int, documents: tuple[dict[str, Any] | None, dict[str, dict[str, Any]]],
         actor: str, name: str | None = None, at: datetime | None = None) -> ProgramDraft:
    """Replace the documents (`(pack, years)`) wholesale; the caller names the version it read. Allowed only while the draft is editable."""
    pack, years = documents
    draft = load(repo, draft_id)
    if draft.version != expected_version:
        raise DraftConflict(f"draft {draft_id} is at version {draft.version}, not {expected_version}; reload it")
    if draft.status not in EDITABLE:
        raise InvalidTransition(f"a draft that is {draft.status.value} cannot be edited; request changes or withdraw it first")
    _check_documents(pack, years)
    now = at or _now()
    changed = draft.with_changes(pack=pack, years={str(k): v for k, v in years.items()}, name=(name or draft.name).strip() or draft.name,
                                 status=DraftStatus.DRAFT, version=draft.version + 1, updated_by=actor, updated_at=now)
    repo.save(changed, draft.version, _event(draft, "edited", actor, now, DraftStatus.DRAFT, content_sha256=changed.content_sha256))
    return changed


def validate(repo: ProgramDraftRepository, draft_id: str, actor: str, at: datetime | None = None) -> tuple[ProgramDraft, dict[str, Any]]:
    """Validate the stored documents; errors move the draft to `needs_changes`, a clean result leaves it `draft`, ready to submit."""
    draft = load(repo, draft_id)
    if draft.status not in EDITABLE:
        raise InvalidTransition(f"a draft that is {draft.status.value} is not validated again; its review is tied to the documents it holds")
    now, result = at or _now(), validate_draft(draft)
    target = DraftStatus.DRAFT if result["valid"] else DraftStatus.NEEDS_CHANGES
    changed = draft.with_changes(validation=for_storage(result), status=target, version=draft.version + 1, updated_by=actor, updated_at=now)
    repo.save(changed, draft.version, _event(draft, "validated", actor, now, target, errors=result["errors"], warnings=result["warnings"],
                                             content_sha256=result["content_sha256"]))
    return changed, result


def validation_is_current(draft: ProgramDraft) -> bool:
    """Whether the stored validation covered exactly the documents the draft holds now."""
    return bool(draft.validation) and draft.validation.get("content_sha256") == draft.content_sha256


def request_review(repo: ProgramDraftRepository, draft_id: str, actor: str, at: datetime | None = None) -> ProgramDraft:
    """Submit for review: only a draft whose CURRENT documents validated with no errors."""
    draft = load(repo, draft_id)
    if draft.status not in EDITABLE:
        raise InvalidTransition(f"a draft that is {draft.status.value} cannot be submitted for review")
    if not validation_is_current(draft):
        raise ReviewRefused("validate the draft first: the documents changed since the last validation, or it was never validated")
    if not draft.validation["valid"]:
        raise ReviewRefused(f"the draft has {draft.validation['errors']} validation error(s); fix them before asking for review")
    now = at or _now()
    changed = draft.with_changes(status=DraftStatus.READY_FOR_REVIEW, review_requested_by=actor, version=draft.version + 1,
                                 updated_by=actor, updated_at=now)
    repo.save(changed, draft.version, _event(draft, "review_requested", actor, now, DraftStatus.READY_FOR_REVIEW))
    return changed


def _authors(repo: ProgramDraftRepository, draft: ProgramDraft) -> set[str]:
    """Everyone who created, edited or submitted the draft: the people who may not review it."""
    return {e.actor for e in repo.events(draft.draft_id) if e.event_type in ("created", "edited", "review_requested")}


def _guard_review(repo: ProgramDraftRepository, draft: ProgramDraft, actor: str, decision: str, comment: str | None) -> None:
    """Every refusal a review can meet, in the order a person would want them explained."""
    if draft.status is not DraftStatus.READY_FOR_REVIEW:
        raise InvalidTransition(f"only a draft that is ready for review can be reviewed (this one is {draft.status.value})")
    if decision not in ("approve", "request_changes"):
        raise DraftInvalid("a decision is approve or request_changes")
    if decision == "request_changes" and not (comment or "").strip():
        raise DraftInvalid("say what must change: a request for changes needs a comment")
    if get_settings().programs.draft_require_second_reviewer and actor in _authors(repo, draft):
        raise ReviewRefused("the reviewer must differ from the people who wrote and submitted the draft (PROGRAM_DRAFT_REQUIRE_SECOND_REVIEWER)")
    if decision == "approve" and not validation_is_current(draft):
        raise ReviewRefused("the documents changed since validation; it cannot be approved")


def review(repo: ProgramDraftRepository, draft_id: str, actor: str, decision: str, comment: str | None,
           at: datetime | None = None) -> ProgramDraft:
    """Approve for export, or send back with a comment. The reviewer must not be an author when a second reviewer is required."""
    draft = load(repo, draft_id)
    _guard_review(repo, draft, actor, decision, comment)
    now, approve = at or _now(), decision == "approve"
    target = DraftStatus.APPROVED_FOR_EXPORT if approve else DraftStatus.NEEDS_CHANGES
    changed = draft.with_changes(status=target, reviewer=actor, decision=decision, decision_comment=(comment or "").strip() or None,
                                 decided_at=now, approved_sha256=draft.content_sha256 if approve else None,
                                 version=draft.version + 1, updated_by=actor, updated_at=now)
    repo.save(changed, draft.version, _event(draft, "approved" if approve else "changes_requested", actor, now, target,
                                             comment=changed.decision_comment))
    return changed

def withdraw(repo: ProgramDraftRepository, draft_id: str, actor: str, reason: str | None = None, at: datetime | None = None) -> ProgramDraft:
    """Close a draft that will not go ahead. An exported draft cannot be withdrawn: its files may already be committed."""
    draft = load(repo, draft_id)
    if draft.status in (DraftStatus.WITHDRAWN, DraftStatus.EXPORTED):
        raise InvalidTransition(f"a draft that is {draft.status.value} cannot be withdrawn")
    now = at or _now()
    changed = draft.with_changes(status=DraftStatus.WITHDRAWN, version=draft.version + 1, updated_by=actor, updated_at=now)
    repo.save(changed, draft.version, _event(draft, "withdrawn", actor, now, DraftStatus.WITHDRAWN, reason=(reason or "").strip() or None))
    return changed
