"""The program catalog: what the platform knows and what it can calculate. [F05.1, ADR-013]

Thin: dispatch through the mediator, shape the answer, with typed responses. Open to any authenticated caller (the app-wide
guard runs first); drafts, which need the writer role, are `api/program_drafts.py`. `GET /api/rules` and the scope selector's
program list are unchanged.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from application.program_catalog import UnknownProgram
from application.queries.program_catalog_reads import GetProgramDetailQuery, ListProgramCatalogQuery
from api.program_drafts import router as drafts_router
from application.services import get_mediator

router = APIRouter(tags=["programs"])
router.include_router(drafts_router)


class Jurisdiction(BaseModel):
    """A program's jurisdiction: level (federal, state, local) and code."""
    level: str
    code: str


class Engagement(BaseModel):
    """Clients per engagement scope for the program (live engagements only)."""
    in_scope: int
    out_of_scope: int
    prospective: int
    clients: int


class ProgramRow(BaseModel):
    """One program as the catalog lists it. `verification` is always `not_verified`: the catalog reports what is encoded."""
    code: str
    name: str
    state: str | None
    jurisdiction: Jurisdiction
    lifecycle: str = Field(description="draft | described | calculable | retired. `calculable` is derived from authored year packs.")
    authored_years: list[int]
    unverified_years: list[int] = Field(description="Authored years whose pack still carries _prototype_verify.")
    verification: str
    calculable: bool
    not_calculable_reason: str
    engagement: Engagement | None = Field(None, description="None when the claims store could not be read.")


class CatalogOut(BaseModel):
    """The catalog: every program, with a note that none is verified."""
    programs: list[ProgramRow]
    total: int
    engagement_available: bool
    verification_note: str


class Issue(BaseModel):
    """One validator finding: severity (error, warning, info), a code, the path inside the pack and a message."""
    severity: str
    code: str
    path: str
    message: str


class PackMeta(BaseModel):
    """What the base pack file says about itself."""
    file: str
    present: bool
    rule_pack_version: str | None
    credit_name: str | None
    citation: str | None
    engine_profile: dict[str, str]
    notes: str


class YearStatus(BaseModel):
    """One authored tax year: its version, whether it is still unverified, its source and its findings."""
    tax_year: int
    rule_pack_version: str | None
    unverified: bool
    source: str | None
    issues: list[Issue]


class Validation(BaseModel):
    """The base pack's findings and the error count across the base and year packs; `valid` is not `verified`."""
    pack: list[Issue]
    error_count: int
    valid: bool


class ProgramDetail(ProgramRow):
    """One program in full: pack metadata, per-year status, validation and what blocks calculation."""
    pack: PackMeta
    years: list[YearStatus]
    validation: Validation
    blockers: list[str]


@router.get("/api/v2/programs", response_model=CatalogOut)
def list_programs() -> Any:
    """Every registered program, with its lifecycle, authored years, unverified years, engagement counts and calculability."""
    return get_mediator().send(ListProgramCatalogQuery())


@router.get("/api/v2/programs/{code}", response_model=ProgramDetail)
def get_program(code: str) -> Any:
    """One program: pack metadata, per-year status, validation results and what blocks calculability."""
    try:
        return get_mediator().send(GetProgramDetailQuery(code=code))
    except UnknownProgram as exc:
        raise HTTPException(status_code=404, detail=f"no program {code!r} in the registry") from exc
