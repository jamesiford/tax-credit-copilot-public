"""The data-question evals can fail. [CH-16e]

`data_routing` rows run each recorded plan through the real catalog, validator and SQLite fixture, and the
`nar-data-*` narration rows go through the real composer. An eval that cannot fail proves nothing, so these
tests break the subject on purpose (a wrong sequence, a forbidden tool, a lane flipped, a hedge guard off)
and expect the score to drop.
"""
from __future__ import annotations

import pytest

from application import composer_hedging
from tests.ai_evals import data_routing, harness

pytestmark = pytest.mark.ai_eval


def row(rid: str) -> dict:
    return next(r for r in data_routing.load_rows() if r["id"] == rid)


def failing(**changes) -> list[str]:
    base = row(changes.pop("rid"))
    return data_routing.score([{**base, **changes}]).failures


def test_there_are_at_least_twenty_five_data_questions_and_every_kind_is_among_them():
    rows = data_routing.load_rows()
    assert len(rows) >= 25 and len({r["id"] for r in rows}) == len(rows)
    refusals = {r["refusal"] for r in rows if r.get("refusal")}
    assert {"unknown_column", "blocked_column", "sql_like_value", "column_not_listable", "operator_not_allowed",
            "aggregation_not_allowed", "order_by_outside_selection", "invalid_arguments"} <= refusals
    assert {"user", "both"} <= {r["lane"] for r in rows if "lane" in r}
    assert any(r.get("truncated") for r in rows) and any(r.get("catalog_hits") == 0 for r in rows)
    assert any(r["plan"] == [] for r in rows), "a question the data cannot answer plans nothing"


def test_the_offline_data_routing_eval_meets_its_threshold_and_is_listed():
    result = data_routing.score(data_routing.load_rows())
    assert result.score >= harness.thresholds("offline")["data_routing"] == 1.0, result.failures
    assert "data_routing" in {r.suite for r in harness.run_offline()}


def test_a_wrong_tool_sequence_fails():
    assert failing(rid="loc-avg", expected=["data_query"])
    assert failing(rid="why-trend", expected=["data_query"])


def test_a_forbidden_tool_fails():
    assert "named forbidden data_query" in " ".join(failing(rid="fixed-first-credit", plan=[{"tool": "data_query", "args": {"dataset": "run_manifest", "select": ["run_status"]}}], expected=["data_query"]))


def test_a_tool_a_model_may_not_name_fails():
    assert "not a tool a model may name" in " ".join(failing(rid="free-form-sql", plan=[{"tool": "sql_query", "args": {}}], expected=["sql_query"]))
    assert "not a tool a model may name" in " ".join(failing(rid="a-write-is-not-data", plan=[{"tool": "engagement_set_commit", "args": {}}], expected=["engagement_set_commit"]))


def test_a_refusal_that_is_no_longer_expected_or_no_longer_happens_fails():
    assert "platform answered unknown_column, expected ok" in " ".join(failing(rid="invented-column", refusal=None))
    assert "expected unknown_column" in " ".join(failing(rid="loc-avg", refusal="unknown_column"))


def test_a_flipped_lane_cap_or_catalog_hit_fails():
    assert "lane user, expected both" in " ".join(failing(rid="employee-rows-user-lane", lane="both"))
    assert "lane both, expected user" in " ".join(failing(rid="employee-aggregate-model-lane", lane="user"))
    assert "truncated True, expected False" in " ".join(failing(rid="capped-list", truncated=False))
    assert "catalog hits" in " ".join(failing(rid="catalog-miss", catalog_hits=3))


def test_the_new_narration_rows_cover_both_verdicts_and_the_data_shapes():
    items = [r for r in harness.load_rows("narration", live=False) if r["id"].startswith("nar-data-")]
    assert sum(r["expect"] == "pass" for r in items) >= 8 and sum(r["expect"] == "reject" for r in items) >= 6
    assert all(r.get("must_contain") for r in items if r["expect"] == "pass")
    text = " ".join(r["narration"] for r in items)
    for shape in ("capped at", "has nothing for that", "not been shown", "No rows matched", "not why"):
        assert shape.lower() in text.lower(), shape


def test_the_data_narration_rows_pass_with_the_guards_and_fail_without_them(monkeypatch):
    items = [r for r in harness.load_rows("narration", live=False) if r["id"].startswith("nar-data-")]
    assert harness.score_narration(items, harness.recorded_reply, "offline").score == 1.0
    monkeypatch.setattr(composer_hedging, "hedged_figures", lambda masked: 0)
    broken = harness.score_narration([r for r in items if r["id"] == "nar-data-hedged-cap"], harness.recorded_reply, "offline")
    assert broken.passed == 0


def test_a_typed_figure_or_an_invented_path_in_a_data_narration_is_never_kept():
    for rid in ("nar-data-typed-cap", "nar-data-typed-count", "nar-data-invented-path", "nar-data-sql-block"):
        item = next(r for r in harness.load_rows("narration", live=False) if r["id"] == rid)
        text, used = harness.composed_reply(item)
        assert not used, rid
