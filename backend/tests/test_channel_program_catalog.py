"""The `program_catalog` capability: a read for Teams and Cowork, list and detail, through the catalog and format layers. [F05.11]

What must hold: it names no client and offers no draft; it says what the portal's catalog says (same queries); every row says it is
not verified; the platform's own figures pass the numeric guard and an invented one does not; an unknown program is "not
calculated", never an invented answer; and a program activated by data appears with no change here.
"""
from __future__ import annotations

import json

import pytest

from application.capabilities import catalog, registry
from application.capabilities.errors import NotCalculated
from application.composer import compose
from application.numeric.guard import REJECTED
from tests import two_program_world as world
from tools.program_registry import load_registry


def test_the_catalog_entry_is_a_read_that_names_no_client_and_exposes_no_draft():
    spec = catalog.get("program_catalog")
    assert spec.kind == catalog.READ and spec.needs_client is False
    assert "client_id" not in json.dumps(spec.schema)
    assert set(spec.schema["properties"]) == {"program_code"}, "a draft id is not an input"
    assert "program_catalog" in {s.name for s in catalog.offered()}
    assert not any("draft" in s.name for s in catalog.CATALOG), "drafts are not exposed to agents"


def test_the_list_matches_the_registry_and_says_not_verified():
    result = registry.call("program_catalog")
    assert [p["code"] for p in result.facts["programs"]] == [e.code for e in load_registry().entries]
    assert result.facts["total"] == len(result.facts["programs"])
    assert result.provenance.source == "program registry and rule packs"
    text = " ".join(b.text for b in result.blocks if getattr(b, "text", None))
    assert "Not verified" in text and "legally correct" in text
    assert all(p["verification"] == "not_verified" for p in result.facts["programs"])


def test_the_table_lists_each_program_with_its_years_and_why_not_when_it_cannot_run():
    table = next(b for b in registry.call("program_catalog").blocks if b.kind == "table")
    rows = {r[0]: r for r in table.rows[1:]}
    georgia = next(r for k, r in rows.items() if "GA_JTC" in k)
    south_carolina = next(r for k, r in rows.items() if "SC_JTC" in k)
    assert georgia[4] == "Yes" and "2019" in georgia[3]
    assert south_carolina[4].startswith("No: ") and south_carolina[3] == "none authored"


def test_the_detail_gives_the_pack_years_blockers_and_a_validation_summary():
    ga = registry.call("program_catalog", program_code="GA_JTC")
    assert ga.facts["code"] == "GA_JTC" and ga.facts["calculable"] is True and ga.facts["validation"]["valid"] is True
    assert ga.facts["years"] and {"tax_year", "unverified", "source"} <= set(ga.facts["years"][0])
    sc = registry.call("program_catalog", program_code="SC_JTC")
    assert sc.facts["calculable"] is False and sc.facts["blockers"] and sc.facts["years"] == []


def test_an_unknown_program_is_not_calculated_never_invented():
    with pytest.raises(NotCalculated, match="NOPE"):
        registry.call("program_catalog", program_code="NOPE")


def test_the_platforms_figures_pass_the_numeric_guard_and_an_invented_one_does_not():
    result = registry.call("program_catalog")
    clean = compose(result.blocks, f"There are {{{{facts.total}}}} programs. None is verified.", result.facts)
    assert clean.narration_used and clean.guard.status != REJECTED
    invented = compose(result.blocks, "There are 4,321 programs, all confirmed correct.", result.facts)
    assert not invented.narration_used, "a figure that is not a supplied fact never reaches the customer"


def test_a_program_activated_by_data_appears_with_no_change_here(tmp_path, monkeypatch):
    world.install(tmp_path, monkeypatch)
    listed = registry.call("program_catalog").facts["programs"]
    alpha = next(p for p in listed if p["code"] == world.ALPHA)
    assert alpha["calculable"] is True and alpha["authored_years"] == list(world.YEARS)
    detail = registry.call("program_catalog", program_code=world.ALPHA)
    assert detail.facts["unverified_years"] == list(world.YEARS) and detail.facts["lifecycle"] == "calculable"


def test_the_read_is_open_to_the_orchestrator_and_the_gateway_surface():
    assert "program_catalog" in registry.FUNCTIONS
    assert "program_catalog" in {s.name for s in catalog.offered()}
