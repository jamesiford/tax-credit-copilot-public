"""How a draft is shown to the portal: its documents, validation, review record and what may be done next. [F05.3]

One shape for the list (no documents) and the detail. `has_runtime_authority` is always false and `verification` is always
`not_verified`: a draft is a proposal, and nothing here says its statute is right. [ADR-005]
"""
from __future__ import annotations

from typing import Any

from application.program_drafts.lifecycle import validation_is_current
from application.program_drafts.naming import pack_file_name
from domain.program_drafts import EDITABLE, DraftEvent, DraftStatus, ProgramDraft


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def allowed_actions(draft: ProgramDraft) -> list[str]:
    """What the draft can do now, so the portal enables exactly those buttons."""
    s, actions = draft.status, []
    if s in EDITABLE:
        actions += ["edit", "validate"]
        if validation_is_current(draft) and (draft.validation or {}).get("valid"):
            actions.append("request_review")
    if s is DraftStatus.READY_FOR_REVIEW:
        actions += ["approve", "request_changes"]
    if s in (DraftStatus.APPROVED_FOR_EXPORT, DraftStatus.EXPORTED):
        actions.append("export")
    if s is not DraftStatus.WITHDRAWN and draft.pack is not None:
        actions.append("preview")
    if s not in (DraftStatus.WITHDRAWN, DraftStatus.EXPORTED):
        actions.append("withdraw")
    return actions


def summary_view(draft: ProgramDraft) -> dict[str, Any]:
    validation = draft.validation
    return {
        "draft_id": draft.draft_id, "proposed_code": draft.proposed_code, "name": draft.name,
        "jurisdiction_level": draft.jurisdiction_level, "state": draft.state, "status": draft.status.value, "version": draft.version,
        "created_by": draft.created_by, "created_at": _iso(draft.created_at), "updated_by": draft.updated_by,
        "updated_at": _iso(draft.updated_at), "pack_file": pack_file_name(draft),
        "validation_errors": None if validation is None else validation.get("errors"),
        "verification": "not_verified", "has_runtime_authority": False,
    }


def draft_view(draft: ProgramDraft) -> dict[str, Any]:
    return {
        **summary_view(draft),
        "documents": {"pack": draft.pack, "years": draft.years}, "content_sha256": draft.content_sha256,
        "validation": draft.validation, "validation_current": validation_is_current(draft),
        "review": {"requested_by": draft.review_requested_by, "reviewer": draft.reviewer, "decision": draft.decision,
                   "comment": draft.decision_comment, "decided_at": _iso(draft.decided_at), "approved_sha256": draft.approved_sha256},
        "export": {"exported_at": _iso(draft.exported_at), "bundle_sha256": draft.export_sha256},
        "allowed_actions": allowed_actions(draft),
    }


def event_view(event: DraftEvent) -> dict[str, Any]:
    return {"seq": event.seq, "event_type": event.event_type, "actor": event.actor, "at": _iso(event.at),
            "from_status": event.from_status, "to_status": event.to_status, "detail": event.detail}
