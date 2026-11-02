"""`book_rank` — who to call, across every client, in the page's own order.

This was `_book_brief` in `api/chat.py`, which called the portfolio router. It
now calls the application's portfolio read (`get_portfolio.portfolio_page`), the
same function the router calls, so the chat, the channel and the page cannot
rank differently.
"""
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from application.capabilities import _support as s
from application.capabilities.envelope import Provenance, ToolResult
from application.queries.get_portfolio import portfolio_page

#: How the page says each band. The chat reads it aloud beside the page, so it
#: must use the page's words — `lib/priority.js` — not the enum ids, which are
#: storage vocabulary ("unclaimed_at_scale" is labelled "Identified" on screen
#: precisely because no filing is held).
BAND_LABEL = {
    "exposed": "Exposed",
    "on_the_line": "On the line",
    "declining": "Declining",
    "unclaimed_at_scale": "Identified",
    "not_assessed": "Not assessed",
    "settled": "Nothing found",
}

_UNVERIFIED = (
    "Some rows rest on a claimed figure that is an unverified assertion, not a "
    "filing. The ranking uses the identified figure, which is computed."
)


def _brief(page: dict[str, Any]) -> dict[str, Any]:
    """The book exactly as the page ranks it.

    It used to come from a second ranking over claim cells, filtered by the
    shell's year. The book has no year, and that ranking had no `declining`
    overlay — so the headline question answered "Northwind first" while the
    page behind the chat said Ironbridge. One ranking, one read.
    """
    items = page.get("items") or []
    if not items:
        return {
            "calculated": False,
            "message": (
                "No client has been assessed yet. There is nothing to rank — "
                "that is not the same as nobody being worth calling."
            ),
        }
    clients = []
    for position, row in enumerate(items, start=1):
        band = row.get("priority_band")
        trend = row.get("trend") or {}
        clients.append({
            "position": position,
            "client_name": row.get("client_name") or f"Account {row.get('client_id')}",
            "reason": BAND_LABEL.get(band, band),
            "program_code": row.get("program_code"),
            "tax_year": row.get("tax_year"),
            "identified_usd": row.get("identified_usd"),
            "jobs_margin": row.get("jobs_margin"),
            "credit_earned_on_trend_usd": trend.get("credit_earned_usd") if band == "declining" else None,
            "provenance_verified": row.get("provenance_verified"),
        })
    return {
        "calculated": True,
        "total_clients": page.get("total_clients"),
        "assessed_clients": page.get("assessed_clients"),
        "clients": clients,
        "ranking_note": (
            "Ordered by what inaction costs, not by size, and in the same order "
            "as the page. 'On the line' outranks 'Identified' because a threshold "
            "missed at year end is gone, while an unclaimed credit is recoverable "
            "retroactively. 'Declining' is a forecast about a year nobody has "
            "filed, not a finding against a filed return."
        ),
        "claimed_is_unverified": any(not c.get("provenance_verified", True) for c in clients),
    }


def _blocks(facts: dict[str, Any]) -> list:
    if not facts.get("calculated"):
        return [s.paragraph(facts["message"])]
    rows = [
        (
            s.cell(c["position"], "count"),
            c["client_name"],
            str(c["reason"]),
            str(c["program_code"] or s.ABSENT),
            s.cell(c["tax_year"] or None, "year"),
            s.cell(c["identified_usd"], "money"),
            s.cell(c["jobs_margin"], "number"),
        )
        for c in facts["clients"]
    ]
    return [
        s.paragraph(
            f"{s.cell(facts['assessed_clients'], 'count')} of "
            f"{s.cell(facts['total_clients'], 'count')} clients have been assessed. "
            f"Ranked by what inaction costs, in the order the page shows."
        ),
        s.table(
            ("#", "Client", "Reason", "Programme", "Tax year", "Identified", "Jobs margin"),
            rows,
        ),
    ]


def book_rank(
    limit: int = 8,
    *,
    page_reader: Callable[..., dict[str, Any]] | None = None,
) -> ToolResult:
    """The top `limit` clients to call, ranked by a named reason, never a score.

    NO YEAR, whatever the caller's scope says: "who do I call" is a question
    about a client across every year they hold, and a year filter flattens the
    bands exactly as it once did on the page.

    `page_reader` is a test seam. The chat passes the router function so the
    suite's existing patches of `api.claims.portfolio_v2` still hold; by default
    the application's own read is used.
    """
    read = page_reader or portfolio_page
    page = read(
        year=None, program=None, outcome=None, scope=None, near=None, status=None,
        sort="priority", order="asc", limit=limit, offset=0,
    )
    facts = _brief(page)
    warnings = [_UNVERIFIED] if facts.get("claimed_is_unverified") else []
    return s.result(
        "book_rank", facts, _blocks(facts),
        provenance=Provenance(source="recorded claims; no run"),
        warnings=warnings,
    )
