"""Figures from the person's lane are not the narrator's context, at the guard itself. [RM-05, ADR-008, ADR-009]

The orchestrator's tests (`channel_orchestrator/test_orch_numeric_lanes.py`) pin this through the whole
turn. These are the same rule at the three modules it rests on, with no orchestrator in the way:

- `lanes.model_facts` is the only projection a model reads, and a figure only the person's rows hold
  is not in it;
- the guard, given that projection, rejects a sentence carrying the figure; given the full facts (what
  the person's own reply is verified against) it passes, so the lane is the whole difference;
- the numerals a reader supplied (`AllowedContext`) are the question and the scope, never the rows;
- a narrator's typed digit is rejected even when the facts hold it: the model only names, the platform prints.
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from application import numeric_guard
from application.capabilities import lanes
from application.capabilities.envelope import Block, Provenance, ToolResult
from application.composer import compose
from application.numeric_guard import AllowedContext, FactIndex

WAGE = "612.45"
HOURS = "37.25"


def employee_envelope() -> dict:
    """A data_query answer the way the API sends it: the rows in the person's lane, the aggregates in both."""
    facts = {
        "dataset": "employee_eligibility", "row_count": 2, "audience": "user",
        "rows": [{"record_token": "record_token-1001-1", "total_wages": float(WAGE), "avg_weekly_hours": float(HOURS)},
                 {"record_token": "record_token-1001-2", "total_wages": 701.1, "avg_weekly_hours": 30.5}],
    }
    return ToolResult(
        tool="data_query", facts=facts, user_only_facts=("rows",), provenance=Provenance(run_id="run-1", source="Source: warehouse"),
        blocks=(Block("heading", text="Query result"),
                Block("table", rows=(("record_token", "total_wages"), ("record_token-1001-1", WAGE)), audience="user")),
    ).to_dict()


def indexes() -> tuple[FactIndex, FactIndex]:
    envelope = employee_envelope()
    return FactIndex.from_facts(envelope["facts"]), FactIndex.from_facts(lanes.model_facts(envelope))


def test_the_figures_only_the_rows_hold_are_not_in_the_models_projection():
    full, shown = indexes()
    for figure in (WAGE, HOURS, "701.1", "30.5"):
        assert Decimal(figure) in full.values
        assert Decimal(figure) not in shown.values
    assert shown.leaves.keys() >= {"row_count", "dataset"} and not any(path.startswith("rows") for path in shown.leaves)


def test_a_projection_that_forgot_to_name_its_rows_still_hides_them():
    envelope = employee_envelope()
    envelope.pop("user_only_facts")
    assert "rows" not in lanes.model_facts(envelope), "a producer that said `user` and forgot to name its rows is still obeyed"


@pytest.mark.parametrize("audience", ["user", "somebody", "USER", "", None])
def test_any_audience_word_that_is_not_both_closes_the_lane(audience):
    envelope = employee_envelope()
    envelope.pop("user_only_facts")
    envelope["facts"]["audience"] = audience if audience is not None else "none"
    assert "rows" not in lanes.model_facts(envelope)


def test_the_guard_given_the_models_view_rejects_a_sentence_carrying_a_row_figure():
    full, shown = indexes()
    sentence = f"The top employee earned {WAGE} in wages."
    assert numeric_guard.check(sentence, facts=shown, allowed_context=AllowedContext()).status == numeric_guard.REJECTED
    assert numeric_guard.check(sentence, facts=full, allowed_context=AllowedContext()).status == numeric_guard.PASS, \
        "the person's own reply, which shows the rows, is verified against them: the lane is the whole difference"


@pytest.mark.parametrize("figure", [WAGE, HOURS, "701.1", "30.5"])
def test_the_narrators_typed_digit_is_rejected_even_when_the_facts_hold_it(figure):
    full, _ = indexes()
    result = numeric_guard.check_raw(f"The figure is {figure}.", allowed_context=AllowedContext())
    assert result.status == numeric_guard.REJECTED
    composed = compose([Block("heading", text="Result")], f"The figure is {figure}.", full, AllowedContext())
    assert composed.narration_used is False and composed.guard.status == numeric_guard.REJECTED


def test_the_readers_allowed_numerals_are_their_words_and_the_scope_never_the_rows():
    envelope = employee_envelope()
    context = AllowedContext.build("list 5 people for client 1001 in 2023", years=[2023], numbers=[1001])
    assert {Decimal(5), Decimal(1001), Decimal(2023)} <= context.values
    rows = {Decimal(WAGE), Decimal(HOURS), Decimal("701.1"), Decimal("30.5")}
    assert not rows & context.values and not rows & context.percents and envelope["facts"]["rows"]


def test_the_reader_saying_a_row_figure_themselves_is_the_only_way_it_becomes_allowed_context():
    """The narrow door: a figure the READER typed may be said back. The rows never open it."""
    full, shown = indexes()
    context = AllowedContext.build(f"is {WAGE} a lot?")
    assert numeric_guard.check(f"You asked about {WAGE}.", facts=shown, allowed_context=context).status == numeric_guard.PASS
    assert numeric_guard.check(f"You asked about {WAGE}.", facts=shown, allowed_context=AllowedContext()).status == numeric_guard.REJECTED
