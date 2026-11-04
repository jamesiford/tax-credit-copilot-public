"""client_eligibility: the credit figure and headcount for one client-year. [CH-02]

Split out of `client`, which re-exports `client_eligibility`. Reads what the run
concluded, from Gold; nothing here computes a figure of its own.
"""
from __future__ import annotations

from typing import Any

from application.capabilities import _support as s
from application.capabilities.envelope import ToolResult


def _snapshot(
    client_id: int, tax_year: int, state: str, context: dict[str, Any], window: Any,
) -> dict[str, Any]:
    """What the run concluded about this client-year — not a synthetic fixture.

    The chat used to narrate `load_payroll_snapshot`, which reads a synthetic
    CSV and cites itself as "not from a client feed", so the answer described
    invented employees while the question was about this client.
    """
    snapshot = {
        "source": "tcc_gold — read from the run that computed it",
        "selected_client_id": client_id,
        "selected_tax_year": tax_year,
        "state": state,
        "calculated": context.get("calculated", False),
        "average_headcount": context.get("current_average"),
        "prior_year_average_headcount": context.get("prior_average"),
        "run_id": context.get("run_id"),
        "fiscal_window": {
            "begin": window.begin.isoformat() if window is not None else None,
            "end": window.end.isoformat() if window is not None else None,
        },
    }
    if not context.get("calculated"):
        snapshot["note"] = (
            f"No calculated run holds TY{tax_year} for this client. That is "
            f"not a zero — say so rather than reporting a figure."
        )
    return snapshot


def _population(client_id: int, tax_year: int, state: str) -> dict[str, Any]:
    """Certified headcount counts for the client-year, without the employee rows."""
    from application.queries._client_run import ClientRunNotAvailable
    from application.queries.get_eligibility import GetEligibilityQuery
    from application.services import get_mediator

    try:
        body = get_mediator().send(
            GetEligibilityQuery(tax_year=tax_year, state=state, account_id=client_id, limit=1)
        )
    except ClientRunNotAvailable as exc:
        raise s.refusal(exc) from exc
    return {
        key: body[key]
        for key in (
            "calculation_state", "employees_evaluated", "min_max_eligible",
            "pay_period_eligible", "near_floor", "eligible_either_method", "reconciliation",
        )
    }


def _credit_blocks(credit: dict[str, Any], tax_year: int) -> list:
    """The measures table, the heading above it and the citation below."""
    rows = [
        ("Average headcount", s.cell(credit.get("average_headcount"), "headcount")),
        ("Prior-year average headcount", s.cell(credit.get("prior_period_average_headcount"), "headcount")),
        ("Qualifying jobs", s.cell(credit.get("qualifying_jobs"), "headcount")),
        ("Annual credit", s.cell(credit.get("annual_credit_usd"), "money")),
        ("Lifetime credit", s.cell(credit.get("lifetime_credit_usd"), "money")),
        ("Benefit period (years)", s.cell(credit.get("benefit_period_years"), "count")),
    ]
    return [
        s.heading(f"{credit['credit_name']} · TY{s.cell(tax_year, 'year')}"),
        s.table(("Measure", "Value"), rows),
        s.paragraph(f"Citation: {credit['citation']}"),
    ]


def client_eligibility(
    client_id: int,
    tax_year: int,
    state: str = "GA",
    method: str = "min_max",
    *,
    window: Any = None,
    include_population: bool = False,
) -> ToolResult:
    """The credit figure and headcount for one client-year, read from the run.

    `facts` carries `snapshot` and `credit`, the two briefs the portal's
    narrators are handed. `window` lets a caller that has already resolved the
    statute (the chat does, to refuse early) skip resolving it again. With
    `include_population` the certified employee counts are added; they cost a
    Gold read the portal chat has never paid, so it does not ask.
    """
    from tools.portfolio import chat_client_context, chat_state_credit

    state = state.upper()
    if window is None:
        window = s.statute(state, client_id, tax_year).window
    capture = s.RunCapture()
    with s.trail_scope() as recorder:
        context = chat_client_context(
            account_id=client_id, tax_year=tax_year, method=s.read_method(method), on_run=capture,
        )
        credit = chat_state_credit(
            state, tax_year=tax_year, account_id=client_id,
            current_average=context.get("current_average"),
            prior_average=context.get("prior_average"),
        )
        provenance = s.run_provenance(capture.run, recorder=recorder, source="tcc_gold")

    facts: dict[str, Any] = {"snapshot": _snapshot(client_id, tax_year, state, context, window), "credit": credit}
    if include_population:
        facts["population"] = _population(client_id, tax_year, state)

    snapshot = facts["snapshot"]
    if not snapshot["calculated"]:
        return s.result("client_eligibility", facts, [s.paragraph(snapshot["note"])], provenance=provenance)
    if credit.get("no_state_pack"):
        return s.result("client_eligibility", facts, [s.paragraph(str(credit["message"]))], provenance=provenance)

    blocks = _credit_blocks(credit, tax_year)
    if include_population and facts["population"].get("calculation_state") == "calculated":
        pop = facts["population"]
        blocks.append(s.table(("Employees", "Count"), [
            ("Evaluated", s.cell(pop["employees_evaluated"], "count")),
            ("Eligible, Min-Max", s.cell(pop["min_max_eligible"], "count")),
            ("Eligible, Pay Period", s.cell(pop["pay_period_eligible"], "count")),
        ]))
    warnings = [s.ILLUSTRATIVE_PACKS] if state != "GA" else []
    return s.result("client_eligibility", facts, blocks, provenance=provenance, warnings=warnings)
