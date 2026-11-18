"""The Python side of the data map: same file, same rules as the .NET loader. [R2.3]"""
import json
import re
from pathlib import Path

import pytest

import data_map
from data_map_load import DataMapError, parse

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = (ROOT / "docs" / "data" / "data-map.json").read_bytes()


def _edit(mutate) -> bytes:
    doc = json.loads(SHIPPED)
    mutate(doc)
    return json.dumps(doc).encode()


def test_the_backend_copy_is_the_shipped_file():
    assert data_map.DEFAULT_FILE.read_bytes() == SHIPPED


def test_accessors_resolve_the_shipped_names_and_refuse_an_unknown_table():
    names = data_map.Names(data_map.default_map())
    assert names.ops.run_manifest == "tcc_ops.run_manifest"
    assert names.gold("unit_year_master") == "tcc_gold.unit_year_master"
    with pytest.raises(DataMapError, match=r"warehouse\.tables\.ops\.nope is not a known key"):
        names.ops.nope


def test_a_renamed_map_changes_every_resolved_name(tmp_path):
    def rename(doc):
        doc["warehouse"]["schemas"] = {"gold": "g1", "ops": "o1"}
        doc["warehouse"]["tables"]["ops.run_manifest"]["table"] = "runs"

    path = tmp_path / "map.json"
    path.write_bytes(_edit(rename))
    names = data_map.Names(data_map.load(str(path)))
    assert names.ops.run_manifest == "o1.runs"
    assert names.gold.unit_year_master == "g1.unit_year_master"
    assert data_map.load(str(path)).source == "file"


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda d: d.update(version=2), "version must be 1"),
        (lambda d: d["warehouse"]["schemas"].update(gold="tcc_ops"), "must differ"),
        (lambda d: d["lakehouse"]["tables"]["Payroll"].update(table="Pay]roll"), "not a plain identifier"),
        (lambda d: d["warehouse"]["tables"]["ops.run_batch_item"].update(table="run_batch"), "already mapped"),
        (lambda d: d["warehouse"]["tables"]["ops.run_manifest"]["columns"]["run_id"].update(column="run_key"), "column renaming is not implemented"),
        (lambda d: d["warehouse"]["tables"].pop("ops.run_manifest"), r"warehouse\.tables\.ops\.run_manifest is missing"),
        (lambda d: d["lakehouse"]["tables"]["Payroll"]["columns"].pop("wages"), r"lakehouse\.tables\.Payroll\.columns\.wages is missing"),
        (lambda d: d["warehouse"]["tables"]["ops.run_manifest"]["columns"]["run_id"].update(column=None), r"columns\.run_id\.column must be a name"),
    ],
)
def test_an_invalid_or_incomplete_map_is_refused_naming_the_key(mutate, message, tmp_path):
    path = tmp_path / "bad.json"
    path.write_bytes(_edit(mutate))
    with pytest.raises(DataMapError, match=message):
        data_map.load(str(path))


def test_lakehouse_columns_may_be_renamed():
    def rename(doc):
        doc["lakehouse"]["tables"]["Payroll"]["columns"]["wages"]["column"] = "GrossPay"

    assert parse(_edit(rename), "file", data_map.default_map()).lakehouse["tables"]["Payroll"]["columns"]["wages"]["column"] == "GrossPay"


def test_no_statement_spells_a_schema_constant_beside_a_table_name():
    pattern = re.compile(r"\{(?:GOLD|OPS)_SCHEMA\}\.[A-Za-z_{]")
    offenders = [
        str(p.relative_to(ROOT))
        for folder in ("backend", "scripts", "contract")
        for p in (ROOT / folder).rglob("*.py")
        if "tests" not in p.parts and "maintainer" not in p.parts and pattern.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], "use names.gold.<table> / names.ops.<table>"
