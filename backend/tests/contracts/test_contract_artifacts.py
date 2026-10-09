"""The artifact repository and byte-store contracts. [BLOB-3, BLOB-6]

The repository runs on SQLite always and on the Warehouse with
`TCC_FABRIC_TESTS=1`; the store runs on the local directory always and on Blob
with `TCC_AZURE_TESTS=1`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from application.artifacts import Artifact, ArtifactAccess

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _package(client_id: int, *, year: int = 2024, run: str = "run-a", at=T0, name: str | None = None) -> Artifact:
    file_name = name or f"claim-package-{client_id}-TY{year}-{uuid.uuid4().hex[:8]}.xlsx"
    return Artifact(
        kind="claim_package", client_id=client_id, program_code="GA_JTC", tax_year=year, run_id=run,
        container_name="outputs", blob_path=f"{client_id}/{run}/{file_name}", file_name=file_name,
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        size_bytes=123, sha256="a" * 64, created_by="analyst@example.com", created_at=at,
    )


def test_a_registered_artifact_round_trips(artifact_repo, client_ids):
    client = client_ids()
    stored = artifact_repo.record(_package(client))
    got = artifact_repo.find(stored.artifact_id)
    assert got is not None
    assert (got.client_id, got.kind, got.tax_year, got.run_id) == (client, "claim_package", 2024, "run-a")
    assert (got.blob_path, got.file_name, got.size_bytes, got.sha256) == (
        stored.blob_path, stored.file_name, 123, "a" * 64)
    assert got.created_by == "analyst@example.com"
    assert abs(got.created_at - T0) < timedelta(seconds=1)
    assert got.superseded_at is None


def test_an_unknown_id_is_none(artifact_repo):
    assert artifact_repo.find(uuid.uuid4().hex) is None


def test_a_new_package_supersedes_the_live_one_for_that_client_year(artifact_repo, client_ids):
    client = client_ids()
    first = artifact_repo.record(_package(client, run="run-a"))
    other_year = artifact_repo.record(_package(client, year=2023, run="run-a"))
    second = artifact_repo.record(_package(client, run="run-b", at=T0 + timedelta(hours=1)))
    live = {a.artifact_id for a in artifact_repo.live(client, kind="claim_package", tax_year=2024)}
    assert live == {second.artifact_id}
    assert artifact_repo.find(first.artifact_id).superseded_at is not None
    assert artifact_repo.find(other_year.artifact_id).superseded_at is None


def test_one_clients_artifacts_are_never_listed_for_another(artifact_repo, client_ids):
    a, b = client_ids(), client_ids()
    artifact_repo.record(_package(a))
    assert artifact_repo.live(b) == []
    assert [x.client_id for x in artifact_repo.live(a)] == [a]


def test_access_rows_are_recorded_per_client(artifact_repo, client_ids):
    a, b = client_ids(), client_ids()
    art = artifact_repo.record(_package(a))
    for outcome in ("served", "denied", "missing"):
        artifact_repo.record_access(ArtifactAccess(
            artifact_id=art.artifact_id, client_id=a, user_upn="analyst@example.com",
            user_oid="oid-1", outcome=outcome, accessed_at=T0,
        ))
    assert sorted(x.outcome for x in artifact_repo.accesses(a)) == ["denied", "missing", "served"]
    assert artifact_repo.accesses(b) == []


def test_the_domain_refuses_a_package_outside_its_clients_prefix():
    with pytest.raises(ValueError, match="prefix"):
        Artifact(kind="claim_package", client_id=1, run_id="r", container_name="outputs",
                 blob_path="2/r/x.xlsx", file_name="x.xlsx", content_type="t", size_bytes=1,
                 sha256="a" * 64, created_by="x")
    with pytest.raises(ValueError, match="one client and one run"):
        Artifact(kind="claim_package", client_id=None, run_id=None, container_name="artifacts",
                 blob_path="x", file_name="x", content_type="t", size_bytes=1, sha256="a" * 64, created_by="x")


# ------------------------------------------------------------------ the bytes


def test_bytes_round_trip_and_an_absent_path_is_none(artifact_store):
    path = f"9{uuid.uuid4().int % 10**8}/run/{uuid.uuid4().hex}.bin"
    artifact_store.put("outputs", path, b"\x00claim\xff", "application/octet-stream")
    assert artifact_store.get("outputs", path) == b"\x00claim\xff"
    assert artifact_store.get("outputs", path + ".absent") is None


def test_a_blob_path_is_never_overwritten(artifact_store):
    path = f"9{uuid.uuid4().int % 10**8}/run/{uuid.uuid4().hex}.bin"
    artifact_store.put("outputs", path, b"first", "application/octet-stream")
    with pytest.raises(Exception):
        artifact_store.put("outputs", path, b"second", "application/octet-stream")
    assert artifact_store.get("outputs", path) == b"first"


def test_the_local_store_refuses_path_traversal(tmp_path):
    from infrastructure.storage.local_store import LocalArtifactStore

    store = LocalArtifactStore(tmp_path)
    for bad in ("../escape.bin", "/abs.bin", "a/../../b.bin"):
        with pytest.raises(ValueError):
            store.put("outputs", bad, b"x", "t")
