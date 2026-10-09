"""Tests for the rules-ingestion spine (A5 / CALC-11 / GOV-01) and the QC
exception report (CALC-07/08), plus the new agent registration."""
from __future__ import annotations

from tools import rules_ingestion as ri
from tools import qc


# --- rules_ingestion --------------------------------------------------------


def test_ga_config_loads_and_has_provenance():
    cfg = ri.load_ingested_config("GA")
    assert cfg is not None
    assert cfg["program"] == "GA_JTC"
    # every parameter carries a source with a URL + retrieved_at (GOV-01)
    for name, node in cfg["parameters"].items():
        assert "value" in node, name
        assert node["source"]["url"], name
        assert node["source"]["retrieved_at"], name


def test_non_ga_has_no_ingested_config():
    assert ri.load_ingested_config("SC") is None
    assert ri.has_ingested_config("SC") is False
    assert ri.has_ingested_config("GA") is True


def test_tn_config_loads_and_is_statute_grounded():
    cfg = ri.load_ingested_config("TN")
    assert cfg is not None
    assert cfg["program"] == "TN_JTC"
    assert ri.has_ingested_config("TN") is True
    # every parameter carries a source with a URL + retrieved_at (GOV-01)
    for name, node in cfg["parameters"].items():
        assert "value" in node, name
        assert node["source"]["url"], name
        assert node["source"]["retrieved_at"], name
    # the hours floor cites the TN statute (T.C.A. § 67-4-2109)
    assert "67-4-2109" in cfg["parameters"]["min_weekly_hours"]["source"]["authority"]


def test_tn_ingested_one_zero_matches_static_pack():
    """The TN cited config must resolve to the SAME floors as the static pack so
    enabling it changes no computed number."""
    from tools.credit_math import load_pack_one_zero

    oz = ri.ingested_one_zero("TN", tax_year=2025)
    assert oz["min_weekly_hours"] == 37.5
    assert oz["min_weekly_wages"] == 600.0
    assert oz["wage_basis"] == "regular"
    assert oz["measuring_date"] == "last_day"
    assert oz["source"] == "rules_ingested"
    pack = load_pack_one_zero("TN", tax_year=2025)
    assert pack.min_weekly_hours == 37.5
    assert pack.min_weekly_wages == 600.0
    assert pack.wage_basis == "regular"


def test_ingest_tn_captured_mode():
    """TN ingestion (captured mode) returns the cited config + one source entry
    per source URL, without hitting the network."""
    res = ri.ingest_tn_jtc(live=False)
    assert res["program"] == "TN_JTC"
    assert res["mode"] == "captured"
    assert res["config"]["program"] == "TN_JTC"
    assert res["sources"]  # >= 1 (statute + TNECD source URLs, deduped)


def test_ingested_one_zero_shape():
    oz = ri.ingested_one_zero("GA", tax_year=2025)
    assert oz["min_weekly_hours"] == 35.0
    # 2025 historical-table year override wins
    assert oz["min_weekly_wages"] == 680.0
    assert oz["wage_basis"] == "all_remuneration"
    assert oz["measuring_date"] == "last_day"
    assert oz["source"] == "rules_ingested"


def test_ingested_2024_uses_workbook_floor():
    oz = ri.ingested_one_zero("GA", tax_year=2024)
    assert oz["min_weekly_wages"] == 686.0


def test_ingested_unconfigured_year_uses_default_floor():
    oz = ri.ingested_one_zero("GA", tax_year=2023)
    assert oz["min_weekly_wages"] == 680.0


def test_provenance_report_flattens_values():
    rows = ri.provenance_report("GA", tax_year=2025)
    params = {r["parameter"] for r in rows}
    assert "min_weekly_hours" in params
    assert "min_weekly_wages" in params
    assert "min_weekly_wages@2025" in params
    for r in rows:
        assert r["url"] or r["artifact_sha256"]


def test_ingest_captured_is_deterministic():
    a = ri.ingest_ga_jtc(live=False)
    b = ri.ingest_ga_jtc(live=False)
    assert a["mode"] == "captured"
    assert a["config"] == b["config"]
    assert len(a["sources"]) >= 1
    # captured mode never probes the network
    for s in a["sources"]:
        assert s["reachable"] is None


def test_ingested_config_drives_engine_floor():
    """The GA One/Zero floors must come from the ingested config (CALC-11)."""
    from tools.credit_math import load_pack_one_zero

    pack = load_pack_one_zero("GA", tax_year=2025)
    assert pack is not None
    assert pack.min_weekly_hours == 35.0
    assert pack.min_weekly_wages == 680.0
    assert pack.wage_basis == "all_remuneration"


# --- qc (CALC-07 / CALC-08) -------------------------------------------------


def _row(emp, unit, wages, hours, pay_date="2025-02-02", pp_start="2025-01-15", pp_end="2025-01-28"):
    return {
        "Tax_Year": 2025,
        "Employee_ID": emp,
        "Worksite_ID": unit,
        "Pay_Period_Start": pp_start,
        "Pay_Period_End": pp_end,
        "Pay_Date": pay_date,
        "Gross_Wages": wages,
        "Hours_Worked": hours,
        "Pay_Code": "Regular",
    }


def test_test_of_twos_flags_multi_unit_month():
    rows = [
        _row("E1", "GA_ATL_HQ", 2000, 80, pay_date="2025-02-05"),
        _row("E1", "GA_SAV_DC", 1000, 40, pay_date="2025-02-20"),
        _row("E2", "GA_ATL_HQ", 2000, 80, pay_date="2025-02-05"),
    ]
    anomalies = qc.detect_test_of_twos(rows, tax_year=2025, state="GA")
    assert len(anomalies) == 1
    a = anomalies[0]
    assert a["employee_id"] == "E1"
    assert a["month"] == "2025-02"
    assert a["unit_count"] == 2
    assert a["resolution"] == "human_review"


def test_test_of_twos_ignores_single_unit():
    rows = [
        _row("E1", "GA_ATL_HQ", 2000, 80, pay_date="2025-02-05"),
        _row("E1", "GA_ATL_HQ", 2000, 80, pay_date="2025-02-20"),
    ]
    assert qc.detect_test_of_twos(rows, tax_year=2025, state="GA") == []


def test_scraggly_pay_period_flagged_not_dropped():
    rows = [
        _row("E1", "GA_ATL_HQ", 10.0, 1.0),   # scraggly
        _row("E2", "GA_ATL_HQ", 2000.0, 80.0),  # normal
    ]
    anomalies = qc.detect_scraggly_pay_periods(rows, tax_year=2025, state="GA")
    assert len(anomalies) == 1
    assert anomalies[0]["employee_id"] == "E1"
    assert anomalies[0]["resolution"] == "human_review"


def test_run_exception_report_summary():
    rows = [
        _row("E1", "GA_ATL_HQ", 2000, 80, pay_date="2025-02-05"),
        _row("E1", "GA_SAV_DC", 1000, 40, pay_date="2025-02-20"),
        _row("E3", "GA_ATL_HQ", 5.0, 0.5),
    ]
    report = qc.run_exception_report(rows, tax_year=2025, state="GA")
    assert report["summary"]["test_of_twos_count"] == 1
    assert report["summary"]["meaningful_pay_period_count"] == 1
    assert report["summary"]["clean"] is False
    assert report["summary"]["requires_human_validation"] is True


def test_clean_run_has_no_anomalies():
    rows = [_row("E1", "GA_ATL_HQ", 2000, 80)]
    report = qc.run_exception_report(rows, tax_year=2025, state="GA")
    assert report["summary"]["clean"] is True
    assert report["summary"]["requires_human_validation"] is False


# --- agent registration -----------------------------------------------------


def test_three_new_agents_registered():
    from agents.factory import list_agent_modules

    names = {m.NAME for m in list_agent_modules()}
    assert "RulesIngestionAgent" in names
    assert "ExceptionReportAgent" in names
    assert "LegislativeMonitorAgent" in names
    # The roster is a decided set, for the same reason the route inventory is.
    # Every agent is a Foundry registration that mints a version on each prompt
    # change, so one arriving unnoticed is a cost nobody chose.
    assert len(list_agent_modules()) == 11


def test_new_agents_have_profiles():
    from agents import rules_ingestion, exception_report, legislative_monitor

    for mod in (rules_ingestion, exception_report, legislative_monitor):
        assert mod.NAME
        assert mod.INSTRUCTIONS
        assert mod.AGENT_PROFILE["tab_label"]
        assert mod.AGENT_PROFILE["tools"]


# --- Web IQ client (offline / honest degradation, no network) ---------------


def test_webiq_unconfigured_by_default(monkeypatch):
    from tools import webiq

    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    monkeypatch.delenv("WEBIQ_BEARER_TOKEN", raising=False)
    assert webiq.is_configured() is False
    assert webiq.runtime_status() == "NEEDS_KEY"


def test_webiq_configured_when_key_present(monkeypatch):
    from tools import webiq

    monkeypatch.setenv("WEBIQ_API_KEY", "test-key-not-real")
    assert webiq.is_configured() is True
    assert webiq.runtime_status() == "READY"
    # header selection prefers the api key
    assert webiq.WebIQConfig.from_env().auth_headers() == {"x-apikey": "test-key-not-real"}


def test_search_ga_source_empty_when_unconfigured(monkeypatch):
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    monkeypatch.delenv("WEBIQ_BEARER_TOKEN", raising=False)
    assert ri.search_ga_source() == []  # no network call when unconfigured


def test_ingest_captured_reports_captured_status():
    result = ri.ingest_ga_jtc(live=False)
    assert result["web_iq_status"] == "captured"
    assert result["config"]["program"] == "GA_JTC"


# --- Date-sensitive rulebook ingestion (extract / compare / apply / log) -----

_SAMPLE_MEMO = (
    "2025 Job Tax Credit Program Designation. "
    "Tier 1 counties necessitate at least 2 net new jobs to be eligible for a credit of $3,500 per net new job. "
    "Tier 2 counties necessitate at least 10 net new jobs to be eligible for a credit of $2,500 per net new job. "
    "Tier 3 counties necessitate only 15 net new jobs to be eligible for a credit of $1,250 per net new job. "
    "Tier 4 counties necessitate at least 25 net new jobs to be eligible for a credit of $750 per net new job. "
    "Job Tax Credit Rankings 2025 | Tier 1 | | 1. Telfair | 13. Treutlen | "
    "| Tier 2 | | 72. Bacon | 78. Lowndes | | Tier 3 | | 119. Chatham | 118. DeKalb |"
)


def _reset_stores():
    ri._APPLIED_RULESETS.clear()
    ri._CHANGELOG.clear()


def test_extract_tier_schedule_from_memo():
    sched = ri.extract_tier_schedule(_SAMPLE_MEMO)
    assert sched["1"] == {"min_new_jobs": 2, "per_job_usd": 3500, "evidence": sched["1"]["evidence"]}
    assert sched["2"]["per_job_usd"] == 2500
    assert sched["3"]["min_new_jobs"] == 15
    assert sched["4"]["per_job_usd"] == 750


def test_extract_county_tiers_from_memo():
    counties = ri.extract_county_tiers(_SAMPLE_MEMO)
    assert counties["Telfair"] == 1
    assert counties["Bacon"] == 2
    assert counties["Chatham"] == 3
    assert counties["DeKalb"] == 3


def test_build_proposals_needs_key_offline(monkeypatch):
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    monkeypatch.delenv("WEBIQ_BEARER_TOKEN", raising=False)
    out = ri.build_proposals("GA", 2025)
    assert out["web_iq_status"] == "NEEDS_KEY"
    assert out["schedule_diff"] == []


def test_apply_is_date_sensitive_and_logs(monkeypatch):
    """Applying 2026 must not touch 2025; both years coexist; changes are logged."""
    _reset_stores()

    def fake_retrieve(state, tax_year):
        # 2026 moves DeKalb from Tier 3 -> Tier 2 vs 2025
        counties = {"Telfair": 1, "Bacon": 2, "Chatham": 3, "DeKalb": 3 if tax_year == 2025 else 2}
        return {
            "state": state, "tax_year": tax_year,
            "source_url": ri._memo_url_for(tax_year), "source_title": "memo",
            "crawled_at": None, "retrieved_at": "2026-06-30",
            "tier_schedule": ri.extract_tier_schedule(_SAMPLE_MEMO),
            "county_tiers": counties, "content_chars": 100,
        }

    monkeypatch.setattr(ri, "retrieve_ruleset", fake_retrieve)

    a25 = ri.apply_ruleset("GA", 2025, confirmed_by="Tester")
    assert a25["tax_year"] == 2025
    assert a25["county_count"] == 4
    # Tier 1 matches the config baseline (2 / 3500) so only Tiers 2-4 log as new.
    assert a25["changes_logged"] == 6

    a26 = ri.apply_ruleset("GA", 2026, confirmed_by="Tester")
    # 2025 rulebook is untouched
    assert ri._APPLIED_RULESETS["GA_JTC:2025"]["county_tiers"]["DeKalb"] == 3
    assert ri._APPLIED_RULESETS["GA_JTC:2026"]["county_tiers"]["DeKalb"] == 2

    years = {y["tax_year"] for y in ri.applied_years("GA")}
    assert years == {2025, 2026}

    log = ri.get_changelog("GA")
    assert len(log) >= 6
    assert log[0]["confirmed_by"] == "Tester"
    _reset_stores()


def test_build_proposals_detects_county_moves(monkeypatch):
    _reset_stores()

    def fake_retrieve(state, tax_year):
        counties = {"Chatham": 3, "DeKalb": 3 if tax_year == 2025 else 2}
        return {
            "state": state, "tax_year": tax_year,
            "source_url": ri._memo_url_for(tax_year), "source_title": "memo",
            "crawled_at": None, "retrieved_at": "2026-06-30",
            "tier_schedule": ri.extract_tier_schedule(_SAMPLE_MEMO),
            "county_tiers": counties, "content_chars": 100,
        }

    monkeypatch.setenv("WEBIQ_API_KEY", "test-key")
    monkeypatch.setattr(ri, "retrieve_ruleset", fake_retrieve)
    ri.apply_ruleset("GA", 2025, confirmed_by="Tester")
    prop = ri.build_proposals("GA", 2026)
    assert prop["web_iq_status"] == "READY"
    moves = {m["county"]: (m["from_tier"], m["to_tier"]) for m in prop["county_moves"]}
    assert moves["DeKalb"] == (3, 2)
    _reset_stores()
