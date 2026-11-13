"""Batch reads go through the client authorizer. [F07.3]

The default authorizer (every signed-in caller may act for every client) changes nothing; a restrictive one narrows the list,
the batch, its counters and its items to the clients the caller may act for, and a batch with none of them does not exist for
that caller.
"""
from __future__ import annotations

import pytest

from application.identity import AllowListAuthorizer
from tests.test_api_run_batches import api  # noqa: F401 - fixture


@pytest.fixture()
def restrict():
    from bootstrap import wiring

    def apply(*client_ids):
        wiring.set_client_authorizer(AllowListAuthorizer({None: set(client_ids)}))

    yield apply
    wiring.set_client_authorizer(None)


def _batch(api, ids):
    return api.post("/api/v2/run-batches", json={"scope": {"kind": "list", "client_ids": ids}}).json()


def test_the_default_authorizer_shows_everything_unchanged(api):
    batch = _batch(api, [1, 2, 3])
    got = api.get(f"/api/v2/run-batches/{batch['batch_id']}").json()
    assert got["counts"]["total"] == 3 and got["scope_spec"]["client_ids"] == [1, 2, 3]
    assert api.get(f"/api/v2/run-batches/{batch['batch_id']}/items").json()["total"] == 3
    assert api.get("/api/v2/run-batches").json()["total"] == 1


def test_a_restrictive_authorizer_narrows_the_batch_its_counts_scope_and_items(api, restrict):
    batch = _batch(api, [1, 2, 3])
    bid = batch["batch_id"]
    restrict(1, 3)
    got = api.get(f"/api/v2/run-batches/{bid}").json()
    assert got["counts"]["total"] == 2 and got["progress"]["total"] == 2
    assert got["scope_spec"]["client_ids"] == [1, 3] and got["dry_run_summary"] == {}
    items = api.get(f"/api/v2/run-batches/{bid}/items").json()
    assert items["total"] == 2 and {i["client_id"] for i in items["items"]} == {1, 3}
    paged = api.get(f"/api/v2/run-batches/{bid}/items", params={"limit": 1, "offset": 1}).json()
    assert paged["total"] == 2 and [i["client_id"] for i in paged["items"]] == [3]
    assert api.get("/api/v2/run-batches").json()["items"][0]["counts"]["total"] == 2


def test_a_batch_with_none_of_the_callers_clients_does_not_exist_for_it(api, restrict):
    batch = _batch(api, [1, 2])
    restrict(5)
    assert api.get("/api/v2/run-batches").json() == {"items": [], "total": 0, "limit": 25, "offset": 0}
    for path in ("", "/items"):
        assert api.get(f"/api/v2/run-batches/{batch['batch_id']}{path}").status_code == 404


def test_the_status_filter_applies_to_the_callers_own_view(api, restrict):
    first = _batch(api, [1, 2])
    api.post(f"/api/v2/run-batches/{first['batch_id']}/cancel")
    _batch(api, [3])
    restrict(3)
    assert api.get("/api/v2/run-batches", params={"status": "cancelled"}).json()["total"] == 0
    assert api.get("/api/v2/run-batches", params={"status": "queued"}).json()["total"] == 1
