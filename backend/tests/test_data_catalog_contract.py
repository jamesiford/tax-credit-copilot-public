"""The data tools' contract: one catalog, one schema, honest descriptions, everywhere they are offered. [CH-16d]

The model's only guide to a tool is its description and schema, so they are tested as the contract
they are. The `data_query` schema in the (vendored) catalog is a written-out copy of the
specification's own schema and must never drift from it; the tools are registered, flagged and
offered read-only everywhere a tool list is built; and a Cowork skill may name them because the
package validator checks names against this same catalog.
"""
from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

from application.capabilities import catalog, lanes, registry
from application.capabilities.catalog_data import DATA_TOOLS, DATASETS, LOOKUP
from application.data.semantic_model import default_model
from application.data.spec_schema import query_spec_schema

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from cowork_plugin.validate_content import validate_tools  # noqa: E402

NAMES = ("data_catalog", "data_query", "data_distinct_values")


def skill(body: str) -> dict[str, bytes]:
    return {"skills/a-skill/SKILL.md": f"---\nname: a-skill\ndescription: Use when asked.\n---\n\n{body}\n".encode()}


def test_the_catalog_copy_of_the_query_schema_equals_the_specifications_own():
    own = query_spec_schema(default_model())
    own.pop("$schema")
    assert catalog.get("data_query").schema == own


def test_the_dataset_names_in_the_catalog_are_the_models():
    assert list(DATASETS) == [d.name for d in default_model().datasets]


def test_the_other_two_schemas_use_the_same_vocabulary():
    distinct = catalog.get("data_distinct_values").schema["properties"]
    assert distinct["dataset"]["enum"] == list(DATASETS) and catalog.get("data_catalog").schema["properties"]["dataset"]["enum"] == list(DATASETS)
    assert catalog.get("data_query").schema["properties"]["tax_years"] == distinct["tax_years"]


def test_the_tools_are_catalogued_built_registered_and_offered():
    assert {s.name for s in DATA_TOOLS} == set(NAMES)
    for name in NAMES:
        spec = catalog.get(name)
        assert spec.implemented and spec.kind == catalog.READ and name in registry.FUNCTIONS
        assert spec in catalog.offered() and spec.schema["additionalProperties"] is False


def test_only_data_query_is_sensitive_because_only_it_can_return_employee_rows():
    assert catalog.get("data_query").sensitive and not catalog.get("data_catalog").sensitive
    assert not catalog.get("data_distinct_values").sensitive


def test_the_catalog_and_the_distinct_values_are_lookups_and_the_query_is_not():
    assert {s.name for s in catalog.CATALOG if LOOKUP in s.tags} == {"data_catalog", "data_distinct_values"}
    assert catalog.LOOKUP == LOOKUP and LOOKUP not in catalog.get("data_query").tags


def test_the_client_comes_from_the_scope_not_the_catalog_tool():
    assert catalog.get("data_catalog").needs_client is False
    assert catalog.get("data_query").needs_client and catalog.get("data_distinct_values").needs_client
    assert "client_id" in catalog.get("data_query").schema["required"]


def test_the_query_description_carries_the_required_guidance():
    text = " ".join(catalog.get("data_query").description.split())
    for phrase in (
        "only for questions the fixed tools", "client_eligibility", "client_trend", "authoritative",
        "returns exact rows and aggregates", "does not interpret", "Never write SQL", "data_catalog first",
        "Copilot Cowork refuses them unless the user is a writer",
    ):
        assert phrase in text, phrase


def test_the_descriptions_for_the_lookups_say_what_they_hold_and_do_not():
    assert "no values" in catalog.get("data_catalog").description.lower() or "Holds no values" in catalog.get("data_catalog").description
    assert "individual people" in catalog.get("data_distinct_values").description


def test_a_cowork_skill_may_name_the_data_tools_and_a_typo_is_caught():
    assert not validate_tools(skill("Read `data_catalog`, then `data_query`; resolve names with `data_distinct_values`."))
    assert {f.code for f in validate_tools(skill("Call `data_querry` first."))} == {"TCC-T001"}


def test_the_lane_constants_are_shared_by_the_api_and_the_gateway():
    from application.capabilities.data_access import is_cowork  # noqa: F401
    from channel.lane_guard import refusal

    status, body = refusal()
    assert status == 403 and body["error"]["code"] == lanes.EMPLOYEE_LEVEL_CODE and body["error"]["message"] == lanes.EMPLOYEE_LEVEL_MESSAGE


@pytest.mark.parametrize("path", ["properties.limit.maximum", "properties.measures.maxItems"])
def test_the_equality_test_would_notice_a_cap_that_drifted(path):
    """Prove the drift check bites: change one cap in a copy and the copies stop being equal."""
    own = query_spec_schema(default_model())
    own.pop("$schema")
    drifted = copy.deepcopy(own)
    node = drifted
    *parents, leaf = path.split(".")
    for key in parents:
        node = node[key]
    node[leaf] += 1
    assert drifted != catalog.get("data_query").schema
