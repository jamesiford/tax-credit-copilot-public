"""A blank `DATA_SOURCE` is the lakehouse everywhere, and an unconfigured lakehouse says so. [03.3]

`config_sections` defaulted only an UNSET value to `lakehouse`, and the reference workspace
read `explicit_data_source or "csv"`, so a blank line in `.env` sent the portal to the private
CSV fixtures and ended in "Reference workspace inputs missing" - an error about a file nobody
had asked for.
"""
from __future__ import annotations

import warnings

import pytest

from application.errors import DependencyUnavailable, SourceNotConfigured
from config import load_settings
from tools.fabric_source import resolve_data_source


@pytest.fixture
def unconfigured(monkeypatch):
    for name in ("FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE"):
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_unset_or_blank_value_is_the_lakehouse(value):
    environ = {} if value is None else {"DATA_SOURCE": value}
    assert load_settings(environ).data_source.data_source == "lakehouse"


def test_csv_is_selected_only_when_it_is_set_explicitly(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "csv")
    assert resolve_data_source() == "csv"
    monkeypatch.setenv("DATA_SOURCE", "")
    assert resolve_data_source() == "lakehouse"
    monkeypatch.delenv("DATA_SOURCE")
    assert resolve_data_source() == "lakehouse"


def test_the_retired_flex_alias_still_resolves_with_its_warning(monkeypatch):
    monkeypatch.setenv("DATA_SOURCE", "flex")
    with pytest.warns(DeprecationWarning):
        assert resolve_data_source() == "lakehouse"


def test_the_reference_workspace_follows_the_same_resolver(unconfigured):
    from tools.reference_workspace import ReferenceWorkspaceService

    unconfigured.setenv("DATA_SOURCE", "")
    assert ReferenceWorkspaceService().source_kind == "lakehouse"
    unconfigured.setenv("DATA_SOURCE", "csv")
    assert ReferenceWorkspaceService().source_kind == "csv"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        unconfigured.setenv("DATA_SOURCE", "flex")
        assert ReferenceWorkspaceService().source_kind == "lakehouse"


def test_a_lakehouse_with_no_workspace_raises_a_typed_error_not_a_missing_csv(unconfigured):
    from tools.reference_workspace import ReferenceWorkspaceService

    unconfigured.setenv("DATA_SOURCE", "")
    with pytest.raises(SourceNotConfigured) as caught:
        ReferenceWorkspaceService().get()
    error = caught.value
    assert isinstance(error, DependencyUnavailable) and error.dependency == "source_lakehouse"
    assert set(error.missing) == {"FABRIC_WORKSPACE", "FABRIC_LAKEHOUSE"}
    assert "One.csv" not in str(error)


def test_only_the_missing_setting_is_named(unconfigured):
    from data.source.from_fabric import FabricLakehouseReader

    unconfigured.setenv("FABRIC_WORKSPACE", "ws")
    reader = FabricLakehouseReader()
    assert reader.missing_settings() == ("FABRIC_LAKEHOUSE",)
    assert "FABRIC_WORKSPACE" not in str(SourceNotConfigured(reader.missing_settings()))


def test_the_front_door_answers_503_with_the_remedy(unconfigured):
    from fastapi.testclient import TestClient

    from api import workspace
    from main import app
    from tools.reference_workspace import ReferenceWorkspaceService

    unconfigured.setenv("DATA_SOURCE", "")
    unconfigured.setattr(workspace, "_SERVICE", ReferenceWorkspaceService())
    response = TestClient(app).get("/api/workspace")
    assert response.status_code == 503
    body = response.json()
    assert body["dependency"] == "source_lakehouse"
    assert "FABRIC_WORKSPACE" in body["remedy"] and "FABRIC_LAKEHOUSE" in body["remedy"]
    assert "csv" not in body["reason"].lower()
