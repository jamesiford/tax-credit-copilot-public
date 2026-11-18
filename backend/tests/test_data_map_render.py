"""The DDL renderer: identity under the shipped map, complete under a renamed one. [R2.4]"""
import json
from pathlib import Path

import pytest

import data_map
from data_map_ddl import DDL_FILES
from data_map_load import parse
from data_map_render import render

SHIPPED = data_map.default_map()
ROOT = Path(__file__).resolve().parents[2]


def _renamed():
    doc = json.loads((ROOT / "docs" / "data" / "data-map.json").read_text(encoding="utf-8"))
    doc["warehouse"]["schemas"] = {"gold": "cust_numbers", "ops": "cust_ops"}
    for key, table in doc["warehouse"]["tables"].items():
        table["table"] = f"x_{table['table']}"
    return parse(json.dumps(doc).encode(), "file", SHIPPED)


@pytest.mark.parametrize("path", DDL_FILES, ids=lambda p: p.name)
def test_the_shipped_map_renders_every_ddl_file_byte_for_byte(path):
    text = path.read_text(encoding="utf-8")
    assert render(text, SHIPPED) == text


@pytest.mark.parametrize("path", DDL_FILES, ids=lambda p: p.name)
def test_a_renamed_map_leaves_no_shipped_schema_name_behind(path):
    out = render(path.read_text(encoding="utf-8"), _renamed())
    assert "tcc_gold" not in out and "tcc_ops" not in out
    assert "cust_ops" in out or "cust_numbers" in out or path.name.startswith("0100") is False


def test_qualified_names_and_information_schema_pairs_are_renamed_together():
    sql = (
        "CREATE TABLE tcc_ops.run_manifest (a INT);\n"
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'tcc_ops' AND TABLE_NAME = 'manual_override')\n"
        "GRANT SELECT ON SCHEMA::tcc_gold TO [p];\n"
    )
    assert render(sql, _renamed()) == (
        "CREATE TABLE cust_ops.x_run_manifest (a INT);\n"
        "IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = 'cust_ops' AND TABLE_NAME = 'x_manual_override')\n"
        "GRANT SELECT ON SCHEMA::cust_numbers TO [p];\n"
    )
