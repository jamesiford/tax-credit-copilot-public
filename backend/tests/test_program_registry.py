"""The program registry: programs as data, with the old dictionaries kept as views. [ADR-013, F04.1-F04.2]"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from application.client_book import programs
from domain.programs import RegistryError
from tools import credit_math
from tools.program_registry import load_registry, parse_registry

RULES = Path(__file__).resolve().parent.parent / "rules"

#: What `credit_math` hardcoded before the registry. Literal on purpose: a registry edit must not move it silently.
OLD_STATE_TO_PACK = {
    "GA": "ga_jtc.json", "NY": "ny_excelsior.json", "SC": "sc_jtc.json", "NC": "nc_jtec.json", "TN": "tn_jtc.json",
    "FL": "fl_qti.json", "OH": "oh_jctc.json", "CO": "co_ez.json", "VA": "va_mbjf.json",
}
OLD_PROGRAM_CODE_TO_PACK = {
    "GA_JTC": "ga_jtc.json", "NY_EXCELSIOR": "ny_excelsior.json", "SC_JTC": "sc_jtc.json", "NC_JTEC": "nc_jtec.json",
    "TN_JTC": "tn_jtc.json", "FL_QTI": "fl_qti.json", "OH_JCTC": "oh_jctc.json", "CO_EZ": "co_ez.json",
    "VA_MBJF": "va_mbjf.json",
}


def _entry(**overrides):
    base = {"code": "XX_TEST", "name": "Test", "jurisdiction": {"level": "state", "code": "XX"}, "state": "XX",
            "pack_file": "ga_jtc.json", "lifecycle": "described"}
    base.update(overrides)
    return base


def _parse(entries, tmp_path=RULES):
    text = json.dumps({"schema_version": 1, "programs": entries})
    return parse_registry(text, Path("programs.json"), tmp_path)


def test_the_old_dictionary_names_are_views_equal_to_what_they_replaced():
    assert credit_math.STATE_TO_PACK == OLD_STATE_TO_PACK
    assert credit_math.PROGRAM_CODE_TO_PACK == OLD_PROGRAM_CODE_TO_PACK
    assert list(credit_math.PROGRAM_CODE_TO_PACK) == list(OLD_PROGRAM_CODE_TO_PACK)
    assert credit_math.STATE_TO_PACK.get("TX") is None and "GA" in credit_math.STATE_TO_PACK


def test_the_program_list_flags_and_authored_years_are_what_they_were():
    rows = {p["program_code"]: p for p in programs()}
    assert sorted(rows) == sorted(OLD_PROGRAM_CODE_TO_PACK)
    assert rows["GA_JTC"]["authored_years"] == list(range(2019, 2027))
    assert rows["GA_JTC"]["placeholder_years"] == [2026] and rows["GA_JTC"]["calculable"] is True
    assert [c for c, p in rows.items() if p["calculable"]] == ["GA_JTC"]


def test_federal_programs_are_first_class_entries_but_not_in_the_state_views():
    registry = load_registry()
    federal = registry.federal()
    assert [e.code for e in federal] == ["FED_WOTC"] and federal[0].state is None
    assert "FED_WOTC" not in credit_math.PROGRAM_CODE_TO_PACK
    assert credit_math.load_pack_one_zero("FED_WOTC") is not None


def test_every_shipped_pack_is_registered_and_agrees_with_its_entry():
    registry = load_registry()
    on_disk = {p.name for p in RULES.glob("*.json")}
    assert on_disk == {e.pack_file for e in registry.entries}
    for entry in registry.entries:
        pack = json.loads((RULES / entry.pack_file).read_text(encoding="utf-8"))
        assert pack["credit"]["code"] == entry.code and pack["credit"]["name"] == entry.name
        assert pack["jurisdiction"]["level"] == entry.level and pack["jurisdiction"]["code"] == entry.jurisdiction_code


def test_calculable_is_derived_from_authored_years_never_typed():
    registry = load_registry()
    ga = registry.get("ga_jtc")
    assert ga.lifecycle == "described" and ga.status([2023]) == "calculable" and ga.status([]) == "described"
    with pytest.raises(RegistryError, match="derived from authored year packs"):
        _parse([_entry(lifecycle="calculable")])


@pytest.mark.parametrize("entry,message", [
    (_entry(code=None), "missing code"),
    (_entry(jurisdiction={"level": "galaxy", "code": "XX"}), "jurisdiction.level"),
    (_entry(state=None), "needs a state"),
    (_entry(jurisdiction={"level": "federal", "code": "US"}), "no state key"),
    (_entry(lifecycle="live"), "lifecycle must be one of"),
    (_entry(pack_file="nope.json"), "not found"),
    (_entry(engine_profile={"credit_model": "pct_of_wages"}), "needs engine work"),
    (_entry(engine_profile={"headcount_model": "fte"}), "needs engine work"),
])
def test_an_unusable_entry_is_refused_naming_the_entry_and_field(entry, message):
    with pytest.raises(RegistryError, match=message):
        _parse([entry])


def test_a_duplicate_code_and_a_bad_file_are_refused():
    with pytest.raises(RegistryError, match="listed twice"):
        _parse([_entry(), _entry()])
    with pytest.raises(RegistryError, match="not valid JSON"):
        parse_registry("{", Path("programs.json"), RULES)
    with pytest.raises(RegistryError, match="schema_version"):
        parse_registry("{}", Path("programs.json"), RULES)


def test_retired_programs_leave_the_views_but_stay_in_the_registry(tmp_path, monkeypatch):
    rules = tmp_path / "rules"
    shutil.copytree(RULES, rules)
    manifest = rules / "registry" / "programs.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for e in data["programs"]:
        if e["code"] == "VA_MBJF":
            e["lifecycle"] = "retired"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("RULES_DIR", str(rules))
    assert "VA_MBJF" not in credit_math.PROGRAM_CODE_TO_PACK and "VA" not in credit_math.STATE_TO_PACK
    assert load_registry().get("VA_MBJF").lifecycle == "retired"
    with pytest.raises(ValueError, match="unknown program code"):
        credit_math.resolve_statutory_floors("VA_MBJF", 2024)


def test_rules_dir_and_registry_file_can_be_pointed_elsewhere(tmp_path, monkeypatch):
    rules = tmp_path / "elsewhere"
    shutil.copytree(RULES, rules)
    custom = tmp_path / "custom-programs.json"
    shutil.move(str(rules / "registry" / "programs.json"), custom)
    monkeypatch.setenv("RULES_DIR", str(rules))
    with pytest.raises(RegistryError, match="not found"):
        load_registry()
    monkeypatch.setenv("PROGRAM_REGISTRY_FILE", str(custom))
    assert load_registry().source == custom.resolve() and credit_math.authored_years("ga_jtc.json")


def test_a_state_can_hold_several_programs_and_the_first_is_the_default():
    registry = _parse([_entry(code="XX_FIRST"), _entry(code="XX_SECOND", pack_file="sc_jtc.json"), _entry(code="YY_ONE", state="YY")])
    assert [e.code for e in registry.for_state("xx")] == ["XX_FIRST", "XX_SECOND"]
    assert registry.state_to_pack()["XX"] == "ga_jtc.json" and registry.for_state("ZZ") == ()


def test_programs_for_state_and_program_for_code_read_the_live_registry_and_skip_retired(tmp_path, monkeypatch):
    from tools.program_registry import program_for_code, programs_for_state

    assert [e.code for e in programs_for_state("GA")] == ["GA_JTC"] and program_for_code("ga_jtc").state == "GA"
    assert program_for_code("NOPE") is None
    rules = tmp_path / "rules"
    shutil.copytree(RULES, rules)
    manifest = rules / "registry" / "programs.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for e in data["programs"]:
        if e["code"] == "VA_MBJF":
            e["lifecycle"] = "retired"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("RULES_DIR", str(rules))
    assert programs_for_state("VA") == () and program_for_code("VA_MBJF") is None
