"""App-owned lookups: resolved in the application, in provider order, never assumed silently. [07]

`PayCodeCategory`, `EntityFiscalYearRules`, `PayFrequency` and `IndustryType` are referenced by the source and are not in
the schema the customer shared. These tests prove the app works with each present, overridden, seeded, empty or absent, that
a statute-affecting fallback is always flagged or blocked, and that an unmapped pay code (the highest risk) is never silent.
"""
from __future__ import annotations

import dataclasses
import json
from datetime import date

import pytest

from application.errors import FiscalRulesMissing, UnmappedPayCodes
from data.lookups import PayCodeResolver, lookup_status, resolve_pay_codes
from data.lookups import store as override_store
from data.lookups.seeds import SeedError, load_seed
from data.lookups.store import GLOBAL_CLIENT, OverrideEntry
from data.source.industry import industry_name
from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
from data.source.to_bcs import frequency_label, projection_controls, source_to_bcs_rows
from infrastructure.persistence.sqlite_lookups import SqliteLookupStore

CANONICAL = {"Regular", "Overtime", "Bonus", "Commission", "Mileage", "Expense_Reimbursement", "Relocation"}


@pytest.fixture(scope="module")
def full():
    return build_synthetic_dataset(SYNTHETIC_CLIENTS[0])


@pytest.fixture
def dataset(full):
    """A small slice: the projection is the subject, not the volume."""
    return dataclasses.replace(full, payroll=full.payroll[:300])


@pytest.fixture
def store():
    previous = override_store.get_store()
    fresh = SqliteLookupStore(":memory:")
    override_store.install(fresh)
    yield fresh
    override_store.install(previous)


def _with_codes(dataset, mapping):
    """The same payroll under different pay-code text (`pay_code_id` -> text)."""
    codes = [dataclasses.replace(c, pay_code=mapping.get(c.pay_code_id, c.pay_code)) for c in dataset.pay_codes]
    return dataclasses.replace(dataset, pay_codes=codes)


def _override(client_id, key, value, kind="code", lookup="pay_code_category", **extra):
    return OverrideEntry(lookup, client_id, kind, key, value, "tester@example.com", basis="test", **extra)


# ------------------------------------------------------------------ pay codes: the five states of the lookup

def test_seeded_a_known_code_resolves_by_the_seed_and_says_it_is_inferred(dataset):
    resolved, report = resolve_pay_codes(dataset)
    assert resolved[dataset.pay_codes[0].pay_code_id] == "Regular" and not report.unmapped_codes
    assert report.inferred_codes == len(dataset.pay_codes), "a seeded answer is flagged inferred, never presented as fact"
    assert report.providers == {"seed": len(dataset.pay_codes)}


def test_overridden_the_override_wins_over_the_seed_and_a_client_beats_the_global_default(dataset, store):
    code = dataset.pay_codes[0]
    store.put(_override(GLOBAL_CLIENT, "REG", "Bonus"))
    store.put(_override(dataset.account.account_id, "REG", "Overtime"))
    assert PayCodeResolver(dataset.account.account_id).resolve("reg")[:2] == ("Overtime", "override")
    assert PayCodeResolver(999).resolve("REG")[:2] == ("Bonus", "override"), "another client sees the global default only"
    resolved, report = resolve_pay_codes(dataset)
    assert resolved[code.pay_code_id] == "Overtime" and report.providers["override"] >= 1


def test_a_category_id_mapping_applies_when_the_customer_supplies_one(dataset, store):
    odd = dataclasses.replace(dataset.pay_codes[0], pay_code="XQ7", pay_code_category_id=42)
    store.put(_override(dataset.account.account_id, "42", "Regular", kind="category"))
    resolved, _ = resolve_pay_codes(dataclasses.replace(dataset, pay_codes=[odd, *dataset.pay_codes[1:]]))
    assert resolved[odd.pay_code_id] == "Regular", "most specific wins: code, then category, client before global"


def test_empty_and_absent_stores_fall_to_the_seed_never_to_an_error(dataset):
    override_store.install(None)
    try:
        assert resolve_pay_codes(dataset)[1].unmapped_codes == ()
    finally:
        from bootstrap.lookup_wiring import install_lookup_store

        install_lookup_store()


# ------------------------------------------------------------------ unmapped pay codes are never silent

def test_an_unmapped_code_under_assume_passes_through_and_is_flagged_counted_and_listed(dataset, monkeypatch):
    monkeypatch.setenv("PAY_CODE_POLICY", "assume")
    odd = _with_codes(dataset, {dataset.pay_codes[0].pay_code_id: "RG01"})
    rows = source_to_bcs_rows(odd)
    assert rows and all(r["_Pay_Code_Unmapped"] and r["Pay_Code"] == "RG01" for r in rows), "the code is kept so the whitelist decides"
    controls = projection_controls(odd, rows)["pay_codes"]
    assert controls["policy"] == "assume" and controls["unmapped_codes"] == ["RG01"] and controls["rows_unmapped"] == len(rows)
    assert controls["distinct_unmapped"] == 1


def test_an_unmapped_code_under_strict_blocks_the_calculation_with_the_codes_listed(dataset, monkeypatch):
    monkeypatch.setenv("PAY_CODE_POLICY", "strict")
    odd = _with_codes(dataset, {dataset.pay_codes[0].pay_code_id: "RG01"})
    with pytest.raises(UnmappedPayCodes) as caught:
        source_to_bcs_rows(odd)
    assert caught.value.codes == ("RG01",) and "RG01" in str(caught.value) and "PAY_CODE_POLICY" in caught.value.remedy
    assert caught.value.dependency == "lookup:pay_code_category"


def test_customer_classified_data_is_strict_and_does_not_trust_the_seed(dataset, monkeypatch):
    """The seed is a convention for generated data. On customer data nothing is mapped until somebody maps it."""
    monkeypatch.setenv("DATA_CLASSIFICATION", "customer")
    with pytest.raises(UnmappedPayCodes):
        source_to_bcs_rows(dataset)


def test_customer_data_runs_once_the_codes_are_mapped_by_an_override(dataset, store, monkeypatch):
    monkeypatch.setenv("DATA_CLASSIFICATION", "customer")
    for code in dataset.pay_codes:
        store.put(_override(dataset.account.account_id, code.pay_code, "Regular"))
    rows = source_to_bcs_rows(dataset)
    assert rows and not any(r["_Pay_Code_Unmapped"] for r in rows)


def test_a_statute_affecting_fallback_is_never_used_without_a_flag(dataset, monkeypatch):
    """Every row either carries a canonical category or says why it does not."""
    monkeypatch.setenv("PAY_CODE_POLICY", "assume")
    mixed = _with_codes(dataset, {dataset.pay_codes[1].pay_code_id: "ZZ9"})
    rows = source_to_bcs_rows(dataset) + source_to_bcs_rows(mixed)
    for r in rows:
        assert r["Pay_Code"] in CANONICAL or r["_Pay_Code_Unmapped"] or r["_Pay_Code_Defaulted"], r


def test_dangling_and_missing_pay_code_ids_degrade_flagged_and_never_drop_a_row(dataset):
    ghost = [dataclasses.replace(p, pay_code_id=999999 if i % 2 else None) for i, p in enumerate(dataset.payroll)]
    broken = dataclasses.replace(dataset, payroll=ghost)
    rows = source_to_bcs_rows(broken)
    assert len(rows) == len(dataset.payroll) and all(r["Pay_Code"] == "Regular" and r["_Pay_Code_Defaulted"] for r in rows)
    assert projection_controls(broken, rows)["pay_codes"]["rows_with_no_pay_code_treated_as_regular"] == len(rows)


# ------------------------------------------------------------------ the override store: tenant binding, audit, history

def test_overrides_are_tenant_bound_and_history_is_kept(store):
    store.put(_override(5, "RG01", "Regular"))
    store.put(_override(6, "RG01", "Bonus"))
    store.put(_override(GLOBAL_CLIENT, "OT1", "Overtime"))
    assert {(e.client_id, e.key) for e in store.entries("pay_code_category", 5)} == {(5, "RG01"), (0, "OT1")}, "never client 6's row"
    store.put(_override(5, "RG01", "Commission"))
    assert [e.value for e in store.entries("pay_code_category", 5) if e.key == "RG01"] == ["Commission"], "one live row per key"
    assert [a["action"] for a in store.audit("pay_code_category") if a["key_value"] == "RG01" and a["client_id"] == 5] == ["put", "put"]


def test_a_removal_closes_the_row_and_is_audited_not_deleted(store):
    store.put(_override(5, "RG01", "Regular"))
    assert store.remove("pay_code_category", 5, "code", "RG01", "tester@example.com") is True
    assert store.entries("pay_code_category", 5) == [] and store.remove("pay_code_category", 5, "code", "RG01", "x") is False
    assert [a["action"] for a in store.audit()] == ["put", "remove"]
    assert store._connect().execute("SELECT COUNT(*) FROM lookup_override").fetchone()[0] == 1, "closed, not deleted"


def test_effective_dates_are_honoured(store):
    store.put(_override(5, "RG01", "Regular", effective_from=date(2999, 1, 1)))
    assert PayCodeResolver(5).resolve("RG01")[0] is None, "not yet effective"


# ------------------------------------------------------------------ fiscal rules

def _lakehouse(monkeypatch, rules):
    from infrastructure.payroll import fiscal_source

    monkeypatch.setattr("tools.fabric_source.active_data_source", lambda: "lakehouse")
    monkeypatch.setattr(fiscal_source, "_fiscal_rules", lambda account_id: rules)
    return fiscal_source


def _rule(account=7, begin="2023-07-01", end="2024-06-30"):
    return _override(account, "default", json.dumps({"fiscal_year_begin": begin, "fiscal_year_end": end}), kind="rule", lookup="entity_fiscal_year_rules")


@pytest.mark.parametrize("source_rules", [None, []], ids=["unreadable", "read-and-empty"])
def test_no_source_rule_and_no_override_is_an_assumed_calendar_year_flagged(monkeypatch, source_rules):
    window = _lakehouse(monkeypatch, source_rules).client_fiscal_window(7, 2023, "begins")
    assert window.assumed and window.basis == "assumed_calendar"


def test_an_override_supplies_the_clients_own_window_and_says_where_it_came_from(monkeypatch, store):
    store.put(_rule())
    window = _lakehouse(monkeypatch, []).client_fiscal_window(7, 2023, "begins")
    assert not window.assumed and (window.begin, window.end) == (date(2023, 7, 1), date(2024, 6, 30))
    assert "app-owned override" in window.note


def test_a_clients_rule_comes_before_the_global_default(monkeypatch, store):
    store.put(_rule(GLOBAL_CLIENT, "2023-01-01", "2023-12-31"))
    store.put(_rule(7, "2023-10-01", "2024-09-30"))
    window = _lakehouse(monkeypatch, None).client_fiscal_window(7, 2023, "begins")
    assert window.begin == date(2023, 10, 1)


def test_strict_fiscal_policy_blocks_instead_of_assuming(monkeypatch):
    monkeypatch.setenv("FISCAL_RULES_POLICY", "strict")
    with pytest.raises(FiscalRulesMissing) as caught:
        _lakehouse(monkeypatch, []).client_fiscal_window(7, 2023, "begins")
    assert "FISCAL_RULES_POLICY" in caught.value.remedy and caught.value.dependency == "lookup:entity_fiscal_year_rules"


def test_the_source_rule_still_wins_over_an_override(monkeypatch, store):
    store.put(_rule())
    source = [dataclasses.replace(r, fiscal_year_begin=date(2023, 4, 1), fiscal_year_end=date(2024, 3, 31))
              for r in build_synthetic_dataset(SYNTHETIC_CLIENTS[0]).fiscal_year_rules[:1]]
    assert _lakehouse(monkeypatch, source).client_fiscal_window(7, 2023, "begins").begin == date(2023, 4, 1)


def test_the_window_object_with_its_assumed_flag_reaches_the_resolver_and_the_assessment(monkeypatch, pay_period_rows):
    from application.assessment import assess_client
    from infrastructure.payroll import fiscal_source

    window = fiscal_source.fiscal_window_for_state_year(1001, "GA", 2024)
    assert window.assumed and fiscal_source.window_for_state_year(1001, "GA", 2024) == (window.begin, window.end)
    cells = assess_client(1001, pay_period_rows, program_code="GA_JTC", tax_years=[2024])["assessed"]
    assert cells and all(c["fiscal_window"]["assumed"] and "calendar" in c["fiscal_window"]["note"].lower() for c in cells)


def test_a_typed_dependency_failure_is_not_swallowed_by_the_window_resolver(monkeypatch):
    monkeypatch.setenv("FISCAL_RULES_POLICY", "strict")
    fiscal_source = _lakehouse(monkeypatch, [])
    with pytest.raises(FiscalRulesMissing):
        fiscal_source.fiscal_window_for_state_year(7, "GA", 2023)


# ------------------------------------------------------------------ pay frequency and industry

@pytest.mark.parametrize(("days", "label"), [(1, "daily"), (7, "weekly"), (14, "biweekly"), (15, "semimonthly"), (16, "semimonthly"), (30, "monthly"), (45, "45d")])
def test_the_pay_frequency_label_is_read_from_the_measured_span(days, label):
    assert frequency_label(date(2024, 1, 1), date.fromordinal(date(2024, 1, 1).toordinal() + days - 1)) == label


def test_the_row_carries_a_derived_label_and_the_raw_id_as_lineage_only(dataset):
    row = source_to_bcs_rows(dataset)[0]
    assert row["Pay_Frequency"] == frequency_label(date.fromisoformat(row["Pay_Period_Start"]), date.fromisoformat(row["Pay_Period_End"]))
    assert "_Source_Pay_Frequency_Id" in row


def test_a_missing_pay_frequency_table_changes_nothing(dataset):
    without = dataclasses.replace(dataset, pay_frequencies=[])
    assert [r["Pay_Frequency"] for r in source_to_bcs_rows(without)] == [r["Pay_Frequency"] for r in source_to_bcs_rows(dataset)]


def test_industry_is_display_only_seeded_inferred_and_never_guessed():
    assert industry_name(44) == "Retail" and industry_name(9999) is None and industry_name(None) is None and industry_name("x") is None
    assert load_seed("industry_type").inferred is True


# ------------------------------------------------------------------ seeds and status

def test_a_seed_must_carry_its_provenance(tmp_path):
    (tmp_path / "thing.v1.json").write_text(json.dumps({"lookup": "thing", "version": 1, "entries": {}}), encoding="utf-8")
    with pytest.raises(SeedError, match="provenance"):
        load_seed("thing", str(tmp_path))


def test_the_newest_seed_version_wins(tmp_path):
    base = {"lookup": "thing", "authored_by": "t", "authored_on": "2026-01-01", "basis": "b", "inferred": False}
    for version, value in ((1, "old"), (3, "new"), (2, "mid")):
        (tmp_path / f"thing.v{version}.json").write_text(json.dumps({**base, "version": version, "entries": {"k": value}}), encoding="utf-8")
    assert load_seed("thing", str(tmp_path)).entries["k"] == "new"


def test_status_lists_every_lookup_with_its_provider_and_what_it_affects(store):
    rows = {r["lookup"]: r for r in lookup_status(account_id=5)}
    assert set(rows) == {"pay_code_category", "entity_fiscal_year_rules", "pay_frequency", "industry_type"}
    assert rows["pay_code_category"]["status"] == "seed v1 (inferred)" and rows["pay_code_category"]["statute_affecting"]
    assert rows["entity_fiscal_year_rules"]["status"].startswith("missing") and rows["entity_fiscal_year_rules"]["if_missing"]
    assert lookup_status({"entity_fiscal_year_rules": True})[1]["status"] == "source"
    store.put(_override(5, "RG01", "Regular"))
    assert next(r for r in lookup_status(account_id=5) if r["lookup"] == "pay_code_category")["status"] == "override"


def test_status_on_customer_data_says_pay_codes_are_missing_until_authored(monkeypatch):
    monkeypatch.setenv("DATA_CLASSIFICATION", "customer")
    pay = next(r for r in lookup_status() if r["lookup"] == "pay_code_category")
    assert pay["status"] == "missing (strict)" and "unmapped pay code" in pay["if_missing"]


# ------------------------------------------------------------------ the CLI

@pytest.fixture
def cli(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    monkeypatch.setenv("LOOKUP_STORE", "sqlite")
    monkeypatch.setenv("OPERATIONAL_DB", str(tmp_path / "ops.db"))
    path = Path(__file__).resolve().parents[2] / "scripts" / "lookups.py"
    spec = importlib.util.spec_from_file_location("lookups_cli", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def run(*argv):
        code = module.main(list(argv))
        return code, capsys.readouterr().out

    return run, tmp_path


def test_the_cli_imports_shows_exports_diffs_and_audits(cli):
    run, tmp = cli
    source = tmp / "codes.csv"
    source.write_text("kind,key,value\ncode,rg01,Regular\ncode,xo2,Overtime\n", encoding="utf-8")
    code, out = run("import", "pay_code_category", "--account", "5", str(source), "--by", "me@example.com", "--basis", "from the customer", "--dry-run")
    assert code == 0 and "added 2" in out and "written" not in out
    code, out = run("import", "pay_code_category", "--account", "5", str(source), "--by", "me@example.com", "--basis", "from the customer")
    assert code == 0 and "written" in out
    assert "RG01" in run("show", "pay_code_category", "--account", "5")[1]
    source.write_text("kind,key,value\ncode,rg01,Bonus\n", encoding="utf-8")
    assert "changed 1" in run("diff", "pay_code_category", "--account", "5", str(source))[1]
    exported = tmp / "out.csv"
    run("export", "pay_code_category", "--account", "5", "--out", str(exported))
    assert "RG01,Regular" in exported.read_text(encoding="utf-8")
    audit = run("audit", "pay_code_category")[1]
    assert audit.count("me@example.com") == 2 and "from the customer" in audit


def test_the_cli_refuses_a_bad_file_a_missing_scope_and_a_store_that_is_off(cli, monkeypatch):
    run, tmp = cli
    bad = tmp / "bad.csv"
    bad.write_text("nonsense\n1\n", encoding="utf-8")
    assert run("import", "pay_code_category", "--account", "5", str(bad), "--by", "x")[0] == 2
    assert run("import", "pay_code_category", str(bad), "--by", "x")[0] == 2, "an import names exactly one of --account and --global"
    assert run("import", "wages", "--account", "5", str(bad), "--by", "x")[0] == 2
    monkeypatch.setenv("LOOKUP_STORE", "none")
    ok = tmp / "ok.csv"
    ok.write_text("kind,key,value\ncode,a,Regular\n", encoding="utf-8")
    assert run("import", "pay_code_category", "--account", "5", str(ok), "--by", "x")[0] == 2


def test_the_fiscal_rule_file_is_validated_before_anything_is_written(cli):
    run, tmp = cli
    rules = tmp / "rules.json"
    rules.write_text(json.dumps({"default": {"fiscal_year_begin": "2023-07-01"}}), encoding="utf-8")
    assert run("import", "entity_fiscal_year_rules", "--account", "5", str(rules), "--by", "x")[0] == 2
    rules.write_text(json.dumps({"default": {"fiscal_year_begin": "2023-07-01", "fiscal_year_end": "2024-06-30"}}), encoding="utf-8")
    assert run("import", "entity_fiscal_year_rules", "--account", "5", str(rules), "--by", "x")[0] == 0
