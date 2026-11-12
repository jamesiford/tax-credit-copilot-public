"""The rows of the portfolio page that are not a plain ranked claim, and the test for the ones that are. [03b.1]

A client can reach the page in four ways, and the difference matters in a tax product:

- **ranked**: a claim exists and matches the filters (`get_portfolio.portfolio_page` builds it);
- **not assessed**: the claim store answered and holds nothing for the client, so the pipeline has not
  reached it. Money is null, and it says "not assessed";
- **unavailable**: the claim store (or this client's engagement scope) could not be read, so we do not
  know whether the client was assessed. Money is null, `data_unavailable` is true, the dependency is
  named, and the status is NOT "not assessed": "we have not looked" and "we could not look" are
  different statements, and only the first one is a fact about the client.

Nothing here reads a store; it shapes rows from what `portfolio_page` already holds.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from application import client_book
from domain.claims import ClaimStatus, EngagementScope, Outcome, ProgramClaim

UNAVAILABLE_BAND = "unavailable"
#: After `settled` (5): an unavailable row is not ranked among rows whose figures we hold.
UNAVAILABLE_RANK = 6

_NULLED_BY_UNAVAILABLE = (
    "status", "outcome", "provenance", "provenance_verified", "identified_usd", "claimed_usd", "certified_usd",
    "variance_usd", "variance_is_computable", "opportunity_usd", "average_headcount", "base_average_headcount",
    "threshold_jobs", "is_base_year", "net_new_jobs", "jobs_to_threshold", "jobs_margin", "near_threshold",
    "is_exposure",
)


def effective_outcome(claim, engagements: dict[str, EngagementScope]) -> str:
    scope = engagements.get(claim.program_code)
    if scope is EngagementScope.OUT_OF_SCOPE and claim.outcome in {Outcome.UNCLAIMED, Outcome.NOT_ASSESSED}:
        return Outcome.OUT_OF_SCOPE.value
    return claim.outcome.value


def claim_matches(
    claim: ProgramClaim,
    engagements: dict[str, EngagementScope],
    *,
    outcome: str | None,
    scope: str | None,
    near: bool | None,
    status: str | None,
) -> bool:
    """Whether one claim survives the page's filters."""
    if outcome and effective_outcome(claim, engagements) != outcome:
        return False
    if scope and engagements.get(claim.program_code) != EngagementScope(scope):
        return False
    if near is not None:
        has_gap = claim.status is ClaimStatus.NOT_ASSESSED or bool(claim.near_threshold)
        if near != has_gap:
            return False
    return not (status and claim.status.value != status)


def default_program_code(program: str | None, engagements: dict[str, EngagementScope]) -> str | None:
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
        calculable = [p["program_code"] for p in client_book.programs() if p.get("calculable")]
    except (OSError, ValueError):  # rule packs unreadable: "unknown", and priceable_states reports it
        return None
    return calculable[0] if len(calculable) == 1 else None


def unassessed_row(
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
    program_code = default_program_code(program, engagements)
    if not program_code:
        return None
    claim = ProgramClaim(
        claim_id="", client_id=int(client["account_id"]), entity_id=None, program_code=program_code,
        tax_year=year or 0, status=ClaimStatus.NOT_ASSESSED,
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


def unavailable_row(
    client: dict[str, Any], *, program: str | None, year: int | None, dependency: str = "claims_store",
) -> dict[str, Any]:
    """A client whose claims or engagement scope could not be read.

    Same shape as every other row (built from `ProgramClaim.to_dict`), then everything that would assert an
    assessment is nulled: no status, no outcome, no band but `unavailable`, no figures. A programme is named
    only when one is knowable; the row exists either way, because a client missing from "who do I call" is
    the one nobody calls.
    """
    program_code = default_program_code(program, {}) or "n/a"
    claim = ProgramClaim(
        claim_id="", client_id=int(client["account_id"]), entity_id=None, program_code=program_code,
        tax_year=year or 0, status=ClaimStatus.NOT_ASSESSED,
    )
    item = claim.to_dict()
    for key in _NULLED_BY_UNAVAILABLE:
        item[key] = None
    for key in ("identified_usd", "claimed_usd", "certified_usd", "variance_usd", "opportunity_usd"):
        item[key] = None
    item.update(
        program_code=None if program_code == "n/a" else program_code,
        tax_year=year, priority_band=UNAVAILABLE_BAND, priority_rank=UNAVAILABLE_RANK,
        effective_outcome=None, engagement_scope=None, gap_jobs=None, one_more_job_qualifies=False,
        client_name=client.get("name"), industry=client.get("industry"),
        data_unavailable=True, unavailable_dependency=dependency,
    )
    return item


def client_states(client_id: int, states_by_client: dict[int, list[str]], priceable: set[str]) -> dict[str, Any]:
    """Where this client operates, and which of those we can put a number on."""
    states = states_by_client.get(int(client_id), [])
    return {"states": states, "priceable_states": [s for s in states if s in priceable]}


def unavailable_rows(
    book_rows: list[dict[str, Any]], ids: list[int], names: dict[int, Any], *, claims_down: bool,
    program: str | None, year: int | None, extra: Callable[[int], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Rows for every client whose claims could not be read: the whole book, or just the ids named.

    `extra(client_id)` adds what is true of a client whether or not it was assessed (where it operates).
    """
    by_id = {int(c["account_id"]): c for c in book_rows}
    wanted = sorted(by_id) if claims_down else sorted(set(ids))
    clients = [by_id.get(i) or {"account_id": i, "name": names.get(i)} for i in wanted]
    return [
        {**unavailable_row(c, program=program, year=year), **extra(int(c["account_id"]))} for c in clients
    ]


def group_claims(
    all_claims: list[ProgramClaim], program: str | None, year: int | None,
) -> tuple[list[ProgramClaim], dict[int, list[ProgramClaim]], dict[int, list[ProgramClaim]]]:
    """(programme-filtered claims, the year-filtered claims by client, the whole history by client).

    A TREND IS NOT A CELL, so it cannot be read from the year filter. `grouped` holds whatever survived
    `year`, which for a page scoped to TY2025 is ONE year per client — and one year has no direction.
    Halloway has fallen for three years running and read as `settled` on every year-scoped load until
    the history was kept apart.
    """
    if program:
        all_claims = [c for c in all_claims if c.program_code.upper() == program.upper()]
    claims = all_claims if year is None else [c for c in all_claims if c.tax_year == year]
    grouped: dict[int, list[ProgramClaim]] = defaultdict(list)
    for claim in claims:
        grouped[claim.client_id].append(claim)
    history: dict[int, list[ProgramClaim]] = defaultdict(list)
    for claim in all_claims:
        history[claim.client_id].append(claim)
    return all_claims, grouped, history
