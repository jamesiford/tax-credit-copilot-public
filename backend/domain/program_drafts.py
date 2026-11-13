"""Program drafts: the types behind "bring on a new program" from the portal. [F05.2, ADR-013, ADR-005]

A draft is a proposal. It holds a base pack and year packs as documents, the last validation and a review decision, and it
moves through a small set of states. **It has no runtime authority**: nothing that calculates reads a draft, and the only way
a program becomes calculable is a human committing the exported files to git and deploying (ADR-005). Pure and
standard-library only; storage is the repository port at the bottom.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

#: The most characters one stored document may hold (the Warehouse column is `VARCHAR(8000)`). A year pack is a few
#: kilobytes; a document past this is refused by name rather than truncated, because a clipped pack is a wrong pack.
MAX_DOCUMENT_CHARS = 8000

#: Bounds that keep a draft a small document set: a few dozen year packs at most, nested a few levels. The year count also keeps
#: an export event's list of written paths inside its `VARCHAR(4000)` column; the depth stops a hostile document recursing a
#: parser or the canonical-JSON writer into an error.
MAX_YEAR_DOCUMENTS = 30
MAX_DOCUMENT_DEPTH = 12

#: A program code: upper case, digits and underscores, starting with a letter (`GA_JTC`, `ZZ_DEMO_JTC`).
CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")


class DraftStatus(str, Enum):
    """Where a draft is. `validating` is reserved for an asynchronous validator; validation is synchronous today."""

    DRAFT = "draft"
    VALIDATING = "validating"
    NEEDS_CHANGES = "needs_changes"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED_FOR_EXPORT = "approved_for_export"
    EXPORTED = "exported"
    WITHDRAWN = "withdrawn"


#: Statuses in which the documents may still be edited. Editing a draft under review would change what was reviewed.
EDITABLE = frozenset({DraftStatus.DRAFT, DraftStatus.NEEDS_CHANGES})
#: Statuses that end a draft's life (an exported draft can still be re-exported, byte for byte).
CLOSED = frozenset({DraftStatus.WITHDRAWN})


class DraftError(Exception):
    """A refusal that names its reason. Routers map each subtype to a status; the message is for a person."""

    code = "draft_refused"


class DraftNotFound(DraftError):
    """No draft with that id."""
    code = "draft_not_found"


class DraftConflict(DraftError):
    """The draft changed since the caller read it (optimistic concurrency), or a live draft for the code exists."""

    code = "draft_conflict"


class DraftInvalid(DraftError):
    """The request itself is malformed: a bad code, an unsupported jurisdiction, a document that is not an object or too large."""

    code = "draft_invalid"


class InvalidTransition(DraftError):
    """The requested move is not allowed from the draft's current status, or its documents cannot be edited now."""
    code = "invalid_transition"


class ReviewRefused(DraftError):
    """The review rule failed: not validated, stale validation, or the reviewer is the author."""

    code = "review_refused"


class PreviewRefused(DraftError):
    """A preview cannot run: the documents do not validate, there is no year to price, or the data is not allowed."""

    code = "preview_refused"


class CustomerDataRefused(PreviewRefused):
    """A preview was asked to read a customer-classified source and nothing allows it."""

    code = "customer_data_refused"


def canonical_json(document: Any) -> str:
    """Compact, key-sorted JSON: the one text a document is stored, hashed and exported as, so equal content is equal bytes."""
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def documents_hash(pack: dict[str, Any] | None, years: dict[str, dict[str, Any]]) -> str:
    """SHA-256 over the canonical documents: what validation and review are tied to."""
    return hashlib.sha256(canonical_json({"pack": pack, "years": years}).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProgramDraft:
    """One proposal. `version` is the optimistic-concurrency token: a write names the version it read."""

    draft_id: str
    proposed_code: str
    name: str
    jurisdiction_level: str
    state: str | None
    status: DraftStatus
    version: int
    created_by: str
    created_at: datetime
    updated_by: str
    updated_at: datetime
    pack: dict[str, Any] | None = None
    years: dict[str, dict[str, Any]] = field(default_factory=dict)
    validation: dict[str, Any] | None = None
    review_requested_by: str | None = None
    reviewer: str | None = None
    decision: str | None = None
    decision_comment: str | None = None
    decided_at: datetime | None = None
    approved_sha256: str | None = None
    exported_at: datetime | None = None
    export_sha256: str | None = None

    @property
    def content_sha256(self) -> str:
        return documents_hash(self.pack, self.years)

    def with_changes(self, **changes: Any) -> "ProgramDraft":
        return replace(self, **changes)


@dataclass(frozen=True)
class DraftEvent:
    """One append-only audit row: who did what to which draft, and what it moved from and to."""

    draft_id: str
    seq: int
    event_type: str
    actor: str
    at: datetime
    from_status: str | None = None
    to_status: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


class ProgramDraftRepository(Protocol):
    """Where drafts live. `save` is conditional on `expected_version`; every save appends its events in the same transaction."""

    def create(self, draft: ProgramDraft, event: DraftEvent) -> None: ...

    def get(self, draft_id: str) -> ProgramDraft | None: ...

    def save(self, draft: ProgramDraft, expected_version: int, event: DraftEvent) -> None:
        """Replace the draft if it is still at `expected_version`, else raise `DraftConflict`; append the event."""

    def list_drafts(self, status: str | None = None, limit: int = 50, offset: int = 0) -> tuple[list[ProgramDraft], int]: ...

    def events(self, draft_id: str) -> list[DraftEvent]: ...

    def live_for_code(self, proposed_code: str) -> ProgramDraft | None:
        """A draft for the code that is neither withdrawn nor exported, if any."""
