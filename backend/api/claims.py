"""Program claims: coverage, decisions, and the matrix B4 renders.

Thin. The lifecycle rules live in `domain/claims.py` and the storage in
`infrastructure/persistence/`; this layer translates HTTP to those and back.

The endpoint that matters is the coverage matrix, and its shape follows one
rule from the data model: **a cell is a variance, not a status.** Claimed versus
unclaimed is too thin for a retroactive audit — the reading is what was claimed
against what we compute they were entitled to, and the sign decides whether it
is revenue or exposure.

Which means the totals are deliberately NOT a single net figure. Opportunity and
exposure are summed separately, because netting them would let a client's
over-claim silently cancel another's recoverable dollars and produce a headline
that is arithmetically true and completely misleading.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api.auth import attributed
from pydantic import BaseModel, Field

from application.commands.assess_client import AssessClientCommand, ClientHasNoPayroll
from application.queries import get_portfolio as portfolio
from application.queries.get_client_situation import (
    GetClientSituationQuery,
    SituationNotAvailable,
    with_client_name,
)
from application.queries.get_coverage import (
    ClaimNotFound,
    GetCellHistoryQuery,
    GetClientCoverageQuery,
    GetPortfolioCoverageQuery,
)
from application.wiring import get_claim_repository, get_mediator, set_claim_repository
from domain.claims import (
    ClaimError,
    ClaimStatus,
    EngagementScope,
    Outcome,
    ProgramClaim,
    ProgramEngagement,
    Provenance,
)
from domain.coverage import matrix, totals
from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

router = APIRouter(prefix="/api/claims", tags=["claims"])
v2_router = APIRouter(prefix="/api/v2", tags=["portfolio"])

_REPO: Any | None = None


def get_repository() -> Any:
    """The claim store. Composition lives in `application.wiring`. [ADR-002]

    Kept as a thin alias because the router and its tests already name it, and
    because a router asking the composition root for an adapter is the right
    direction of dependency — the reverse was not.
    """
    return get_claim_repository()


def set_repository(repo: Any) -> None:
    """Point the application at another adapter. Used by tests and by wiring."""
    set_claim_repository(repo)


# ------------------------------------------------------------------ payloads


class RecordClaimBody(BaseModel):
    """Assert a claim we did not compute — onboarding, or a prior provider."""

    client_id: int
    program_code: str
    tax_year: int
    status: ClaimStatus
    provenance: Provenance
    #: Ignored when the caller is authenticated: the token names the author.
    decided_by: str | None = None
    identified_usd: Decimal = Decimal("0")
    claimed_usd: Decimal = Decimal("0")
    certified_usd: Decimal = Decimal("0")
    average_headcount: float | None = None
    base_average_headcount: float | None = None
    threshold_jobs: float | None = None
    entity_id: int | None = None
    filing_reference: str | None = None
    decline_reason: str | None = None
    identified_run_id: str | None = None
    assumption_set_id: str | None = None
    rule_pack_version: str | None = None


class TransitionBody(BaseModel):
    """Move an existing cell along the lifecycle."""

    status: ClaimStatus
    #: Ignored when the caller is authenticated: the token names the author.
    decided_by: str | None = None
    decline_reason: str | None = None
    claimed_usd: Decimal | None = None
    certified_usd: Decimal | None = None
    filing_reference: str | None = None
    provenance: Provenance | None = None


class EngagementBody(BaseModel):
    client_id: int
    program_code: str
    scope: EngagementScope
    note: str | None = None


class AssessBody(BaseModel):
    """Run the engine over a client and record what it computes."""

    client_id: int
    program_code: str | None = None
    tax_years: list[int] | None = None
    assessed_by: str = Field(default="engine", min_length=1)


# ------------------------------------------------------------------- helpers


def _statutory_threshold(program_code: str) -> float | None:
    """The programme's minimum-new-jobs figure, or None if we hold no pack."""
    from tools.credit_math import PROGRAM_CODE_TO_PACK, _load_pack

    pack_file = PROGRAM_CODE_TO_PACK.get(program_code.upper())
    if not pack_file:
        return None
    try:
        pack = _load_pack(pack_file)
    except FileNotFoundError:
        return None
    value = (pack.get("thresholds") or {}).get("minimum_new_jobs")
    return float(value) if value is not None else None


# `_totals` and `_matrix` moved to domain/coverage.py. How a cell reads in the
# light of the engagement we hold is a business rule, and it must be identical
# whether it reaches a screen, a report or an export.
_totals = totals
_matrix = matrix


# -------------------------------------------------------------------- routes


@router.get("/coverage/{client_id}")
def client_coverage(
    client_id: int,
    program_code: str | None = None,
    tax_year: int | None = None,
    tax_years: list[int] | None = Query(default=None),
) -> dict[str, Any]:
    """One client's coverage: the program x year grid rendered at account scope."""
    years = tuple(tax_years) if tax_years else ((tax_year,) if tax_year else ())
    return get_mediator().send(
        GetClientCoverageQuery(
            client_id=client_id, program_code=program_code, tax_years=years
        )
    )


@router.get("/coverage")
def portfolio_coverage(tax_year: int | None = None) -> dict[str, Any]:
    """Every client's coverage — the portfolio matrix."""
    return get_mediator().send(GetPortfolioCoverageQuery(tax_year=tax_year))


# The portfolio read moved to `application/queries/get_portfolio`. These names
# stay module-level because `portfolio_v2` passes them in as the seams its tests
# have always patched (`_client_book`, `_footprint`, `_priceable_states`).
_effective_outcome = portfolio.effective_outcome
_portfolio_sort_key = portfolio.portfolio_sort_key
_portfolio_sort_value = portfolio.portfolio_sort_value
_client_book = portfolio.client_book_rows
_footprint = portfolio.footprint
_priceable_states = portfolio.priceable_states


@v2_router.get("/portfolio")
def portfolio_v2(
    year: int | None = Query(default=None),
    program: str | None = Query(default=None),
    outcome: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    near: bool | None = Query(default=None),
    status: str | None = Query(default=None),
    sort: str = Query(default="priority"),
    order: str = Query(default="asc"),
    limit: int = Query(default=25, ge=1),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """General-purpose portfolio instrument: filter and sort one row per client.

    The page-level question is "who do I call?" not "what cell is this?". This
    endpoint therefore returns the most actionable cell for each client and lets
    the caller decide which book view it is looking at via the same filters used
    for the saved views: outcome, engagement scope, near-threshold, status, year,
    and program.

    EVERY CLIENT IN THE BOOK APPEARS, including ones no run has reached yet.
    A client absent from the page whose stated job is "who do I call" is the one
    client you can be certain nobody calls. Northwind has real payroll and five
    locations and used to be invisible here purely because no run had written a
    claim for it.

    Not-yet-assessed rows carry NULL money rather than zero. Zero reads as "we
    looked and found nothing"; null reads as "the pipeline has not reached this
    yet", and those must not render alike. They sort as a block after the ranked
    rows because they hold no figure to rank on, and the response reports
    `assessed_clients` against `total_clients` so coverage is visible before
    anyone scrolls. That counter is a DIAGNOSTIC: under the pipeline model a
    client sitting unassessed is a gap to close, not a bucket it belongs in.
    """
    return portfolio.portfolio_page(
        year=year, program=program, outcome=outcome, scope=scope, near=near,
        status=status, sort=sort, order=order, limit=limit, offset=offset,
        # Looked up on this module at call time, so the seams tests patch hold.
        book=_client_book, states=_footprint, priceable=_priceable_states,
    )


@router.get("/cell/{client_id}/{program_code}/{tax_year}")
def cell_history(client_id: int, program_code: str, tax_year: int) -> dict[str, Any]:
    """One cell and everything that ever happened to it."""
    try:
        return get_mediator().send(
            GetCellHistoryQuery(
                client_id=client_id, program_code=program_code, tax_year=tax_year
            )
        )
    except ClaimNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", status_code=201)
def record_claim(body: RecordClaimBody, request: Request = None) -> dict[str, Any]:
    """Record a claim directly — onboarding assertions and inherited records."""
    try:
        claim = ProgramClaim(
            client_id=body.client_id,
            program_code=body.program_code,
            tax_year=body.tax_year,
            status=body.status,
            provenance=body.provenance,
            identified_usd=body.identified_usd,
            claimed_usd=body.claimed_usd,
            certified_usd=body.certified_usd,
            average_headcount=body.average_headcount,
            base_average_headcount=body.base_average_headcount,
            threshold_jobs=body.threshold_jobs if body.threshold_jobs is not None else (
                # Default to the programme's statutory minimum so a caller
                # supplying headcounts alone still gets a real gap.
                _statutory_threshold(body.program_code)
                if body.average_headcount is not None else None
            ),
            entity_id=body.entity_id,
            filing_reference=body.filing_reference,
            decline_reason=body.decline_reason,
            identified_run_id=body.identified_run_id,
            assumption_set_id=body.assumption_set_id,
            rule_pack_version=body.rule_pack_version,
            decided_by=attributed(request, body.decided_by),
        )
    except ClaimError as exc:
        # A domain rejection is the caller's error, not a server fault.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return get_repository().record(claim).to_dict()


@router.post("/cell/{client_id}/{program_code}/{tax_year}/transition")
def transition_cell(
    client_id: int, program_code: str, tax_year: int, body: TransitionBody, request: Request = None
) -> dict[str, Any]:
    """Move a cell along the lifecycle, appending to its history."""
    repo = get_repository()
    current = repo.current(client_id, program_code, tax_year)
    if current is None:
        raise HTTPException(
            status_code=404,
            detail=f"No claim recorded for client {client_id}, {program_code.upper()}, TY{tax_year}.",
        )
    try:
        nxt = current.transition_to(
            body.status,
            decided_by=attributed(request, body.decided_by),
            decline_reason=body.decline_reason,
            claimed_usd=body.claimed_usd,
            certified_usd=body.certified_usd,
            filing_reference=body.filing_reference,
            provenance=body.provenance,
        )
    except ClaimError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return repo.record(nxt).to_dict()


@router.put("/engagement")
def set_engagement(body: EngagementBody, request: Request = None) -> dict[str, Any]:
    """Declare whether a program is our mandate for this client."""
    engagement = ProgramEngagement(
        client_id=body.client_id,
        program_code=body.program_code,
        scope=body.scope,
        note=body.note,
        set_by=attributed(request, None),
        set_at=datetime.now(timezone.utc),
    )
    return get_repository().set_engagement(engagement).to_dict()


@router.post("/assess")
def assess(body: AssessBody, request: Request = None) -> dict[str, Any]:
    """Run the engine over a client and record each programme-year it can price.

    This is what turns the coverage matrix from "unknown" into a computed
    artifact. Years with no authored statute are **declined by name** rather
    than estimated from a neighbouring year [ADR-005].
    """
    try:
        return get_mediator().send(
            AssessClientCommand(
                actor=attributed(request, body.assessed_by, default="engine"),
                client_id=body.client_id,
                program_code=body.program_code,
                tax_years=tuple(body.tax_years or ()),
            )
        )
    except ClientHasNoPayroll as exc:
        # A named client with no rows is a different fact from an absent
        # dataset, and must never fall through to another client's payroll.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@v2_router.get("/clients/{client_id}/situation")
def client_situation(client_id: int, year: int | None = Query(default=None)) -> dict[str, Any]:
    """Why you would call this client, ranked, and what to say.

    The brief behind Ask Copilot. Deterministic: it reads recorded coverage and
    orders it by `PriorityBand`, touching no payroll and running no engine, so
    a per-row button costs a query rather than a replay.

    The agent is handed this object and narrates it. It cannot add a figure to
    it because it never sees anything else [ADR-004].
    """
    try:
        body = get_mediator().send(GetClientSituationQuery(client_id=client_id, tax_year=year))
    except SituationNotAvailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return with_client_name(body, client_id, _client_book)


@router.get("/lifecycle")
def lifecycle() -> dict[str, Any]:
    """The vocabulary, so the UI does not hardcode its own copy of it."""
    return {
        "statuses": [
            {"value": s.value, "is_claimed": s.is_claimed} for s in ClaimStatus
        ],
        "provenance": [
            {"value": p.value, "verified": p.verified} for p in Provenance
        ],
        "outcomes": [o.value for o in Outcome],
        "engagement_scopes": [e.value for e in EngagementScope],
    }
