"""One client's situation — why you would call them, and what to say.

Reads recorded coverage and orders it by `PriorityBand`. Computes nothing the
matrix does not already know, and reaches no payroll: the question "why would I
ring this client" is answered from claims, which is why it costs one query
rather than an engine pass.

The output is a brief. `ClientSituationAgent` narrates it and can add no figure
to it, because it is handed the object and nothing else [ADR-004].

The client's display NAME is not resolved here. The book lives behind the scope
router, and reaching into `api/` from the application layer is the dependency
`test_application_does_not_import_a_router` exists to stop — so the caller
decorates the brief with it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.mediator import Query


@dataclass(frozen=True)
class GetClientSituationQuery(Query):
    """Everything recorded about one client, ranked by why it matters."""

    client_id: int
    tax_year: int | None = None


class SituationNotAvailable(LookupError):
    """No client, or no book to read it from."""


def handle_get_client_situation(query: GetClientSituationQuery) -> dict[str, Any]:
    from application.wiring import get_claim_repository
    from domain.coverage import situation

    repo = get_claim_repository()
    claims = [
        claim for claim in repo.portfolio_coverage(
            tax_years=[query.tax_year] if query.tax_year else None
        )
        if claim.client_id == query.client_id
    ]

    if not claims:
        # Not a zero. A client nobody has assessed has no figures, and inventing
        # a $0 situation for them would read as "we looked and found nothing".
        return {
            "client_id": query.client_id,
            "tax_year": query.tax_year,
            "assessed": False,
            "message": (
                f"No assessment has been run for this client"
                f"{f' in TY{query.tax_year}' if query.tax_year else ''}. "
                f"There is no figure to report — that is not the same as zero."
            ),
        }

    return {
        "client_id": query.client_id,
        "tax_year": query.tax_year,
        "assessed": True,
        **situation(claims),
    }
