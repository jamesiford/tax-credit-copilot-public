"""The program catalog API: it matches the registry, derives calculability and never says verified. [F05.1]"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from application.client_book import programs
from tests import two_program_world as world
from tools.program_registry import load_registry


@pytest.fixture()
def api():
    import main

    return TestClient(main.app)


def test_the_catalog_lists_exactly_the_registry_in_order(api):
    body = api.get("/api/v2/programs").json()
    assert [p["code"] for p in body["programs"]] == [e.code for e in load_registry().entries]
    assert body["total"] == len(body["programs"])


def test_it_agrees_with_the_existing_program_list_about_calculability(api):
    old = {p["program_code"]: p for p in programs()}
    new = {p["code"]: p for p in api.get("/api/v2/programs").json()["programs"]}
    for code, row in old.items():
        assert new[code]["calculable"] == row["calculable"] and new[code]["authored_years"] == row["authored_years"]
        assert new[code]["unverified_years"] == row["placeholder_years"]


def test_nothing_is_ever_labelled_verified_and_a_reason_names_why_not_calculable(api):
    body = api.get("/api/v2/programs").json()
    assert all(p["verification"] == "not_verified" for p in body["programs"])
    assert "Not verified" in body["verification_note"]
    for p in body["programs"]:
        assert bool(p["not_calculable_reason"]) is (not p["calculable"])


def test_the_detail_carries_pack_years_validation_and_blockers(api):
    detail = api.get("/api/v2/programs/GA_JTC").json()
    assert detail["pack"]["file"] == "ga_jtc.json" and detail["pack"]["present"] is True
    assert [y["tax_year"] for y in detail["years"]] == detail["authored_years"]
    assert detail["validation"]["valid"] is True and detail["blockers"] == []
    sc = api.get("/api/v2/programs/SC_JTC").json()
    assert sc["calculable"] is False and sc["blockers"] and sc["years"] == []


def test_an_unknown_program_is_a_404(api):
    assert api.get("/api/v2/programs/NOPE").status_code == 404


def test_a_program_added_by_data_appears_calculable_with_no_code_change(api, tmp_path, monkeypatch):
    world.install(tmp_path, monkeypatch)
    rows = {p["code"]: p for p in api.get("/api/v2/programs").json()["programs"]}
    alpha = rows[world.ALPHA]
    assert alpha["calculable"] is True and alpha["lifecycle"] == "calculable" and alpha["authored_years"] == list(world.YEARS)
    assert alpha["unverified_years"] == list(world.YEARS) and alpha["state"] == world.STATE
    assert api.get(f"/api/v2/programs/{world.ALPHA}").json()["years"][0]["unverified"] is True
