"""After activation: a program that becomes calculable through a normal deployment shows up everywhere with no code change. [F05.9]

"Normal deployment" is modelled the only way ADR-005 allows: the files are in the rules folder and the registry lists the program
(`two_program_world.install` writes both into a temporary folder). Nothing else is touched: no setting, no database row, no
frontend or engine edit. The fictional program must then appear in the catalog, in the scope selector's program list (which the
run dialog, the filters and the engagement controls read), and be accepted by the run batch preview as a selectable program; a
program that is described but not authored must NOT be offered.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from application.runs import selection
from tests import two_program_world as world

BOOK = [{"account_id": i, "name": f"Client {i}"} for i in range(1, 4)]


@pytest.fixture()
def api(monkeypatch, tmp_path):
    import main
    from bootstrap import run_batch_wiring
    from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository

    repo = SqliteRunBatchRepository(":memory:")
    run_batch_wiring.set_run_batch_repository(repo)
    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    monkeypatch.setattr(selection, "_portfolio_page", lambda: {"items": [], "degraded": []})
    monkeypatch.setattr("application.runs.plan._assumptions", lambda: [])
    monkeypatch.setattr("application.services.get_run_manifest_repository", lambda: type("M", (), {"latest": lambda s, c, **k: None})())
    yield TestClient(main.app), tmp_path, monkeypatch
    run_batch_wiring.set_run_batch_repository(None)
    repo.close()


def _scope_programs(client) -> dict:
    return {p["program_code"]: p for p in client.get("/api/scope").json()["programs"]}


def test_before_activation_the_program_is_not_offered_anywhere(api):
    client, _, _ = api
    assert world.ALPHA not in _scope_programs(client)
    assert world.ALPHA not in {p["code"] for p in client.get("/api/v2/programs").json()["programs"]}


def test_after_activation_it_appears_in_the_catalog_the_scope_options_and_the_run_preview(api):
    client, tmp_path, monkeypatch = api
    world.install(tmp_path, monkeypatch)
    catalog = {p["code"]: p for p in client.get("/api/v2/programs").json()["programs"]}
    assert catalog[world.ALPHA]["calculable"] is True and catalog[world.ALPHA]["authored_years"] == list(world.YEARS)
    offered = _scope_programs(client)[world.ALPHA]
    assert offered["authored_years"] == list(world.YEARS) and offered["jurisdiction"]["code"] == world.STATE and offered["calculable"] is True
    # The run dialog offers exactly the scope options' programs that have authored years, and sends the code it was given.
    preview = client.post("/api/v2/run-batches", json={
        "kind": "calculate", "scope": {"kind": "list", "client_ids": [1, 2]}, "program_code": world.ALPHA, "dry_run": True})
    assert preview.status_code == 202 and preview.json()["dry_run"] is True


def test_two_programs_in_the_activated_state_are_both_offered_so_the_picker_has_something_to_pick(api):
    client, tmp_path, monkeypatch = api
    world.install(tmp_path, monkeypatch)
    offered = _scope_programs(client)
    in_state = [c for c, p in offered.items() if p["jurisdiction"]["code"] == world.STATE and p["authored_years"]]
    assert sorted(in_state) == sorted([world.ALPHA, world.BETA])


def test_a_program_that_is_only_described_is_listed_but_never_offered_as_runnable(api):
    client, tmp_path, monkeypatch = api
    world.install(tmp_path, monkeypatch, second_authored=False)
    catalog = {p["code"]: p for p in client.get("/api/v2/programs").json()["programs"]}
    assert catalog[world.BETA]["calculable"] is False and "not inherited" in catalog[world.BETA]["not_calculable_reason"]
    assert _scope_programs(client)[world.BETA]["authored_years"] == [], "the run dialog filters on authored years, so it is not selectable"
