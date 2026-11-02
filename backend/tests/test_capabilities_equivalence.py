"""Each capability returns exactly what the endpoint or brief it replaced returns.

CH-01 moved compute out of `api/` and into `application/capabilities/`. The only
proof that nothing changed on the way is to ask the old entry point and the new
one the same question and compare. Where the old entry point no longer exists
(`_book_brief` used to hold its own ranking), its body is reproduced here as the
oracle, so the comparison is against what the code *did*, not what it does now.

Offline, on the synthetic dataset (`conftest.py` pins DATA_SOURCE=csv). Gold is
faked where the real reader needs a warehouse.
"""
from __future__ import annotations

import copy
import json
from decimal import Decimal

import pytest

from application import client_book
from application.capabilities import registry
from application.capabilities.errors import (
    Ambiguous,
    ClientNotFound,
    InvalidArguments,
    NotCalculated,
    YearNotAuthored,
)

# Reused from the suites that already built these harnesses.
from test_api_employee_drill import _KNOWN_TOKEN, _DrillReader  # noqa: F401
from test_simulate_unit import SITE, cascade, wired  # noqa: F401

BOOK = [
    {"account_id": 2001, "name": "Cascade Retail Partners", "industry": "Retail"},
    {"account_id": 2002, "name": "Northwind Care Systems", "industry": "Healthcare"},
    {"account_id": 2003, "name": "Ironbridge Logistics", "industry": "Logistics"},
]


@pytest.fixture
def book(monkeypatch):
    monkeypatch.setattr(client_book, "clients", lambda: copy.deepcopy(BOOK))
    return BOOK


@pytest.fixture
def claims_repo(tmp_path):
    from api import claims as claims_api
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

    original = claims_api._REPO
    repo = SqliteClaimRepository(tmp_path / "claims.db")
    claims_api.set_repository(repo)
    try:
        yield repo
    finally:
        repo.close()
        claims_api.set_repository(original)


def _seed(claims_repo):
    """Two assessed clients and one the book holds but nobody has run."""
    from fastapi.testclient import TestClient

    from main import app

    http = TestClient(app)
    for client_id, year, identified in ((2001, 2023, "140000"), (2002, 2024, "40495")):
        response = http.post("/api/claims", json={
            "client_id": client_id, "program_code": "GA_JTC", "tax_year": year,
            "status": "assessed", "provenance": "computed",
            "decided_by": "analyst@example.com", "identified_usd": identified,
        })
        assert response.status_code == 201, response.text


def _same(a, b) -> bool:
    """Equal as data, and as the bytes the narrator is handed."""
    return a == b and json.dumps(a, indent=2, default=str) == json.dumps(b, indent=2, default=str)


# ------------------------------------------------------------------ book_rank


_LEGACY_BAND_LABEL = {
    "exposed": "Exposed", "on_the_line": "On the line", "declining": "Declining",
    "unclaimed_at_scale": "Identified", "not_assessed": "Not assessed", "settled": "Nothing found",
}


def _legacy_book_brief(limit: int = 8) -> dict:
    """`api/chat._book_brief` as it was before CH-01, reading the page's endpoint."""
    from api.claims import portfolio_v2

    page = portfolio_v2(
        year=None, program=None, outcome=None, scope=None, near=None, status=None,
        sort="priority", order="asc", limit=limit, offset=0,
    )
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
            "reason": _LEGACY_BAND_LABEL.get(band, band),
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


def test_book_rank_equals_the_brief_the_chat_used_to_build(book, claims_repo):
    from api.chat import _book_brief
    from application.capabilities.book import book_rank

    _seed(claims_repo)
    result = book_rank()

    assert result.facts["calculated"] is True
    assert _same(result.facts, _legacy_book_brief())
    # The chat's own entry point now routes through the capability and must agree.
    assert _same(_book_brief(), _legacy_book_brief())


def test_book_rank_is_the_page_order_by_name(book, claims_repo):
    from application.capabilities.book import book_rank

    _seed(claims_repo)
    names = [c["client_name"] for c in book_rank().facts["clients"]]
    assert set(names) == {"Cascade Retail Partners", "Northwind Care Systems", "Ironbridge Logistics"}


def test_an_empty_book_says_so_rather_than_ranking_nothing(monkeypatch, claims_repo):
    from application.capabilities.book import book_rank

    monkeypatch.setattr(client_book, "clients", lambda: [])
    result = book_rank()
    assert _same(result.facts, _legacy_book_brief())
    assert result.facts["calculated"] is False
    assert result.blocks[0].kind == "paragraph"


# ----------------------------------------------------------- client_situation


def test_client_situation_equals_the_rest_endpoint(book, claims_repo):
    from api.claims import client_situation as endpoint
    from application.capabilities.client import client_situation

    _seed(claims_repo)
    for year in (None, 2023):
        facts = client_situation(2001, year).facts
        assert _same(facts, endpoint(client_id=2001, year=year))
        assert facts["client_name"] == "Cascade Retail Partners"


def test_the_narrator_brief_is_the_endpoint_without_the_display_name(book, claims_repo):
    from application.capabilities.client import client_situation
    from application.queries.get_client_situation import GetClientSituationQuery
    from application.wiring import get_mediator

    _seed(claims_repo)
    facts = client_situation(2001, 2023).facts
    raw = get_mediator().send(GetClientSituationQuery(client_id=2001, tax_year=2023))
    assert {k: v for k, v in facts.items() if k != "client_name"} == raw


def test_an_unassessed_client_is_not_a_zero(book, claims_repo):
    from application.capabilities.client import client_situation

    _seed(claims_repo)
    facts = client_situation(2003, 2023).facts
    assert facts["assessed"] is False
    assert "not the same as zero" in facts["message"]


# -------------------------------------------------------------- client_resolve


def test_client_resolve_equals_the_chat_resolver(book):
    from application.capabilities.client import client_resolve
    from application.chat_scope import ClientName, resolve_referent

    names = [ClientName(c["account_id"], c["name"]) for c in BOOK]
    history = [{"role": "user", "text": "brief me on Cascade"}]
    cases = [
        ("what is their trend?", history, None),
        ("what is Halloway's trend?", [], 2001),
        ("compare Cascade and Northwind", [], None),
        ("how are things?", [], 2002),
    ]
    for text, hist, scope in cases:
        expected = resolve_referent(text, hist, scope, names)
        facts = client_resolve(text, hist, scope).facts
        assert facts["client_id"] == expected.client_id
        assert facts["clarify"] == expected.clarify
        assert [c["client_id"] for c in facts["candidates"]] == list(expected.candidates)
        assert facts["reason"] == expected.reason


def test_an_ambiguous_question_raises_when_strict(book):
    from application.capabilities.client import client_resolve

    with pytest.raises(Ambiguous) as caught:
        client_resolve("compare Cascade and Northwind", strict=True)
    assert len(caught.value.candidates) == 2


def test_resolving_against_an_unreadable_book_is_a_typed_error(monkeypatch):
    from application.capabilities.client import client_resolve

    monkeypatch.setattr(client_book, "clients", lambda: [])
    with pytest.raises(ClientNotFound):
        client_resolve("anyone")


# ------------------------------------------------------------ gold-backed reads


class _Gold:
    """A Gold reader that answers the reads the chat tools make."""

    RUN = {
        "run_id": "run-42", "rule_pack_version": "rules/ga_jtc/2023.json",
        "step1_assumption_set_id": "GDS-STEP1-TEST", "onezero_assumption_set_id": "GDS-ONEZERO-TEST",
    }

    def headcount_series(self, client_id, *, tax_year, method="pay_period"):
        average = {2023: 120.5, 2022: 100.25}.get(tax_year)
        return {
            "run": self.RUN if average is not None else None,
            "annual_average": average,
            "month_ends": [f"{tax_year}-{m:02d}-28" for m in range(1, 13)],
        }

    def client_year_series(self, client_id, *, method="pay_period"):
        years = [
            {"tax_year": 2021, "annual_average": 80.0, "eligible_employees": 60, "employees_evaluated": 90,
             "annual_credit_usd": "0", "is_base_year": True, "qualified_units": 0, "units": 3},
            {"tax_year": 2022, "annual_average": 100.25, "eligible_employees": 71, "employees_evaluated": 99,
             "annual_credit_usd": "52500", "is_base_year": False, "qualified_units": 2, "units": 3},
        ]
        return {"run": self.RUN, "years": years, "method": method}

    def at_risk(self, client_id, *, tax_year, method, min_weekly_hours, min_weekly_wages):
        def row(i, hours, wages):
            return {
                "employee_id": f"E{i}", "record_token": f"{i:08d}" * 2, "weeks_worked": 52,
                "total_hours": hours * 52, "total_wages": wages * 52,
                "avg_weekly_hours": hours, "avg_weekly_wages": wages, "weight": 1,
            }

        return {
            "run": self.RUN,
            "counts": {"eligible_count": 3, "evaluated": 9},
            "rows": [row(1, 36.5, 900.0), row(2, 40.0, 700.0), row(3, 60.0, 2000.0)],
        }


@pytest.fixture
def gold():
    from application.wiring import set_gold_reader

    reader = _Gold()
    set_gold_reader(reader)
    yield reader
    set_gold_reader(None)


def test_client_trend_equals_the_chat_tool(gold):
    from application.capabilities.client import client_trend
    from tools.portfolio import chat_client_trend

    result = client_trend(2001)
    assert _same(result.facts, chat_client_trend(account_id=2001))
    assert result.provenance.run_id == "run-42"
    assert result.provenance.rule_pack_version == "rules/ga_jtc/2023.json"
    assert result.provenance.assumption_set_id == "GDS-STEP1-TEST + GDS-ONEZERO-TEST"


def test_client_at_risk_equals_the_chat_tool(gold):
    from application.capabilities.client import client_at_risk
    from tools.portfolio import chat_jobs_at_risk

    expected = chat_jobs_at_risk(account_id=2001, state="GA", tax_year=2023, method="min_max")
    result = client_at_risk(2001, 2023, "GA", "min_max")
    assert expected["calculated"] is True
    assert _same(result.facts, expected)
    # `both` has no single answer; the chat has always read min_max for it.
    assert _same(client_at_risk(2001, 2023, "GA", "both").facts, expected)


def test_client_at_risk_declines_an_unauthored_year_by_name(gold):
    from application.capabilities.client import client_at_risk

    with pytest.raises(YearNotAuthored, match="ADR-005"):
        client_at_risk(2001, 1999, "GA")


def test_client_eligibility_equals_the_two_briefs_the_chat_hands_its_narrators(gold):
    from application.capabilities.client import client_eligibility
    from application.queries._client_run import resolve_statute
    from tools.portfolio import chat_client_context, chat_state_credit

    window = resolve_statute(account_id=2001, state="GA", tax_year=2023).window
    context = chat_client_context(account_id=2001, tax_year=2023, method="pay_period")
    credit = chat_state_credit(
        "GA", tax_year=2023, account_id=2001,
        current_average=context.get("current_average"), prior_average=context.get("prior_average"),
    )

    result = client_eligibility(2001, 2023, "GA", "pay_period", window=window)

    assert result.facts["credit"] == credit
    snapshot = result.facts["snapshot"]
    assert snapshot["average_headcount"] == context["current_average"] == 120.5
    assert snapshot["prior_year_average_headcount"] == 100.25
    assert snapshot["run_id"] == "run-42"
    assert snapshot["fiscal_window"] == {"begin": window.begin.isoformat(), "end": window.end.isoformat()}
    # The capability resolves the window itself when the caller has not.
    assert client_eligibility(2001, 2023, "GA", "pay_period").facts == result.facts
    assert result.provenance.trail_sha256, "the credit step is recorded, so there is a trail to hash"


def test_an_uncalculated_year_is_not_a_zero(gold):
    from application.capabilities.client import client_eligibility

    facts = client_eligibility(2001, 2024, "GA", "pay_period").facts
    assert facts["snapshot"]["calculated"] is False
    assert "not a zero" in facts["snapshot"]["note"]


def test_client_eligibility_declines_an_unauthored_year_by_name(gold):
    from application.capabilities.client import client_eligibility

    with pytest.raises(YearNotAuthored, match="ADR-005"):
        client_eligibility(2001, 1999, "GA")


def test_calc_walkthrough_wraps_a_cached_trail_unchanged():
    from application.capabilities.walkthrough import calc_walkthrough
    from domain.calculation.trail import TrailRecorder

    recorder = TrailRecorder(title="Georgia Jobs Tax Credit", citation="O.C.G.A. 48-7-40.26")
    recorder.record(step="Apply", inputs={"average_headcount": 12.67}, formula="max(0, a - b)",
                    output={"annual_credit_usd": 3500}, citation="O.C.G.A. 48-7-40.26")
    cached = recorder.to_dict()

    result = calc_walkthrough(trail=cached)
    assert _same(result.facts, cached)
    assert result.provenance.trail_sha256 == cached["evidence_hash"].removeprefix("sha256:")


def test_calc_walkthrough_records_the_credit_step_afresh(gold):
    from application.capabilities.walkthrough import calc_walkthrough

    result = calc_walkthrough(2001, 2023, "GA")
    steps = result.facts["steps"]
    assert steps and steps[0]["output"]["annual_credit_usd"] is not None
    assert result.facts["evidence_hash"].startswith("sha256:")
    assert result.provenance.trail_sha256 == result.facts["evidence_hash"].removeprefix("sha256:")
    assert result.provenance.run_id == "run-42"


def test_calc_walkthrough_needs_a_scope_unless_given_a_trail():
    from application.capabilities.walkthrough import calc_walkthrough

    with pytest.raises(InvalidArguments):
        calc_walkthrough()


def test_calc_walkthrough_refuses_an_uncalculated_year(gold):
    from application.capabilities.walkthrough import calc_walkthrough

    with pytest.raises(NotCalculated):
        calc_walkthrough(2001, 2024, "GA")


# ------------------------------------------------------------- csv-backed reads


def test_client_discovery_equals_the_chat_tool():
    from application.capabilities.client import client_discovery
    from tools.discovery import discover_credits

    assert _same(client_discovery(exclude_codes=["GA_JTC"]).facts, discover_credits(exclude_codes=["GA_JTC"]))
    assert _same(client_discovery(exclude_codes=[]).facts, discover_credits())


def test_discovery_excludes_the_programme_in_scope_by_default():
    from application.capabilities.client import client_discovery

    codes = {h["credit_code"] for h in client_discovery(state="GA").facts["hits"]}
    assert "GA_JTC" not in codes
    assert client_discovery(state="GA").facts["excluded"] == ["GA_JTC"]


def test_simulate_headcount_equals_the_chat_tool():
    from application.capabilities.simulate import simulate_headcount
    from tools.simulation import simulate_hiring

    for location, hires in (("Atlanta", 25), ("Nashville", -10)):
        assert _same(simulate_headcount(location, hires).facts, simulate_hiring(location, hires))
    with pytest.raises(InvalidArguments):
        simulate_headcount("Atlanta", 0)


# ----------------------------------------------------------------- simulate


def test_simulate_equals_the_location_query(wired):
    from application.capabilities.simulate import simulate
    from application.queries.simulate_unit import SimulateUnitQuery
    from application.wiring import get_mediator

    expected = get_mediator().send(SimulateUnitQuery(
        client_id=2001, worksite_id=SITE, tax_year=2025, action="add_headcount", magnitude=2,
    ))
    result = simulate(2001, 2025, SITE, "add_headcount", 2)
    assert _same(result.facts, expected)
    assert result.provenance.run_id == "test-run"


def test_simulate_translates_the_queries_refusals(wired):
    from application.capabilities.simulate import simulate

    with pytest.raises(NotCalculated, match="base year"):
        simulate(2001, 2020, SITE)
    with pytest.raises(InvalidArguments):
        simulate(2001, 2025, SITE, action="bribe")


# -------------------------------------------------------------- employee_drill


def test_employee_drill_equals_the_query():
    from application.capabilities.walkthrough import employee_drill
    from application.queries.get_employee_drill import GetEmployeeDrillQuery
    from application.wiring import get_mediator, set_gold_reader

    set_gold_reader(_DrillReader())
    try:
        expected = get_mediator().send(GetEmployeeDrillQuery(
            record_token=_KNOWN_TOKEN, tax_year=2025, state="GA", account_id=1001,
        ))
        result = employee_drill(1001, _KNOWN_TOKEN, 2025, "GA")
        assert result.facts == expected
        assert result.provenance.run_id == "run-1"
        assert any("Sensitive" in w for w in result.warnings)
        with pytest.raises(NotCalculated):
            employee_drill(1001, "0" * 24, 2025, "GA")
    finally:
        set_gold_reader(None)


# ---------------------------------------------------------------- findings_list


@pytest.fixture
def findings_repo(tmp_path):
    from api import findings as findings_api
    from infrastructure.persistence.sqlite_findings import SqliteFindingRepository

    original = findings_api._REPO
    repo = SqliteFindingRepository(tmp_path / "findings.db")
    findings_api.set_repository(repo)
    try:
        yield repo
    finally:
        repo.close()
        findings_api.set_repository(original)


def test_findings_list_equals_the_rest_endpoint(findings_repo):
    from api.findings import findings as endpoint
    from application.capabilities.findings import findings_list

    result = findings_list(1001, 2025, "GA")
    assert _same(result.facts, endpoint(1001, 2025, "GA"))
    assert result.facts["findings"], "the synthetic payroll carries test-of-twos anomalies"
    assert result.warnings


def test_findings_for_a_client_with_no_payroll_is_a_typed_error(findings_repo, monkeypatch):
    from application.capabilities.findings import findings_list
    from application.queries import list_findings

    monkeypatch.setattr(list_findings, "load_pay_periods", lambda account_id=None: [])
    with pytest.raises(ClientNotFound, match="No payroll for client 7"):
        findings_list(7, 2025)


# ------------------------------------------------------------ claim_cell_history


def test_claim_cell_history_equals_the_rest_endpoint(book, claims_repo):
    from api.claims import cell_history as endpoint
    from application.capabilities.claims import claim_cell_history

    _seed(claims_repo)
    result = claim_cell_history(2001, "GA_JTC", 2023)
    assert _same(result.facts, endpoint(2001, "GA_JTC", 2023))
    assert result.provenance.source == "recorded claims"


def test_a_cell_nobody_recorded_is_not_an_empty_history(claims_repo):
    from application.capabilities.claims import claim_cell_history

    with pytest.raises(NotCalculated, match="No claim recorded"):
        claim_cell_history(2001, "GA_JTC", 2023)


# --------------------------------------------------------------------- registry


def test_the_registry_runs_a_capability_by_name(book, claims_repo):
    _seed(claims_repo)
    result = registry.call("client_situation", client_id=2001)
    assert result.tool == "client_situation"
    assert result.facts["client_name"] == "Cascade Retail Partners"


def test_an_unbuilt_tool_cannot_be_called():
    with pytest.raises(NotImplementedError):
        registry.get("verify_figures")
    with pytest.raises(NotImplementedError):
        registry.get("claim_transition_commit")


def test_money_in_facts_stays_exact(book, claims_repo):
    from application.capabilities.client import client_situation

    _seed(claims_repo)
    identified = client_situation(2001).facts["identified_usd"]
    assert isinstance(identified, str) and Decimal(identified) == Decimal("140000")
