"""Program drafts: propose a new program, validate it, review it and export it. [F05, ADR-013, ADR-005]

Thin: parse, dispatch through the mediator, shape the answer, with typed bodies and responses. Every route needs the writer
role (the policy is on the command or query itself) and every change is audited with the actor. A draft has **no runtime
authority**: nothing here activates statute. The only route to a calculable program is a person committing the exported files.
A refusal is a 4xx whose `detail` carries `code` and `reason`, so the portal can show what to change.
"""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from api.auth import attributed
from application.commands.create_program_draft import CreateProgramDraftCommand
from application.commands.edit_program_draft import EditProgramDraftCommand
from application.commands.request_program_review import RequestProgramReviewCommand
from application.commands.review_program_draft import ReviewProgramDraftCommand
from application.commands.validate_program_draft import ValidateProgramDraftCommand
from application.commands.withdraw_program_draft import WithdrawProgramDraftCommand
from application.queries.program_draft_reads import GetProgramDraftQuery, ListProgramDraftsQuery
from application.services import get_mediator
from domain.program_drafts import (
    DraftConflict, DraftError, DraftInvalid, DraftNotFound, InvalidTransition, ReviewRefused,
)

router = APIRouter(prefix="/api/v2/program-drafts", tags=["program-drafts"])

_STATUS = {DraftNotFound: 404, DraftConflict: 409, InvalidTransition: 409, DraftInvalid: 422, ReviewRefused: 422}


class Finding(BaseModel):
    """One validation finding, addressed to a field: `file` names the document, `path` the place inside it."""
    file: str
    severity: str
    code: str
    path: str
    message: str


class ValidationOut(BaseModel):
    """A validation result. `valid` means well-formed, never verified; `content_sha256` says which documents it covered."""
    content_sha256: str
    valid: bool
    errors: int
    warnings: int
    infos: int
    findings: list[Finding]
    truncated: bool
    verification: str


class ReviewRecord(BaseModel):
    """Who asked for review, who decided, and what they said."""
    requested_by: str | None
    reviewer: str | None
    decision: str | None
    comment: str | None
    decided_at: str | None
    approved_sha256: str | None


class ExportRecord(BaseModel):
    """When the bundle was first exported and its SHA-256."""
    exported_at: str | None
    bundle_sha256: str | None


class EventOut(BaseModel):
    """One append-only audit row."""
    seq: int
    event_type: str
    actor: str
    at: str | None
    from_status: str | None
    to_status: str | None
    detail: dict[str, Any]


class DraftSummary(BaseModel):
    """A draft without its documents, as the list shows it."""
    draft_id: str
    proposed_code: str
    name: str
    jurisdiction_level: str
    state: str | None
    status: str
    version: int
    created_by: str
    created_at: str | None
    updated_by: str
    updated_at: str | None
    pack_file: str
    validation_errors: int | None
    verification: str
    has_runtime_authority: bool


class DraftOut(DraftSummary):
    """A draft in full. `allowed_actions` is what may be done now, so the portal enables exactly those."""
    documents: dict[str, Any]
    content_sha256: str
    validation: ValidationOut | None
    validation_current: bool
    review: ReviewRecord
    export: ExportRecord
    allowed_actions: list[str]
    events: list[EventOut] = Field(default_factory=list)


class DraftsPage(BaseModel):
    """One page of drafts, most recently changed first."""
    items: list[DraftSummary]
    total: int
    limit: int
    offset: int


class CreateBody(BaseModel):
    """Propose a program. A federal program is not runnable yet, so a draft needs a two-letter state."""
    code: str
    name: str
    state: str
    years: list[int] = Field(default_factory=list, description="Tax years to scaffold as empty, flagged year packs.")
    actor: str | None = Field(None, description="Used only when the caller is not signed in (local development).")


class EditBody(BaseModel):
    """A full replace of the documents. `expected_version` is the version the editor read."""
    expected_version: int
    pack: dict[str, Any] | None
    years: dict[str, dict[str, Any]] = Field(default_factory=dict)
    name: str | None = None
    actor: str | None = None


class ActorBody(BaseModel):
    """A request with no fields of its own."""
    actor: str | None = None


class ReviewBody(BaseModel):
    """A reviewer's decision. A request for changes needs a comment."""
    decision: Literal["approve", "request_changes"]
    comment: str | None = None
    actor: str | None = None


class WithdrawBody(BaseModel):
    """Why the draft is being withdrawn (optional)."""
    reason: str | None = None
    actor: str | None = None


def _send(request: Any) -> Any:
    try:
        return get_mediator().send(request)
    except DraftError as exc:
        raise HTTPException(status_code=_STATUS.get(type(exc), 422), detail={"code": exc.code, "reason": str(exc)}) from exc


def _who(request: Request, supplied: str | None) -> str:
    return attributed(request, supplied, default="anonymous")


@router.get("", response_model=DraftsPage)
def list_drafts(status: str | None = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)) -> Any:
    return _send(ListProgramDraftsQuery(status=status, limit=limit, offset=offset))


@router.post("", response_model=DraftOut, status_code=201)
def create_draft(body: CreateBody, request: Request) -> Any:
    """Start a draft from the scaffold template: every statutory value empty and flagged, so it fails validation until filled in."""
    return _send(CreateProgramDraftCommand(actor=_who(request, body.actor), code=body.code, name=body.name, state=body.state,
                                           years=tuple(body.years)))


@router.get("/{draft_id}", response_model=DraftOut)
def get_draft(draft_id: str) -> Any:
    return _send(GetProgramDraftQuery(draft_id=draft_id))


@router.put("/{draft_id}/documents", response_model=DraftOut)
def edit_documents(draft_id: str, body: EditBody, request: Request) -> Any:
    """Replace the documents. A stale `expected_version` is a 409; a draft under review cannot be edited."""
    return _send(EditProgramDraftCommand(actor=_who(request, body.actor), draft_id=draft_id, expected_version=body.expected_version,
                                         pack=body.pack, years=body.years, name=body.name))


@router.post("/{draft_id}/validate", response_model=DraftOut)
def validate_draft(draft_id: str, request: Request, body: ActorBody | None = None) -> Any:
    """Validate the stored documents: schema, supported models, identity and citations. Valid is not verified."""
    return _send(ValidateProgramDraftCommand(actor=_who(request, body.actor if body else None), draft_id=draft_id))


@router.post("/{draft_id}/request-review", response_model=DraftOut)
def request_review(draft_id: str, request: Request, body: ActorBody | None = None) -> Any:
    return _send(RequestProgramReviewCommand(actor=_who(request, body.actor if body else None), draft_id=draft_id))


@router.post("/{draft_id}/review", response_model=DraftOut)
def review_draft(draft_id: str, body: ReviewBody, request: Request) -> Any:
    """Approve for export or request changes. Approval activates nothing and verifies nothing."""
    return _send(ReviewProgramDraftCommand(actor=_who(request, body.actor), draft_id=draft_id, decision=body.decision, comment=body.comment))


@router.post("/{draft_id}/withdraw", response_model=DraftOut)
def withdraw_draft(draft_id: str, request: Request, body: WithdrawBody | None = None) -> Any:
    return _send(WithdrawProgramDraftCommand(actor=_who(request, body.actor if body else None), draft_id=draft_id,
                                             reason=body.reason if body else None))
