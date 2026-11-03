"""client_trend, client_at_risk, client_discovery: the multi-year and what-else reads. [CH-02]

Split out of `client`, which re-exports all three. Each returns the brief the
portal's narrator agents already received, wrapped in an envelope with
platform-rendered blocks and provenance. Nothing here computes a figure of its own.
"""
from __future__ import annotations

from collections.abc import Sequence

from application.capabilities import _support as s
from application.capabilities.envelope import ToolResult
from application.capabilities.errors import YearNotAuthored


def _trend_line(facts: dict) -> str:
    """The one-sentence verdict under the trend table."""
    verdict = facts["eligible_every_year_since_base"]
    if verdict is None:
        return "There is no year after the base year to judge."
    if verdict:
        return "Eligible employees were found in every year since the base year."
    missing = ", ".join(s.cell(y, "year") for y in facts["years_with_no_eligible_employees"])
    return f"No eligible employees were found in: {missing}."


def client_trend(client_id: int, method: str = "pay_period") -> ToolResult:
    """How a client has moved across years, and whether it has stayed eligible.

    A year the run does not hold carries no figure, which is not a zero; and
    "eligible every year since the base year" is None — not False — when there
    is no year after the base to judge.
    """
    from tools.portfolio import chat_client_trend

    capture = s.RunCapture()
    facts = chat_client_trend(account_id=client_id, method=method, on_run=capture)
    provenance = s.run_provenance(capture.run, source="tcc_gold")

    if not facts.get("calculated"):
        blocks = [s.paragraph("No calculated run holds any year for this client. That is not a zero.")]
        return s.result("client_trend", facts, blocks, provenance=provenance)

    rows = [
        (
            s.cell(y["tax_year"], "year"),
            s.cell(y["annual_average"], "headcount"),
            s.cell(y["eligible_employees"], "count"),
            s.cell(y["employees_evaluated"], "count"),
            s.cell(y["annual_credit_usd"], "money"),
            "Base year" if y.get("is_base_year") else "",
        )
        for y in facts["years"]
    ]
    blocks = [
        s.table(("Tax year", "Average headcount", "Eligible", "Evaluated", "Annual credit", ""), rows),
        s.paragraph(_trend_line(facts)),
    ]
    return s.result("client_trend", facts, blocks, provenance=provenance)


def client_at_risk(
    client_id: int, tax_year: int, state: str = "GA", method: str = "min_max",
) -> ToolResult:
    """Counted jobs close enough to a floor that they could fall out of the credit.

    About the people already INSIDE the credit — the near-miss cohort is
    everybody outside it and cannot answer this. It describes a completed year:
    what would have to change to lose these jobs, never a forecast.
    """
    from tools.portfolio import chat_jobs_at_risk

    if method == "both":
        method = "min_max"
    capture = s.RunCapture()
    facts = chat_jobs_at_risk(
        account_id=client_id, state=state, tax_year=tax_year, method=method, on_run=capture,
    )
    provenance = s.run_provenance(capture.run, source="tcc_gold")

    if not facts.get("calculated"):
        note = facts.get("declined") or (
            f"No calculated run holds TY{s.cell(tax_year, 'year')} for this client. That is not a zero."
        )
        if facts.get("declined"):
            raise YearNotAuthored(str(note))
        return s.result("client_at_risk", facts, [s.paragraph(note)], provenance=provenance)

    binding = facts["binding_floors"]
    blocks = [
        s.paragraph(
            f"{s.cell(facts['within_band'], 'count')} of {s.cell(facts['eligible'], 'count')} "
            f"counted employees sit within {s.cell(facts['band_weekly_hours'], 'number')} weekly hours "
            f"of a floor: {s.cell(binding['hours'], 'count')} bind on hours and "
            f"{s.cell(binding['wages'], 'count')} on wages. "
            f"Jobs at risk: {s.cell(facts['jobs_at_risk'], 'headcount')}."
        ),
        s.paragraph(str(facts["method_note"])),
    ]
    return s.result("client_at_risk", facts, blocks, provenance=provenance)


def _program_for_state(state: str | None) -> str | None:
    from tools.credit_math import PROGRAM_CODE_TO_PACK, STATE_TO_PACK

    pack = STATE_TO_PACK.get((state or "").upper())
    return next((code for code, p in PROGRAM_CODE_TO_PACK.items() if p == pack), None) if pack else None


def client_discovery(
    client_id: int | None = None,
    tax_year: int | None = None,
    state: str | None = None,
    *,
    exclude_codes: Sequence[str] | None = None,
) -> ToolResult:
    """Programmes beyond the one in scope, from the rule-pack library.

    `exclude_codes=None` excludes the programme `state` maps to, so "what else"
    does not list what the client is already being assessed for; pass `[]` for
    the full portfolio. With no `client_id` the scan reads the configured
    default tenant, which is what the portal chat has always done — see
    DECISIONS D-06.
    """
    from tools.discovery import discover_credits

    if exclude_codes is None:
        scoped = _program_for_state(state)
        exclude_codes = [scoped] if scoped else []

    with s.trail_scope() as recorder:
        facts = discover_credits(
            exclude_codes=list(exclude_codes) or None, account_id=client_id, tax_year=tax_year,
        )
        provenance = s.run_provenance(None, recorder=recorder, source="rule-pack library scan")

    rows = [
        (
            str(h["credit_name"]),
            str(h["jurisdiction"]),
            s.cell(h["qualifying_jobs"], "headcount"),
            s.cell(h["annual_credit_usd"], "money"),
            s.cell(h["lifetime_credit_usd"], "money"),
        )
        for h in facts["hits"]
    ]
    blocks = [
        s.paragraph(
            "Programmes with a positive statutory credit, largest lifetime credit first."
            if rows else "No programme produced a positive credit."
        ),
    ]
    if rows:
        blocks.append(s.table(("Programme", "Jurisdiction", "Qualifying jobs", "Annual credit", "Lifetime credit"), rows))
    return s.result("client_discovery", facts, blocks, provenance=provenance, warnings=[s.ILLUSTRATIVE_PACKS])
