"""The same question through every door returns the same figures, on the real engine. [RM-13]

The architecture rule of the remediation run is ONE CALCULATION, MANY ADAPTERS: REST, the gateway, MCP, the MAF
tools and the portal chat are logic-free adapters over the capability catalog. This is the proof. Each case in
`parity_cases.py` is asked of each door the way that door is asked (`parity_rig.py` builds the real gateway in
front of the real API over a Gold store the engine wrote from the synthetic payroll; no model takes part), and:

* the envelopes the REST, gateway, MCP and MAF-tool doors return are identical byte for byte once the declared
  volatile fields are masked (`parity_compare.py` lists each one and says why it is not a figure);
* what a Cowork model reads (the MCP text) and what a Teams or Copilot Chat reader is shown (a whole orchestrator
  turn, the composer, a fixed fake narrator) contain the platform's own blocks verbatim and no number the engine
  did not state;
* the portal chat's evidence is the same blocks and facts, and the figures in the briefs its narrators are
  handed are the capability's, never one the pipeline made up;
* a prepared write changes nothing on any door.

The portal's narration is not composed (its prose still streams unchecked: the known limit, ADR-008), so for the
portal the claim is about what it SHOWS and what its narrators are TOLD, not about what a model then says.

Each check is a function, and `test_a_door_that_changes_one_figure_fails_the_check` runs it against an adapter
that has been made to lie, so a check that could not fail would not pass the suite.
"""
from __future__ import annotations

import json
import re
from decimal import Decimal

import pytest

from bootstrap import wiring
from application.capabilities.envelope import DISCLAIMER
from channel.render import VERBATIM
from parity_cases import CASES, NAME, YEAR, Case
from parity_compare import (
    brief_leaves, canonical, envelope_figures, flat_envelope, flat_evidence, numerals, platform_markdown, same_value, scalar_facts,
)
from parity_rig import CLIENT, PORTAL_OID, USER_OID, engine, entra, rig, world  # noqa: F401 - fixtures

IDS = [c.id for c in CASES]
PORTAL_CASES = [c for c in CASES if c.portal]
WRITES = [c for c in CASES if c.lane == "write"]
BY_ID = {c.id: c for c in CASES}


def doors(rig, case: Case) -> dict:
    """The four doors that return an envelope, asked the case's catalog arguments."""
    seen = (rig.rest_api(case.tool, case.args), rig.rest_gateway(case.tool, case.args), rig.mcp(case.tool, case.args),
            rig.maf(case.tool, case.args))
    return {s.surface: s for s in seen}


# ------------------------------------------------------------------ the matrix is what it says


def test_the_matrix_covers_what_the_brief_asks_and_every_gap_says_why():
    tools = {c.tool for c in CASES}
    assert len(CASES) >= 12
    assert {"client_eligibility", "client_trend", "client_at_risk", "client_situation", "book_rank", "simulate",
            "data_catalog", "data_distinct_values", "data_query"} <= tools
    assert {c.args.get("method") for c in CASES if c.tool == "client_eligibility"} == {"min_max", "pay_period"}
    assert [c.id for c in CASES if c.tool == "data_query"] == ["data-aggregate", "data-capped", "data-employee"]
    assert len(WRITES) >= 2 and all(c.tool.endswith("_prepare") for c in WRITES)
    assert all(c.portal or c.portal_na for c in CASES), "a case the portal cannot answer must say why"
    assert not [c for c in CASES if c.portal and c.portal_na]
    assert len(PORTAL_CASES) >= 6


# ------------------------------------------------------------ REST, gateway, MCP and the MAF tool


def check_envelopes(rig, case: Case) -> None:
    seen = doors(rig, case)
    assert {s.status for s in seen.values()} == {200}, {k: (v.status, v.body.get("error")) for k, v in seen.items()}
    assert {s.body["tool"] for s in seen.values()} == {case.tool}
    assert canonical(seen["rest-api"].body) == canonical(seen["mcp"].body), "two doors of one lane must agree exactly"
    assert canonical(seen["rest-gateway"].body) == canonical(seen["maf"].body), "two doors of one lane must agree exactly"
    assert canonical(seen["rest-api"].body, lane_notes=True) == canonical(seen["maf"].body, lane_notes=True)
    assert all("correlation_id" in seen[d].body for d in ("rest-gateway", "mcp", "maf")), "the gateway stamps every answer"
    assert "correlation_id" not in seen["rest-api"].body


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_every_door_returns_the_same_envelope(rig, case):
    check_envelopes(rig, case)


def test_a_capped_result_says_so_and_an_employee_result_travels_in_the_persons_lane(rig):
    capped = rig.rest_gateway("data_query", BY_ID["data-capped"].args).body["facts"]
    assert capped["truncated"] is True and capped["row_limit"] == 2 and len(capped["rows"]) == 2
    employees = {d: s.body for d, s in doors(rig, BY_ID["data-employee"]).items()}
    assert all(b["user_only_facts"] == ["rows"] for b in employees.values())
    assert len({json.dumps(b["facts"]["rows"], sort_keys=True) for b in employees.values()}) == 1


# --------------------------------------------------------------------------------- MCP text


def check_mcp_text(rig, case: Case) -> None:
    reference, mcp = rig.rest_api(case.tool, case.args), rig.mcp(case.tool, case.args)
    text = mcp.extra["text"]
    assert text.startswith(VERBATIM) and text.endswith(DISCLAIMER) and mcp.extra["is_error"] is False
    assert all(md in text for md in platform_markdown(mcp.body)), "a block is not in the text as the platform rendered it"
    assert numerals(text) <= envelope_figures(reference.body) | numerals(DISCLAIMER)


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_the_text_cowork_reads_is_the_platforms_blocks_and_no_other_number(rig, case):
    check_mcp_text(rig, case)


# ----------------------------------------------------------------- Teams and Copilot Chat turns


def _resolve(facts: dict, path: str):
    node = facts
    for part in path.split("."):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node


def _placeholders(narration: str) -> list[str]:
    return [m.removeprefix("facts.") for m in re.findall(r"\{\{(facts\.[^}|]+)(?:\|[^}]*)?\}\}", narration)]


def check_teams_turn(rig, case: Case) -> None:
    reference = rig.rest_gateway(case.tool, case.args)
    seen = rig.teams(case.question, case.tool, case.proposed)
    reply = seen.extra["reply"]
    assert reply.kind == "answer" and reply.guard_status == "pass", reply.text
    assert [(r.name, r.args) for r in reply.runs] == [(case.tool, case.args)], "the reader's words settle the same arguments"
    assert canonical(reply.runs[0].envelope) == canonical(reference.body)
    assert all(md in reply.text for md in platform_markdown(reference.body))
    assert numerals(reply.text) <= envelope_figures(reference.body) | numerals(DISCLAIMER) | numerals(case.question)
    for path in _placeholders(seen.extra["narration"]):
        _label, _, within = path.partition(".")
        assert Decimal(str(_resolve(reference.body["facts"], within))) in numerals(reply.text), path


@pytest.mark.parametrize("case", CASES, ids=IDS)
def test_a_teams_turn_shows_the_platforms_blocks_and_the_engines_figures_only(rig, case):
    check_teams_turn(rig, case)


def test_an_unnamed_method_runs_both_certified_methods_and_each_is_the_rest_answer(rig):
    seen = rig.teams(f"What is the credit for {NAME} in {YEAR}?", "client_eligibility", {})
    reply = seen.extra["reply"]
    assert reply.kind == "answer" and [r.args["method"] for r in reply.runs] == ["min_max", "pay_period"]
    for run in reply.runs:
        assert canonical(run.envelope) == canonical(rig.rest_gateway(run.name, run.args).body)
        assert all(md in reply.text for md in platform_markdown(run.envelope))


def test_a_model_is_shown_the_names_of_the_persons_rows_and_never_the_rows(rig):
    case = BY_ID["data-employee"]
    tokens = [row["record_token"] for row in rig.rest_gateway(case.tool, case.args).body["facts"]["rows"]]
    seen = rig.teams(case.question, case.tool, case.proposed)
    reply, narrator = seen.extra["reply"], seen.extra["narrator"]
    assert tokens and all(t in reply.text for t in tokens), "the person is shown their rows"
    assert narrator.handed and not any(t in narrator.handed for t in tokens), "the model is handed no row"


# ----------------------------------------------------------------------------- the portal chat


def _leaves(value):
    if isinstance(value, dict):
        for item in value.values():
            yield from _leaves(item)
    elif isinstance(value, list):
        for item in value:
            yield from _leaves(item)
    elif value is not None and not isinstance(value, bool):
        yield value


def check_portal(rig, case: Case) -> None:
    reference = rig.rest_api(case.tool, case.args).body
    seen = rig.portal(case.portal.intent, case.portal.message, case.portal.scope)
    evidence = [d for name, d in seen.extra["events"] if name == "evidence"]
    assert seen.status == 200 and len(evidence) == 1
    item = evidence[0]
    assert flat_evidence(item["blocks"]) == flat_envelope(reference)
    assert item["facts"] == scalar_facts(reference["facts"])
    assert item["disclaimer"] == reference["disclaimer"]
    held = reference["provenance"]
    wire = (("run_id", "run_id"), ("rule_pack_version", "rule_pack"), ("trail_sha256", "trail_hash"))
    assert item.get("provenance", {}) == {w: str(held[f]) for f, w in wire if held.get(f)}
    allowed = list(_leaves(reference["facts"])) + [case.portal.scope.get(k) for k in ("client_id", "tax_year", "state")]
    told = [leaf for _, prompt in seen.extra["briefs"] for leaf in brief_leaves(prompt)]
    invented = [leaf for leaf in told if isinstance(leaf, (int, float)) and not any(same_value(leaf, a) for a in allowed)]
    assert not invented, f"a narrator was told a figure the capability did not state: {invented}"


@pytest.mark.parametrize("case", PORTAL_CASES, ids=[c.id for c in PORTAL_CASES])
def test_the_portal_shows_the_same_blocks_and_facts_and_tells_its_narrators_only_those_figures(rig, case):
    check_portal(rig, case)


# -------------------------------------------------------------------- a preview changes nothing


@pytest.mark.parametrize("case", WRITES, ids=[c.id for c in WRITES])
def test_a_prepared_write_changes_nothing_on_any_door(rig, case):
    repository = wiring.get_claim_repository()
    before = (len(repository.history(CLIENT, "GA_JTC", YEAR)), len(repository.history(CLIENT, "GA_JTC", YEAR - 1)))
    seen = doors(rig, case)
    turn = rig.teams(case.question, case.tool, case.proposed)
    assert {s.status for s in seen.values()} == {200} and turn.extra["reply"].kind == "answer"
    for door, s in seen.items():
        assert s.body["facts"]["confirmation"]["token"] and "Nothing has changed yet" in json.dumps(s.body["blocks"]), door
    after = (len(repository.history(CLIENT, "GA_JTC", YEAR)), len(repository.history(CLIENT, "GA_JTC", YEAR - 1)))
    assert after == before
    assert not [e for oid in (USER_OID, PORTAL_OID) for e in rig.world.audit.for_user(oid) if e.tool_name.endswith("_commit")]


# ------------------------------------------------------- the checks can fail: an adapter that lies


def _lie(text: str) -> str:
    """One figure changed by one unit: the first dollar amount in `text`."""
    return re.sub(r"\$(\d[\d,]*)", lambda m: "$" + format(int(m.group(1).replace(",", "")) + 1, ","), text, count=1)


def _lie_in_rows(rows):
    return [[_lie(cell) for cell in row] for row in rows]


def test_a_door_that_changes_one_figure_fails_the_check(rig, monkeypatch):
    import api.chat.evidence as evidence
    import channel.mcp as mcp_module
    from app.core.tools import ToolRunner
    from channel.render import render_tool_text

    case = BY_ID["eligibility-pay-period"]
    original_forward = ToolRunner.forward

    async def lying_forward(self, spec, args):
        reply = await original_forward(self, spec, args)
        for block in reply.body.get("blocks", []):
            block["rows"] = _lie_in_rows(block.get("rows", []))
        return reply

    check_envelopes(rig, case)
    monkeypatch.setattr(ToolRunner, "forward", lying_forward)
    with pytest.raises(AssertionError):
        check_envelopes(rig, case)
    monkeypatch.undo()

    check_mcp_text(rig, case)
    monkeypatch.setattr(mcp_module, "render_tool_text", lambda body, base_url="": _lie(render_tool_text(body, base_url)))
    with pytest.raises(AssertionError):
        check_mcp_text(rig, case)
    monkeypatch.undo()

    check_portal(rig, case)
    original_blocks = evidence._blocks
    monkeypatch.setattr(evidence, "_blocks", lambda blocks, **kw: [
        {**b, "rows": _lie_in_rows(b["rows"])} if b["kind"] == "table" else b for b in original_blocks(blocks, **kw)])
    with pytest.raises(AssertionError):
        check_portal(rig, case)


def test_a_portal_pipeline_that_adds_up_figures_of_its_own_fails_the_check(rig, monkeypatch):
    import api.chat.pipelines_core as core

    case = BY_ID["discovery-all"]
    check_portal(rig, case)
    original = core._brief
    monkeypatch.setattr(core, "_brief", lambda label, payload: original(label, {**payload, "grand_total": 123456789}))
    with pytest.raises(AssertionError, match="did not state"):
        check_portal(rig, case)
