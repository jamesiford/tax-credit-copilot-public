"""The lakehouse endpoint grants: read-only, object level, the API identity only. [CH-16f]

The governed data query reads the source payroll tables through the lakehouse SQL analytics
endpoint. What that needs beyond the API identity's existing Warehouse grants is `SELECT` on
exactly the tables the semantic model names. These tests pin the generated T-SQL: no write,
no schema grant, no role membership, and never the channel gateway's identity.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|ALTER|CONTROL|EXECUTE|DROP|CREATE|DENY|REVOKE|db_owner|db_datawriter|ADD MEMBER|GRANT OPTION)\b|SCHEMA::",
    re.IGNORECASE,
)


def _load(name: str, filename: str):
    if str(SCRIPTS) not in sys.path:
        sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def grants():
    return _load("grant_cli_lakehouse", "grant-warehouse-sql.py")


def test_the_lakehouse_profile_grants_select_on_the_three_source_tables_and_nothing_else(grants):
    statements = grants.statements_for("lakehouse", "tcc-api", "tcc_gold", "tcc_ops", "tcc_source")
    assert statements == [
        "GRANT SELECT ON OBJECT::tcc_source.Location TO [tcc-api];",
        "GRANT SELECT ON OBJECT::tcc_source.PayCode TO [tcc-api];",
        "GRANT SELECT ON OBJECT::tcc_source.Payroll TO [tcc-api];",
    ]


def test_every_lakehouse_dataset_in_the_model_is_granted_and_nothing_more(grants):
    from application.data.semantic_model import Source, default_model

    modelled = {d.table for d in default_model().datasets if d.source is Source.LAKEHOUSE}
    granted = {re.search(r"OBJECT::\w+\.(\w+) TO", s).group(1) for s in grants.statements_for("lakehouse", "p", "g", "o", "s")}
    assert granted == modelled, "a lakehouse dataset added to the model must be granted, and a grant needs a dataset"


def test_the_lakehouse_grants_are_read_only_object_level_and_name_no_role(grants):
    for statement in grants.statements_for("lakehouse", "tcc-api", "tcc_gold", "tcc_ops", "tcc_source"):
        assert statement.startswith("GRANT SELECT ON OBJECT::"), statement
        assert not FORBIDDEN.search(statement), statement
        assert statement.endswith("];")


def test_the_lakehouse_grants_are_idempotent_grants_not_creates(grants):
    statements = grants.statements_for("lakehouse", "tcc-api", "tcc_gold", "tcc_ops", "tcc_source")
    assert all(s.split()[0] == "GRANT" for s in statements)


def test_the_schema_follows_the_deployment_setting(grants):
    statements = grants.lakehouse_grant_statements("tcc-api", "customer_src", ("Payroll",))
    assert statements == ["GRANT SELECT ON OBJECT::customer_src.Payroll TO [tcc-api];"]


@pytest.mark.parametrize("principal", ["x]; DROP TABLE y; --", "a'b", "tcc-api]; GRANT CONTROL TO [evil", ""])
def test_an_unusual_principal_is_refused(grants, principal):
    with pytest.raises(ValueError):
        grants.statements_for("lakehouse", principal, "tcc_gold", "tcc_ops", "tcc_source")


def test_an_unusual_schema_or_table_is_refused(grants):
    with pytest.raises(ValueError):
        grants.lakehouse_grant_statements("tcc-api", "tcc_source; DROP TABLE x", ("Payroll",))
    with pytest.raises(ValueError):
        grants.lakehouse_grant_statements("tcc-api", "tcc_source", ("Payroll TO [evil]; --",))


def test_no_profile_issues_a_write_or_role_grant_on_the_lakehouse_endpoint(grants):
    for profile in ("lakehouse",):
        assert not any(FORBIDDEN.search(s) for s in grants.statements_for(profile, "p", "g", "o", "s"))


def test_the_existing_profiles_are_unchanged(grants):
    assert grants.statements_for("api", "tcc-api", "tcc_gold", "tcc_ops") == [
        "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::tcc_gold TO [tcc-api];",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::tcc_ops TO [tcc-api];",
    ]
    assert grants.statements_for("gateway", "tcc-gw", "tcc_gold", "tcc_ops") == [
        "GRANT INSERT, SELECT ON OBJECT::tcc_ops.channel_audit TO [tcc-gw];"
    ]


def test_the_lakehouse_dry_run_prints_the_grants_for_the_api_identity(grants, capsys, monkeypatch):
    monkeypatch.setenv("API_IDENTITY_NAME", "tcc-api-identity")
    monkeypatch.delenv("GATEWAY_IDENTITY_NAME", raising=False)
    assert grants.main(["--target", "deployed", "--profile", "lakehouse", "--dry-run"]) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 3 and all("[tcc-api-identity]" in line for line in lines)


def test_the_lakehouse_profile_refuses_the_gateway_identity(grants, monkeypatch):
    monkeypatch.setenv("GATEWAY_IDENTITY_NAME", "tcc-gw-identity")
    with pytest.raises(SystemExit) as refused:
        grants.main(["--target", "deployed", "--profile", "lakehouse", "--principal", "tcc-gw-identity", "--dry-run"])
    assert refused.value.code == 2


def test_the_lakehouse_endpoint_must_share_the_guarded_workspace_host():
    common = _load("sql_common_lakehouse", "sql_common.py")
    from infrastructure.persistence.schema_admin import ResolvedTarget, TargetMismatch

    resolved = ResolvedTarget("w", "i", "abc.datawarehouse.fabric.microsoft.com", "wh")
    common.check_lakehouse_endpoint(resolved, "ABC.datawarehouse.fabric.microsoft.com,1433")
    with pytest.raises(TargetMismatch):
        common.check_lakehouse_endpoint(resolved, "other.datawarehouse.fabric.microsoft.com")


def test_postprovision_grants_the_lakehouse_only_when_the_source_is_on_and_never_to_the_gateway():
    text = (SCRIPTS / "postprovision.ps1").read_text(encoding="utf-8")
    start = text.index("--profile lakehouse")
    block = text[text.rindex("if (", 0, start):text.index("\n}\n", start)]
    assert "$env:TCC_DATA_QUERY_SOURCE_ENABLED -eq 'true'" in block
    assert "GATEWAY_IDENTITY_NAME" not in block and "--principal" not in block, "the API identity is the default principal"
    assert text.index("--profile gateway") < start, "after the schema grants the endpoint grant relies on"
    assert text.count("--profile lakehouse") == 1
