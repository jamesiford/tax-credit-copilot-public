"""The T-SQL grant script builds safe, idempotent statements. [FAB-2]"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


@pytest.fixture
def grants(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location("grant_cli", SCRIPTS / "grant-warehouse-sql.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_grants_cover_both_schemas_read_and_write(grants):
    statements = grants.grant_statements("id-tcc-api-abc123", ["tcc_gold", "tcc_ops"])
    assert statements == [
        "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::tcc_gold TO [id-tcc-api-abc123];",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::tcc_ops TO [id-tcc-api-abc123];",
    ]


@pytest.mark.parametrize("principal", ["x]; DROP TABLE t; --", "a\nb", ""])
def test_an_unusual_principal_is_refused(grants, principal):
    with pytest.raises(ValueError):
        grants.grant_statements(principal, ["tcc_gold"])


def test_a_bad_schema_is_refused(grants):
    with pytest.raises(ValueError):
        grants.grant_statements("id-api", ["tcc_gold; DROP"])


def test_nothing_private_is_packaged_for_app_service():
    ignore = (Path(__file__).resolve().parents[1] / ".webappignore").read_text(encoding="utf-8").splitlines()
    for pattern in (".env", "data/payroll/", "data/reference_output/", "data/operational.db"):
        assert pattern in ignore, f"{pattern} would be zipped into the App Service package"
