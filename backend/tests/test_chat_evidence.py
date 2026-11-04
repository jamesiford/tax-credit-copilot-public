"""The portal chat's `evidence` event. [CH-15d]

Contract: docs/design/ASK-EVIDENCE-CONTRACT.md. The frontend half of the same
contract is `frontend/src/lib/evidence.js`; `askBackendShape.json` is the golden
file both sides read, so a change to the shape fails here AND in the frontend suite.

What is pinned: the event appears, once per capability that ran; it is JSON the
contract accepts (every figure a string, rows as wide as their header); it arrives
after the capability ran and before `done`; every existing event is unchanged; and
a sensitive capability's rows reach only a signed-in reader and never the model.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from api.chat import _dispatch
from api.chat.evidence import INTENT_TITLE, evidence_item
from api.chat.models import ChatRequest
from api.chat.sse import _AUTHENTICATED
from application.capabilities.catalog import CAPABILITIES, CHAT_INTENT_TOOL
from application.capabilities.envelope import Block, Provenance, ToolResult

GOLDEN = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "askBackendShape.json"
BLOCK_KINDS = {"text", "kpis", "table", "callout", "list"}
TONES = {"neutral", "above-min", "below-min", "partial", "base-year"}

#: Synthetic only. These look like what an employee-grain table would hold.
EMPLOYEE_ROWS = (("Worker A", "EMP-0001", "36.5"), ("Worker B", "EMP-0002", "35.2"))
EMPLOYEE_TABLE = Block("table", rows=(("Employee", "Id", "Hours"), *EMPLOYEE_ROWS))


def check_contract(item: dict) -> None:
    """The contract as the backend must honour it: strict where the frontend drops."""
    assert json.loads(json.dumps(item)) == item, "not JSON-stable"
    assert isinstance(item["tool"], str) and item["tool"]
    assert item.get("kind", "evidence") in {"evidence", "confirmation"}
    assert all(isinstance(v, str) for v in item.get("facts", {}).values()), "a fact is not a string"
    assert item["blocks"], "an evidence item needs a block"
    for block in item["blocks"]:
        assert block["kind"] in BLOCK_KINDS
        assert isinstance(block.get("title", ""), str)
        if block["kind"] in {"text", "callout"}:
            assert isinstance(block["text"], str)
        if block["kind"] == "callout":
            assert block.get("tone", "neutral") in TONES
        if block["kind"] == "list":
            assert all(isinstance(r, str) for r in block["rows"])
        if block["kind"] == "table":
            assert all(isinstance(c, str) for c in block["columns"])
            for row in block["rows"]:
                assert len(row) == len(block["columns"]), "a row of the wrong width"
                assert all(isinstance(cell, str) for cell in row), "a figure that is not a string"
    assert set(item.get("provenance", {})) <= {"run_id", "rule_pack", "trail_hash", "produced_at"}
    assert isinstance(item.get("disclaimer", ""), str)


def _result(tool: str, blocks, *, facts=None, warnings=(), provenance=None) -> ToolResult:
    return ToolResult(
        tool=tool, facts=facts or {}, blocks=tuple(blocks),
        provenance=provenance or Provenance(), warnings=tuple(warnings),
    )


def _situation() -> ToolResult:
    """The layout `client_situation` renders: a heading, a sentence, a table."""
    return _result(
        "client_situation",
        [
            Block("heading", text="Example Client A"),
            Block("paragraph", text="3 recorded cells. Identified credit: $31,185."),
            Block("table", rows=(
                ("Reason", "Programme", "Tax year", "Identified", "Jobs margin"),
                ("On the line", "GA_JTC", "2023", "$31,185", "-0.83"),
                ("Identified", "GA_JTC", "2024", "$0", "\u2014"),
            )),
            Block("bullets", rows=(("First point",), ("Second point",))),
        ],
        facts={"client_name": "Example Client A", "cells": 3, "assessed": True, "by_band": {"x": []}},
        warnings=("The claimed side of this book is an unverified assertion.",),
        provenance=Provenance(run_id="run-0123456789ab", rule_pack_version="ga_jtc/2023", source="recorded claims; no run"),
    )


def _book_result() -> ToolResult:
    from application.capabilities.book import book_rank

    page = {
        "total_clients": 2, "assessed_clients": 2,
        "items": [
            {"client_id": 2003, "client_name": "Example Client B", "priority_band": "on_the_line",
             "program_code": "GA_JTC", "tax_year": 2022, "identified_usd": "0", "jobs_margin": -0.83},
            {"client_id": 2002, "client_name": "Example Client C", "priority_band": "unclaimed_at_scale",
             "program_code": "GA_JTC", "tax_year": 2025, "identified_usd": "40495"},
        ],
    }
    return book_rank(8, page_reader=lambda **_: page)


# ------------------------------------------------------------ the item itself


def test_a_result_becomes_an_item_the_contract_accepts():
    item = evidence_item("situation", _situation(), 1, authenticated=False)
    check_contract(item)
    assert item["id"] == "ev-situation-1" and item["tool"] == "situation"
    assert item["title"] == INTENT_TITLE["situation"]


def test_text_and_rows_pass_through_character_for_character():
    item = evidence_item("situation", _situation(), 1, authenticated=False)
    paragraph, table, bullets, note = item["blocks"]
    assert paragraph["text"] == "3 recorded cells. Identified credit: $31,185."
    assert table["columns"] == ["Reason", "Programme", "Tax year", "Identified", "Jobs margin"]
    assert table["rows"] == [
        ["On the line", "GA_JTC", "2023", "$31,185", "-0.83"], ["Identified", "GA_JTC", "2024", "$0", "\u2014"],
    ]
    assert bullets["rows"] == ["First point", "Second point"]
    assert note["text"] == "The claimed side of this book is an unverified assertion."


def test_a_heading_titles_the_block_after_it_and_is_not_lost():
    item = evidence_item("situation", _situation(), 1, authenticated=False)
    assert item["blocks"][0]["title"] == "Example Client A"
    lone = evidence_item("trend", _result("client_trend", [Block("heading", text="Only a heading")]), 1, authenticated=False)
    assert lone["blocks"] == [{"kind": "text", "text": "Only a heading"}]


def test_provenance_carries_what_the_envelope_holds_and_nothing_else():
    item = evidence_item("situation", _situation(), 1, authenticated=False)
    assert item["provenance"] == {"run_id": "run-0123456789ab", "rule_pack": "ga_jtc/2023"}
    bare = evidence_item("book", _book_result(), 1, authenticated=False)
    assert "provenance" not in bare, "a claims-only read has no run to cite"


def test_facts_are_scalar_strings_and_nested_values_are_left_out():
    item = evidence_item("situation", _situation(), 1, authenticated=False)
    assert item["facts"] == {"client_name": "Example Client A", "cells": "3"}


def test_a_result_with_nothing_to_show_emits_no_item():
    assert evidence_item("trend", _result("client_trend", []), 1, authenticated=True) is None


def test_every_intent_has_a_tab_label_and_a_tool():
    assert set(INTENT_TITLE) == set(CAPABILITIES) == set(CHAT_INTENT_TOOL)


def test_the_golden_file_matches_what_the_backend_emits():
    expected = {
        "book": evidence_item("book", _book_result(), 1, authenticated=False),
        "situation": evidence_item("situation", _situation(), 1, authenticated=False),
    }
    assert json.loads(GOLDEN.read_text(encoding="utf-8")) == expected


# ----------------------------------------------------- sensitive capabilities


def _at_risk() -> ToolResult:
    return _result(
        "client_at_risk",
        [Block("paragraph", text="2 of 539 counted employees sit within 5 weekly hours of a floor."),
         EMPLOYEE_TABLE],
        facts={"within_band": 2, "eligible": 539},
    )


@pytest.mark.parametrize("tool", ["client_at_risk", "employee_drill", "findings_list"])
def test_a_sensitive_table_is_withheld_from_an_unauthenticated_reader_and_the_count_is_kept(tool):
    result = _result(tool, [EMPLOYEE_TABLE], facts={"within_band": 2})
    item = evidence_item("at_risk", result, 1, authenticated=False)
    check_contract(item)
    wire = json.dumps(item)
    assert "EMP-0001" not in wire and "Worker A" not in wire
    assert "2 rows withheld" in item["blocks"][0]["text"]
    assert item["facts"] == {}
    assert not any(b["kind"] == "table" for b in item["blocks"]), "an empty table would read as nobody"


def test_a_sensitive_table_is_shown_to_a_signed_in_reader():
    item = evidence_item("at_risk", _at_risk(), 1, authenticated=True)
    check_contract(item)
    table = next(b for b in item["blocks"] if b["kind"] == "table")
    assert table["rows"] == [list(r) for r in EMPLOYEE_ROWS]
    assert item["facts"] == {"within_band": "2", "eligible": "539"}


def test_an_ordinary_table_is_never_withheld():
    item = evidence_item("book", _book_result(), 1, authenticated=False)
    assert any(b["kind"] == "table" and b["rows"] for b in item["blocks"])


def test_a_tool_the_catalog_does_not_know_is_treated_as_sensitive():
    item = evidence_item("book", _result("not_in_the_catalog", [EMPLOYEE_TABLE]), 1, authenticated=False)
    assert "EMP-0001" not in json.dumps(item)


# --------------------------------------------------------------- the stream


def _frames(raw: list[str]) -> list[tuple[str, dict]]:
    out = []
    for frame in raw:
        event, data = frame.split("\n")[:2]
        out.append((event.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return out


@pytest.fixture
def stub_narrator(monkeypatch):
    """A narrator that writes one token, and remembers every prompt it was handed."""
    import api.chat.pipelines_briefs as briefs
    from api.chat.sse import _sse

    prompts: list[str] = []

    async def narrate(agent_name, prompt, **_):
        prompts.append(prompt)
        yield _sse("agent_start", {"agent": agent_name})
        yield _sse("token", {"agent": agent_name, "content": "Narration."})
        yield _sse("agent_end", {"agent": agent_name})

    monkeypatch.setattr(briefs, "_stream_agent", narrate)
    return prompts


def _run(intents, *, authenticated=False, scope=None, message="who to call?") -> list[tuple[str, dict]]:
    import api.chat.dispatch as dispatch

    async def plan(*_args, **_kwargs):
        return list(intents)

    async def go():
        _AUTHENTICATED.set(authenticated)
        req = ChatRequest(message=message, client_id=2001, tax_year=2025)
        raw = [f async for f in _dispatch(SimpleNamespace(state=SimpleNamespace()), req, scope=scope)]
        return _frames(raw)

    original = dispatch._plan
    dispatch._plan = plan
    try:
        return asyncio.run(go())
    finally:
        dispatch._plan = original


@pytest.fixture
def book_page(monkeypatch):
    import api.claims as claims

    monkeypatch.setattr(claims, "portfolio_v2", lambda **_: {
        "total_clients": 1, "assessed_clients": 1,
        "items": [{"client_id": 2003, "client_name": "Example Client B", "priority_band": "on_the_line",
                   "program_code": "GA_JTC", "tax_year": 2022, "identified_usd": "0", "jobs_margin": -0.83}],
    })


def test_the_event_is_emitted_after_the_capability_ran_and_before_done(stub_narrator, book_page):
    frames = _run(["book"])
    names = [e for e, _ in frames]
    assert names.count("evidence") == 1
    assert names.index("plan") < names.index("evidence") < names.index("agent_start") < names.index("done")
    assert names[-1] == "done" and names.count("done") == 1
    check_contract(next(d for e, d in frames if e == "evidence"))


def test_every_existing_event_is_unchanged_and_in_order(stub_narrator, book_page):
    names = [e for e, _ in _run(["book"]) if e != "evidence"]
    assert names == ["plan", "status", "agent_start", "token", "agent_end", "done"]


def test_two_capabilities_give_two_items_and_one_done(monkeypatch, stub_narrator, book_page):
    import api.chat.pipelines_briefs as briefs

    monkeypatch.setattr(briefs, "client_trend", lambda *_a, **_k: _result(
        "client_trend", [Block("table", rows=(("Tax year", "Credit"), ("2023", "$0")))], facts={"calculated": True},
    ))
    scope = {"account_id": 2001, "tax_year": 2025, "state": "GA", "method": "min_max"}
    frames = _run(["book", "trend"], scope=scope)
    names = [e for e, _ in frames]
    assert [d["tool"] for e, d in frames if e == "evidence"] == ["book", "trend"]
    assert names.count("done") == 1 and names[-1] == "done"
    assert max(i for i, n in enumerate(names) if n == "evidence") < names.index("done")


def test_an_unauthenticated_at_risk_answer_withholds_rows_and_the_model_never_sees_them(monkeypatch, stub_narrator):
    import api.chat.pipelines_briefs as briefs

    monkeypatch.setattr(briefs, "client_at_risk", lambda *_a, **_k: _at_risk())
    scope = {"account_id": 2001, "tax_year": 2025, "state": "GA", "method": "min_max"}
    frames = _run(["at_risk"], scope=scope)
    wire = json.dumps(frames)
    assert "EMP-0001" not in wire and "Worker A" not in wire
    assert "2 rows withheld" in json.dumps([d for e, d in frames if e == "evidence"])
    assert all("EMP-0001" not in p and "Worker A" not in p for p in stub_narrator)


def test_a_signed_in_reader_gets_the_rows_in_the_evidence_but_the_model_still_does_not(monkeypatch, stub_narrator):
    import api.chat.pipelines_briefs as briefs

    monkeypatch.setattr(briefs, "client_at_risk", lambda *_a, **_k: _at_risk())
    scope = {"account_id": 2001, "tax_year": 2025, "state": "GA", "method": "min_max"}
    frames = _run(["at_risk"], authenticated=True, scope=scope)
    evidence = next(d for e, d in frames if e == "evidence")
    assert any(b["kind"] == "table" and b["rows"][0][1] == "EMP-0001" for b in evidence["blocks"])
    assert all("EMP-0001" not in p for p in stub_narrator)


def test_a_capability_that_raises_emits_no_evidence_and_the_stream_still_ends(monkeypatch, stub_narrator):
    import api.chat.pipelines_briefs as briefs
    from application.capabilities.errors import YearNotAuthored

    def declined(*_a, **_k):
        raise YearNotAuthored("no authored statute for that year")

    monkeypatch.setattr(briefs, "client_at_risk", declined)
    scope = {"account_id": 2001, "tax_year": 2025, "state": "GA", "method": "min_max"}
    names = [e for e, _ in _run(["at_risk"], scope=scope)]
    assert "evidence" not in names and names[-1] == "done"


def test_the_endpoint_streams_evidence_for_an_anonymous_reader(monkeypatch, stub_narrator, book_page, client):
    import bootstrap.wiring as wiring

    monkeypatch.setattr(wiring, "get_narration_service", lambda: SimpleNamespace(available=lambda _agents: True))
    response = client.post("/api/chat", json={"message": "Who should we reach out to first?"})
    assert response.status_code == 200
    events = [line[7:] for line in response.text.splitlines() if line.startswith("event: ")]
    assert "evidence" in events and events[-1] == "done"
