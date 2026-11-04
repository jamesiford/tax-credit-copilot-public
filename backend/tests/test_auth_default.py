"""Authentication is the default; running without it is a stated local-development choice. [RM-03, AUTH-5, D26]

`AUTH_MODE` used to default to `none`, so an environment that forgot the setting served payroll
to anybody who could reach it. It now defaults to `entra`. `none` needs `ENVIRONMENT=local` set on
purpose (an unset `ENVIRONMENT` means local for store defaults, and is not permission to skip
sign-in); the one other route is a deployed demo over synthetic data that says so with
`ALLOW_ANONYMOUS_SYNTHETIC=1`. The suite itself opts in through conftest, so none of this is
weakened to keep the tests running.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from application import wiring
from application.deployment import (
    DeploymentConfigurationError, auth_mode, check_deployment_configuration, explicit_local_dev,
)
from test_auth import AUDIENCE, TENANT, _validator, mint

DURABLE = {"CLAIM_STORE": "warehouse", "FINDING_STORE": "warehouse", "RUN_MANIFEST_STORE": "warehouse",
           "ARTIFACT_STORE": "blob", "ARTIFACT_REPOSITORY": "warehouse"}
ENTRA = {"AUTH_MODE": "entra", "AUTH_TENANT_ID": TENANT, "API_AUDIENCE": AUDIENCE}
LOCAL_DEV = {"ENVIRONMENT": "local", "AUTH_MODE": "none"}


def deployed(**over):
    return {"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "synthetic", **DURABLE, **over}


# ------------------------------------------------------------------ the default


def test_the_default_is_entra_not_none():
    assert auth_mode({}) == "entra" and auth_mode({"AUTH_MODE": ""}) == "entra" and auth_mode({"AUTH_MODE": "  "}) == "entra"


def test_a_process_that_says_nothing_about_auth_does_not_start_without_a_tenant():
    with pytest.raises(DeploymentConfigurationError, match="AUTH_TENANT_ID") as raised:
        check_deployment_configuration({})
    assert "ENVIRONMENT=local" in str(raised.value), "the refusal says how to opt in for local development"


def test_a_deployed_process_that_says_nothing_about_auth_must_have_entra_settings():
    with pytest.raises(DeploymentConfigurationError, match="AUTH_TENANT_ID|API_AUDIENCE"):
        check_deployment_configuration(deployed())


def test_a_request_with_no_auth_setting_demands_a_token(monkeypatch):
    import main

    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.setenv("AUTH_TENANT_ID", TENANT)
    monkeypatch.setenv("API_AUDIENCE", AUDIENCE)
    wiring.set_token_validator(_validator())
    try:
        api = TestClient(main.app)
        assert api.get("/api/me").status_code == 401, "the unset default is not anonymous access"
        assert api.get("/api/me", headers={"Authorization": f"Bearer {mint()}"}).status_code == 200
    finally:
        wiring.set_token_validator(None)
        wiring.set_client_authorizer(None)


# ------------------------------------------------------------- the local opt-in


def test_none_with_local_stated_outright_is_the_local_development_opt_in():
    assert check_deployment_configuration(LOCAL_DEV)["auth_mode"] == "none"


@pytest.mark.parametrize("environment", ["local", "LOCAL", " local "])
def test_the_opt_in_ignores_case_and_padding(environment):
    assert explicit_local_dev({"ENVIRONMENT": environment})
    check_deployment_configuration({"ENVIRONMENT": environment, "AUTH_MODE": "none"})


def test_none_with_environment_unset_is_refused():
    with pytest.raises(DeploymentConfigurationError, match="only for local development"):
        check_deployment_configuration({"AUTH_MODE": "none"})
    assert not explicit_local_dev({})


@pytest.mark.parametrize("environment", ["azure", "prod", "staging", "dev", "test", "localhost", "local-dev"])
def test_none_is_refused_in_every_environment_that_is_not_explicitly_local(environment):
    with pytest.raises(DeploymentConfigurationError, match="only for local development"):
        check_deployment_configuration(deployed(ENVIRONMENT=environment, AUTH_MODE="none"))


def test_entra_in_a_deployed_environment_starts():
    assert check_deployment_configuration(deployed(**ENTRA))["auth_mode"] == "entra"


# -------------------------------------------------- the deployed synthetic demo


def test_a_deployed_synthetic_demo_may_run_without_sign_in_only_by_saying_so():
    flagged = deployed(AUTH_MODE="none", ALLOW_ANONYMOUS_SYNTHETIC="1")
    assert check_deployment_configuration(flagged)["auth_mode"] == "none"
    with pytest.raises(DeploymentConfigurationError, match="ALLOW_ANONYMOUS_SYNTHETIC"):
        check_deployment_configuration(deployed(AUTH_MODE="none"))


@pytest.mark.parametrize("flag", ["0", "false", "no", "off", "", "maybe"])
def test_anything_but_an_affirmative_flag_is_not_the_opt_in(flag):
    with pytest.raises(DeploymentConfigurationError, match="only for local development"):
        check_deployment_configuration(deployed(AUTH_MODE="none", ALLOW_ANONYMOUS_SYNTHETIC=flag))


def test_the_demo_flag_never_covers_customer_data():
    env = deployed(AUTH_MODE="none", ALLOW_ANONYMOUS_SYNTHETIC="1", DATA_CLASSIFICATION="customer")
    with pytest.raises(DeploymentConfigurationError, match="DATA_CLASSIFICATION=customer"):
        check_deployment_configuration(env)


def test_the_demo_flag_needs_an_explicit_synthetic_classification():
    env = deployed(AUTH_MODE="none", ALLOW_ANONYMOUS_SYNTHETIC="1")
    del env["DATA_CLASSIFICATION"]
    with pytest.raises(DeploymentConfigurationError, match="DATA_CLASSIFICATION is required"):
        check_deployment_configuration(env)


def test_the_flag_does_not_turn_entra_off():
    with pytest.raises(DeploymentConfigurationError, match="AUTH_TENANT_ID"):
        check_deployment_configuration(deployed(AUTH_MODE="entra", ALLOW_ANONYMOUS_SYNTHETIC="1"))


# ------------------------------------------------- the test suite's own opt-in


def test_terraform_sets_the_demo_flag_only_where_auth_is_none():
    from pathlib import Path

    main_tf = (Path(__file__).resolve().parents[2] / "infra" / "main.tf").read_text(encoding="utf-8")
    assert main_tf.count("ALLOW_ANONYMOUS_SYNTHETIC") == 1
    assert '} : { ALLOW_ANONYMOUS_SYNTHETIC = "1" }' in main_tf, "the else branch of `auth_mode == entra`"
    assert 'local.auth_mode == "entra" ? {\n    AUTH_TENANT_ID' in main_tf

def test_the_suite_says_both_halves_of_the_opt_in_explicitly():
    import os

    assert os.environ["ENVIRONMENT"] == "local" and os.environ["AUTH_MODE"] == "none"
    assert check_deployment_configuration()["auth_mode"] == "none"
