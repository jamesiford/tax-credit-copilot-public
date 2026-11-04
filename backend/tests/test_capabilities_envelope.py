"""The envelope, the catalog and the registry hold together.

Three promises, each checked from the outside:

* A `ToolResult` is plain JSON and serialises identically every time.
* The text a capability renders (`blocks`) contains no numeral the engine did not
  supply. This is a first cut of the numeric guard (ADR-008): a simple scan, with
  a corrupted block proving the scan can fail.
* The catalog, the registry and the portal's intent list name the same things.
"""
from __future__ import annotations

import inspect
import json
import re
from decimal import Decimal
from pathlib import Path

import pytest

from application.capabilities import catalog, registry
from application.capabilities import format as fmt
from application.capabilities.envelope import DISCLAIMER, Block, Provenance, ToolResult

from test_capabilities_equivalence import (  # noqa: F401
    SITE,
    _DrillReader,
    _KNOWN_TOKEN,
    _seed,
    book,
    cascade,
    claims_repo,
    findings_repo,
    gold,
    wired,
)

_NUMERAL = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _decimals(text: str) -> set[Decimal]:
    return {Decimal(m.group(0).replace(",", "")) for m in _NUMERAL.finditer(text)}


def _fact_values(value) -> set[Decimal]:
    """Every number the facts supply: numbers, numeric strings, and the digits
    inside any string (a citation, a date, a note the engine wrote)."""
    out: set[Decimal] = set()
    if isinstance(value, dict):
        for v in value.values():
            out |= _fact_values(v)
    elif isinstance(value, (list, tuple)):
        for v in value:
            out |= _fact_values(v)
    elif isinstance(value, bool) or value is None:
        pass
    elif isinstance(value, (int, float, Decimal)):
        out.add(fmt.to_decimal(value))
    elif isinstance(value, str):
        out |= _decimals(value)
    return out


def _block_text(block: Block) -> list[str]:
    return [block.text, *(cell for row in block.rows for cell in row)]


def unexplained_numerals(result: ToolResult, scope: set[int]) -> list[str]:
    """Numerals in the rendered blocks that neither the facts nor the call's own
    scope (client id, tax year) supply."""
    allowed = _fact_values(result.facts) | {Decimal(n) for n in scope}
    bad = []
    for block in result.blocks:
        for text in _block_text(block):
            for numeral in _decimals(text):
                if numeral not in allowed:
                    bad.append(f"{numeral} in {text!r}")
    return bad


# ------------------------------------------------------------------ the results


def _results(book, claims_repo, gold, findings_repo):
    """One result from every capability the Gold fake can answer."""
    from application.capabilities import claims, client, findings, simulate, walkthrough
    from application.capabilities.book import book_rank

    _seed(claims_repo)
    return [
        (book_rank(), set()),
        (client.client_resolve("compare Cascade and Northwind"), set()),
        (client.client_situation(2001, 2023), {2001, 2023}),
        (client.client_situation(2003), {2003}),
        (client.client_eligibility(2001, 2023, "GA", "pay_period"), {2001, 2023}),
        (client.client_eligibility(2001, 2024, "GA", "pay_period"), {2001, 2024}),
        (client.client_trend(2001), {2001}),
        (client.client_at_risk(2001, 2023, "GA", "min_max"), {2001, 2023}),
        (client.client_discovery(state="GA"), set()),
        (simulate.simulate_headcount("Atlanta", 25), {25}),
        (walkthrough.calc_walkthrough(2001, 2023, "GA"), {2001, 2023}),
        (claims.claim_cell_history(2001, "GA_JTC", 2023), {2001, 2023}),
        (findings.findings_list(1001, 2025, "GA"), {1001, 2025}),
    ]


@pytest.fixture
def every_result(book, claims_repo, gold, findings_repo):
    return _results(book, claims_repo, gold, findings_repo)


def test_the_location_whatif_renders_only_its_facts(wired):
    from application.capabilities import simulate

    whatif = simulate.simulate(2001, 2025, SITE, "add_headcount", 2)
    assert unexplained_numerals(whatif, {2001, 2025, 2}) == []
    assert whatif.to_json()


def test_the_employee_drill_renders_only_its_facts():
    from application.capabilities import walkthrough
    from application.wiring import set_gold_reader

    set_gold_reader(_DrillReader())
    try:
        drill = walkthrough.employee_drill(1001, _KNOWN_TOKEN, 2025, "GA")
    finally:
        set_gold_reader(None)
    assert unexplained_numerals(drill, {1001, 2025}) == []
    assert drill.to_json()


def test_every_result_is_json_and_serialises_identically(every_result):
    assert len(every_result) >= 12
    for result, _scope in every_result:
        first = result.to_json()
        assert json.loads(first)["tool"] == result.tool
        assert result.to_json() == first, f"{result.tool} did not serialise stably"
        assert result.disclaimer == DISCLAIMER
        assert result.blocks, f"{result.tool} rendered nothing"


def test_every_figure_rendered_into_a_block_comes_from_the_facts(every_result):
    for result, scope in every_result:
        assert unexplained_numerals(result, scope) == [], result.tool


def test_the_scan_can_fail(every_result):
    """A check that passes whatever it is shown proves nothing."""
    result, scope = next(r for r in every_result if r[0].tool == "client_eligibility")
    table = next(b for b in result.blocks if b.kind == "table")
    corrupted = Block("table", rows=tuple(
        tuple(cell.replace("3", "9") if i else cell for i, cell in enumerate(row))
        for row in table.rows
    ))
    forged = ToolResult(
        tool=result.tool, facts=result.facts, blocks=(corrupted,), provenance=result.provenance,
    )
    assert unexplained_numerals(forged, scope), "a changed digit must not look derivable"


def test_every_capability_reply_passes_the_real_guard_and_no_flipped_digit_does(every_result):
    """CH-01's blocks, held to CH-02's guard (ADR-008): the platform's own text
    must be acceptable, and one corrupted digit anywhere in it must not be."""
    from application import composer, numeric_guard
    from application.numeric_guard import AllowedContext, FactIndex
    from test_numeric_guard import _mutations

    flipped = 0
    for result, scope in every_result:
        context = AllowedContext.build(years=[n for n in scope if 1900 <= n <= 2100], numbers=sorted(scope))
        index = FactIndex.from_facts(result.facts)
        reply = composer.compose(result.blocks, None, index, context)
        assert reply.guard.passed and reply.blocks_verified, (result.tool, reply.guard.to_dict())

        accept = {"values": set(index.values) | set(context.values), "dates": set(index.dates)}
        for numeral, mutated in _mutations(reply.text, accept):
            flipped += 1
            verdict = numeric_guard.check(mutated, facts=index, allowed_context=context)
            assert verdict.status == numeric_guard.REJECTED, (result.tool, numeral.text, mutated)
    assert flipped > 100, "the corruption loop barely ran"


def test_provenance_is_never_invented(every_result):
    by_tool = {r.tool: r for r, _ in every_result}
    assert by_tool["book_rank"].provenance.run_id is None
    assert by_tool["client_situation"].provenance.trail_sha256 is None
    assert by_tool["client_trend"].provenance.run_id == "run-42"
    assert by_tool["calc_walkthrough"].provenance.trail_sha256
    assert by_tool["claim_cell_history"].provenance.source == "recorded claims"


def test_the_envelope_rejects_a_malformed_block():
    with pytest.raises(ValueError):
        Block("carousel")
    with pytest.raises(ValueError):
        Block("table", rows=(("a", "b"), ("c",)))
    with pytest.raises(ValueError):
        Block("bullets", rows=(("a", "b"),))


def test_to_dict_keeps_money_exact_and_sorts_keys():
    result = ToolResult(
        tool="t", facts={"b": Decimal("3500.50"), "a": {"z": 1, "y": (1, 2)}},
        provenance=Provenance(run_id="r"),
    )
    body = result.to_dict()
    assert body["facts"] == {"a": {"y": [1, 2], "z": 1}, "b": "3500.50"}
    assert list(body["facts"]) == ["a", "b"]
    assert list(result.facts) == ["b", "a"], "the producer's own order is kept on `facts`"


def test_the_disclaimer_is_one_sentence_and_says_so():
    assert DISCLAIMER.count(". ") == 0 and DISCLAIMER.endswith(".")
    assert "not tax advice" in DISCLAIMER.lower()
    source = (Path(__file__).resolve().parents[2] / "DISCLAIMER.md").read_text(encoding="utf-8")
    assert "not tax advice" in source.lower(), "DISCLAIMER.md is where the statement comes from"


# ---------------------------------------------------------------------- catalog


def test_every_catalog_entry_has_a_schema():
    for spec in catalog.CATALOG:
        schema = spec.schema
        assert schema["type"] == "object", spec.name
        assert isinstance(schema["properties"], dict), spec.name
        assert schema["additionalProperties"] is False, spec.name
        assert set(schema["required"]) <= set(schema["properties"]), spec.name
        assert spec.description.strip(), spec.name
        json.dumps(schema)


def test_catalog_names_are_unique_and_kinds_are_known():
    names = [s.name for s in catalog.CATALOG]
    assert len(names) == len(set(names))
    assert {s.kind for s in catalog.CATALOG} <= set(catalog.KINDS)


def test_every_implemented_entry_has_a_function_and_nothing_else_does():
    implemented = {s.name for s in catalog.CATALOG if s.implemented}
    assert implemented == set(registry.FUNCTIONS)
    assert {s.name for s in catalog.CATALOG if not s.implemented}.isdisjoint(registry.FUNCTIONS)


def test_function_names_match_catalog_names():
    for name, fn in registry.FUNCTIONS.items():
        assert fn.__name__ == name or name == "simulate", name


def test_every_schema_property_is_a_parameter_of_its_function():
    """The orchestrator calls a tool with the schema's arguments, so they must fit.

    One function declares `**query` instead of a parameter per property: `data_query`'s arguments
    are a ten-field specification, and `QuerySpec.from_dict` is what checks them by name (an unknown
    key is refused). That is the only exception, and it is named.
    """
    spread = {"data_query"}
    for name, fn in registry.FUNCTIONS.items():
        spec = catalog.get(name)
        params = inspect.signature(fn).parameters
        if name in spread:
            assert any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()), name
            continue
        assert set(spec.schema["properties"]) <= set(params), name
        for required in spec.schema["required"]:
            assert required in params, (name, required)


def test_every_catalogued_tool_is_built():
    """Prompt 3 built the last two (`claim_package_create`, `verify_figures`); nothing is declared-only now."""
    assert {s.name for s in catalog.CATALOG if not s.implemented} == set()
    writes = {s.name for s in catalog.CATALOG if s.kind != catalog.READ}
    assert writes <= {s.name for s in catalog.CATALOG if s.implemented}
    for base in ("finding_resolve", "finding_reopen", "claim_transition", "claim_record",
                 "engagement_set", "base_year_set", "claim_package_create"):
        assert catalog.get(f"{base}_prepare").kind == catalog.WRITE_PREPARE
        assert catalog.get(f"{base}_commit").kind == catalog.WRITE_COMMIT


def test_employee_level_tools_are_marked_sensitive():
    sensitive = {s.name for s in catalog.CATALOG if s.sensitive}
    assert {"employee_drill", "findings_list", "client_at_risk"} <= sensitive
    assert not sensitive & {"book_rank", "client_situation", "client_trend"}


# --------------------------------------------------------- the portal's intents


def test_the_chat_reads_the_one_list():
    import api.chat as chat

    assert chat.CAPABILITIES is catalog.CAPABILITIES
    assert chat._NEEDS_CLIENT is catalog.NEEDS_CLIENT


def test_every_chat_intent_runs_a_catalogued_tool():
    assert set(catalog.CHAT_INTENT_TOOL) == set(catalog.CAPABILITIES)
    for intent, tool in catalog.CHAT_INTENT_TOOL.items():
        spec = catalog.get(tool)
        assert spec.implemented, (intent, tool)
        assert (intent in catalog.NEEDS_CLIENT) == spec.needs_client or intent in {"explain", "multi_state"}, (intent, tool)


def test_intents_that_need_a_client_name_a_client_tool():
    for intent in catalog.NEEDS_CLIENT:
        assert catalog.get(catalog.CHAT_INTENT_TOOL[intent]).needs_client, intent
    assert not catalog.get(catalog.CHAT_INTENT_TOOL["book"]).needs_client
