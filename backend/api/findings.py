"""Agent findings — what an agent noticed, and what a human decided.

Replaces the Agent Workbench's registry listing. A list of registered agents is
topology; a finding is a judgement that changes a number on a filed return, and
it has to reach a human and carry their answer back.

The pattern is the one the app already gets right in One/Zero's test-of-twos
review: surface an exception **at the point where it affects the answer**,
attached to the employees it affects, with a decision attached. This generalises
that rather than inventing something new.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from api.auth import attributed
from pydantic import BaseModel, Field

from application.commands.resolve_finding import (
    InvalidResolution,
    ReopenFindingCommand,
    ResolveFindingCommand,
)
from application.queries import list_findings
from application.queries.list_findings import FindingsNotAvailable, ListFindingsQuery
from bootstrap.wiring import get_finding_repository, get_mediator, set_finding_repository
from infrastructure.persistence.sqlite_findings import (
    FindingResolution,
    SqliteFindingRepository,
)

router = APIRouter(prefix="/api/findings", tags=["findings"])

_REPO: SqliteFindingRepository | None = None


def get_repository() -> SqliteFindingRepository:
    """The finding store. Composition lives in `bootstrap.wiring`. [ADR-002]"""
    return get_finding_repository()


def set_repository(repo: Any) -> None:
    """Point the application at another adapter. Used by tests."""
    set_finding_repository(repo)


# What each kind of finding means, what an agent proposes, and the GRAIN a human
# decides at now live in `application/queries/list_findings`. The underscore
# names stay because the findings tests and the resolve command read them here.
_KINDS = list_findings.KINDS
_RESOLUTIONS = ("accept", "assign", "drop", "flag")
_SAMPLE_SIZE = list_findings.SAMPLE_SIZE
_DOMINANCE = list_findings.DOMINANCE
_INSTANCE_CAP = list_findings.INSTANCE_CAP
_is_ambiguous = list_findings.is_ambiguous
_dominant_unit = list_findings.dominant_unit
_finding_id = list_findings.finding_id
_policy_finding_id = list_findings.policy_finding_id
_roll_up_policy = list_findings.roll_up_policy


class ResolveBody(BaseModel):
    client_id: int
    tax_year: int
    resolution: str = Field(pattern="^(accept|assign|drop|flag)$")
    #: Ignored when the caller is authenticated: the token names the author.
    decided_by: str | None = None
    # For `assign`: which worksite the employee is kept at.
    keep_worksite: str | None = None
    note: str | None = None


@router.get("/{client_id}/{tax_year}")
def findings(client_id: int, tax_year: int, state: str | None = None) -> dict[str, Any]:
    """Everything an agent found for one client-year, at the grain it is decided at.

    The grain rules live in `application/queries/list_findings`; this maps its
    one failure onto a status code.
    """
    try:
        return get_mediator().send(
            ListFindingsQuery(client_id=client_id, tax_year=tax_year, state=state)
        )
    except FindingsNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{finding_id}/resolve")
def resolve(finding_id: str, body: ResolveBody, request: Request = None) -> dict[str, Any]:
    """Record a human decision about a finding."""
    try:
        return get_mediator().send(
            ResolveFindingCommand(
                actor=attributed(request, body.decided_by),
                finding_id=finding_id,
                client_id=body.client_id,
                tax_year=body.tax_year,
                resolution=body.resolution,
                keep_worksite=body.keep_worksite,
                note=body.note,
            )
        )
    except InvalidResolution as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/{finding_id}/reopen")
def reopen(finding_id: str, body: ResolveBody, request: Request = None) -> dict[str, Any]:
    """Withdraw a decision, leaving the finding open again.

    The prior decision is closed rather than deleted: somebody decided something
    once, and that fact survives them changing their mind.
    """
    try:
        return get_mediator().send(
            ReopenFindingCommand(
                actor=attributed(request, body.decided_by),
                finding_id=finding_id,
                client_id=body.client_id,
            )
        )
    except InvalidResolution as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{client_id}/{finding_id}/history")
def history(client_id: int, finding_id: str) -> dict[str, Any]:
    """Every decision ever recorded against one finding."""
    return {
        "finding_id": finding_id,
        "history": [r.to_dict() for r in get_repository().history(client_id, finding_id)],
    }
