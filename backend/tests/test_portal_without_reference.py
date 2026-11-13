"""The portal opens when the reference client is not in the source. [03.6]

The shell shows nothing until `/api/workspace` answers, and that endpoint builds the sealed run for
the reference account. A source that does not hold it (any real customer's) therefore left the
portal on "Workspace unavailable" with the real book unreachable. Now the endpoint says the sealed
run is not available, and why; the sealed views say so; everything else reads the real data.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from local_lakehouse import use_local_lakehouse, write_lakehouse

from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset


@pytest.fixture
def source_without_the_reference_client(tmp_path, monkeypatch):
    dataset = build_synthetic_dataset(SYNTHETIC_CLIENTS[0])
    assert dataset.account.account_id != 1001, "the point is a source that lacks the reference account"
    write_lakehouse(tmp_path, dataset, schema="tcc_source")
    use_local_lakehouse(monkeypatch, tmp_path)
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    monkeypatch.setenv("FABRIC_WORKSPACE", "ws")
    monkeypatch.setenv("FABRIC_LAKEHOUSE", "lh")

    from api import workspace
    from tools.reference_workspace import ReferenceWorkspaceService

    monkeypatch.setattr(workspace, "_SERVICE", ReferenceWorkspaceService(source_kind="lakehouse"))
    from main import app

    return TestClient(app, raise_server_exceptions=False)


def test_the_front_door_answers_and_says_the_sealed_run_is_not_available(source_without_the_reference_client):
    response = source_without_the_reference_client.get("/api/workspace")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is False and body["workspace"] is None
    assert "1001" in body["reason"], "it says which account the sealed run needs"
    assert body["remedy"]


def test_a_refresh_says_the_same_rather_than_failing(source_without_the_reference_client):
    response = source_without_the_reference_client.post("/api/workspace/refresh")
    assert response.status_code == 200 and response.json()["available"] is False


def test_the_other_sealed_endpoints_still_refuse_rather_than_invent_a_run(source_without_the_reference_client):
    assert source_without_the_reference_client.get("/api/workspace/assumptions").status_code in (500, 503)


def test_no_reference_account_configured_still_opens_the_front_door(source_without_the_reference_client, monkeypatch):
    monkeypatch.delenv("REFERENCE_ACCOUNT_ID", raising=False)
    for response in (
        source_without_the_reference_client.get("/api/workspace"),
        source_without_the_reference_client.post("/api/workspace/refresh"),
    ):
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["available"] is False and body["workspace"] is None
        assert "REFERENCE_ACCOUNT_ID" in body["reason"] and body["remedy"]


def test_a_source_that_is_not_configured_is_still_a_503_with_the_settings_to_set(monkeypatch):
    from api import workspace
    from main import app
    from tools.reference_workspace import ReferenceWorkspaceService

    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    for name in ("FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(workspace, "_SERVICE", ReferenceWorkspaceService(source_kind="lakehouse"))
    response = TestClient(app).get("/api/workspace")
    assert response.status_code == 503 and response.json()["dependency"] == "source_lakehouse"
