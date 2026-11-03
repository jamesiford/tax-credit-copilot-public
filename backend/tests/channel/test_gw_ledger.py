"""The fact ledger and `verify_figures`. [CH-06, ADR-008]

The gateway remembers the facts of every result it returned in a conversation and
checks a draft against exactly those. What matters: a figure the conversation was told
passes; the same figure with one digit changed is rejected; nothing is waved through
for a conversation that was told nothing; and results that carry digits which are not
figures (a confirmation token, a ticket, the check's own positions) are never kept.
"""
from __future__ import annotations

import pytest

from channel.ledger import MAX_CONVERSATIONS, MAX_RESULTS, TTL_SECONDS, FactLedger
from gateway_harness import FakeApi, agent_headers, build_gateway, envelope

ELIGIBILITY = "/channel/v1/tools/client_eligibility"
VERIFY = "/channel/v1/tools/verify_figures"
ASKED = {"args": {"client_id": 2001, "tax_year": 2023}}
FACTS = {"credit": {"annual_credit_usd": "31500.00", "per_job_usd": "3500.00"}, "headcount": {"eligible_jobs": 9}}


@pytest.fixture
def told(gateway, fake_api):
    """A gateway whose conversation `conv-1` has been told FACTS."""
    fake_api.replies["client_eligibility"] = (200, envelope("client_eligibility", FACTS))
    assert gateway.client.post(ELIGIBILITY, json=ASKED, headers=agent_headers()).status_code == 200
    return gateway


def verify(gw, text, *, allowed=None, **headers):
    args = {"draft_text": text, **({"allowed_context": allowed} if allowed else {})}
    response = gw.client.post(VERIFY, json={"args": args}, headers=agent_headers(**headers))
    assert response.status_code == 200, response.text
    return response.json()["facts"]


# --------------------------------------------------------------- positive


@pytest.mark.parametrize("text", [
    "The credit is 31500.00 across 9 eligible jobs.", "At 3500.00 a job.", "Nine hundred is not a figure and 9 jobs is.",
])
def test_a_figure_the_conversation_was_told_passes(told, text):
    facts = verify(told, text)
    assert facts["status"] == "pass" and facts["violations"] == [] and facts["checked_numerals"] >= 1


def test_the_readers_own_numerals_pass_as_allowed_context(told):
    assert verify(told, "You asked about 5 hires.")["status"] == "rejected"
    assert verify(told, "You asked about 5 hires.", allowed=["5 hires"])["status"] == "pass"


# --------------------------------------------------------------- mutations


def _flipped(text: str):
    for position, char in enumerate(text):
        if char.isdigit():
            yield text[:position] + str((int(char) + 1) % 10) + text[position + 1:]


@pytest.mark.parametrize("figure", ["31500.00", "3500.00"])
def test_flipping_any_one_digit_of_a_returned_figure_is_rejected(told, figure):
    mutations = list(_flipped(figure))
    assert mutations
    for mutated in mutations:
        facts = verify(told, f"The figure is {mutated}.")
        assert facts["status"] == "rejected", mutated
        assert facts["violations"][0]["token"] and facts["violations"][0]["reason"]
        assert isinstance(facts["violations"][0]["position"], int)


def test_a_dropped_decimal_and_a_stray_figure_are_rejected(told):
    assert verify(told, "The credit is 3150000.")["status"] == "rejected"
    assert verify(told, "Also 12345 other things.")["status"] == "rejected"


# ------------------------------------------------------- isolation and honesty


def test_a_conversation_that_was_told_nothing_passes_nothing(gateway):
    facts = verify(gateway, "The credit is 31500.00.")
    assert facts["status"] == "rejected" and facts["checked_numerals"] == 1


def test_conversations_do_not_share_facts(told):
    assert verify(told, "The credit is 31500.00.", conversation="conv-2")["status"] == "rejected"
    assert verify(told, "The credit is 31500.00.", conversation="conv-1")["status"] == "pass"


def test_the_checks_own_result_is_not_recorded_so_it_cannot_launder_a_figure(told):
    first = verify(told, "A figure of 777.")
    assert first["status"] == "rejected"
    assert verify(told, "A figure of 777.")["status"] == "rejected"
    assert all("violations" not in held for held in told.ledger.facts_for("conv-1"))


def test_a_confirmation_token_and_a_ticket_are_not_kept(gateway, fake_api):
    fake_api.replies["engagement_set_prepare"] = (200, envelope("engagement_set_prepare", {
        "preview": {"after": {"scope": "in_scope"}}, "confirmation": {"token": "t0k3n" + "8" * 40, "expires_at": "2026-11-02T12:00:00"}}))
    gateway.client.post("/channel/v1/tools/engagement_set_prepare", json={"args": {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope"}},
                        headers=agent_headers(oid="bbbbbbbb-0000-4000-8000-000000000002"))
    held = gateway.ledger.facts_for("conv-1")
    assert held and "confirmation" not in held[0] and "preview" in held[0]
    fake_api.replies["claim_package_link"] = (200, envelope("claim_package_link", {"download_path": "/channel/v1/downloads/abc123456789012345"}))
    gateway.client.post("/channel/v1/tools/claim_package_link", json={"args": {"client_id": 2001, "tax_year": 2023}}, headers=agent_headers())
    assert len(gateway.ledger.facts_for("conv-1")) == 1


def test_verify_is_audited_as_a_read_with_the_guards_verdict(told):
    verify(told, "The credit is 31500.00.")
    verify(told, "The credit is 31501.00.")
    ends = [e for e in told.events() if e.tool_name == "verify_figures" and e.phase == "end"]
    assert [(e.outcome, e.numeric_guard) for e in ends] == [("ok", "pass"), ("ok", "rejected")]


def test_verify_never_reaches_the_api(told, fake_api):
    before = len(fake_api.calls)
    verify(told, "31500.00")
    assert len(fake_api.calls) == before


def test_verify_rejects_a_malformed_request(gateway):
    response = gateway.client.post(VERIFY, json={"args": {"draft_text": 5}}, headers=agent_headers())
    assert response.status_code == 422 and response.json()["error"]["code"] == "invalid_arguments"


# ---------------------------------------------------------------------- bounds


def test_facts_expire_after_the_ttl():
    clock = [0.0]
    ledger = FactLedger(clock=lambda: clock[0])
    ledger.record("c", "client_trend", {"a": 1})
    clock[0] = TTL_SECONDS - 1
    assert ledger.facts_for("c")
    clock[0] = TTL_SECONDS + 1
    assert ledger.facts_for("c") == []


def test_the_ledger_is_bounded_in_conversations_and_in_results():
    ledger = FactLedger()
    for n in range(MAX_CONVERSATIONS + 5):
        ledger.record(f"c{n}", "client_trend", {"n": n})
    assert ledger.facts_for("c0") == [] and ledger.facts_for(f"c{MAX_CONVERSATIONS + 4}")
    for n in range(MAX_RESULTS + 10):
        ledger.record("one", "client_trend", {"n": n})
    held = ledger.facts_for("one")
    assert len(held) == MAX_RESULTS and held[-1] == {"n": MAX_RESULTS + 9}


def test_a_restart_forgets_and_the_strict_answer_is_no(tmp_path):
    api = FakeApi(replies={"client_eligibility": (200, envelope("client_eligibility", FACTS))})
    first = build_gateway(tmp_path, api=api)
    first.client.post(ELIGIBILITY, json=ASKED, headers=agent_headers())
    assert verify(first, "31500.00")["status"] == "pass"
    second = build_gateway(tmp_path, api=api)
    assert verify(second, "31500.00")["status"] == "rejected"
