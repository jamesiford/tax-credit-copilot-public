"""The book, one row per client, ranked by why you would call them.

This was the body of `api/claims.portfolio_v2`. It moved here because the chat
(`_book_brief`) and the channel's `book_rank` capability both need the page's
exact ranking, and a use case that has to import a router to get one drags
FastAPI into every caller.

Behaviour is unchanged. The three readers of external state — the client book,
the payroll footprint and the priceable-state set — are parameters that default
to the real ones, so the router can keep passing the seams its tests have always
patched.
"""
from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from application import client_book
from application.queries.portfolio_rows import (  # noqa: F401 - effective_outcome is re-exported for its callers
    claim_matches, client_states, effective_outcome, group_claims, unassessed_row, unavailable_rows,
)
from application.queries.portfolio_reads import (  # noqa: F401 - re-exported: callers and tests patch them here
    _engagements, _read_claims, prefetch_engagements, _tolerating, _unique, client_book_rows, footprint, priceable_states,
)
from domain.claims import (
    ClaimStatus,
    EngagementScope,
    Outcome,
    PriorityBand,
    ProgramClaim,
    declining_reading,
)



def portfolio_sort_key(sort: str) -> str:
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


def portfolio_sort_value(item: dict[str, Any], sort: str, order: str) -> float:
    field = portfolio_sort_key(sort)
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


def portfolio_page(
    *,
    year: int | None = None,
    program: str | None = None,
    outcome: str | None = None,
    scope: str | None = None,
    near: bool | None = None,
    status: str | None = None,
    sort: str = "priority",
    order: str = "asc",
    limit: int = 25,
    offset: int = 0,
    book: Callable[[], list[dict[str, Any]]] = client_book_rows,
    states: Callable[[], dict[int, list[str]]] = footprint,
    priceable: Callable[[], set[str]] = priceable_states,
) -> dict[str, Any]:
    """General-purpose portfolio instrument: filter and sort one row per client.

    The page-level question is "who do I call?" not "what cell is this?". This
    returns the most actionable cell for each client and lets the caller decide
    which book view it is looking at via the same filters used for the saved
    views: outcome, engagement scope, near-threshold, status, year, and program.

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

    degraded: list[dict[str, Any]] = []
    repo, all_claims = _read_claims(degraded)

    all_claims, grouped, history = group_claims(all_claims, program, year)

    book_rows = _tolerating(book, [], degraded)
    names = {int(c["account_id"]): c.get("name") for c in book_rows}
    industries = {int(c["account_id"]): c.get("industry") for c in book_rows}
    footprint_by_client = _tolerating(states, {}, degraded)
    priceable_set = _tolerating(priceable, set(), degraded)

    rows: list[dict[str, Any]] = []
    assessed_ids: set[int] = set()
    unavailable_ids: list[int] = []
    claims_down, scopes = repo is None, prefetch_engagements(repo, grouped, book_rows)
    for client_id, client_claims in sorted(grouped.items()):
        engagements = _engagements(repo, client_id, degraded, scopes)
        if engagements is None:
            # The claims were read but this client's engagement scope was not: whether its gap is ours to
            # report is unknown, so the row says so instead of asserting an outcome.
            unavailable_ids.append(client_id)
            continue
        candidates = [
            c for c in client_claims
            if claim_matches(c, engagements, outcome=outcome, scope=scope, near=near, status=status)
        ]
        # Assessed means the repository holds a claim for this client at all —
        # not that it survived the current filter. Otherwise the "2 of 5
        # assessed" denominator would move every time somebody changed a filter.
        if client_claims:
            assessed_ids.add(client_id)
        if not candidates:
            continue

        chosen = sorted(
            candidates,
            key=lambda claim: portfolio_sort_value(
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
        item["effective_outcome"] = effective_outcome(chosen, engagements)
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
        item.update(client_states(client_id, footprint_by_client, priceable_set))
        rows.append(item)

    sort_name = portfolio_sort_key(sort)
    rows.sort(
        key=lambda item: portfolio_sort_value(item, sort_name, order_name),
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
    if wanted_unassessed and not claims_down:
        for client in book_rows:
            client_id = int(client["account_id"])
            if client_id in grouped:
                continue
            engagements = _engagements(repo, client_id, degraded, scopes)
            if engagements is None:
                unavailable_ids.append(client_id)
                continue
            if scope and EngagementScope(scope) not in set(engagements.values()):
                continue
            row = unassessed_row(client, program=program, year=year, engagements=engagements)
            if row is not None:
                # Where a client operates is a fact about its payroll, not about
                # whether we have run it. Omitting it here would drop the
                # unassessed clients off the map — the ones a footprint filter
                # most needs to surface.
                row.update(client_states(client_id, footprint_by_client, priceable_set))
                # An industry is a fact about the client, not about a run.
                row["industry"] = client.get("industry")
                unassessed_rows.append(row)
        unassessed_rows.sort(key=lambda item: str(item.get("client_name") or item["client_id"]))

    # Unavailable rows are in EVERY view, whatever the filters say: a client we could not read is not a client
    # with nothing to do, and a saved view that dropped it would show exactly that.
    unavailable_rows_ = unavailable_rows(
        book_rows, unavailable_ids, names, claims_down=claims_down, program=program, year=year,
        extra=lambda cid: client_states(cid, footprint_by_client, priceable_set),
    )
    all_rows = rows + unassessed_rows + unavailable_rows_
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
        "total_clients": len(book_rows) or total,
        # None, not 0, when the claim store could not be read: "none assessed" would be a statement about the
        # clients, and the truth is that nobody knows.
        "assessed_clients": None if claims_down else len(assessed_ids),
        "unavailable_clients": len(unavailable_rows_),
        # What could not be read, and what that costs. Empty when everything answered. An EMPTY
        # claims table is not listed here: that is a normal state, every client simply reads as
        # not yet assessed. A store that cannot be reached or was never initialised IS listed.
        "degraded": _unique(degraded),
        "unassessed_clients": None if claims_down else len(unassessed_rows),
        "_note": (
            "One row per client, with the most actionable matching cell surfaced. "
            "Ranking is by the jobs gap when possible, because a cell worth $0 can "
            "still be the one to call. Clients never assessed are included with "
            "null money — not zero — and sort after the ranked rows."
        ),
    }
