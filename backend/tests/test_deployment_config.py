"""A deployed process refuses to start on a non-durable store or an unstated
data classification. [DATA-5, D26]

Both failures are silent if allowed through: SQLite on an App Service writes to
a filesystem the platform can discard, and an unstated classification is a
guess about whether the data is payroll.
"""
from __future__ import annotations

import pytest

from application.deployment import (
    DeploymentConfigurationError,
    check_deployment_configuration,
    store_choice,
)

DURABLE = {
    "CLAIM_STORE": "warehouse",
    "FINDING_STORE": "warehouse",
    "RUN_MANIFEST_STORE": "warehouse",
    "ARTIFACT_STORE": "blob",
    "ARTIFACT_REPOSITORY": "warehouse",
}


def test_local_is_the_default_and_accepts_local_stores():
    resolved = check_deployment_configuration({})
    assert resolved["environment"] == "local"
    assert resolved["CLAIM_STORE"] == "sqlite" and resolved["RUN_MANIFEST_STORE"] == "memory"
    assert resolved["OVERRIDE_STORE"] == "memory", "overrides follow the run manifest store"


def test_a_deployed_environment_with_durable_stores_starts():
    resolved = check_deployment_configuration({"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "synthetic", **DURABLE})
    assert resolved["OVERRIDE_STORE"] == "warehouse"
    assert resolved["data_classification"] == "synthetic"


def test_the_fabric_alias_is_durable():
    env = {"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "customer", "AUTH_MODE": "entra",
           "AUTH_TENANT_ID": "tenant", "API_AUDIENCE": "api://tcc", **{k: ("blob" if k == "ARTIFACT_STORE" else "fabric") for k in DURABLE}}
    assert check_deployment_configuration(env)["CLAIM_STORE"] == "warehouse"


@pytest.mark.parametrize("store", ["CLAIM_STORE", "FINDING_STORE", "RUN_MANIFEST_STORE", "OVERRIDE_STORE"])
@pytest.mark.parametrize("value", ["sqlite", "memory"])
def test_a_deployed_environment_refuses_any_non_durable_store(store, value):
    env = {"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "synthetic", **DURABLE, store: value}
    with pytest.raises(DeploymentConfigurationError, match=store):
        check_deployment_configuration(env)


def test_a_deployed_environment_requires_an_explicit_classification():
    with pytest.raises(DeploymentConfigurationError, match="DATA_CLASSIFICATION is required"):
        check_deployment_configuration({"ENVIRONMENT": "azure", **DURABLE})


def test_an_unknown_classification_is_refused_even_locally():
    with pytest.raises(DeploymentConfigurationError, match="not one of"):
        check_deployment_configuration({"DATA_CLASSIFICATION": "probably-fine"})


def test_every_problem_is_reported_at_once():
    with pytest.raises(DeploymentConfigurationError) as raised:
        check_deployment_configuration({"ENVIRONMENT": "azure"})
    message = str(raised.value)
    for name in ("DATA_CLASSIFICATION", "CLAIM_STORE", "FINDING_STORE", "RUN_MANIFEST_STORE", "OVERRIDE_STORE"):
        assert name in message


def test_store_choice_normalises_case_whitespace_and_alias():
    assert store_choice("CLAIM_STORE", {"CLAIM_STORE": "  FABRIC "}) == "warehouse"
    assert store_choice("OVERRIDE_STORE", {"RUN_MANIFEST_STORE": "fabric"}) == "warehouse"
    assert store_choice("OVERRIDE_STORE", {"RUN_MANIFEST_STORE": "fabric", "OVERRIDE_STORE": "memory"}) == "memory"


# ------------------------------------------------------------- at startup


def _start_app():
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app):
        pass


def test_startup_with_environment_azure_and_a_sqlite_claim_store_raises(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "azure")
    monkeypatch.setenv("DATA_CLASSIFICATION", "synthetic")
    for name, value in DURABLE.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("OVERRIDE_STORE", raising=False)
    monkeypatch.setenv("CLAIM_STORE", "sqlite")
    with pytest.raises(DeploymentConfigurationError, match="CLAIM_STORE"):
        _start_app()


def test_startup_without_a_classification_when_deployed_raises(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "azure")
    monkeypatch.delenv("DATA_CLASSIFICATION", raising=False)
    for name, value in DURABLE.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(DeploymentConfigurationError, match="DATA_CLASSIFICATION"):
        _start_app()


@pytest.mark.parametrize("name, value", [("ARTIFACT_STORE", "local"), ("ARTIFACT_REPOSITORY", "sqlite")])
def test_a_deployed_environment_refuses_local_artifact_storage(name, value):
    env = {"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "synthetic", **DURABLE, name: value}
    with pytest.raises(DeploymentConfigurationError, match=name):
        check_deployment_configuration(env)


@pytest.mark.parametrize("name", ["ARTIFACT_STORE", "ARTIFACT_REPOSITORY"])
def test_an_unknown_artifact_store_is_refused(name):
    with pytest.raises(DeploymentConfigurationError, match=name):
        check_deployment_configuration({name: "ftp"})
