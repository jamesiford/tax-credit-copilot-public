"""Credit discovery: surface every rule-pack opportunity for the chat
discovery intent.

Discovery is now a thin view over the statutory portfolio builder
(`tools.portfolio.build_portfolio`) so the chat "what credits are we missing?"
answer is identical to what the Discovery page renders — both come from the
One/Zero net-new engine. No FTE proxy, no separate tax math here.
"""
from __future__ import annotations

from typing import Any

from domain.calculation.trail import current_recorder


def discover_credits(exclude_codes: list[str] | None = None) -> dict[str, Any]:
    """Return every jurisdiction with a positive statutory credit, minus any
    codes the caller is already tracking.

    `exclude_codes` lets the caller suppress credits the client is already
    claiming (e.g. ['GA_JTC'] when answering 'what *other* credits').
    """
    from .portfolio import build_portfolio, latest_tax_year

    exclude = set(exclude_codes or [])
    tax_year = latest_tax_year()
    tiles = build_portfolio(tax_year)

    considered = [t["code"] for t in tiles]
    hits: list[dict[str, Any]] = []
    for t in tiles:
        if t["code"] in exclude:
            continue
        if t.get("basis") == "no_pack":
            continue
        if (t.get("lifetime_credit_usd") or 0) <= 0:
            continue
        hits.append({
            "credit_code": t["code"],
            "credit_name": t["name"],
            "jurisdiction": t["jurisdiction"],
            "citation": t["citation"],
            "qualifying_jobs": t["qualifying_jobs"],
            "basis": t["basis"],
            "annual_credit_usd": t["annual_credit_usd"],
            "benefit_period_years": t["benefit_period_years"],
            "lifetime_credit_usd": t["lifetime_credit_usd"],
        })

    hits.sort(key=lambda h: h["lifetime_credit_usd"], reverse=True)

    recorder = current_recorder()
    if recorder is not None:
        if not recorder.title or recorder.title == "Pending":
            recorder.title = "Credit Discovery"
        if not recorder.citation:
            recorder.citation = "multiple rule packs"
        recorder.record(
            step="Scan rule library (statutory One/Zero engine)",
            inputs={"tax_year": tax_year, "packs_considered": considered, "excluded": sorted(exclude)},
            formula="build statutory portfolio; keep jurisdictions with lifetime_credit > 0 and not excluded",
            output={"hit_count": len(hits)},
            citation="rule packs in backend/rules/ + tools/portfolio.py",
        )
        for h in hits:
            recorder.record(
                step=f"Hit: {h['credit_code']}",
                inputs={"jurisdiction": h["jurisdiction"], "qualifying_jobs": h["qualifying_jobs"], "basis": h["basis"]},
                formula="qualifying_jobs * per_job (or pct_of_wages) * benefit_period_years",
                output={"lifetime_credit_usd": h["lifetime_credit_usd"], "annual_credit_usd": h["annual_credit_usd"]},
                citation=h["citation"],
            )

    return {"hits": hits, "packs_considered": considered, "excluded": sorted(exclude)}

