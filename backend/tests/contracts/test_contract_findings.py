"""The finding-store contract: SQLite and the Warehouse behave the same. [DATA-2, DATA-3, DATA-4]"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from infrastructure.persistence.sqlite_findings import FindingResolution

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


def _res(client_id: int, finding_id: str = "dup-worksite-1", *, resolution="accept", at=T0, year=2024, **kw):
    return FindingResolution(
        finding_id=finding_id,
        client_id=client_id,
        tax_year=year,
        resolution=resolution,
        decided_by="analyst@example.com",
        decided_at=at.isoformat(),
        **kw,
    )


def _at(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_a_resolution_round_trips(finding_repo, client_ids):
    client = client_ids()
    finding_repo.record(_res(client, detail={"keep": "GA_001"}, note="kept the larger site"))
    [live] = finding_repo.live(client)
    assert (live.finding_id, live.client_id, live.tax_year, live.resolution) == ("dup-worksite-1", client, 2024, "accept")
    assert live.detail == {"keep": "GA_001"} and live.note == "kept the larger site"
    assert live.decided_by == "analyst@example.com"
    assert abs(_at(live.decided_at) - T0) < timedelta(seconds=1)
    assert live.superseded_at is None


def test_a_new_decision_supersedes_the_live_one(finding_repo, client_ids):
    client = client_ids()
    finding_repo.record(_res(client, resolution="flag"))
    finding_repo.record(_res(client, resolution="drop", at=T0 + timedelta(hours=1)))
    [live] = finding_repo.live(client)
    assert live.resolution == "drop"
    history = finding_repo.history(client, "dup-worksite-1")
    assert [h.resolution for h in history] == ["flag", "drop"]
    assert history[0].superseded_at is not None and history[1].superseded_at is None


def test_reopen_closes_without_deleting(finding_repo, client_ids):
    client = client_ids()
    finding_repo.record(_res(client))
    finding_repo.reopen(client, "dup-worksite-1", decided_by="analyst@example.com")
    assert finding_repo.live(client) == []
    [prior] = finding_repo.history(client, "dup-worksite-1")
    assert prior.resolution == "accept" and prior.superseded_at is not None


def test_live_narrows_by_tax_year(finding_repo, client_ids):
    client = client_ids()
    finding_repo.record(_res(client, "f-2023", year=2023))
    finding_repo.record(_res(client, "f-2024", year=2024))
    assert [r.finding_id for r in finding_repo.live(client, 2024)] == ["f-2024"]
    assert {r.finding_id for r in finding_repo.live(client)} == {"f-2023", "f-2024"}


def test_one_clients_decisions_are_never_returned_for_another(finding_repo, client_ids):
    a, b = client_ids(), client_ids()
    finding_repo.record(_res(a))
    assert finding_repo.live(b) == []
    assert finding_repo.history(b, "dup-worksite-1") == []


def test_the_same_finding_id_is_independent_per_client(finding_repo, client_ids):
    a, b = client_ids(), client_ids()
    finding_repo.record(_res(a, resolution="accept"))
    finding_repo.record(_res(b, resolution="drop", at=T0 + timedelta(minutes=5)))
    finding_repo.reopen(b, "dup-worksite-1", decided_by="analyst@example.com")
    [live_a] = finding_repo.live(a)
    assert live_a.resolution == "accept" and live_a.superseded_at is None
    assert finding_repo.live(b) == []
