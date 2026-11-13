"""Schema and semantic validation of rule packs. [ADR-013, F04.3-F04.4]

A pass means a pack is well-formed and consistent: never that its values are legally correct.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.pack_validation import schema_version, validate_all, validate_pack

RULES = Path(__file__).resolve().parent.parent / "rules"


def _write(tmp_path: Path, name: str, data: dict) -> Path:
    path = tmp_path / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _base() -> dict:
    return json.loads((RULES / "ga_jtc.json").read_text(encoding="utf-8"))


def _year() -> dict:
    return json.loads((RULES / "ga_jtc" / "2023.json").read_text(encoding="utf-8"))


def _codes(report) -> set[str]:
    return {i.code for i in report.issues if i.severity == "error"}


def test_every_shipped_pack_and_year_pack_validates():
    reports = validate_all()
    assert len(reports) == 18  # ten base packs and eight Georgia year packs
    assert [(r.file, [i.message for i in r.issues if i.severity == "error"]) for r in reports if not r.ok] == []


def test_the_one_documented_exception_is_a_warning_not_a_pass_for_pricing():
    """NY's percentage-of-wages benefit is describable, not priceable: reported, never silently accepted."""
    reports = {Path(r.file).name: r for r in validate_all()}
    assert [i.code for i in reports["ny_excelsior.json"].issues if i.severity == "warning"] == ["unsupported_credit_model"]


def test_the_schema_is_versioned_and_has_an_id():
    schema = json.loads((RULES / "schema" / "rule-pack.schema.json").read_text(encoding="utf-8"))
    assert schema["$id"].endswith("rule-pack.schema.json") and schema_version() == 1


@pytest.mark.parametrize("mutate,expected", [
    (lambda p: p.pop("benefit"), "schema"),
    (lambda p: p["jurisdiction"].update(level="galaxy"), "schema"),
    (lambda p: p.update(rule_pack_version="one"), "schema"),
    (lambda p: p["filing"].update(cycle="whenever"), "schema"),
    (lambda p: p["one_zero"].update(wage_basis="vibes"), "schema"),
    (lambda p: p["one_zero"].update(methodology={"minimum_pay_period_day": 7}), "unsupported_methodology"),
    (lambda p: p["benefit"].pop("amount_per_qualifying_job_usd"), "schema"),
])
def test_each_kind_of_invalid_base_pack_is_reported(tmp_path, mutate, expected):
    pack = _base()
    mutate(pack)
    assert expected in _codes(validate_pack(_write(tmp_path, "ga_jtc.json", pack)))


def test_a_pack_file_must_be_named_for_its_jurisdiction(tmp_path):
    assert "filename" in _codes(validate_pack(_write(tmp_path, "tx_jtc.json", _base())))


@pytest.mark.parametrize("mutate,expected", [
    (lambda p: p.pop("_year_provenance"), "schema"),
    (lambda p: p.update(extends="2022"), "schema"),
    (lambda p: p.pop("one_zero"), "schema"),
    (lambda p: p.update(tax_year=2022), "filename"),
    (lambda p: p["one_zero"].update(thresholds_by_year={"2023": {"min_weekly_hours": 1, "min_weekly_wages": 1}}), "thresholds_by_year"),
])
def test_a_year_pack_is_complete_never_inherited(tmp_path, mutate, expected):
    pack = copy.deepcopy(_year())
    mutate(pack)
    assert expected in _codes(validate_pack(_write(tmp_path, "ga_jtc/2023.json", pack)))


def test_a_percentage_benefit_cannot_be_a_year_pack(tmp_path):
    pack = _year()
    pack["benefit"] = {"benefit_period_years": 1, "amount_per_qualifying_job_pct_of_wages": 0.1}
    assert "unsupported_credit_model" in _codes(validate_pack(_write(tmp_path, "ga_jtc/2023.json", pack)))


def test_a_verified_claim_needs_no_flags_and_a_source(tmp_path):
    pack = _year()
    pack["_verified"] = True
    assert "verified_with_flags" in _codes(validate_pack(_write(tmp_path, "ga_jtc/2023.json", pack)))


def test_unverified_flags_are_carried_into_the_report():
    report = next(r for r in validate_all() if r.file.endswith("ga_jtc.json"))
    assert any(i.code == "unverified" for i in report.issues)


def test_an_unregistered_pack_and_a_duplicate_code_are_errors(tmp_path, monkeypatch):
    import shutil
    rules = tmp_path / "rules"
    shutil.copytree(RULES, rules)
    twin = _base()
    (rules / "ga_twin.json").write_text(json.dumps(twin), encoding="utf-8")
    monkeypatch.setenv("RULES_DIR", str(rules))
    report = next(r for r in validate_all() if r.file.endswith("ga_twin.json"))
    assert {"unregistered", "duplicate_code"} <= _codes(report)
