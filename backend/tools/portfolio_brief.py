"""The brief behind the portfolio page's Copilot summary. [03b.1]

The book as the page ranks it: clients in band order, each with the reason. A client whose claim figures
are unavailable is NOT ranked and is never called "not assessed": it is named separately, because
"we could not look" and "we have not looked" are different statements.
"""
from __future__ import annotations

from typing import Any

from tools.brief_format import BAND_LABEL, num, plural, usd

_RANKING_CAVEATS = (
    "The ranking is by reason to act, not by dollar value: 'On the line' outranks "
    "'Identified' because a threshold missed at year end is gone, while an "
    "unclaimed credit is recoverable retroactively.",
    "'Declining' is a forecast about a year nobody has filed, not a finding.",
)


def _name(row: dict[str, Any]) -> str:
    return row.get("client_name") or f"Account {row.get('client_id')}"


def _declining_detail(trend: dict[str, Any]) -> str:
    out = ""
    fallen = num(trend.get("fallen_by"))
    if fallen is not None:
        out += f", down {fallen:.1f} jobs since TY{trend.get('peak_tax_year')}"
    if trend.get("below_base"):
        out += ", now below its base year"
    if trend.get("credit_earned_usd") is not None:
        out += f", {usd(trend['credit_earned_usd'])} already earned"
    return out


def _client_fact(position: int, row: dict[str, Any]) -> str:
    """One ranked client as a sentence: the band, the programme-year, and the figure that band moves in."""
    band = row.get("priority_band")
    margin = num(row.get("jobs_margin"))
    fact = f"{position}. {_name(row)}: {BAND_LABEL.get(band, band or 'unranked')}"
    if row.get("program_code") and row.get("tax_year"):
        fact += f" ({row['program_code']} TY{row['tax_year']})"
    if band == "on_the_line" and margin is not None:
        fact += f", {abs(margin):.2f} jobs short of the minimum" if margin < 0 else f", {margin:.2f} jobs over the minimum"
    elif band == "declining" and row.get("trend"):
        fact += _declining_detail(row["trend"])
    elif num(row.get("identified_usd")):
        fact += f", {usd(row['identified_usd'])} identified"
    return fact


def _coverage_facts(total: int, assessed: int | None, unavailable: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    """The opening fact and the caveats about coverage, keeping unassessed and unavailable apart."""
    if assessed is None:
        facts = [f"{plural(total, 'client')} in the book; how many are assessed is unavailable right now."]
    else:
        facts = [f"{plural(total, 'client')} in the book, {assessed} assessed."]
    caveats = list(_RANKING_CAVEATS)
    if assessed is not None and total > assessed + len(unavailable):
        caveats.append(f"{total - assessed - len(unavailable)} client(s) have not been assessed: that is not a zero.")
    if unavailable:
        names = ", ".join(_name(r) for r in unavailable)
        facts.append(f"Claim figures are unavailable for {plural(len(unavailable), 'client')} ({names}); they are not ranked.")
        caveats.append(
            "Unavailable is not the same as not assessed and not a zero: the claim figures are unavailable, "
            "so nothing is known about those clients' assessment."
        )
    return facts, caveats


def portfolio_brief(book: dict[str, Any]) -> dict[str, Any]:
    """The book as the page ranks it: clients in band order, with their reason."""
    items = book.get("items") or []
    total = int(book.get("total_clients") or len(items))
    assessed = None if book.get("assessed_clients") is None else int(book.get("assessed_clients") or 0)
    unavailable = [r for r in items if r.get("data_unavailable")]
    ranked = [r for r in items if not r.get("data_unavailable")]
    clients = [
        {
            "position": position, "client": _name(row), "industry": row.get("industry"),
            "reason": BAND_LABEL.get(row.get("priority_band"), row.get("priority_band")),
            "fact": _client_fact(position, row),
        }
        for position, row in enumerate(ranked, start=1)
    ]
    facts, caveats = _coverage_facts(total, assessed, unavailable)
    facts[1:1] = [c["fact"] for c in clients]
    return {
        "page": "portfolio",
        "subject": "the whole book of clients",
        "headline": facts[0],
        "facts": facts,
        "caveats": caveats,
        "data": {"total_clients": total, "assessed_clients": assessed, "clients": clients},
    }
