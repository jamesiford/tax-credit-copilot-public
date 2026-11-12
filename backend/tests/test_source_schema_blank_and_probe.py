"""A blank SOURCE_SCHEMA is warned about, and the layout probe says which layout opens the table. [03b.3]

A `SOURCE_SCHEMA=` line that is present but blank used to mean the default schema and now means "no schema" (a
lakehouse that is not schema-enabled). That is easy to trigger from a copied template, so it is said at startup,
and `--probe-layout` removes the guesswork by trying both layouts.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from local_lakehouse import use_local_lakehouse, write_lakehouse

from application.store_readiness import settings_findings
from config import override_settings
from data.source import from_fabric
from data.source.onelake_diagnostics import layouts, probe_layout
from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"


def _codes(env):
    return {f.code for f in settings_findings(env)}


def test_a_blank_source_schema_is_warned_about_once_with_the_remedy():
    findings = [f for f in settings_findings({"SOURCE_SCHEMA": "  "}) if f.code == "source_schema_blank"]
    assert len(findings) == 1 and findings[0].severity == "warning"
    assert "not schema-enabled" in findings[0].message
    assert "SOURCE_SCHEMA=dbo" in findings[0].remedy and "--probe-layout" in findings[0].remedy


@pytest.mark.parametrize("env", [{}, {"SOURCE_SCHEMA": "dbo"}, {"SOURCE_SCHEMA": "tcc_source"}])
def test_an_unset_or_named_schema_is_not_warned_about(env):
    assert "source_schema_blank" not in _codes(env)


def test_the_template_says_what_a_blank_schema_does():
    template = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    assert "SOURCE_SCHEMA=dbo" in template and "NOT schema-enabled" in template and "--probe-layout" in template
    assert not any(line.startswith("SOURCE_SCHEMA=") for line in template.splitlines()), "the template line is commented out"


def test_the_layouts_tried_are_the_configured_one_then_the_other():
    assert layouts("dbo") == ["dbo", ""] and layouts("") == ["", "dbo"]


def _local(monkeypatch, tmp_path, schema):
    write_lakehouse(tmp_path, build_synthetic_dataset(SYNTHETIC_CLIENTS[0]), schema=schema)
    use_local_lakehouse(monkeypatch, tmp_path)


@pytest.mark.parametrize("on_disk", ["dbo", ""])
@pytest.mark.parametrize("configured", ["dbo", ""])
def test_the_probe_finds_the_layout_that_exists_whichever_one_is_configured(tmp_path, monkeypatch, on_disk, configured):
    _local(monkeypatch, tmp_path, on_disk)

    def opener(schema):
        return from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema=schema).table_lineage("Account") or {}

    steps, winner = probe_layout(opener, "Account", configured)
    assert winner == on_disk
    assert len(steps) == 2 and [s.ok for s in steps].count(True) == 1


def test_the_probe_reports_none_when_neither_layout_opens_it(tmp_path, monkeypatch):
    use_local_lakehouse(monkeypatch, tmp_path)
    steps, winner = probe_layout(
        lambda schema: from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema=schema).table_lineage("Account") or {},
        "Account", "dbo",
    )
    assert winner is None and not any(s.ok for s in steps)


def _script(monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    monkeypatch.setitem(sys.modules, "sql_common", importlib.import_module("sql_common"))
    spec = importlib.util.spec_from_file_location("check_onelake_access_probe", SCRIPTS / "check-onelake-access.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "load_env", lambda: None)
    return module


def test_the_script_names_the_layout_that_differs_from_the_configuration(tmp_path, monkeypatch, capsys):
    _local(monkeypatch, tmp_path, "")
    from data.source import onelake_diagnostics as diag

    monkeypatch.setattr(diag, "check_dns", lambda host: diag.Step("dns", True, "private"))
    monkeypatch.setattr(diag, "check_token", lambda *a, **k: diag.Step("token", True, "ok"))
    module = _script(monkeypatch)
    with override_settings({"DATA_SOURCE": "lakehouse", "FABRIC_WORKSPACE": "ws", "FABRIC_LAKEHOUSE": "lh", "SOURCE_SCHEMA": "dbo"}):
        status = module.main(["--probe-layout"])
    out = capsys.readouterr().out
    assert status == 0, out
    assert "SOURCE_SCHEMA= (blank: not schema-enabled)" in out and "THAT DIFFERS from what is configured" in out
    assert "layout: schema '" in out and "layout: no schema" in out
