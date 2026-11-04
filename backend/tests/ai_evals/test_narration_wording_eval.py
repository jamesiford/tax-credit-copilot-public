"""The new narration and routing eval items can fail. [CH-15c]

An eval that cannot fail proves nothing, so these tests break the subject on purpose and
expect the score to drop: the hedging guard switched off, a client question sent to the whole
book, a narration that is kept but written the way the prompt forbids.
"""
from __future__ import annotations

import re

import pytest

from application import composer_hedging
from tests.ai_evals import harness

pytestmark = pytest.mark.ai_eval


def rows(suite: str, prefix: str):
    return [r for r in harness.load_rows(suite, live=False) if r["id"].startswith(prefix)]


def test_the_new_narration_rows_cover_the_six_answers_and_both_verdicts():
    items = rows("narration", "nar-")
    assert {r["expect"] for r in items} == {"pass", "reject"}
    assert sum(r["expect"] == "pass" for r in items) >= 6 and sum(r["expect"] == "reject" for r in items) >= 6
    assert all(r.get("must_contain") for r in items if r["expect"] == "pass")


def test_the_hedge_rows_fail_if_the_composer_stops_rejecting_hedges(monkeypatch):
    monkeypatch.setattr(composer_hedging, "hedged_figures", lambda masked: 0)
    result = harness.score_narration(rows("narration", "nar-hedge"), harness.recorded_reply, "offline")
    assert result.passed == 0 and len(result.failures) == len(rows("narration", "nar-hedge"))


def test_the_hedge_rows_pass_with_the_guard_in_place():
    result = harness.score_narration(rows("narration", "nar-hedge"), harness.recorded_reply, "offline")
    assert result.score == 1.0, result.failures


def test_rank_prose_is_flagged_by_the_wording_check_even_though_the_composer_keeps_it():
    for row in rows("narration", "nar-rank"):
        text, used = harness.composed_reply(row)
        assert used, "the composer cannot see rank prose; the eval is what holds the line"
        assert harness._wording_problems(row, text)


def test_a_good_narration_is_judged_on_its_must_contain_and_forbidden_patterns():
    good = rows("narration", "nar-book-ranking")[0]
    assert harness._judge_composed(good)[1]
    assert not harness._judge_composed({**good, "must_contain": ["a sentence it never says"]})[1]
    assert not harness._judge_composed({**good, "forbidden": ["Start with"]})[1]


def test_the_default_forbidden_wording_catches_the_failures_seen_live():
    banned = harness.FORBIDDEN_WORDING
    for sample in ("about", "Roughly", "approximately", "around", "nearly", "rounded", "up to", "position 1",
                   "ranked first", "number one"):
        assert any(re.search(p, sample) for p in banned), sample


def test_a_client_question_sent_to_the_whole_book_fails_the_routing_eval():
    client_rows = [r for r in harness.load_rows("routing", live=False) if r.get("forbidden")]
    assert len(client_rows) >= 6
    result = harness.score_routing(client_rows, lambda q: ["book"], "offline")
    assert result.passed == 0
    also_book = harness.score_routing(client_rows, lambda q: [next(r for r in client_rows if r["question"] == q)["expected"][0], "book"], "offline")
    assert also_book.passed == 0 and "forbidden ['book']" in also_book.failures[0]


def test_the_client_rows_pass_with_the_real_keyword_router():
    client_rows = [r for r in harness.load_rows("routing", live=False) if r.get("forbidden")]
    assert harness.score_routing(client_rows, harness.keyword_route, "offline").score == 1.0
