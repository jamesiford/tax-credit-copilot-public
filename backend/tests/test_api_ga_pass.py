"""Endpoint tests for the ingested-rules + QC surfaces added in the GA pass."""
from __future__ import annotations


def test_ingested_rules_ga(client):
    r = client.get("/api/rules/ingested/GA?tax_year=2025")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "GA"
    assert body["program"] == "GA_JTC"
    assert body["provenance"]
    assert all(row["url"] or row["artifact_sha256"] for row in body["provenance"])


def test_ingested_rules_non_ga_404(client):
    assert client.get("/api/rules/ingested/SC").status_code == 404


def test_ingested_rules_tn_statute_grounded(client):
    r = client.get("/api/rules/ingested/TN?tax_year=2025")
    assert r.status_code == 200
    body = r.json()
    assert body["provenance"]
    assert all(row["url"] for row in body["provenance"])


def test_ingested_tn_refresh_ok_but_proposals_ga_only(client):
    # TN carries a statute-grounded cited config and now supports live
    # source reachability/drift refresh; the annual-memo proposals/apply flow
    # stays GA-only in this pass.
    r = client.get("/api/rules/ingested/TN/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["state"] == "TN"
    assert body["sources"]  # one reachability/drift entry per source URL
    assert client.get("/api/rules/ingested/TN/proposals").status_code == 404


def test_ingested_refresh_captured(client):
    r = client.get("/api/rules/ingested/GA/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "captured"
    assert body["parameter_count"] >= 5


def test_qc_report_ga(client):
    r = client.get("/api/qc/2025?state=GA")
    assert r.status_code == 200
    body = r.json()
    assert "test_of_twos" in body
    assert "meaningful_pay_period" in body
    assert "summary" in body
    assert body["summary"]["requires_human_validation"] in (True, False)


def test_agent_factory_lists_new_agents():
    """The three later agents are discoverable from the factory.

    Was asserted through `GET /api/agents`, a route nothing in the portal ever
    called. The property worth holding is that the modules are registered, not
    that an HTTP surface reports them.
    """
    from agents.factory import list_agent_modules

    names = {getattr(m, "NAME", None) for m in list_agent_modules()}
    assert {"RulesIngestionAgent", "ExceptionReportAgent", "LegislativeMonitorAgent"} <= names


def test_ingestion_proposals_needs_key(client, monkeypatch):
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    monkeypatch.delenv("WEBIQ_BEARER_TOKEN", raising=False)
    r = client.get("/api/rules/ingested/GA/proposals?tax_year=2025")
    assert r.status_code == 200
    body = r.json()
    assert body["web_iq_status"] == "NEEDS_KEY"


def test_ingestion_apply_requires_key(client, monkeypatch):
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    monkeypatch.delenv("WEBIQ_BEARER_TOKEN", raising=False)
    r = client.post("/api/rules/ingested/GA/apply", json={"tax_year": 2025})
    assert r.status_code == 503


def test_ingestion_changelog_shape(client):
    r = client.get("/api/rules/ingested/GA/changelog")
    assert r.status_code == 200
    body = r.json()
    assert "applied_years" in body
    assert "changelog" in body


def test_ingestion_endpoints_non_ga_404(client):
    assert client.get("/api/rules/ingested/SC/proposals").status_code == 404
    assert client.get("/api/rules/ingested/SC/changelog").status_code == 404
