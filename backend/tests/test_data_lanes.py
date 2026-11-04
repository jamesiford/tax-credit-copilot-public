"""The lanes on the envelope: the audience of a block, the person-only facts and the model projection. [CH-16d, ADR-009]

A lane is a property of the envelope, enforced by the one projection a model-facing caller reads,
not a habit. These tests pin that an old envelope serialises exactly as before, that an unknown
word fails closed, and that the projection removes what a model must not be handed.
"""
from __future__ import annotations

import json

import pytest

from application.capabilities import lanes
from application.capabilities.envelope import AUDIENCES, Block, Provenance, ToolResult


def employee_result(rows: int = 3) -> dict:
    facts = {"audience": "user", "row_count": rows, "rows": [{"record_token": f"tok-{i}"} for i in range(rows)], "dataset": "d"}
    return ToolResult(
        tool="data_query", facts=facts, user_only_facts=("rows",),
        blocks=(Block("heading", text="Result"), Block("table", rows=(("record_token",), ("tok-0",)), audience="user")),
    ).to_dict()


# ------------------------------------------------------------------------------ envelope


def test_the_default_audience_is_both_and_an_old_block_serialises_unchanged():
    block = Block("paragraph", text="hello")
    assert block.audience == "both" and block.to_dict() == {"kind": "paragraph", "rows": [], "text": "hello"}


def test_a_user_block_says_so_on_the_wire():
    assert Block("table", rows=(("a",), ("1",)), audience="user").to_dict()["audience"] == "user"


def test_an_audience_the_envelope_does_not_know_cannot_be_constructed():
    with pytest.raises(ValueError):
        Block("paragraph", text="x", audience="everyone")
    assert set(AUDIENCES) == {"both", "user"}


def test_a_result_with_no_person_only_facts_serialises_without_the_key():
    wire = ToolResult(tool="t", facts={"a": 1}).to_dict()
    assert "user_only_facts" not in wire and list(wire) == sorted(wire)


def test_user_only_facts_must_name_facts_that_exist():
    with pytest.raises(ValueError):
        ToolResult(tool="t", facts={"a": 1}, user_only_facts=("rows",))


def test_the_wire_form_is_stable_json():
    first = ToolResult(tool="t", facts={"rows": [1]}, user_only_facts=("rows",)).to_json()
    assert first == ToolResult(tool="t", facts={"rows": [1]}, user_only_facts=("rows",)).to_json() and json.loads(first)["user_only_facts"] == ["rows"]


# --------------------------------------------------------------------------- projection


def test_the_projection_drops_person_only_blocks_and_facts():
    envelope = employee_result()
    assert [b["kind"] for b in lanes.model_blocks(envelope)] == ["heading"]
    facts = lanes.model_facts(envelope)
    assert "rows" not in facts and facts["row_count"] == 3 and facts["dataset"] == "d"


def test_the_whole_envelope_carries_no_row_value_into_the_projection():
    envelope = employee_result()
    seen = json.dumps({"facts": lanes.model_facts(envelope), "blocks": lanes.model_blocks(envelope)})
    assert "tok-" not in seen


def test_has_user_lane_sees_either_a_block_or_a_fact():
    assert lanes.has_user_lane(employee_result())
    only_facts = {**employee_result(), "blocks": []}
    only_blocks = {**employee_result(), "user_only_facts": []}
    assert lanes.has_user_lane(only_facts) and lanes.has_user_lane(only_blocks)
    assert not lanes.has_user_lane(ToolResult(tool="t", facts={"a": 1}, blocks=(Block("paragraph", text="x"),)).to_dict())


@pytest.mark.parametrize("word", ["everyone", "", "USER", None, 0])
def test_a_word_that_is_not_both_fails_closed(word):
    assert lanes.is_user_block({"kind": "paragraph", "audience": word}) is True
    assert lanes.is_user_block({"kind": "paragraph"}) is False and lanes.is_user_block({"kind": "paragraph", "audience": "both"}) is False


def test_a_producer_that_said_user_but_forgot_to_name_its_rows_is_still_obeyed():
    envelope = {"facts": {"audience": "user", "rows": [{"a": "secret"}], "row_count": 1}, "blocks": []}
    assert "rows" not in lanes.model_facts(envelope)


def test_a_long_rows_list_is_cut_for_the_model_only():
    envelope = ToolResult(tool="t", facts={"rows": [{"n": i} for i in range(200)]}).to_dict()
    assert len(lanes.model_facts(envelope)["rows"]) == lanes.MODEL_ROW_LIMIT and len(envelope["facts"]["rows"]) == 200


def test_the_projection_does_not_alter_the_envelope_it_reads():
    envelope = employee_result()
    before = json.dumps(envelope, sort_keys=True)
    lanes.model_facts(envelope), lanes.model_blocks(envelope)
    assert json.dumps(envelope, sort_keys=True) == before


def test_the_provenance_of_a_lane_split_result_is_untouched():
    assert Provenance(run_id="r").to_dict()["run_id"] == "r"
