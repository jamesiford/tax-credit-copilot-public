"""The catalog says which arguments the reader owns, what a model is shown, and how a channel words a tool. [RM-07]

Before RM-07 the orchestrator and the MCP facade each kept their own list of argument names (`client_id`, the year
keys, a what-if's sizes) and the facade edited descriptions by hand. These tests pin the catalog's answers, and
pin them against the historical behaviour, so moving the lists into the catalog changed nothing a model or a
Cowork client could see.
"""
from __future__ import annotations

import pytest

from application.capabilities import catalog
from application.capabilities.catalog_types import (
    CODE_ONLY, OWNED_CLIENT, OWNED_EXPLICIT_YEAR, OWNED_METHOD, OWNED_METHOD_BOTH, OWNED_SCENARIO, OWNED_SIZE, OWNED_YEAR,
    OWNED_YEARS, ReaderOwned, owned_arguments,
)

OFFERED = catalog.offered()


def _kinds(name: str) -> dict[str, str]:
    return {o.name: o.kind for o in catalog.BY_NAME[name].reader_owned}


def _old_model_schema(spec):
    """The projection the orchestrator wrote by hand before the catalog owned it (the oracle)."""
    schema = {**spec.schema, "properties": {k: v for k, v in spec.schema["properties"].items() if k != "client_id"}}
    schema["required"] = [n for n in spec.schema.get("required", []) if n not in ("client_id", "tax_year", "year", "base_year", "magnitude")]
    schema["additionalProperties"] = True
    return schema


@pytest.mark.parametrize("spec", OFFERED, ids=lambda s: s.name)
def test_the_models_schema_is_what_the_orchestrator_used_to_build_by_hand(spec):
    assert catalog.model_schema(spec) == _old_model_schema(spec)


@pytest.mark.parametrize("spec", OFFERED, ids=lambda s: s.name)
def test_the_models_schema_never_shows_a_client_and_never_requires_anything_the_reader_owns(spec):
    shown = catalog.model_schema(spec)
    assert "client_id" not in shown["properties"]
    assert not {o.name for o in spec.reader_owned} & set(shown["required"])
    assert shown["additionalProperties"] is True
    assert spec.schema["additionalProperties"] is False, "the catalog's own schema stays strict"


def test_every_tool_that_takes_a_client_marks_it_the_readers_and_nothing_else_does():
    for spec in catalog.CATALOG:
        takes = "client_id" in spec.schema["properties"]
        assert (OWNED_CLIENT in {o.kind for o in spec.reader_owned}) is takes, spec.name


def test_what_each_kind_of_argument_is():
    assert _kinds("client_eligibility") == {"client_id": OWNED_CLIENT, "tax_year": OWNED_YEAR, "method": OWNED_METHOD_BOTH}
    assert _kinds("client_situation") == {"client_id": OWNED_CLIENT, "year": OWNED_YEAR}
    assert _kinds("data_query") == {"client_id": OWNED_CLIENT, "tax_years": OWNED_YEARS, "method": OWNED_METHOD}
    assert _kinds("simulate")["magnitude"] == OWNED_SIZE
    assert _kinds("simulate")["hire_weekly_hours"] == OWNED_SCENARIO == _kinds("simulate")["hire_hourly_rate"]
    assert _kinds("client_at_risk")["method"] == OWNED_METHOD, "only eligibility reads an unnamed method as both"


def test_a_writes_year_and_a_base_year_are_only_ever_a_year_the_reader_wrote():
    for name in ("finding_resolve_prepare", "claim_transition_prepare", "claim_record_prepare", "claim_package_create_prepare"):
        assert _kinds(name)["tax_year"] == OWNED_EXPLICIT_YEAR, name
    assert _kinds("base_year_set_prepare")["base_year"] == OWNED_EXPLICIT_YEAR
    assert _kinds("client_trend") == {"client_id": OWNED_CLIENT}
    assert not catalog.BY_NAME["book_rank"].reader_owned


def test_the_derivation_reads_the_schema_and_an_explicit_value_wins():
    schema = {"type": "object", "properties": {"client_id": {}, "tax_year": {}, "colour": {}}}
    assert owned_arguments(schema, catalog.READ) == (ReaderOwned("client_id", OWNED_CLIENT), ReaderOwned("tax_year", OWNED_YEAR))
    assert owned_arguments(schema, catalog.WRITE_PREPARE)[1].kind == OWNED_EXPLICIT_YEAR
    spec = catalog.CapabilitySpec("t", "d", catalog.READ, True, False, schema, reader_owned=())
    assert spec.reader_owned == () and spec.owned() == ()


def test_owned_names_and_the_certified_methods_come_from_the_catalog():
    assert {"magnitude", "hire_weekly_hours", "hire_hourly_rate"} == catalog.owned_names(OWNED_SIZE, OWNED_SCENARIO)
    assert catalog.CERTIFIED_METHODS == ("min_max", "pay_period") and catalog.METHODS == (*catalog.CERTIFIED_METHODS, "both")
    assert catalog.TAX_YEAR == "tax_year"


def test_who_may_name_a_tool_is_a_tag_in_the_catalog():
    by_tag = {spec.name for spec in catalog.CATALOG if CODE_ONLY in spec.tags}
    assert by_tag == {"client_resolve", "employee_drill"} and catalog.CLIENT_RESOLVER in by_tag
    offered = {s.name for s in catalog.model_offered()}
    assert not by_tag & offered and not {n for n in offered if n.endswith("_commit")}
    assert not {"verify_figures", "claim_package_redeem", "channel_ping"} & offered
    assert {s.name for s in OFFERED if s.kind == catalog.WRITE_PREPARE} <= offered


def test_the_gateways_diagnostic_is_defined_in_the_catalog_and_offered_only_on_request():
    assert catalog.CHANNEL_PING in catalog.DIAGNOSTICS and catalog.CHANNEL_PING.name not in catalog.BY_NAME
    assert catalog.offered_for_channel() == catalog.offered()
    assert catalog.offered_for_channel(debug=True) == (*catalog.offered(), catalog.CHANNEL_PING)
    assert catalog.CHANNEL_PING.schema == {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
    assert not catalog.CHANNEL_PING.reader_owned and catalog.GATEWAY_LOCAL in catalog.CHANNEL_PING.tags


@pytest.mark.parametrize("spec", catalog.CATALOG, ids=lambda s: s.name)
def test_a_channel_words_each_kind_of_tool_the_way_the_facade_always_did(spec):
    expected = spec.description
    if spec.kind == catalog.WRITE_PREPARE:
        expected += " Returns a preview — nothing is changed until the matching commit tool is called with the returned token after the user confirms."
    elif spec.kind == catalog.WRITE_COMMIT:
        expected += " Call only after the user has confirmed the preview from the matching prepare tool."
    assert catalog.channel_description(spec) == expected
    hints = catalog.behaviour_hints(spec)
    assert hints == {
        "readOnlyHint": spec.kind == catalog.READ, "destructiveHint": spec.kind == catalog.WRITE_COMMIT,
        "idempotentHint": spec.kind == catalog.READ, "openWorldHint": False,
    }


def test_the_rest_api_contract_is_unchanged_by_the_new_metadata():
    for spec in catalog.CATALOG:
        assert set(spec.to_dict()) == {
            "name", "description", "kind", "needs_client", "needs_year", "sensitive", "implemented", "schema", "tags",
        }
