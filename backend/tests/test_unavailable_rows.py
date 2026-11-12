"""Unavailable is not the same as not assessed. [03b.1]

When the claim store (or one client's engagement scope) cannot be read, a client's row must not assert an
assessment state. "Not assessed" says the pipeline has not reached a client, which is a fact about the
client; "unavailable" says we could not look, which is a fact about us. Rows carry null figures, an explicit
`data_unavailable` flag and the dependency, the counters that would be wrong become null, and the chat and the
channel say the figures are unavailable instead of implying a result.

HTTP status: the page keeps answering 200 with `degraded`. A 503 would be simpler, but it would take the
whole book (names, industries, footprint, the clients that DID read) off the screen for one failing
dependency, and the page can say exactly what is missing. The status was decided in prompt 03 and is kept.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from application.capabilities import book
from application.queries import portfolio_reads
from tools.page_brief import portfolio_brief


class _Down:
    def __init__(self, error):
        self.error = error

    def portfolio_coverage(self, **_kw):
        raise self.error

    def engagements(self, *_a, **_kw):
        raise self.error


@pytest.fixture
def api(tmp_path, monkeypatch):
    from bootstrap import wiring
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
    from main import app

    repo = SqliteClaimRepository(tmp_path / "claims.db")
    wiring.set_claim_repository(repo)
    monkeypatch.setattr(portfolio_reads, "_footprint_failure", None)
    yield TestClient(app, raise_server_exceptions=False), wiring, repo
    repo.close()
    wiring.set_claim_repository(None)


def _record(client, client_id=1001, **over):
    body = {"client_id": client_id, "program_code": "GA_JTC", "tax_year": 2023, "status": "assessed",
            "provenance": "computed", "decided_by": "a@example.com", "identified_usd": "100", **over}
    assert client.post("/api/claims", json=body).status_code == 201


@pytest.mark.parametrize("error", [
    OSError("08001 connection timed out"), RuntimeError("Invalid object name 'tcc_ops.program_claim'."),
])
def test_a_store_that_cannot_be_read_gives_unavailable_rows_never_not_assessed(api, error):
    client, wiring, _ = api
    wiring.set_claim_repository(_Down(error))
    response = client.get("/api/v2/portfolio")
    assert response.status_code == 200
    body = response.json()
    (row,) = body["items"]
    assert row["data_unavailable"] is True and row["unavailable_dependency"] == "claims_store"
    assert row["priority_band"] == "unavailable"
    for field in ("status", "outcome", "effective_outcome", "identified_usd", "claimed_usd", "opportunity_usd", "jobs_margin"):
        assert row[field] is None, field
    assert row["status"] != "not_assessed" and row["effective_outcome"] != "not_assessed"
    assert body["assessed_clients"] is None and body["unassessed_clients"] is None, "nobody knows, so not 0"
    assert body["unavailable_clients"] == 1 and body["degraded"][0]["dependency"] == "claims_store"


def test_an_empty_store_is_still_not_assessed_and_counted(api):
    client, _, _ = api
    body = client.get("/api/v2/portfolio").json()
    assert body["items"][0]["status"] == "not_assessed" and "data_unavailable" not in body["items"][0]
    assert body["assessed_clients"] == 0 and body["unassessed_clients"] == 1 and body["unavailable_clients"] == 0


@pytest.mark.parametrize("query", [
    "", "?outcome=unclaimed", "?status=assessed", "?near=true", "?near=false", "?scope=in_scope", "?year=2024",
])
def test_unavailable_rows_are_in_every_view_so_a_saved_view_never_shows_nothing_to_do(api, query):
    client, wiring, _ = api
    wiring.set_claim_repository(_Down(OSError("timed out")))
    body = client.get(f"/api/v2/portfolio{query}").json()
    assert [r["data_unavailable"] for r in body["items"]] == [True]


def test_one_clients_engagement_read_failing_makes_only_that_row_unavailable(api, monkeypatch):
    client, _, repo = api
    _record(client, 1001)
    _record(client, 2001, identified_usd="500")
    real = repo.engagements

    def flaky(client_id):
        if client_id == 2001:
            raise OSError("connection timed out")
        return real(client_id)

    monkeypatch.setattr(repo, "engagements", flaky)
    monkeypatch.setattr("infrastructure.persistence.engagement_batch.EngagementBatchReader.read", lambda self, repo, ids: None)  # the per-client read is what is under test
    monkeypatch.setattr("application.client_book.clients", lambda: [
        {"account_id": 1001, "name": "Ok", "industry": None}, {"account_id": 2001, "name": "Flaky", "industry": None},
    ])
    body = client.get("/api/v2/portfolio").json()
    by_id = {r["client_id"]: r for r in body["items"]}
    assert by_id[1001].get("data_unavailable") is None and by_id[1001]["identified_usd"] == "100"
    assert by_id[2001]["data_unavailable"] is True and by_id[2001]["identified_usd"] is None
    assert body["assessed_clients"] == 1, "the claims were read, so the counter stays a number"
    assert body["unavailable_clients"] == 1
    assert [r["client_id"] for r in body["items"]] == [1001, 2001], "unavailable rows sort after the ranked ones"


def test_unavailable_rows_sort_after_not_assessed_and_ranked_rows_whatever_the_sort(api, monkeypatch):
    client, _, repo = api
    _record(client, 1001)
    monkeypatch.setattr(repo, "engagements", lambda cid: (_ for _ in ()).throw(OSError("timed out")) if cid == 3001 else [])
    monkeypatch.setattr("application.client_book.clients", lambda: [
        {"account_id": 1001, "name": "A", "industry": None}, {"account_id": 2001, "name": "B", "industry": None},
        {"account_id": 3001, "name": "C", "industry": None},
    ])
    for params in ("?sort=priority&order=asc", "?sort=identified_usd&order=desc", "?sort=client_id&order=asc"):
        ids = [r["client_id"] for r in client.get(f"/api/v2/portfolio{params}").json()["items"]]
        assert ids[-1] == 3001, params


# ---------------------------------------------------- the chat and the channel


def _page(*rows, assessed=0, degraded=None):
    return {"items": list(rows), "total_clients": len(rows), "assessed_clients": assessed, "degraded": degraded or []}


def _unavailable(cid, name):
    return {"client_id": cid, "client_name": name, "data_unavailable": True, "priority_band": "unavailable"}


def test_book_rank_says_figures_are_unavailable_and_never_implies_a_result():
    result = book.book_rank(page_reader=lambda **kw: _page(_unavailable(1, "Acme"), assessed=None, degraded=[{"dependency": "claims_store"}]))
    facts = result.facts
    assert facts["calculated"] is False and facts["unavailable"] is True
    assert "unavailable" in facts["message"] and "Acme" in facts["unavailable_clients"]
    text = str(result.blocks).lower()
    assert "has been assessed yet" not in text and "nothing to rank" not in text


def test_book_rank_with_some_unavailable_ranks_the_rest_and_names_the_others():
    ranked = {"client_id": 2, "client_name": "Beta", "priority_band": "on_the_line", "program_code": "GA_JTC",
              "tax_year": 2023, "identified_usd": "10", "jobs_margin": -0.5, "provenance_verified": True}
    result = book.book_rank(page_reader=lambda **kw: _page(ranked, _unavailable(1, "Acme"), assessed=1))
    assert [c["client_name"] for c in result.facts["clients"]] == ["Beta"]
    assert result.facts["unavailable_clients"] == ["Acme"]
    assert "Unavailable is not the same as not assessed" in str(result.blocks)


def test_book_rank_is_unchanged_when_nothing_is_unavailable():
    ranked = {"client_id": 2, "client_name": "Beta", "priority_band": "on_the_line", "program_code": "GA_JTC",
              "tax_year": 2023, "identified_usd": "10", "jobs_margin": -0.5, "provenance_verified": True}
    facts = book.book_rank(page_reader=lambda **kw: _page(ranked, assessed=1)).facts
    assert "unavailable_clients" not in facts and "degraded" not in facts


def test_the_page_summary_brief_does_not_call_unavailable_not_assessed():
    brief = portfolio_brief(_page(_unavailable(1, "Acme"), assessed=None))
    text = " ".join(brief["facts"] + brief["caveats"]).lower()
    assert "unavailable" in text and "not the same as not assessed" in text
    assert "0 assessed" not in text and "1 client(s) have not been assessed" not in text
    assert brief["data"]["assessed_clients"] is None and brief["data"]["clients"] == []
