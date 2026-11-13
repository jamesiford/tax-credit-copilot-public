"""Program drafts: propose a new program, validate it, review it and export it. [F05, ADR-013, ADR-005]

Thin: parse, dispatch through the mediator, shape the answer, with typed bodies and responses. Every route needs the writer
role (the policy is on the command or query itself) and every change is audited with the actor. A draft has **no runtime
authority**: nothing here activates statute. The only route to a calculable program is a person committing the exported files.
A refusal is a 4xx whose `detail` carries `code` and `reason`, so the portal can show what to change.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from api._rate_limit import rate_limited
from api.auth import attributed
from api.program_draft_models import (
    ActorBody, CreateBody, DraftOut, DraftsPage, EditBody, ExportBody, ManifestOut, PreviewBody, PreviewOut, ReviewBody, WithdrawBody,
)
from application.commands.create_program_draft import CreateProgramDraftCommand
from application.commands.edit_program_draft import EditProgramDraftCommand
from application.commands.export_program_draft import ExportProgramDraftCommand
from application.commands.request_program_review import RequestProgramReviewCommand
from application.commands.review_program_draft import ReviewProgramDraftCommand
from application.commands.validate_program_draft import ValidateProgramDraftCommand
from application.commands.withdraw_program_draft import WithdrawProgramDraftCommand
from application.queries.preview_program_draft import PreviewProgramDraftQuery
from application.queries.program_draft_reads import GetProgramDraftManifestQuery, GetProgramDraftQuery, ListProgramDraftsQuery
from application.services import get_mediator
from domain.program_drafts import (
    CustomerDataRefused, DraftConflict, DraftError, DraftInvalid, DraftNotFound, InvalidTransition, PreviewRefused, ReviewRefused,
)

router = APIRouter(prefix="/api/v2/program-drafts", tags=["program-drafts"])

_STATUS = {DraftNotFound: 404, DraftConflict: 409, InvalidTransition: 409, DraftInvalid: 422, ReviewRefused: 422,
           PreviewRefused: 422, CustomerDataRefused: 403}


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


@router.put("/{draft_id}/documents", response_model=DraftOut, dependencies=[Depends(rate_limited("draft_save"))])
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


@router.post("/{draft_id}/preview", response_model=PreviewOut, dependencies=[Depends(rate_limited("draft_preview"))])
def preview_draft(draft_id: str, body: PreviewBody | None = None) -> Any:
    """Price the draft's year packs on synthetic data with the engine's own functions. Reads only: nothing is written or stored."""
    body = body or PreviewBody()
    return _send(PreviewProgramDraftQuery(draft_id=draft_id, dataset=body.dataset, client_id=body.client_id, tax_years=tuple(body.tax_years)))


@router.post("/{draft_id}/withdraw", response_model=DraftOut)
def withdraw_draft(draft_id: str, request: Request, body: WithdrawBody | None = None) -> Any:
    return _send(WithdrawProgramDraftCommand(actor=_who(request, body.actor if body else None), draft_id=draft_id,
                                             reason=body.reason if body else None))


@router.post("/{draft_id}/export", response_class=Response, responses={200: {"content": {"application/zip": {}}}},
             dependencies=[Depends(rate_limited("draft_export"))])
def export_draft(draft_id: str, request: Request, body: ExportBody | None = None) -> Response:
    """Download the deterministic bundle of an approved draft (pack and year packs at their final paths, registry entry, validation,
    review record, commit checklist). Records the export; verifies nothing and activates nothing."""
    body = body or ExportBody()
    out = _send(ExportProgramDraftCommand(actor=_who(request, body.actor), draft_id=draft_id, write_local=body.write_local))
    code = out["draft"]["proposed_code"].lower()
    return Response(content=out["bundle"], media_type="application/zip", headers={
        "Content-Disposition": f'attachment; filename="{code}-bundle.zip"', "X-Bundle-Sha256": out["bundle_sha256"],
        "X-Verification": "not_verified", "X-Wrote-Local-Files": str(len(out["written_files"]))})


@router.get("/{draft_id}/export/manifest", response_model=ManifestOut)
def export_manifest(draft_id: str) -> Any:
    """The manifest of the bundle an approved or exported draft produces, with no status change."""
    return _send(GetProgramDraftManifestQuery(draft_id=draft_id))
