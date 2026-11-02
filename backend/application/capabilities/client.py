"""Client-scoped capabilities: resolve, situation, eligibility, trend, at-risk, discovery.

Each returns the brief the portal's narrator agents already received — the same
tools, called the same way — wrapped in an envelope with platform-rendered
blocks and provenance. Nothing here computes a figure of its own.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from application import client_book
from application.capabilities import _support as s
from application.capabilities.book import BAND_LABEL
from application.capabilities.errors import Ambiguous, ClientNotFound, YearNotAuthored
from application.capabilities.envelope import Provenance, ToolResult
from application.chat_scope import ClientName, resolve_referent

_ILLUSTRATIVE = (
    "Rule packs other than the Georgia Jobs Tax Credit are illustrative. "
    "Do not rely on a figure from one."
)


# --------------------------------------------------------------- client_resolve


def client_resolve(
    name_or_text: str,
    history: Sequence[Mapping[str, Any]] = (),
    current_client_id: int | None = None,
    *,
    strict: bool = False,
) -> ToolResult:
    """Whose answer this is — or the choices to ask about.

    Deterministic and model-free: it decides whose payroll an answer describes,
    so it must give the same response every time the same question is asked
    [`chat_scope`]. When the client is not unambiguous the result says so and
    lists candidates; with `strict` it raises `Ambiguous` instead.
    """
    book = client_book.clients_or_empty()
    if not book:
        raise ClientNotFound("The client book could not be read, so no client can be resolved.")
    names = {int(c["account_id"]): str(c["name"]) for c in book}
    clients = [ClientName(client_id, name) for client_id, name in names.items()]

    referent = resolve_referent(name_or_text, list(history), current_client_id, clients)
    candidates = [
        {"client_id": cid, "name": names.get(cid, f"Account {cid}")} for cid in referent.candidates
    ]
    facts = {
        "client_id": referent.client_id,
        "client_name": names.get(referent.client_id) if referent.client_id is not None else None,
        "clarify": referent.clarify,
        "candidates": candidates,
        "reason": referent.reason,
        "named": list(referent.named),
    }
    if referent.clarify and strict:
        raise Ambiguous(referent.reason or "the question does not name one client", tuple(candidates))

    if referent.clarify:
        asked = "Which client do you mean?" + (f" ({referent.reason})" if referent.reason else "")
        blocks = [s.paragraph(asked), s.bullets([c["name"] for c in candidates])]
    else:
        blocks = [s.paragraph(f"Answering for {facts['client_name']}.")]
    return s.result("client_resolve", facts, blocks, provenance=Provenance(source="client book"))


# ------------------------------------------------------------- client_situation


def client_situation(client_id: int, year: int | None = None) -> ToolResult:
    """Why you would call this client, ranked, from recorded claims alone.

    No payroll and no engine: the brief is an ordering of claims by
    `PriorityBand`. `facts` equals the REST endpoint's body, display name
    included; the portal narrator is handed the same object without
    `client_name`, which it never received.
    """
    from application.queries.get_client_situation import (
        GetClientSituationQuery,
        SituationNotAvailable,
        with_client_name,
    )
    from application.wiring import get_mediator

    try:
        body = get_mediator().send(GetClientSituationQuery(client_id=client_id, tax_year=year))
    except SituationNotAvailable as exc:
        raise ClientNotFound(str(exc)) from exc
    facts = with_client_name(body, client_id)

    name = facts["client_name"] or f"Account {client_id}"
    if not facts.get("assessed"):
        blocks = [s.heading(name), s.paragraph(facts["message"])]
        return s.result(
            "client_situation", facts, blocks, provenance=Provenance(source="recorded claims; no run"),
        )

    rows = []
    for band, cells in facts["by_band"].items():
        for c in cells:
            rows.append((
                BAND_LABEL.get(band, band),
                str(c["program_code"]),
                s.cell(c["tax_year"], "year"),
                s.cell(c["identified_usd"], "money"),
                s.cell(c["jobs_margin"], "number"),
            ))
    blocks = [
        s.heading(name),
        s.paragraph(
            f"{s.cell(facts['cells'], 'count')} recorded cells. "
            f"Identified credit: {s.cell(facts['identified_usd'], 'money')}."
        ),
        s.table(("Reason", "Programme", "Tax year", "Identified", "Jobs margin"), rows),
    ]
    warnings = []
    if facts.get("claimed_is_unverified"):
        warnings.append(
            "The claimed side of this book is an unverified assertion; do not read "
            "recoverable or exposure figures as findings against a filed return."
        )
    return s.result(
        "client_situation", facts, blocks,
        provenance=Provenance(source="recorded claims; no run"), warnings=warnings,
    )


# ----------------------------------------------------------- client_eligibility


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
    from application.wiring import get_mediator

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
        blocks = [s.paragraph(snapshot["note"])]
        return s.result("client_eligibility", facts, blocks, provenance=provenance)

    if credit.get("no_state_pack"):
        blocks = [s.paragraph(str(credit["message"]))]
        return s.result("client_eligibility", facts, blocks, provenance=provenance)

    rows = [
        ("Average headcount", s.cell(credit.get("average_headcount"), "headcount")),
        ("Prior-year average headcount", s.cell(credit.get("prior_period_average_headcount"), "headcount")),
        ("Qualifying jobs", s.cell(credit.get("qualifying_jobs"), "headcount")),
        ("Annual credit", s.cell(credit.get("annual_credit_usd"), "money")),
        ("Lifetime credit", s.cell(credit.get("lifetime_credit_usd"), "money")),
        ("Benefit period (years)", s.cell(credit.get("benefit_period_years"), "count")),
    ]
    blocks = [
        s.heading(f"{credit['credit_name']} · TY{s.cell(tax_year, 'year')}"),
        s.table(("Measure", "Value"), rows),
        s.paragraph(f"Citation: {credit['citation']}"),
    ]
    if include_population and facts["population"].get("calculation_state") == "calculated":
        pop = facts["population"]
        blocks.append(s.table(("Employees", "Count"), [
            ("Evaluated", s.cell(pop["employees_evaluated"], "count")),
            ("Eligible, Min-Max", s.cell(pop["min_max_eligible"], "count")),
            ("Eligible, Pay Period", s.cell(pop["pay_period_eligible"], "count")),
        ]))
    warnings = [_ILLUSTRATIVE] if state != "GA" else []
    return s.result("client_eligibility", facts, blocks, provenance=provenance, warnings=warnings)


# ----------------------------------------------------------------- client_trend


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
    verdict = facts["eligible_every_year_since_base"]
    if verdict is None:
        line = "There is no year after the base year to judge."
    elif verdict:
        line = "Eligible employees were found in every year since the base year."
    else:
        missing = ", ".join(s.cell(y, "year") for y in facts["years_with_no_eligible_employees"])
        line = f"No eligible employees were found in: {missing}."
    blocks = [
        s.table(("Tax year", "Average headcount", "Eligible", "Evaluated", "Annual credit", ""), rows),
        s.paragraph(line),
    ]
    return s.result("client_trend", facts, blocks, provenance=provenance)


# -------------------------------------------------------------- client_at_risk


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


# ------------------------------------------------------------- client_discovery


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
    return s.result("client_discovery", facts, blocks, provenance=provenance, warnings=[_ILLUSTRATIVE])
