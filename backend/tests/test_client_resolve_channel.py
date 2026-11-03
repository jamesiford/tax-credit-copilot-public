"""The channel's `client_resolve` settles one exact name instead of asking about it. [CH-15e]

Live (3 Nov): "brief me on <full client name>" still came back as a question, because with no
client selected the resolver always asked, so every Teams or Cowork conversation paid one
extra turn for a name the reader had already given. The channel now takes one exact name or
alias as the answer; partial text and two names still ask, and the portal's `strict`
behaviour and `chat_scope.resolve_referent` are unchanged.
"""
from __future__ import annotations

import copy

import pytest

from application import client_book
from application.capabilities.client import client_resolve
from application.capabilities.errors import Ambiguous
from application.chat_scope import ClientName, resolve_referent

BOOK = [
    {"account_id": 2001, "name": "Cascade Retail Partners"},
    {"account_id": 2002, "name": "Cascade Foods Group"},
    {"account_id": 2003, "name": "Northwind Care Systems"},
    {"account_id": 2004, "name": "Ironbridge Logistics"},
]


@pytest.fixture(autouse=True)
def book(monkeypatch):
    monkeypatch.setattr(client_book, "clients", lambda: copy.deepcopy(BOOK))


def _facts(text, history=(), current=None):
    return client_resolve(text, history, current).facts


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Northwind Care Systems", 2003),
        ("what is the trend for NORTHWIND CARE SYSTEMS?", 2003),
        ("brief me on Northwind", 2003),
        ("Ironbridge's position", 2004),
        ("Cascade Retail Partners", 2001),
        ("Cascade Foods Group", 2002),
    ],
    ids=["full", "case-insensitive", "alias", "possessive-alias", "full-shared-first-word", "full-other"],
)
def test_one_exact_name_or_alias_resolves_with_nothing_selected(text, expected):
    facts = _facts(text)
    assert facts["resolved"] is True and facts["clarify"] is False
    assert facts["client_id"] == expected and facts["candidates"] == []


@pytest.mark.parametrize(
    "text",
    ["Cascade", "compare Cascade Retail Partners and Northwind", "Northwind and Ironbridge", "Northw", "the Casc account", "Acme Corp"],
    ids=["alias-shared-by-two", "two-full-names", "two-aliases", "partial", "partial-in-sentence", "no-match"],
)
def test_partial_ambiguous_or_missing_names_still_ask(text):
    facts = _facts(text)
    assert facts["resolved"] is False and facts["clarify"] is True and facts["client_id"] is None
    assert facts["candidates"], "numbered candidates are offered, never a guess"


def test_the_two_similar_names_are_offered_as_the_two_candidates():
    facts = _facts("Cascade")
    assert [c["client_id"] for c in facts["candidates"]] == [2001, 2002]


def test_a_referent_with_a_current_client_resolves_and_without_one_asks():
    for word in ("their trend", "what about them", "this client's headcount"):
        assert _facts(word, current=2003)["resolved"] is True
        assert _facts(word, current=2003)["client_id"] == 2003
        without = _facts(word)
        assert without["resolved"] is False and without["clarify"] is True


def test_a_referent_after_a_turn_naming_two_clients_still_asks():
    history = [{"role": "user", "text": "compare Northwind and Ironbridge"}]
    facts = _facts("and their trend?", history, current=2003)
    assert facts["resolved"] is False and {c["client_id"] for c in facts["candidates"]} == {2003, 2004}


def test_naming_a_client_other_than_the_current_one_switches_to_the_named():
    facts = _facts("what about Ironbridge Logistics?", current=2003)
    assert facts["resolved"] is True and facts["client_id"] == 2004


def test_a_resolved_answer_says_whose_it_is():
    result = client_resolve("Northwind Care Systems")
    assert result.facts["client_name"] == "Northwind Care Systems"
    assert "Answering for Northwind Care Systems" in result.to_dict()["blocks"][0]["text"]


def test_strict_keeps_the_portals_rule_and_the_chat_resolver_is_untouched():
    with pytest.raises(Ambiguous):
        client_resolve("Northwind Care Systems", strict=True)
    names = [ClientName(c["account_id"], c["name"]) for c in BOOK]
    portal = resolve_referent("Northwind Care Systems", [], None, names)
    assert portal.clarify is True and portal.client_id is None
