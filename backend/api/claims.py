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

import os
from collections import defaultdict
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from api.auth import attributed
from pydantic import BaseModel, Field

from application.commands.assess_client import AssessClientCommand, ClientHasNoPayroll
from application.queries.get_client_situation import (
    GetClientSituationQuery,
    SituationNotAvailable,
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
    PriorityBand,
    ProgramClaim,
    ProgramEngagement,
    Provenance,
    declining_reading,
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


def _effective_outcome(claim, engagements: dict[str, EngagementScope]) -> str:
    scope = engagements.get(claim.program_code)
    if scope is EngagementScope.OUT_OF_SCOPE and claim.outcome in {
        Outcome.UNCLAIMED,
        Outcome.NOT_ASSESSED,
    }:
        return Outcome.OUT_OF_SCOPE.value
    return claim.outcome.value


def _portfolio_sort_key(sort: str) -> str:
    aliases = {
        "priority": "priority",
        "band": "priority",
        "gap_jobs": "jobs_to_threshold",
        "jobs_gap": "jobs_to_threshold",
        "jobs_to_threshold": "jobs_to_threshold",
        "jobs_margin": "jobs_margin",
        "margin": "jobs_margin",
        "variance": "variance_usd",
        "variance_usd": "variance_usd",
        "opportunity": "opportunity_usd",
        "opportunity_usd": "opportunity_usd",
        "identified": "identified_usd",
        "identified_usd": "identified_usd",
        "claimed_usd": "claimed_usd",
        "tax_year": "tax_year",
        "client_id": "client_id",
        "client": "client_id",
        "status": "status",
    }
    return aliases.get((sort or "").lower(), (sort or "priority").lower())


def _portfolio_sort_value(item: dict[str, Any], sort: str, order: str) -> float:
    field = _portfolio_sort_key(sort)
    if field == "priority":
        # Ascending rank IS descending priority, so the caller asks for `asc`.
        # Within a band, bigger money first — once the kind of conversation is
        # fixed, size is the only comparable thing left.
        rank = float(item.get("priority_rank") if item.get("priority_rank") is not None else 99)
        identified = float(item.get("identified_usd") or 0)
        return rank - min(identified / 1e12, 0.999)
    if field == "jobs_to_threshold":
        value = item.get("gap_jobs")
        if value is None:
            return float("-inf") if order.lower() == "desc" else float("inf")
        return float(value)
    if field == "jobs_margin":
        value = item.get("jobs_margin")
        if value is None:
            return float("-inf") if order.lower() == "desc" else float("inf")
        return float(value)
    if field in {"variance_usd", "opportunity_usd", "identified_usd", "claimed_usd"}:
        value = item.get(field)
        if value is None:
            return float("-inf") if order.lower() == "desc" else float("inf")
        return float(value)
    if field == "tax_year":
        return float(item.get("tax_year") or 0)
    if field == "client_id":
        return float(item.get("client_id") or 0)
    if field == "status":
        return float(len(item.get("status") or ""))
    return 0.0


def _client_book() -> list[dict[str, Any]]:
    """Every client we hold payroll for, assessed or not.

    Imported from the scope router rather than re-read, because a second reader
    is a second answer to "who are our clients". Degrades to an empty book if the
    source is unreachable: the portfolio still renders what it has rather than
    failing whole, and an absent book understates the client count rather than
    inventing one.
    """
    try:
        from api.scope import _clients

        return _clients()
    except Exception:  # noqa: BLE001 - a missing book must not take the page down
        return []


def _default_program_code(program: str | None, engagements: dict[str, EngagementScope]) -> str | None:
    """Which programme an unassessed client should be reported against.

    In order: the one the caller filtered to, the one we are engaged on, or the
    sole calculable programme. Returns None when the answer is genuinely
    ambiguous — several programmes and nothing to choose between them — because
    picking one arbitrarily would assert an engagement that does not exist.
    """
    if program:
        return program.upper()
    if engagements:
        return next(iter(engagements))
    try:
        from api.scope import _programs

        calculable = [p["program_code"] for p in _programs() if p.get("calculable")]
    except Exception:  # noqa: BLE001 - fall through to "unknown" rather than fail
        return None
    return calculable[0] if len(calculable) == 1 else None


def _unassessed_row(
    client: dict[str, Any],
    *,
    program: str | None,
    year: int | None,
    engagements: dict[str, EngagementScope],
) -> dict[str, Any] | None:
    """A client we have never run, as a first-class portfolio row.

    Synthesised from `ProgramClaim`'s own defaults rather than hand-built, so the
    row carries exactly the shape every other row does and `outcome` derives
    NOT_ASSESSED through the same property as everything else. A hand-rolled dict
    would drift from the domain the first time a field is added.

    Returns None when no programme can be named. The domain requires one, and it
    is right to: a claim against no programme is not a claim.
    """
    program_code = _default_program_code(program, engagements)
    if not program_code:
        return None
    claim = ProgramClaim(
        claim_id="",
        client_id=int(client["account_id"]),
        entity_id=None,
        program_code=program_code,
        tax_year=year or 0,
        status=ClaimStatus.NOT_ASSESSED,
    )
    scope = engagements.get(program_code)
    item = claim.to_dict()
    item["engagement_scope"] = scope.value if scope is not None else None
    item["effective_outcome"] = Outcome.NOT_ASSESSED.value
    item["gap_jobs"] = None
    item["one_more_job_qualifies"] = False
    item["client_name"] = client.get("name")
    # The figures are absent, not zero. A client with no run has no dollars to
    # report, and reporting 0 would read as "we looked and found nothing" —
    # which is a different, and wrong, statement.
    for field in ("identified_usd", "claimed_usd", "certified_usd", "variance_usd", "opportunity_usd"):
        item[field] = None
    return item


def _declining_overlay(client_claims: list[Any], chosen: Any) -> dict[str, Any]:
    """A falling headcount, read across the client's years rather than one cell.

    No single claim can carry this: "trending downward" is a statement about a
    series, and every row in the book is one cell. So the reading is taken over
    all of the client's claims and applied on top of the band the chosen cell
    already computed.

    It only ever applies DOWNWARD. `exposed` is a finding against a filed return
    and `on_the_line` is a threshold about to be crossed; both are facts, and
    this is a forecast, so neither may be displaced by it. What it does displace
    is `unclaimed_at_scale`, `not_assessed` and `settled` — and `settled` is the
    reading that matters, because a client shedding jobs for three years running
    currently reads as "nothing outstanding".
    """
    reading = declining_reading(client_claims)
    if reading is None:
        return {}
    out: dict[str, Any] = {"trend": reading}
    if chosen.priority_band.rank > PriorityBand.DECLINING.rank:
        out["priority_band"] = PriorityBand.DECLINING.value
        out["priority_rank"] = PriorityBand.DECLINING.rank
    return out


def _footprint() -> dict[int, list[str]]:
    """Payroll states for every client, in one scan.

    Degrades to an empty map for the same reason `_client_book` does: a book
    that cannot say where a client operates is still a usable book, and a map
    with nothing on it is a visibly weaker answer rather than a wrong one.
    """
    try:
        from infrastructure.persistence.source_sql import SourceSqlReader
        from tools.fabric_source import active_data_source

        if active_data_source() != "lakehouse":
            return {}
        reader = SourceSqlReader()
        if not reader.is_configured():
            return {}
        return reader.footprint()
    except Exception:  # noqa: BLE001 - a missing footprint must not take the page down
        return {}


def _priceable_states() -> set[str]:
    """States a rule pack can actually price.

    A state we hold payroll in but cannot price is a real gap in statutory
    coverage, and the map is the one screen that shows it. Deriving the set here
    keeps the two halves of that distinction from being authored twice.
    """
    try:
        from tools.credit_math import PROGRAM_CODE_TO_PACK, _load_pack, authored_years

        out: set[str] = set()
        for pack_file in set(PROGRAM_CODE_TO_PACK.values()):
            try:
                pack = _load_pack(pack_file)
            except FileNotFoundError:
                continue
            jurisdiction = pack.get("jurisdiction") or {}
            code = (jurisdiction.get("code") or "").upper()
            if code and authored_years(pack_file):
                out.add(code)
        return out
    except Exception:  # noqa: BLE001
        return set()


def _client_states(client_id: int, footprint: dict[int, list[str]], priceable: set[str]) -> dict[str, Any]:
    """Where this client operates, and which of those we can put a number on."""
    states = footprint.get(int(client_id), [])
    return {
        "states": states,
        "priceable_states": [s for s in states if s in priceable],
    }


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
    order_name = (order or "asc").lower()
    if order_name not in {"asc", "desc"}:
        order_name = "asc"

    repo = get_repository()
    # Read every year ONCE, then narrow. The page needs two different views of
    # the same claims and they must not come from two reads.
    all_claims = repo.portfolio_coverage(tax_years=None)

    if program:
        all_claims = [c for c in all_claims if c.program_code.upper() == program.upper()]

    claims = all_claims if year is None else [c for c in all_claims if c.tax_year == year]

    grouped: dict[int, list[ProgramClaim]] = defaultdict(list)
    for claim in claims:
        grouped[claim.client_id].append(claim)

    # A TREND IS NOT A CELL, so it cannot be read from the year filter.
    # `grouped` holds whatever survived `year`, which for a page scoped to
    # TY2025 is ONE year per client — and one year has no direction. Halloway
    # has fallen for three years running and read as `settled` on every
    # year-scoped load until this was separated out.
    history: dict[int, list[ProgramClaim]] = defaultdict(list)
    for claim in all_claims:
        history[claim.client_id].append(claim)

    book = _client_book()
    names = {int(c["account_id"]): c.get("name") for c in book}
    industries = {int(c["account_id"]): c.get("industry") for c in book}
    footprint = _footprint()
    priceable = _priceable_states()

    rows: list[dict[str, Any]] = []
    assessed_ids: set[int] = set()
    for client_id, client_claims in sorted(grouped.items()):
        engagements = {e.program_code: e.scope for e in repo.engagements(client_id)}
        candidates: list[ProgramClaim] = []
        for claim in client_claims:
            if outcome and _effective_outcome(claim, engagements) != outcome:
                continue
            if scope and engagements.get(claim.program_code, None) is None:
                continue
            if scope and engagements.get(claim.program_code) != EngagementScope(scope):
                continue
            if near is not None:
                has_gap = claim.status is ClaimStatus.NOT_ASSESSED or bool(claim.near_threshold)
                if near and not has_gap:
                    continue
                if not near and has_gap:
                    continue
            if status and claim.status.value != status:
                continue
            candidates.append(claim)
        # Assessed means the repository holds a claim for this client at all —
        # not that it survived the current filter. Otherwise the "2 of 5
        # assessed" denominator would move every time somebody changed a filter.
        if client_claims:
            assessed_ids.add(client_id)
        if not candidates:
            continue

        chosen = sorted(
            candidates,
            key=lambda claim: _portfolio_sort_value(
                {
                    "gap_jobs": claim.jobs_to_threshold,
                    "jobs_margin": claim.jobs_margin,
                    "priority_rank": claim.priority_band.rank,
                    "variance_usd": str(claim.variance_usd),
                    "opportunity_usd": str(claim.opportunity_usd),
                    "identified_usd": str(claim.identified_usd),
                    "claimed_usd": str(claim.claimed_usd),
                    "tax_year": claim.tax_year,
                    "client_id": claim.client_id,
                    "status": claim.status.value,
                },
                sort,
                order_name,
            ),
            reverse=(order_name == "desc"),
        )[0]

        chosen_scope = engagements.get(chosen.program_code)
        item = chosen.to_dict()
        item["engagement_scope"] = chosen_scope.value if chosen_scope is not None else None
        item["effective_outcome"] = _effective_outcome(chosen, engagements)
        item["gap_jobs"] = chosen.jobs_to_threshold
        item["one_more_job_qualifies"] = bool(
            chosen.jobs_to_threshold is not None and chosen.jobs_to_threshold <= 1.0
        )
        item["client_name"] = names.get(client_id)
        item["industry"] = industries.get(client_id)
        # A trend is a statement about SEVERAL years, so no single claim can
        # carry it. Applied over the cell band, and only where nothing more
        # urgent already applies: exposure and the threshold both outrank it.
        item.update(_declining_overlay(history[client_id], chosen))
        item.update(_client_states(client_id, footprint, priceable))
        rows.append(item)

    sort_name = _portfolio_sort_key(sort)
    rows.sort(
        key=lambda item: _portfolio_sort_value(item, sort_name, order_name),
        reverse=(order_name == "desc"),
    )

    # Clients the repository has never seen. They match only the filters that are
    # true of "we have not looked": an unassessed client is not `unclaimed`, and
    # claiming otherwise would put it in a list of opportunities we have measured.
    unassessed_rows: list[dict[str, Any]] = []
    wanted_unassessed = (
        (outcome in (None, Outcome.NOT_ASSESSED.value))
        and (status in (None, ClaimStatus.NOT_ASSESSED.value))
        # `near` already reads NOT_ASSESSED as a possible gap for stored claims;
        # keep the two consistent rather than answering the same question twice.
        and (near is not False)
    )
    if wanted_unassessed:
        for client in book:
            client_id = int(client["account_id"])
            if client_id in grouped:
                continue
            engagements = {e.program_code: e.scope for e in repo.engagements(client_id)}
            if scope and EngagementScope(scope) not in set(engagements.values()):
                continue
            row = _unassessed_row(client, program=program, year=year, engagements=engagements)
            if row is not None:
                # Where a client operates is a fact about its payroll, not about
                # whether we have run it. Omitting it here would drop the
                # unassessed clients off the map — the ones a footprint filter
                # most needs to surface.
                row.update(_client_states(client_id, footprint, priceable))
                # An industry is a fact about the client, not about a run.
                row["industry"] = client.get("industry")
                unassessed_rows.append(row)
        unassessed_rows.sort(key=lambda item: str(item.get("client_name") or item["client_id"]))

    all_rows = rows + unassessed_rows
    total = len(all_rows)
    page = all_rows[offset: offset + limit]
    return {
        "items": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort": sort_name,
        "order": order_name,
        "year": year,
        "program": program,
        "outcome": outcome,
        "scope": scope,
        "near": near,
        "status": status,
        # The denominator the page needs to say "5 clients · 2 assessed". Without
        # it a headline figure over a mostly-unassessed book reads as though it
        # covered the whole book.
        "total_clients": len(book) or total,
        "assessed_clients": len(assessed_ids),
        "unassessed_clients": len(unassessed_rows),
        "_note": (
            "One row per client, with the most actionable matching cell surfaced. "
            "Ranking is by the jobs gap when possible, because a cell worth $0 can "
            "still be the one to call. Clients never assessed are included with "
            "null money — not zero — and sort after the ranked rows."
        ),
    }


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
def set_engagement(body: EngagementBody) -> dict[str, Any]:
    """Declare whether a program is our mandate for this client."""
    engagement = ProgramEngagement(
        client_id=body.client_id,
        program_code=body.program_code,
        scope=body.scope,
        note=body.note,
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

    # The display name lives behind the scope router. The query deliberately
    # does not reach for it — `application` importing `api` is the dependency
    # `test_application_does_not_import_a_router` exists to stop.
    name = next(
        (c.get("name") for c in _client_book() if int(c["account_id"]) == client_id),
        None,
    )
    return {**body, "client_name": name}


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
