"""Data Ingestion endpoints (Stage 1 — the automated ingest surface).

Shows *how the source becomes the output*: raw BCS pay-period rows → canonical
records (field map + worksite join + pay-code classification + cash-basis trim)
→ QC exception report — with a human validation/correction checkpoint on every
anomaly (nothing is silently dropped).

  GET  /api/ingestion/{tax_year}                              — source → canonical → QC
  GET  /api/ingestion/{tax_year}/rows                         — the source browser
  POST /api/ingestion/{tax_year}/exceptions/{exception_id}/resolve — human resolution

Thin [ADR-003]: the reads are queries and the resolution is a command, in
`application/queries/get_ingestion_*` and `application/commands/resolve_qc_exception`;
the resolution store is `application/qc_resolutions`.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from api._payperiods import payroll_errors_as_http
from api.auth import attributed
from application.commands.resolve_qc_exception import ResolveQcExceptionCommand
from application.queries.get_ingestion_overview import GetIngestionOverviewQuery
from application.queries.get_ingestion_rows import GetIngestionRowsQuery
from application.services import get_mediator

router = APIRouter(prefix="/api", tags=["ingestion"])


class ResolveExceptionRequest(BaseModel):
    """Human validation/correction of a QC exception."""
    resolution: str = Field("accept", pattern="^(accept|drop|flag|assign|reopen)$")
    keep_worksite: str | None = None  # test-of-twos: the unit that owns the head
    note: str | None = None
    reviewer: str = "Reviewer"


@router.get("/ingestion/{tax_year}")
def ingestion_overview(
    tax_year: int,
    state: str = "GA",
    account_id: int | None = None,
) -> dict[str, Any]:
    """Source → canonical → QC for a tax year (default GA).

    Returns the raw-row sample, the field map, the pipeline row counts at each
    transform stage, the pay-code classification split, and the QC exception
    report with any human resolution attached.
    """
    with payroll_errors_as_http():
        return get_mediator().send(
            GetIngestionOverviewQuery(tax_year=tax_year, state=state, account_id=account_id)
        )


@router.post("/ingestion/{tax_year}/exceptions/{exception_id}/resolve")
def resolve_exception(
    tax_year: int, exception_id: str, req: ResolveExceptionRequest, request: Request
) -> dict[str, Any]:
    """Record a human resolution for a QC exception (accept / drop / flag /
    reopen). In-memory; resets on restart — prod persists to the audit store."""
    return get_mediator().send(ResolveQcExceptionCommand(
        actor=attributed(request, req.reviewer, default="Reviewer"),
        exception_id=exception_id, resolution=req.resolution,
        keep_worksite=req.keep_worksite, note=req.note,
    ))


@router.get("/ingestion/{tax_year}/rows")
def ingestion_rows(
    tax_year: int,
    state: str = "GA",
    q: str = "",
    limit: int = 50,
    offset: int = 0,
    account_id: int | None = None,
    sort: str = "employee",
    order: str = "asc",
) -> dict[str, Any]:
    """Full source browser — paged + searchable, read-only.

    Sorted before paging, so the first page is the top of the whole list and
    not the top of whichever 25 rows happened to be fetched.
    """
    with payroll_errors_as_http():
        return get_mediator().send(GetIngestionRowsQuery(
            tax_year=tax_year, state=state, q=q, limit=limit, offset=offset,
            account_id=account_id, sort=sort, order=order,
        ))
