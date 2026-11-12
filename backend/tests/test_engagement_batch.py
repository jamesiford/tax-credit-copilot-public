"""The portfolio reads every client's engagement scopes in a batch, not one round trip per client. [08.1b]"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from application.queries import portfolio_reads
from infrastructure.persistence.engagement_batch import EngagementBatchReader


@pytest.fixture
def api(tmp_path, monkeypatch):
    from bootstrap import wiring
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
    from main import app

    repo = SqliteClaimRepository(tmp_path / "claims.db")
    wiring.set_claim_repository(repo)
    monkeypatch.setattr(portfolio_reads, "_footprint_failure", None)
    yield TestClient(app, raise_server_exceptions=False), repo
    repo.close()
    wiring.set_claim_repository(None)


def _record(client, client_id, **over):
    body = {"client_id": client_id, "program_code": "GA_JTC", "tax_year": 2023, "status": "assessed", "provenance": "computed",
            "decided_by": "a@example.com", "identified_usd": "100", **over}
    assert client.post("/api/claims", json=body).status_code == 201


def test_the_page_makes_no_per_client_engagement_reads(api, monkeypatch):
    client, repo = api
    for cid in (11, 12, 13, 14, 15):
        _record(client, cid)
    calls = []
    original = repo.engagements
    monkeypatch.setattr(repo, "engagements", lambda cid: calls.append(cid) or original(cid))
    assert client.get("/api/v2/portfolio").status_code == 200
    assert calls == [], "one batched read answered for every client"


def test_the_batch_returns_every_id_asked_with_an_empty_list_for_a_client_with_none(api):
    client, repo = api
    from domain.claims import EngagementScope, ProgramEngagement

    repo.set_engagement(ProgramEngagement(client_id=21, program_code="GA_JTC", scope=EngagementScope.IN_SCOPE))
    found = EngagementBatchReader().read(repo, [21, 22, 21])
    assert set(found) == {21, 22} and [e.program_code for e in found[21]] == ["GA_JTC"] and found[22] == []


def test_the_batch_is_chunked_so_thousands_of_clients_are_a_few_reads(api, monkeypatch):
    _, repo = api
    statements = []
    real = repo._connect()

    class Spy:
        def execute(self, sql, params=()):
            statements.append(len(params))
            return real.execute(sql, params)

    monkeypatch.setattr(repo, "_connect", lambda: Spy())
    found = EngagementBatchReader().read(repo, list(range(1200)))
    assert len(found) == 1200 and statements == [500, 500, 200]


def test_a_batch_that_fails_falls_back_to_the_per_client_read_which_reports(api, monkeypatch):
    client, repo = api
    _record(client, 31)
    monkeypatch.setattr(EngagementBatchReader, "read", lambda self, repo, ids: (_ for _ in ()).throw(OSError("timed out")))
    assert client.get("/api/v2/portfolio").status_code == 200, "the page still answers, per client"


def test_an_unknown_repository_gets_no_batch_and_the_page_uses_the_per_client_read():
    assert EngagementBatchReader().read(object(), [1, 2]) is None
    assert portfolio_reads.prefetch_engagements(None, [1], []) == {}
