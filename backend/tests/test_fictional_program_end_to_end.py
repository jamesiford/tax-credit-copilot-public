"""A program is added by data, not by code: the fictional `ZZ_DEMO_JTC`, end to end. [ADR-013, F04.7]

Everything about ZZ_DEMO_JTC lives under a temporary rules folder this test builds (`RULES_DIR`): a pack, two year packs and a
registry entry, with synthetic payroll for a made-up state code derived from the committed synthetic fixture. No source file
under `backend/` is touched, and no value is presented as law: every statutory number is fictional and flagged
`_prototype_verify`.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
from pathlib import Path

import pytest

import application.source_ports as source_ports
from application.assessment import assess_client
from application.client_book import programs
from application.commands.run_client_calculation import RunClientCalculationCommand
from tools.pack_validation import validate_all, validate_pack

BACKEND = Path(__file__).resolve().parent.parent
RULES = BACKEND / "rules"
CLIENT = 7777


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _fictional_pack(code: str, state: str, year: int | None) -> dict:
    flag = {"_prototype_verify": True}
    pack = {
        "_prototype_verification": "FICTIONAL demo program for tests. Every value is invented and flagged; it is not law.",
        "rule_pack_version": "0.0.1" if year is None else f"0.0.1+ty{year}",
        "jurisdiction": {"level": "state", "code": state, "name": "Zedland (fictional)"},
        "credit": {"code": code, "name": f"{code} (fictional)", "statutory_citation": "Fictional Code § 0-0-0"},
        "tax_year_convention": {"label": "begins", **flag},
        "filing": {"window": "Fictional filing window", "cycle": "annual", **flag},
        "thresholds": {"minimum_new_jobs": 1, "minimum_hours_per_week_full_time": 30, **flag},
        "benefit": {"amount_per_qualifying_job_usd": 1000, "benefit_period_years": 3, "carryforward_years": 5, "currency": "USD", **flag},
        "one_zero": {
            "min_weekly_hours": 30.0, "min_weekly_wages": 400.0, "wage_basis": "regular", "geographic_granularity": "statewide",
            "pt_aggregation": False, "headcount_unit_field": "Worksite_ID", "entity_combination": "permitted", **flag,
            "wage_floor_basis": {"note": "invented for tests", **flag},
        },
    }
    if year is not None:
        pack["tax_year"] = year
        pack["_year_provenance"] = {"source": "invented for tests", "adr": "ADR-005"}
    return pack


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _zz_payroll() -> list[dict]:
    """The committed synthetic payroll, re-labelled to the made-up state ZZ."""
    rows = []
    with (BACKEND / "data" / "payroll_pay_periods.csv").open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["Worksite_ID"].startswith("GA_") and int(row["Tax_Year"]) in (2024, 2025):
                rows.append({**row, "Worksite_ID": "ZZ_" + row["Worksite_ID"][3:], "Tax_Year": int(row["Tax_Year"]),
                             "Hours_Worked": float(row["Hours_Worked"]), "Gross_Wages": float(row["Gross_Wages"])})
    return rows


@pytest.fixture()
def demo(tmp_path, monkeypatch):
    shipped_before = _tree_digest(RULES)
    rules = tmp_path / "rules"
    shutil.copytree(RULES, rules)
    _write(rules / "zz_demo_jtc.json", _fictional_pack("ZZ_DEMO_JTC", "ZZ", None))
    for year in (2024, 2025):
        _write(rules / "zz_demo_jtc" / f"{year}.json", _fictional_pack("ZZ_DEMO_JTC", "ZZ", year))
    _write(rules / "yy_described_only.json", _fictional_pack("YY_DESCRIBED_ONLY", "YY", None))
    manifest = rules / "registry" / "programs.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for code, state, pack in (("ZZ_DEMO_JTC", "ZZ", "zz_demo_jtc.json"), ("YY_DESCRIBED_ONLY", "YY", "yy_described_only.json")):
        data["programs"].append({"code": code, "name": f"{code} (fictional)", "jurisdiction": {"level": "state", "code": state},
                                 "state": state, "pack_file": pack, "lifecycle": "described",
                                 "engine_profile": {"credit_model": "per_net_new_job", "headcount_model": "one_zero"}})
    manifest.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("RULES_DIR", str(rules))
    rows = _zz_payroll()
    assert rows, "the synthetic fixture should hold Georgia rows to relabel"
    monkeypatch.setattr(source_ports, "load_pay_periods", lambda account_id=None: rows)
    monkeypatch.setattr(source_ports, "payroll_scope", lambda account_id: type("S", (), {"states": ["ZZ"], "tax_years": [2024, 2025]})())
    yield {"rules": rules, "rows": rows}
    assert _tree_digest(RULES) == shipped_before, "the shipped rules folder must not change"


def test_the_fictional_packs_are_valid_flagged_and_the_registry_accepts_them(demo):
    reports = validate_all()
    assert [r.file for r in reports if not r.ok] == []
    zz = [r for r in reports if "zz_demo_jtc" in r.file]
    assert len(zz) == 3 and all(any(i.code == "unverified" for i in r.issues) for r in zz)
    assert validate_pack(demo["rules"] / "zz_demo_jtc" / "2025.json", years_authored=True).ok


def test_the_program_list_shows_it_calculable_for_its_authored_years_and_the_other_described_only(demo):
    rows = {p["program_code"]: p for p in programs()}
    zz, described = rows["ZZ_DEMO_JTC"], rows["YY_DESCRIBED_ONLY"]
    assert zz["calculable"] is True and zz["authored_years"] == [2024, 2025] and zz["placeholder_years"] == [2024, 2025]
    assert described["calculable"] is False and "not inherited" in described["not_calculable_reason"]
    assert rows["GA_JTC"]["authored_years"] == list(range(2019, 2027))


def test_an_assessment_prices_it_and_the_described_program_is_declined_by_name(demo):
    priced = assess_client(CLIENT, demo["rows"], program_code="ZZ_DEMO_JTC", tax_years=[2025])
    assert [c["program_code"] for c in priced["assessed"]] == ["ZZ_DEMO_JTC"] and priced["assessed"][0]["tax_year"] == 2025
    assert priced["states"] == ["ZZ"] and priced["assessed"][0]["status"] != "not_assessed"
    cell = priced["assessed"][0]
    # Priced from the pack's own fictional $1,000 per job over its own threshold, by the unchanged engine.
    assert int(cell["identified_usd"]) == round((cell["net_new_jobs"] - cell["threshold_jobs"]) * 1000) > 0
    declined = assess_client(CLIENT, demo["rows"], program_code="YY_DESCRIBED_ONLY", tax_years=[2025])
    assert declined["assessed"] == []


def test_a_calculation_prices_it_with_the_state_derived_from_payroll(demo, tmp_path):
    from bootstrap import wiring
    from infrastructure.persistence.memory_overrides import InMemoryManualOverrideRepository
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository

    class Writer:
        payload = None

        def write_run(self, payload):
            Writer.payload = payload
            return {k: len(v) for k, v in payload.items() if isinstance(v, list)}

        def validate(self):
            return []

    claims = SqliteClaimRepository(tmp_path / "claims.db")
    original = wiring.get_claim_repository()
    wiring.set_gold_writer(Writer())
    wiring.set_claim_repository(claims)
    wiring.set_override_repository(InMemoryManualOverrideRepository())
    try:
        wiring.get_mediator().send(RunClientCalculationCommand(client_id=CLIENT, tax_year=2025, actor="tests"))
    finally:
        wiring.set_gold_writer(None)
        wiring.set_claim_repository(original)
        wiring.set_override_repository(None)
        claims.close()
    assert Writer.payload is not None and Writer.payload["employee_eligibility"]
    manifest = Writer.payload["run_manifest_row"]
    assert "ZZ_DEMO_JTC" in manifest


def test_an_unregistered_state_and_a_program_with_no_authored_year_are_declined_by_name(demo):
    from application.queries._client_run import ClientRunNotAvailable, resolve_statute

    with pytest.raises(ClientRunNotAvailable, match="no programme maps to state"):
        resolve_statute(account_id=CLIENT, state="QQ", tax_year=2025)
    with pytest.raises(ClientRunNotAvailable, match="YY_DESCRIBED_ONLY is not year-scoped"):
        resolve_statute(account_id=CLIENT, state="YY", tax_year=2025)
