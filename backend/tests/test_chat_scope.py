"""WI-14: when the client is not unambiguous, the chat asks — it never picks.

The 23 Sep call caught a follow-up answered about Halloway Foods while the room
was talking about Cascade. A client was in scope, so the refusal never fired.
These pin every rule `resolve_referent` applies, and then drive the endpoint
end to end with no model, because whose payroll an answer describes must not
depend on a router being up.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from application.chat_scope import ClientName, aliases, clients_named, resolve_referent

BOOK = [
    ClientName(1001, "Candle Bottle"),
    ClientName(2001, "Cascade Retail Partners"),
    ClientName(2002, "Northwind Care Systems"),
    ClientName(2003, "Ironbridge Logistics"),
    ClientName(2004, "Halloway Foods"),
]
BOOK_ANSWER = [
    {"role": "user", "text": "Who is our next best customer?"},
    {"role": "assistant", "text": "Ironbridge Logistics first, then Halloway Foods, then Cascade Retail Partners."},
]


# ------------------------------------------------------------ naming


def test_a_client_is_named_in_full_or_by_its_first_word():
    assert aliases(ClientName(2001, "Cascade Retail Partners")) == ["cascade retail partners", "cascade"]
    assert clients_named("brief me on Cascade", BOOK) == [2001]
    assert clients_named("what about halloway foods?", BOOK) == [2004]


def test_names_come_back_in_the_order_they_were_said():
    assert clients_named("compare Halloway with Ironbridge", BOOK) == [2004, 2003]


def test_a_word_inside_another_word_is_not_a_name():
    assert clients_named("cascaded failures", BOOK) == []


# ------------------------------------------------------------ the rules


def test_the_meeting_bug_a_pronoun_after_a_list_is_asked_not_guessed():
    """Scoped to Halloway, the room just heard three clients, and says "their"."""
    r = resolve_referent("what is their trend since the base year?", BOOK_ANSWER, 2004, BOOK)
    assert r.clarify
    assert set(r.candidates) == {2003, 2004, 2001}
    assert r.client_id is None


def test_naming_a_different_client_from_the_scope_asks_which():
    r = resolve_referent("brief me on Cascade", [], 2004, BOOK)
    assert r.clarify
    assert r.candidates == (2001, 2004)


def test_naming_the_client_in_scope_just_answers():
    r = resolve_referent("brief me on Cascade", [], 2001, BOOK)
    assert not r.clarify and r.client_id == 2001


def test_two_clients_in_one_question_asks_which():
    r = resolve_referent("brief me on Cascade and Halloway", [], 2001, BOOK)
    assert r.clarify and r.candidates == (2001, 2004)


def test_one_client_named_with_nothing_selected_asks_to_confirm():
    """So the year the answer is for is on the button, not assumed."""
    r = resolve_referent("brief me on Ironbridge", [], None, BOOK)
    assert r.clarify and r.candidates == (2003,)


def test_a_pronoun_that_points_at_the_scoped_client_answers():
    history = [{"role": "assistant", "text": "Cascade Retail Partners is on the line."}]
    r = resolve_referent("what is their trend?", history, 2001, BOOK)
    assert not r.clarify and r.client_id == 2001


def test_a_question_about_the_page_with_a_client_selected_answers():
    r = resolve_referent("show me the eligibility", BOOK_ANSWER, 2001, BOOK)
    assert not r.clarify and r.client_id == 2001


def test_a_question_about_nobody_with_nothing_selected_offers_the_book():
    r = resolve_referent("show me the eligibility", [], None, BOOK)
    assert r.clarify and set(r.candidates) == {c.client_id for c in BOOK}


def test_a_client_that_is_not_on_the_book_is_not_a_scope():
    r = resolve_referent("show me the eligibility", [], 9999, BOOK)
    assert r.clarify


def test_the_same_question_gets_the_same_answer_every_time():
    """Shashi rehearses fixed questions. Deterministic is the requirement."""
    first = resolve_referent("what is their trend?", BOOK_ANSWER, 2004, BOOK)
    assert all(resolve_referent("what is their trend?", BOOK_ANSWER, 2004, BOOK) == first for _ in range(5))


# ------------------------------------------------------------ the endpoint


def _frames(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        event, data = "message", "{}"
        for line in block.splitlines():
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        out.append((event, json.loads(data)))
    return out


@pytest.fixture
def client(monkeypatch):
    import api.chat as chat
    from main import app

    monkeypatch.setattr(chat, "_chat_clients", lambda: list(BOOK))
    monkeypatch.setattr(chat, "_candidate_year", lambda cid, req: req.tax_year if cid == req.client_id else 2025)
    return TestClient(app)


def _ask(client, **payload):
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 200
    return _frames(response.text)


def test_the_endpoint_asks_instead_of_answering_for_the_scoped_client(client):
    frames = _ask(
        client, message="what is their trend since the base year?",
        client_id=2004, tax_year=2025, history=BOOK_ANSWER,
    )
    clarify = [data for event, data in frames if event == "clarify"]
    assert clarify, "asked nothing"
    names = [c["name"] for c in clarify[0]["choices"]]
    assert set(names) == {"Ironbridge Logistics", "Halloway Foods", "Cascade Retail Partners"}
    # The scoped client keeps the page's year; the others carry the year of
    # their own latest run, so the button says what it will answer for.
    years = {c["client_id"]: c["tax_year"] for c in clarify[0]["choices"]}
    assert years[2004] == 2025
    text = "".join(d.get("content", "") for e, d in frames if e == "token")
    assert "Which client do you mean" in text
    assert frames[-1][0] == "done"
    assert not any(e == "calculation_trail" for e, _ in frames)


def test_a_confirmed_choice_is_answered_not_asked_again(client):
    frames = _ask(
        client, message="what is their trend since the base year?",
        client_id=2001, tax_year=2025, history=BOOK_ANSWER, client_confirmed=True,
    )
    assert not any(e == "clarify" for e, _ in frames)


def test_the_book_question_is_never_held_up_by_clarification(client):
    """It is about everybody. Nothing to disambiguate."""
    frames = _ask(client, message="Who is our next best customer, and why?")
    assert not any(e == "clarify" for e, _ in frames)


# ------------------------------------------------ the book the chat reads


def test_the_chat_reads_the_book_in_the_page_order_by_name(monkeypatch):
    """The headline question once answered "Northwind first" beside a page that
    said Ironbridge: a second ranking, filtered by the shell's year, with no
    `declining` overlay. The brief now IS the page's read."""
    import api.chat as chat
    import api.claims as claims

    calls = []

    def page(**kwargs):
        calls.append(kwargs)
        return {
            "total_clients": 3, "assessed_clients": 3,
            "items": [
                {"client_id": 2003, "client_name": "Ironbridge Logistics", "priority_band": "on_the_line",
                 "program_code": "GA_JTC", "tax_year": 2022, "identified_usd": "0", "jobs_margin": -0.83},
                {"client_id": 2004, "client_name": "Halloway Foods", "priority_band": "declining",
                 "program_code": "GA_JTC", "tax_year": 2021, "identified_usd": "77000",
                 "trend": {"declining": True, "credit_earned_usd": "97000"}},
                {"client_id": 2002, "client_name": "Northwind Care Systems", "priority_band": "unclaimed_at_scale",
                 "program_code": "GA_JTC", "tax_year": 2025, "identified_usd": "40495"},
            ],
        }

    monkeypatch.setattr(claims, "portfolio_v2", page)
    brief = chat._book_brief()

    assert calls[0]["year"] is None, "the book has no year"
    assert calls[0]["sort"] == "priority" and calls[0]["order"] == "asc"
    assert [c["client_name"] for c in brief["clients"]] == [
        "Ironbridge Logistics", "Halloway Foods", "Northwind Care Systems",
    ]
    # The page's words, never the enum ids.
    assert [c["reason"] for c in brief["clients"]] == ["On the line", "Declining", "Identified"]
    assert brief["clients"][1]["credit_earned_on_trend_usd"] == "97000"
    assert "unclaimed_at_scale" not in json.dumps(brief)


def test_an_empty_book_says_so_rather_than_ranking_nothing(monkeypatch):
    import api.chat as chat
    import api.claims as claims

    monkeypatch.setattr(claims, "portfolio_v2", lambda **_: {"items": []})
    assert chat._book_brief()["calculated"] is False
