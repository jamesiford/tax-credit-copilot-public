"""The telemetry switch, where its value came from, and one clear warning when export is refused. [03.4]"""
from __future__ import annotations

import logging

import pytest

import telemetry
from config import override_settings

CONN = f"InstrumentationKey={'0' * 8}"


@pytest.fixture(autouse=True)
def _fresh(monkeypatch):
    monkeypatch.setattr(telemetry, "_initialized", False)


def _on(**env):
    return override_settings({"APPLICATIONINSIGHTS_CONNECTION_STRING": CONN, **env})


def test_on_only_when_a_connection_string_is_set_unless_stated():
    with override_settings({}):
        assert telemetry.telemetry_enabled() is False
    with _on():
        assert telemetry.telemetry_enabled() is True
    with override_settings({"APPLICATIONINSIGHTS_CONNECTION_STRING": ""}):
        assert telemetry.telemetry_enabled() is False, "an empty string really disables it"


def test_the_switch_can_turn_it_off_but_cannot_turn_it_on_without_a_string():
    with _on(TELEMETRY_ENABLED="false"):
        assert telemetry.telemetry_enabled() is False
    with override_settings({"TELEMETRY_ENABLED": "true"}):
        assert telemetry.telemetry_enabled() is False


def test_a_value_that_is_not_a_boolean_is_refused():
    from config import load_settings

    with pytest.raises(ValueError):
        load_settings({"TELEMETRY_ENABLED": "sometimes"}).observability


def test_a_disabled_switch_never_touches_the_exporter(monkeypatch, caplog):
    monkeypatch.setitem(__import__("sys").modules, "azure.monitor.opentelemetry", None)  # an import would fail loudly
    with caplog.at_level(logging.INFO, logger="telemetry"), _on(TELEMETRY_ENABLED="false"):
        telemetry.configure_telemetry()
    assert "TELEMETRY_ENABLED=false" in caplog.text and "Failed to initialize" not in caplog.text


def test_an_empty_connection_string_says_so_and_where_it_came_from(caplog):
    with caplog.at_level(logging.INFO, logger="telemetry"), override_settings({"APPLICATIONINSIGHTS_CONNECTION_STRING": ""}):
        telemetry.configure_telemetry()
    assert "empty or unset" in caplog.text and "from " in caplog.text


def test_an_os_variable_that_overrides_the_env_file_is_called_out(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("APPLICATIONINSIGHTS_CONNECTION_STRING=\nOTHER=1\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with override_settings({"APPLICATIONINSIGHTS_CONNECTION_STRING": CONN}):
        assert "overrides the value in .env" in telemetry._where("APPLICATIONINSIGHTS_CONNECTION_STRING")
    with override_settings({"APPLICATIONINSIGHTS_CONNECTION_STRING": ""}):
        assert ".env" in telemetry._where("APPLICATIONINSIGHTS_CONNECTION_STRING")
    with override_settings({"NOT_IN_FILE": "x"}):
        assert telemetry._where("NOT_IN_FILE") == "the OS environment"


def _record(message: str) -> logging.LogRecord:
    return logging.LogRecord("azure.monitor.opentelemetry.exporter", logging.WARNING, __file__, 1, message, (), None)


def test_a_refused_export_is_explained_once_and_not_repeated(caplog):
    gate = telemetry._ExporterAuthFilter()
    with caplog.at_level(logging.WARNING, logger="telemetry"):
        results = [gate.filter(_record("Non-retryable server side error: 403 Forbidden")) for _ in range(5)]
    assert results == [False] * 5
    assert caplog.text.count("refused the telemetry export") == 1
    for cause in ("Entra", "Monitoring Metrics Publisher", "wrong identity"):
        assert cause in caplog.text


def test_a_message_that_is_not_an_authorisation_failure_passes_through():
    assert telemetry._ExporterAuthFilter().filter(_record("Transient error: timeout, retrying")) is True
