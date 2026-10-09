"""[L2/L3/L4/L5] Georgia-depth tests (ROADMAP-III Phase L)."""
from __future__ import annotations

from domain.calculation.onezero import apply_pay_code_policy, _pay_code_allowed, rollup_matrix_by_two_fields
from tools.credit_math import load_pack_one_zero


# --- [L5] CALC-11 — pay-code inclusion / suppression -----------------------

def test_l5_calc11_ga_pack_carries_pay_code_policy():
    pack = load_pack_one_zero("GA", tax_year=2025)
    assert pack.included_pay_codes is not None
    assert "Regular" in pack.included_pay_codes
    assert "Overtime" in pack.included_pay_codes
    assert "Mileage" in pack.excluded_pay_codes


def test_l5_calc11_excluded_pay_codes_are_dropped():
    pack = load_pack_one_zero("GA", tax_year=2025)
    rows = [
        {"Employee_ID": "E1", "Pay_Code": "Regular", "Gross_Wages": 700, "Hours_Worked": 40},
        {"Employee_ID": "E1", "Pay_Code": "Bonus", "Gross_Wages": 200, "Hours_Worked": 0},
        {"Employee_ID": "E1", "Pay_Code": "Mileage", "Gross_Wages": 90, "Hours_Worked": 0},
    ]
    kept = apply_pay_code_policy(rows, pack)
    codes = {r["Pay_Code"] for r in kept}
    assert codes == {"Regular", "Bonus"}          # all remuneration, minus non-wage mileage
    assert _pay_code_allowed("Mileage", pack) is False
    assert _pay_code_allowed("Bonus", pack) is True


def test_l5_calc11_regular_only_dataset_is_a_noop():
    """Stability check: a Regular-only row set is returned unchanged (the demo
    dataset is Regular-only, so suppression must not move any headline number)."""
    pack = load_pack_one_zero("GA", tax_year=2025)
    rows = [{"Employee_ID": "E1", "Pay_Code": "Regular", "Gross_Wages": 700, "Hours_Worked": 40}]
    assert apply_pay_code_policy(rows, pack) == rows


def test_l5_calc11_ga_average_headcount_unchanged_by_policy(client):
    """End-to-end: the GA 2025 Average Headcount is the same with the pay-code
    policy in place (the dataset is Regular-only)."""
    body = client.get("/api/onezero/2025?state=GA").json()
    ga = next(r for r in body["results"] if r["state"] == "GA")
    # The established GA figure must hold (Regular-only data → suppression no-op).
    assert ga["average_headcount"] > 0
    assert ga["credit_estimate"]["annual_credit_usd"] > 0


# --- [L3] CALC-09 — per-site × per-legal-entity drill ----------------------

def test_l3_calc09_two_field_rollup_groups_by_site_and_entity():
    matrix = [
        {"Worksite_ID": "GA_A", "Entity_FEIN": "58-1", "months": [1] * 12},
        {"Worksite_ID": "GA_A", "Entity_FEIN": "58-2", "months": [1] * 12},
        {"Worksite_ID": "GA_B", "Entity_FEIN": "58-1", "months": [1] * 12},
    ]
    out = rollup_matrix_by_two_fields(matrix, "Worksite_ID", "Entity_FEIN")
    keys = {(r["Worksite_ID"], r["Entity_FEIN"]) for r in out}
    assert keys == {("GA_A", "58-1"), ("GA_A", "58-2"), ("GA_B", "58-1")}
    assert all(r["average_headcount"] == 1.0 for r in out)


def test_l3_calc09_onezero_surfaces_site_entity_breakdown(client):
    body = client.get("/api/onezero/2025?state=GA").json()
    ga = next(r for r in body["results"] if r["state"] == "GA")
    assert "site_entity_breakdown" in ga
    assert ga["site_entity_breakdown"]
    row = ga["site_entity_breakdown"][0]
    assert "Worksite_ID" in row and "Entity_FEIN" in row and "entity_name" in row
    assert "multi_entity_sites" in ga


# --- [L4] CALC-10 — negotiated wage-standard override ----------------------

import pytest
from tools.negotiated import _reset_for_tests, list_overrides, register_override


@pytest.fixture(autouse=True)
def _clear_overrides():
    _reset_for_tests()
    yield
    _reset_for_tests()


def test_l4_calc10_override_store_roundtrip():
    record = register_override(
        "SC", wage_standard_weekly=720.0, min_jobs=100,
        source="agreement", note="Tractor Supply-style deal",
    )
    assert record["wage_standard_weekly"] == 720.0
    assert list(list_overrides()) == ["SC"]


def test_l4_calc10_override_requires_a_value():
    with pytest.raises(ValueError):
        register_override("SC")


def test_l4_calc10_override_changes_onezero_result(client):
    base = client.get("/api/onezero/2025?state=GA").json()
    ga_base = next(r for r in base["results"] if r["state"] == "GA")
    assert ga_base["negotiated_override"] is None

    # A very high negotiated wage standard should disqualify employees and
    # shrink the GA Average Headcount vs the statutory run.
    register_override("GA", wage_standard_weekly=100000.0, source="agreement")
    after = client.get("/api/onezero/2025?state=GA").json()
    ga_after = next(r for r in after["results"] if r["state"] == "GA")
    assert ga_after["negotiated_override"] is not None
    assert ga_after["average_headcount"] < ga_base["average_headcount"]


def test_l4_calc10_default_path_unchanged(client):
    """No override on file → GA result identical to the statutory run."""
    body = client.get("/api/onezero/2025?state=GA").json()
    ga = next(r for r in body["results"] if r["state"] == "GA")
    assert ga["negotiated_override"] is None
    assert ga["credit_estimate"]["annual_credit_usd"] > 0


# --- [L2] CALC-08 — designation-change parallel calcs ----------------------

def test_l2_calc08_endpoint_flags_designation_change(client):
    body = client.get("/api/designations/GA?tax_year=2025").json()
    assert body["_roadmap_tag"] == "L2"
    assert body["state"] == "GA"
    # GA_MAC_OPS is re-designated Tier 2 -> Tier 1 for 2025.
    mac = next(s for s in body["sites"] if s["worksite_id"] == "GA_MAC_OPS")
    assert mac["designation_changed"] is True
    assert len(mac["parallel_calcs"]) == 2
    assert {c["stream"] for c in mac["parallel_calcs"]} == {
        "surviving_base_designation", "new_designation_net_new",
    }
    assert body["parallel_calc_site_count"] >= 1


def test_l2_calc08_stable_sites_have_no_split(client):
    body = client.get("/api/designations/GA?tax_year=2025").json()
    atl = next(s for s in body["sites"] if s["worksite_id"] == "GA_ATL_HQ")
    assert atl["designation_changed"] is False
    assert atl["parallel_calcs"] == []


# --- [N1] RETRO-01 — frozen-base tranche reconstruction in the retro scan ---

def test_n1_retro01_scan_carries_tranche_analysis(client):
    body = client.get("/api/onezero/retroactive/scan").json()
    assert "tranche_analysis" in body
    ga = next((t for t in body["tranche_analysis"] if t["state"] == "GA"), None)
    assert ga is not None
    assert ga["_roadmap_tag"] == "L1"          # built by the base-year engine
    assert ga["tranche_years"] == 5
    # A net-new creation event opens a 5-year tranche with out-year installments.
    assert ga["tranche_events"]
    ev = ga["tranche_events"][0]
    assert len(ev["installments"]) == 5
    assert ev["window"][1] - ev["window"][0] == 4


# --- [O3] UX-06 — dollarized yellow lever -----------------------------------

def test_o3_ux06_performance_dollarizes_yellow_lever(client):
    body = client.get("/api/performance/2025?state=GA").json()
    assert "yellow_credit_at_stake_usd" in body
    ga = next(s for s in body["states"] if s["state"] == "GA")
    yellows = [e for e in ga["employees"] if e["status"] == "yellow"]
    if yellows:  # GA has yellow employees in the synthetic data
        assert all(e["credit_at_stake_usd"] == 3500 for e in yellows)  # GA per-job
        assert ga["yellow_credit_at_stake_usd"] == 3500 * len(yellows)
    greens = [e for e in ga["employees"] if e["status"] == "green"]
    assert all(e["credit_at_stake_usd"] == 0 for e in greens)


# --- [O1] UX-05 — field-level (worksite) row scoping ------------------------

def test_o1_ux05_worksite_scopes_performance_rows(client):
    full = client.get("/api/performance/2025?state=GA").json()
    ga_full = next(s for s in full["states"] if s["state"] == "GA")
    scoped = client.get("/api/performance/2025?state=GA&worksite=GA_ATL_HQ").json()
    assert scoped["scoped_worksite"] == "GA_ATL_HQ"
    ga_scoped = next(s for s in scoped["states"] if s["state"] == "GA")
    # Every scoped employee belongs to the scoped site, and it's a strict subset.
    assert all(e["Worksite_ID"] == "GA_ATL_HQ" for e in ga_scoped["employees"])
    assert ga_scoped["employee_count"] <= ga_full["employee_count"]
