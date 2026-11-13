"""Typed request and response models for the program draft routes. [F05]

Split from `api/program_drafts.py` by size. `verification` is always `not_verified` and `has_runtime_authority` always false:
a draft is a proposal and nothing here says its statute is right. [ADR-005]
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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


class PreviewBody(BaseModel):
    """What to preview on. The default is the committed synthetic sample; a client needs the environment to allow it."""
    dataset: Literal["synthetic_sample", "client"] = "synthetic_sample"
    client_id: int | None = None
    tax_years: list[int] = Field(default_factory=list, description="Empty: every tax year the draft has a pack for.")


class PreviewYear(BaseModel):
    """One year priced under the draft's own year pack for that year."""
    tax_year: int
    average_headcount: float
    prior_average_headcount: float | None
    is_base_year: bool
    threshold_jobs: float
    qualifying_jobs: float
    per_job_usd: float
    annual_credit_usd: float
    benefit_period_years: int
    rows_used: int
    months_with_payroll: int
    window: str


class PreviewOut(BaseModel):
    """A preview. `label` is always "Preview, not verified, not for filing"; nothing is stored (`persisted` is false)."""
    label: str
    draft_id: str
    proposed_code: str
    state: str | None
    dataset: dict[str, Any]
    unverified: bool
    unverified_flags: int
    years: list[PreviewYear]
    declined: list[dict[str, Any]]
    persisted: bool
    wrote_nothing: bool


class WithdrawBody(BaseModel):
    """Why the draft is being withdrawn (optional)."""
    reason: str | None = None
    actor: str | None = None


class ExportBody(BaseModel):
    """`write_local` writes the pack files into the rules folder: developers only, local development with the setting on."""
    write_local: bool = False
    actor: str | None = None


class ManifestOut(BaseModel):
    """The bundle a draft produces: every file with its SHA-256, the checklist line for the changelog and the bundle's own hash."""
    kind: str
    schema_version: int
    draft_id: str
    proposed_code: str
    name: str
    state: str | None
    content_sha256: str
    approved_sha256: str | None
    verification: str
    has_runtime_authority: bool
    changelog_line: str
    files: list[dict[str, Any]]
    bundle_sha256: str
    bundle_bytes: int
