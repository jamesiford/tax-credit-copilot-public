"""The run batch capabilities in Teams and Cowork: a two-step write, and two reads. [ADR-012, CH-05]

What must hold for a batch started from a chat: the preview writes nothing and reads no payroll; the batch is authored
by the PERSON, never the gateway; a person who may not write cannot get a token; above the confirmation threshold the
preview refuses until the count is in the arguments (the portal's typed confirmation, in two steps); a retry with the
same key queues once; and the reads say what the queue says. Offline: a private queue and a stubbed client book.
"""
from __future__ import annotations

import json

import pytest

from application.capabilities import catalog, registry
from application.capabilities.errors import NotCalculated
from application.capabilities.write_specs import InvalidWrite
from application.identity import NotAuthorized
from application.runs import selection
from infrastructure.persistence.sqlite_run_batches import SqliteRunBatchRepository
from tests.test_channel_writes import OTHER, USER, agent_for, commit, prepare, world  # noqa: F401 - fixtures

BOOK = [{"account_id": i, "name": f"Client {i}"} for i in range(1, 31)]


class _NoRuns:
    def latest(self, client_id, *, program_code=None):
        return None


@pytest.fixture()
def queue(world, monkeypatch):  # noqa: F811
    from bootstrap import run_batch_wiring

    repo = SqliteRunBatchRepository(":memory:")
    run_batch_wiring.set_run_batch_repository(repo)
    monkeypatch.setattr(selection, "_book", lambda: BOOK)
    monkeypatch.setattr(selection, "_portfolio_page", lambda: {"items": [], "degraded": []})
    monkeypatch.setattr("application.runs.plan._assumptions", lambda: [])
    monkeypatch.setattr("application.services.get_run_manifest_repository", lambda: _NoRuns())
    monkeypatch.setenv("RUN_BATCH_CONFIRM_ABOVE", "5")
    yield repo
    run_batch_wiring.set_run_batch_repository(None)
    repo.close()


SMALL = {"scope": {"kind": "list", "account_ids": [1, 2, 3]}}


def test_the_pair_names_no_client_and_the_model_schema_holds_no_client_id():
    for name in ("run_batch_prepare", "run_batch_commit"):
        spec = catalog.get(name)
        assert spec.needs_client is False
        assert "client_id" not in json.dumps(spec.schema), "the client is the reader's, never the model's"
    assert catalog.get("run_batch_status").needs_client is False and catalog.get("run_batch_list").needs_client is False


def test_prepare_writes_nothing_and_previews_the_counts_with_an_upper_bound(queue):
    prepared = prepare("run_batch", **SMALL)
    assert queue.list_batches(10, 0)[1] == 0
    after = prepared.facts["preview"]["after"]
    assert after["clients"] == 3 and after["runs to queue"] == 3 and after["never calculated"] == 3
    assert any("upper bound" in key for key in after)
    assert after["first clients"] == "Client 1, Client 2, Client 3"
    assert len(prepared.facts["confirmation"]["token"]) >= 32
    assert "Nothing has changed yet" in prepared.blocks[-1].text


def test_the_commit_enqueues_a_batch_authored_by_the_person(queue):
    principal = agent_for()
    prepared = prepare("run_batch", principal, **SMALL)
    done = commit("run_batch", prepared, SMALL, principal=principal)
    batch = done.facts["result"]
    assert batch["status"] == "queued" and batch["counts"]["total"] == 3
    assert batch["requested_by"] == principal.actor and "gateway" not in batch["requested_by"].lower()
    assert queue.list_batches(10, 0)[1] == 1


def test_the_same_commit_twice_queues_once(queue):
    prepared = prepare("run_batch", **SMALL)
    first = commit("run_batch", prepared, SMALL, key="same")
    again = commit("run_batch", prepared, SMALL, key="same")
    assert again.facts["replayed"] is True and again.facts["result"]["batch_id"] == first.facts["result"]["batch_id"]
    assert queue.list_batches(10, 0)[1] == 1


def test_a_person_who_may_not_write_gets_no_token(queue):
    with pytest.raises(NotAuthorized):
        prepare("run_batch", agent_for(OTHER), **SMALL)
    assert queue.list_batches(10, 0)[1] == 0


def test_above_the_threshold_the_preview_refuses_until_the_count_is_confirmed(queue):
    everyone = {"scope": {"kind": "all"}}
    with pytest.raises(InvalidWrite) as refused:
        prepare("run_batch", **everyone)
    assert "30 runs for 30 clients" in str(refused.value) and "confirm_items=30" in str(refused.value)
    assert queue.list_batches(10, 0)[1] == 0
    with pytest.raises(InvalidWrite):
        prepare("run_batch", confirm_items=29, **everyone)
    confirmed = {**everyone, "confirm_items": 30}
    prepared = prepare("run_batch", **confirmed)
    assert prepared.facts["preview"]["after"]["runs to queue"] == 30
    done = commit("run_batch", prepared, confirmed)
    assert done.facts["result"]["counts"]["total"] == 30


def test_a_filter_and_the_options_are_validated_before_a_token_exists(queue):
    with pytest.raises(InvalidWrite):
        prepare("run_batch", scope={"kind": "filter", "filter": {"colour": "red"}})
    with pytest.raises(InvalidWrite):
        prepare("run_batch", scope={"kind": "list", "account_ids": []})
    with pytest.raises(InvalidWrite):
        prepare("run_batch", scope={"kind": "everyone"})
    with pytest.raises(InvalidWrite):
        prepare("run_batch", options={"refresh_once": False}, **SMALL)
    ok = prepare("run_batch", tax_years=[2024, 2025], options={"force": True}, confirm_items=6, **SMALL)
    assert ok.facts["preview"]["after"]["runs to queue"] == 6
    assert ok.facts["preview"]["after"]["re-run even if unchanged"] == "yes"


def test_a_client_the_book_does_not_hold_is_refused_at_prepare(queue):
    with pytest.raises(InvalidWrite) as refused:
        prepare("run_batch", scope={"kind": "list", "account_ids": [1, 999]})
    assert "999" in str(refused.value)


def test_the_status_and_list_reads_say_what_the_queue_says(queue):
    with pytest.raises(NotCalculated):
        registry.call("run_batch_status")
    with pytest.raises(NotCalculated):
        registry.call("run_batch_list")
    prepared = prepare("run_batch", **SMALL)
    started = commit("run_batch", prepared, SMALL).facts["result"]
    latest = registry.call("run_batch_status")
    assert latest.facts["batch_id"] == started["batch_id"] and latest.facts["counts"]["queued"] == 3
    assert registry.call("run_batch_status", batch_id=started["batch_id"]).facts["progress"] == {"done": 0, "total": 3}
    listing = registry.call("run_batch_list", limit=3)
    assert [b["batch_id"] for b in listing.facts["items"]] == [started["batch_id"]]
    with pytest.raises(NotCalculated):
        registry.call("run_batch_status", batch_id="nope")


def test_a_failed_item_is_reported_by_cause(queue):
    from datetime import datetime, timezone

    from domain.runs import ItemResult, ItemStatus

    prepared = prepare("run_batch", **SMALL)
    batch = commit("run_batch", prepared, SMALL).facts["result"]
    claimed = queue.claim("w", 1, 120, datetime.now(timezone.utc))[0]
    queue.finish(claimed.item_id, "w", datetime.now(timezone.utc),
                 ItemResult(ItemStatus.FAILED, error_dependency="operational_store", error_message="the server could not be reached."))
    queue.refresh(batch["batch_id"], datetime.now(timezone.utc))
    status = registry.call("run_batch_status", batch_id=batch["batch_id"])
    assert status.facts["failures"] == [{"dependency": "operational_store", "count": 1, "message": "the server could not be reached."}]
    assert any("failed with operational_store" in b.text for b in status.blocks if hasattr(b, "text"))


def test_the_orchestrator_may_call_the_reads_and_the_pair_over_the_gateway_surface():
    offered = {s.name for s in catalog.offered()}
    assert {"run_batch_prepare", "run_batch_commit", "run_batch_status", "run_batch_list"} <= offered
