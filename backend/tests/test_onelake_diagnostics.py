"""The OneLake access check: each step reports, and the usual errors are explained. [03.1]"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from config import override_settings
from data.source import onelake_diagnostics as diag

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-onelake-access.py"


@pytest.mark.parametrize("error,fragment", [
    ("... IncorrectEndpointError ...", "BLOB API"),
    ("Generic MicrosoftAzure error: DeniedByPolicy: public network access", "private link"),
    ("HTTP 403 AuthorizationFailure", "workspace"),
    ("status 401 Unauthorized", "az login"),
    ("ArtifactNotFound", "paused capacity"),
    ("operation timed out", "private host"),
    ("TableNotFound: no log", "SOURCE_SCHEMA"),
])
def test_the_usual_errors_are_translated(error, fragment):
    assert fragment in diag.explain(error)


def test_an_unknown_error_is_left_alone():
    assert diag.explain("something nobody has seen") == ""


def test_a_public_address_is_flagged_when_a_private_endpoint_is_configured():
    with override_settings({"ONELAKE_ENDPOINT": "https://abc.zab.blob.fabric.microsoft.com"}):
        public = diag.check_dns("abc.zab.blob.fabric.microsoft.com", resolver=lambda host, port: [(0, 0, 0, "", ("20.1.2.3", port))])
        private = diag.check_dns("abc.zab.blob.fabric.microsoft.com", resolver=lambda host, port: [(0, 0, 0, "", ("10.0.0.4", port))])
    assert not public.ok and "PUBLIC" in public.detail and "VPN" in public.hint
    assert private.ok and "10.0.0.4" in private.detail


def test_a_name_that_does_not_resolve_fails_with_the_cause():
    def refuse(host, port):
        raise OSError("no such host")

    step = diag.check_dns("nowhere.invalid", resolver=refuse)
    assert not step.ok and "did not resolve" in step.detail and "private DNS" in step.hint


def test_the_host_it_calls_is_the_private_one_when_set_and_the_public_one_otherwise():
    with override_settings({"ONELAKE_ENDPOINT": "https://abc.zab.blob.fabric.microsoft.com"}):
        assert diag.target_host() == "abc.zab.blob.fabric.microsoft.com"
    with override_settings({}):
        assert diag.target_host() == "onelake.dfs.fabric.microsoft.com"


def test_a_token_failure_is_reported_without_the_token():
    def refuse():
        raise RuntimeError("no login")

    assert not diag.check_token(refuse).ok
    step = diag.check_token(lambda: "SECRET-TOKEN")
    assert step.ok and "SECRET-TOKEN" not in step.detail


def test_the_table_step_reports_version_and_files_or_the_translated_error():
    ok = diag.check_table(lambda: {"version": 12, "files": 3}, "Account")
    assert ok.ok and "version 12" in ok.detail and "3 file" in ok.detail

    def deny():
        raise OSError("403 AuthorizationFailure")

    failed = diag.check_table(deny, "Account")
    assert not failed.ok and "Contributor" in failed.hint


def test_the_script_stops_with_the_missing_setting_when_nothing_is_configured(monkeypatch, capsys):
    for name in ("FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE"):
        monkeypatch.delenv(name, raising=False)
    spec = importlib.util.spec_from_file_location("check_onelake_access", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    import sys

    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    monkeypatch.setitem(sys.modules, "sql_common", importlib.import_module("sql_common"))
    spec.loader.exec_module(module)
    monkeypatch.setattr("sql_common.load_env", lambda: None)
    monkeypatch.setattr(module, "load_env", lambda: None)
    assert module.main([]) == 2
    out = capsys.readouterr().out
    assert "FABRIC_WORKSPACE" in out and "FABRIC_LAKEHOUSE" in out
