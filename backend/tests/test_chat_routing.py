"""Routing: what the chat can answer, and how one question becomes several.

The router is a language model, so these tests pin the DETERMINISTIC half —
validation, fallback and splitting. A model that invents `trend_analysis` must
not be able to dispatch it, and a model that is unavailable must not be able to
take the whole feature down with it.
"""
from __future__ import annotations

import pytest

from api.chat import (
    CAPABILITIES,
    ChatRequest,
    ChatTurn,
    _keyword_intents,
    _validate_plan,
)


def test_every_capability_has_a_pipeline():
    """A named capability nothing can run is a promise the router will keep making."""
    from api.chat import _run_intent

    assert set(CAPABILITIES) == {
        "book", "situation", "eligibility", "at_risk", "trend", "multi_state",
        "discovery", "simulate", "explain",
    }
    assert callable(_run_intent)


def test_an_invented_intent_is_dropped_not_dispatched():
    """Models invent plausible names. A made-up one must not fall through to
    the default pipeline, which would answer a question nobody asked."""
    assert _validate_plan({"intents": ["trend_analysis", "client_deep_dive"]}, "x") \
        == _keyword_intents("x")
    assert _validate_plan({"intents": ["trend", "nonsense"]}, "x") == ["trend"]


def test_the_plan_keeps_order_and_collapses_duplicates():
    plan = _validate_plan({"intents": ["situation", "discovery", "situation"]}, "x")
    assert plan == ["situation", "discovery"]


def test_an_empty_plan_falls_back_rather_than_answering_nothing():
    """A chat that answers nothing because a router hiccupped is worse than one
    that answers approximately."""
    assert _validate_plan({"intents": []}, "what if we hired 5 people") == ["simulate"]
    assert _validate_plan(None, "walk me through the calculation") == ["explain"]
    assert _validate_plan("garbage", "brief me on them") == ["situation"]


def test_a_bare_string_plan_is_accepted():
    # Models ignore "reply with JSON" often enough that this is not defensive.
    assert _validate_plan("trend", "x") == ["trend"]


def test_one_sentence_can_be_two_questions():
    """The reason routing moved off a single keyword match.

    The old router returned the FIRST match and dropped the rest silently, so
    half the question went unanswered with nothing to show it had been asked.
    """
    plan = _keyword_intents("brief me on them and what else might they qualify for")
    assert "situation" in plan
    assert "discovery" in plan


def test_the_follow_up_from_the_screenshot_routes_to_trend():
    """"What is their trend for subsequent years to their base year?"

    This previously matched no keyword, fell through to `eligibility`, and
    would have described a single year as though it were the whole history.
    """
    plan = _keyword_intents(
        "What is their trend for subsequent years to their base year? "
        "Have they been eligible since their base year?"
    )
    assert plan[0] == "trend"


def test_an_unrecognised_question_still_answers():
    assert _keyword_intents("how much is the credit") == ["eligibility"]


def test_jobs_that_may_fall_off_route_to_at_risk_not_simulate():
    """The question the router got wrong in use.

    "Of the net-new jobs counted toward the credit, are any close to the
    threshold and may fall off?" is about the CURRENT population, not a
    hypothetical — but it reads like a what-if, and simulate answered it by
    removing all nine counted jobs and reporting no impact on a closed year.
    """
    plan = _keyword_intents(
        "of the net new jobs that counted toward the credit, were there any "
        "close to the threshold that may fall off in upcoming years?"
    )
    assert plan[0] == "at_risk"
    assert "simulate" not in plan[:1]


def test_at_risk_is_not_the_near_miss_cohort():
    """Opposite populations: one is everybody OUTSIDE the credit, one INSIDE.

    Answering either with the other is a category error, and the words are
    close enough that it is an easy one to make.
    """
    coming_in = _keyword_intents("who is close to qualifying but has not yet?")
    falling_out = _keyword_intents("which counted jobs might fall off next year?")

    assert falling_out[0] == "at_risk"
    assert "at_risk" not in coming_in


# --- the portfolio question ------------------------------------------------


def test_who_should_we_reach_out_to_is_the_book_not_a_rule_pack_scan():
    """`multi_state` used to be called `portfolio` and is a scan for ONE client.

    With a capability literally named "portfolio", the router picks it for the
    cross-client question and answers something else entirely.
    """
    assert _keyword_intents("Who should we reach out to?")[0] == "book"
    assert _keyword_intents("which client should we call first?")[0] == "book"
    assert _keyword_intents("show me our complete credit picture")[0] == "multi_state"


def test_the_targeting_prompt_routes_to_the_book():
    """The portfolio page's own prompt, in the partner's words from the 24 Sep session.

    Keyword routing is what answers when Foundry is down. Rewording the page's
    prompt without teaching the fallback the new words would send the demo's
    headline question to whichever capability happened to match. Both the
    current wording and the 23 Sep one must still route.
    """
    for prompt in (
        "Who should we be targeting, and why? Rank them and say what I would open the call with.",
        "Who is our next best customer, and why?",
        "Who should we target first?",
    ):
        assert _keyword_intents(prompt)[0] == "book", prompt


def test_the_book_is_the_only_capability_that_needs_no_client():
    """Asked from the title bar, where no client is selected BY DESIGN."""
    from api.chat import _NEEDS_CLIENT

    assert "book" not in _NEEDS_CLIENT
    assert _NEEDS_CLIENT == set(CAPABILITIES) - {"book"}


def test_a_client_scoped_question_without_a_client_is_still_refused():
    """The refusal is about answering for the wrong company, and it stays.

    It is also checked with KEYWORDS so it does not depend on Foundry being
    configured — scope integrity must not hinge on whether a router is up.
    """
    from api.chat import _NEEDS_CLIENT

    plan = _keyword_intents("what is their trend since the base year?")
    assert all(i in _NEEDS_CLIENT for i in plan)


def test_history_travels_with_the_request():
    """Without it, "their" has no referent and the turn is unanswerable."""
    req = ChatRequest(
        message="what is their trend?",
        client_id=2001,
        tax_year=2023,
        history=[ChatTurn(role="user", text="brief me on Cascade")],
    )
    assert req.history[0].text == "brief me on Cascade"


def test_history_defaults_to_empty_rather_than_required():
    # The first turn of a conversation has none, and must not 422.
    assert ChatRequest(message="hello").history == []


@pytest.mark.parametrize("intent", sorted(CAPABILITIES))
def test_every_capability_is_reachable_by_words_alone(intent):
    """The keyword table is the fallback path, so it must cover the set.

    `eligibility` is the default and needs no keyword of its own.
    """
    if intent == "eligibility":
        pytest.skip("the default; reached when nothing else matches")
    from api.chat import _KEYWORDS

    assert any(name == intent for name, _ in _KEYWORDS)


# --- the trend brief -------------------------------------------------------


class _Reader:
    def __init__(self, years):
        self._years = years

    def client_year_series(self, client_id, *, method="pay_period"):
        return {"run": {"run_id": "r"}, "years": self._years, "method": method}


def _year(tax_year, eligible, *, base=False):
    return {
        "tax_year": tax_year, "annual_average": 100.0,
        "eligible_employees": eligible, "employees_evaluated": 150,
        "annual_credit_usd": "0", "is_base_year": base,
        "qualified_units": 0, "units": 5,
    }


def _trend(monkeypatch, years):
    import application.wiring as wiring
    from tools.portfolio import chat_client_trend

    monkeypatch.setattr(wiring, "get_gold_reader", lambda: _Reader(years))
    return chat_client_trend(account_id=2001)


def test_no_year_after_the_base_is_unknown_not_a_no(monkeypatch):
    """`False` there asserts "they have not been eligible since".

    The truth is that there is no year to judge. The reference client holds
    TY2023 and nothing else, so it hits this on every single read.
    """
    brief = _trend(monkeypatch, [_year(2023, 656, base=True)])
    assert brief["years_after_base"] == 0
    assert brief["eligible_every_year_since_base"] is None


def test_eligible_in_every_year_since_the_base(monkeypatch):
    brief = _trend(monkeypatch, [
        _year(2020, 91, base=True), _year(2021, 116), _year(2022, 123),
    ])
    assert brief["eligible_every_year_since_base"] is True
    assert brief["years_with_no_eligible_employees"] == []


def test_a_year_with_nobody_eligible_is_named(monkeypatch):
    """"Have they been eligible since their base year" needs the exception."""
    brief = _trend(monkeypatch, [
        _year(2020, 64, base=True), _year(2021, 0), _year(2022, 82),
    ])
    assert brief["eligible_every_year_since_base"] is False
    assert brief["years_with_no_eligible_employees"] == [2021]


def test_a_client_no_run_has_reached_carries_no_trend(monkeypatch):
    brief = _trend(monkeypatch, [])
    assert brief["calculated"] is False
    assert "years" not in brief
