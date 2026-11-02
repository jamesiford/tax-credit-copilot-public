"""One client's situation — why you would call them, and what to say.

Reads recorded coverage and orders it by `PriorityBand`. Computes nothing the
matrix does not already know, and reaches no payroll: the question "why would I
ring this client" is answered from claims, which is why it costs one query
rather than an engine pass.

The output is a brief. `ClientSituationAgent` narrates it and can add no figure
to it, because it is handed the object and nothing else [ADR-004].

The client's display NAME is not part of the query result. It is a fact about the
book rather than about recorded coverage, so `with_client_name` decorates the
brief for callers that want it (the REST endpoint and the channel capability).
The chat narrator is deliberately handed the undecorated brief.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from application.client_book import clients_or_empty
from application.mediator import Query


@dataclass(frozen=True)
class GetClientSituationQuery(Query):
    """Everything recorded about one client, ranked by why it matters."""

    client_id: int
    tax_year: int | None = None


class SituationNotAvailable(LookupError):
    """No client, or no book to read it from."""


def with_client_name(
    body: dict[str, Any],
    client_id: int,
    book: Callable[[], list[dict[str, Any]]] = clients_or_empty,
) -> dict[str, Any]:
    """The brief plus the client's display name, or None when the book lacks it."""
    name = next(
        (c.get("name") for c in book() if int(c["account_id"]) == int(client_id)),
        None,
    )
    return {**body, "client_name": name}


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
