"""Read program drafts: a page of them, and one with its audit trail. [F05.3]

Queries with the writer policy: drafts are working material, so reading them needs the same entitlement as changing them.
A read changes nothing.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.identity import Policy
from application.mediator import Query


@dataclass(frozen=True)
class ListProgramDraftsQuery(Query):
    """A page of drafts, most recently changed first, optionally one status."""
    status: str | None = None
    limit: int = 50
    offset: int = 0
    policy = Policy.WRITER


@dataclass(frozen=True)
class GetProgramDraftQuery(Query):
    """One draft with its documents, validation, review record and its append-only event trail."""
    draft_id: str = ""
    policy = Policy.WRITER


@dataclass(frozen=True)
class GetProgramDraftManifestQuery(Query):
    """The manifest of the bundle an approved or exported draft produces (file paths and hashes); no status change, no event."""
    draft_id: str = ""
    policy = Policy.WRITER


def handle_list_program_drafts(query: ListProgramDraftsQuery) -> dict[str, Any]:
    from application.program_drafts.views import summary_view
    from application.services import get_program_draft_repository

    items, total = get_program_draft_repository().list_drafts(query.status, max(1, min(query.limit, 200)), max(0, query.offset))
    return {"items": [summary_view(d) for d in items], "total": total, "limit": query.limit, "offset": query.offset}


def handle_get_program_draft(query: GetProgramDraftQuery) -> dict[str, Any]:
    from application.program_drafts import lifecycle
    from application.program_drafts.views import draft_view, event_view
    from application.services import get_program_draft_repository

    repo = get_program_draft_repository()
    draft = lifecycle.load(repo, query.draft_id)
    return {**draft_view(draft), "events": [event_view(e) for e in repo.events(draft.draft_id)]}


def handle_get_program_draft_manifest(query: GetProgramDraftManifestQuery) -> dict[str, Any]:
    from application.program_drafts import export
    from application.services import get_program_draft_repository

    return export.manifest(get_program_draft_repository(), query.draft_id)
