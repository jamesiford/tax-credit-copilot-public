"""Preview what a program draft would calculate, on synthetic data, writing nothing. [F05.4]

A **query**: it changes nothing and its result is never stored. Needs the writer role like every draft read. The data is the
committed synthetic sample unless the environment allows a client's payroll; every figure is labelled preview, not verified,
not for filing. [ADR-005]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.identity import Policy
from application.mediator import Query


@dataclass(frozen=True)
class PreviewProgramDraftQuery(Query):
    """`dataset` is `synthetic_sample` (default) or `client` (with `client_id`; refused unless allowed)."""
    draft_id: str = ""
    dataset: str = "synthetic_sample"
    client_id: int | None = None
    tax_years: tuple[int, ...] = ()
    policy = Policy.WRITER


def handle_preview_program_draft(query: PreviewProgramDraftQuery) -> dict[str, Any]:
    from application.program_drafts import lifecycle, preview
    from application.services import get_program_draft_repository

    draft = lifecycle.load(get_program_draft_repository(), query.draft_id)
    return preview.run(draft, dataset=query.dataset, client_id=query.client_id, tax_years=query.tax_years)
