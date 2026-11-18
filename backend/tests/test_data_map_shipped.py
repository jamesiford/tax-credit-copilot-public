"""R2.1 gate: the shipped data map is valid, complete, and exactly the repository's inventory.

Why: a customer copies this file, so it must list every Warehouse table and column the DDL
creates and every Lakehouse table and column the source mapping reads, and nothing else.
"""
import importlib.util
import json
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
SHIPPED = ROOT / "docs" / "data" / "data-map.json"
SCHEMA = ROOT / "docs" / "data" / "data-map.schema.json"
LAKEHOUSE_DEFAULT = ROOT / "backend" / "data" / "source" / "mapping" / "default.json"


def _script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_").removesuffix(".py"), path)
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.path.insert(0, str(path.parent))
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def shipped():
    return json.loads(SHIPPED.read_text(encoding="utf-8"))


def test_the_schema_validates_the_shipped_file(shipped):
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    assert [e.message for e in jsonschema.Draft202012Validator(schema).iter_errors(shipped)] == []


def test_the_shipped_file_lists_every_ddl_table_and_column_and_nothing_else(shipped):
    ddl = _script("data_map_ddl.py").read_warehouse_ddl()
    assert len(ddl) == 38 and sum(len(c) for c in ddl.values()) == 498
    listed = {k: [(n, c["type"]) for n, c in t["columns"].items()] for k, t in shipped["warehouse"]["tables"].items()}
    assert listed == {k: list(v) for k, v in ddl.items()}
    assert list(listed) == list(ddl), "order follows the DDL"
    assert ("write_order", "BIGINT") in listed["ops.manual_override"]


def test_the_shipped_file_lists_every_lakehouse_table_and_column_and_nothing_else(shipped):
    source = json.loads(LAKEHOUSE_DEFAULT.read_text(encoding="utf-8"))
    listed = shipped["lakehouse"]["tables"]
    assert list(listed) == list(source["tables"])
    for name, table in source["tables"].items():
        assert listed[name]["table"] == table["table"]
        assert {n: c["column"] for n, c in listed[name]["columns"].items()} == {n: f["column"] for n, f in table["fields"].items()}
        for field, spec in table["fields"].items():
            col = listed[name]["columns"][field]
            assert (col["type"], col["required"], col["engine"]) == (spec["type"], spec.get("required", True), spec.get("engine", True))


def test_the_defaults_generator_reproduces_the_shipped_file_byte_for_byte():
    gen = _script("generate-data-map.py")
    assert gen.render(gen.build_defaults()) == SHIPPED.read_text(encoding="utf-8")
