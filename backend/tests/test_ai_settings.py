"""AI settings: one place, validated at startup. [AI-02, AI-03]

A configuration that would fail at the first question, or send a prompt somewhere
unsafe, must stop the process instead. Every variable is also required to be
documented: a setting nobody can find in ENV-VARS.md is a setting nobody sets.
"""
from __future__ import annotations

import pathlib
import re

import pytest

from application.ai.gateway_settings import GatewayConfigurationError, load_gateway_settings
from application.ai.settings import AiConfigurationError, AiSettings, load_ai_settings, parse_pins
from domain.ai import ModelRole

GW = {"AI_GATEWAY_ENDPOINT": "https://gw.example.com", "AI_GATEWAY_AUTH": "api_key", "AI_GATEWAY_API_KEY": "k"}


def test_the_defaults_are_foundry_only_and_allow_all():
    s = load_ai_settings({})
    assert s.provider_chain == ("foundry",) and s.egress_policy == "allow_all" and s.gateway is None
    assert s.chain_for(ModelRole.NARRATOR) == ("foundry",) and s.model_for(ModelRole.NARRATOR, "foundry") == "gpt-5.4-mini"


def test_foundry_model_keeps_its_existing_name():
    assert load_ai_settings({"FOUNDRY_MODEL": "gpt-x"}).model_for(ModelRole.ROUTER, "foundry") == "gpt-x"


def test_the_chain_is_ordered_and_roles_can_override_it():
    s = load_ai_settings({**GW, "AI_PROVIDER_CHAIN": "gateway, Foundry", "AI_PROVIDER_CHAIN__ROUTER": "foundry",
                          "AI_MODEL_NARRATOR__GATEWAY": "big"})
    assert s.chain_for(ModelRole.NARRATOR) == ("gateway", "foundry") and s.chain_for(ModelRole.ROUTER) == ("foundry",)
    assert set(s.providers_in_use) == {"gateway", "foundry"}


def test_model_resolution_prefers_the_provider_specific_name_then_the_role_wide_one():
    s = load_ai_settings({**GW, "AI_PROVIDER_CHAIN": "gateway", "AI_MODEL_NARRATOR": "wide",
                          "AI_MODEL_NARRATOR__GATEWAY": "specific", "AI_MODEL_ROUTER": "r"})
    assert s.model_for(ModelRole.NARRATOR, "gateway") == "specific"
    assert s.model_for(ModelRole.ROUTER, "gateway") == "r"


def test_a_gateway_model_with_no_name_is_a_clear_error_not_a_guess():
    s = load_ai_settings({**GW, "AI_PROVIDER_CHAIN": "gateway"})
    with pytest.raises(AiConfigurationError, match="AI_MODEL_NARRATOR__GATEWAY"):
        s.model_for(ModelRole.NARRATOR, "gateway")


def test_version_pins_parse_and_a_malformed_pair_is_an_error():
    assert parse_pins("A=3, B=7") == {"A": "3", "B": "7"} and parse_pins("") == {}
    for bad in ("A", "A=", "=3"):
        with pytest.raises(AiConfigurationError, match="AI_AGENT_VERSION_PINS"):
            parse_pins(bad)


def test_an_unknown_egress_policy_is_refused():
    with pytest.raises(AiConfigurationError, match="AI_EGRESS_POLICY"):
        load_ai_settings({"AI_EGRESS_POLICY": "mostly"})


def test_budgets_and_resilience_numbers_are_read_and_validated():
    s = load_ai_settings({"AI_TOKEN_BUDGET_DAILY": "1000", "AI_TOKEN_BUDGET_PER_PRINCIPAL_DAILY": "100",
                          "AI_RETRY_MAX_ATTEMPTS": "5", "AI_CALL_TIMEOUT_SECONDS": "12.5"})
    assert (s.budget_global_daily, s.budget_principal_daily) == (1000, 100)
    assert s.resilience.retry_attempts == 5 and s.resilience.call_timeout_s == 12.5
    with pytest.raises(AiConfigurationError, match="AI_RETRY_MAX_ATTEMPTS"):
        load_ai_settings({"AI_RETRY_MAX_ATTEMPTS": "many"})


def test_the_connection_provider_needs_its_connection_name():
    with pytest.raises(AiConfigurationError, match="AI_FOUNDRY_CONNECTION_NAME"):
        load_ai_settings({"AI_PROVIDER_CHAIN": "foundry_connection"})
    assert load_ai_settings({"AI_PROVIDER_CHAIN": "foundry_connection", "AI_FOUNDRY_CONNECTION_NAME": "gw"}).connection_name == "gw"


# ----------------------------------------------------------------------- gateway


def test_there_is_no_default_auth_scheme_a_gateway_must_choose_one():
    with pytest.raises(GatewayConfigurationError, match="AI_GATEWAY_AUTH must be set explicitly"):
        load_ai_settings({"AI_PROVIDER_CHAIN": "gateway", "AI_GATEWAY_ENDPOINT": "https://gw.example.com"})


def test_a_gateway_in_the_chain_needs_an_endpoint():
    with pytest.raises(GatewayConfigurationError, match="AI_GATEWAY_ENDPOINT"):
        load_ai_settings({"AI_PROVIDER_CHAIN": "gateway", "AI_GATEWAY_AUTH": "none"})


@pytest.mark.parametrize("env, missing", [
    ({"AI_GATEWAY_AUTH": "api_key"}, "AI_GATEWAY_API_KEY"),
    ({"AI_GATEWAY_AUTH": "oauth_client_credentials"}, "AI_GATEWAY_OAUTH_TOKEN_URL"),
    ({"AI_GATEWAY_AUTH": "oauth_client_credentials", "AI_GATEWAY_OAUTH_TOKEN_URL": "https://t", "AI_GATEWAY_OAUTH_CLIENT_ID": "c"},
     "AI_GATEWAY_OAUTH_CLIENT_SECRET"),
    ({"AI_GATEWAY_AUTH": "entra_token"}, "AI_GATEWAY_ENTRA_AUDIENCE"),
])
def test_each_scheme_names_what_it_cannot_work_without(env, missing):
    with pytest.raises(GatewayConfigurationError, match=missing):
        load_gateway_settings({"AI_GATEWAY_ENDPOINT": "https://gw.example.com", **env})


def test_the_gateway_must_be_https_and_the_style_known():
    with pytest.raises(GatewayConfigurationError, match="https"):
        load_gateway_settings({**GW, "AI_GATEWAY_ENDPOINT": "http://gw.example.com"})
    with pytest.raises(GatewayConfigurationError, match="AI_GATEWAY_API_STYLE"):
        load_gateway_settings({**GW, "AI_GATEWAY_API_STYLE": "soap"})
    with pytest.raises(GatewayConfigurationError, match="AI_GATEWAY_EXTRA_HEADERS"):
        load_gateway_settings({**GW, "AI_GATEWAY_EXTRA_HEADERS": "[1]"})


def test_gateway_options_are_read():
    s = load_gateway_settings({**GW, "AI_GATEWAY_ENDPOINT": "https://gw.example.com/", "AI_GATEWAY_STREAMING": "false",
                               "AI_GATEWAY_SUPPORTS_TOOLS": "no", "AI_GATEWAY_TIMEOUT_SECONDS": "9",
                               "AI_GATEWAY_EXTRA_HEADERS": '{"X-Team": "tax"}', "AI_GATEWAY_API_KEY_HEADER": "x-api-key",
                               "AI_GATEWAY_API_KEY_PREFIX": ""})
    assert s.endpoint == "https://gw.example.com" and not s.streaming and not s.supports_tools
    assert s.timeout_s == 9.0 and s.extra_headers == {"X-Team": "tax"} and s.api_key_header == "x-api-key" and s.api_key_prefix == ""


# ----------------------------------------------------- refuse to start when deployed


def _env(**extra):
    return {"ENVIRONMENT": "azure", "DATA_CLASSIFICATION": "synthetic", "CLAIM_STORE": "warehouse",
            "AUTH_MODE": "none", "ALLOW_ANONYMOUS_SYNTHETIC": "1",
            "FINDING_STORE": "warehouse", "RUN_MANIFEST_STORE": "warehouse", "ARTIFACT_STORE": "blob",
            "ARTIFACT_REPOSITORY": "warehouse", "OVERRIDE_STORE": "warehouse", "CHANNEL_STORE": "warehouse", **extra}


def test_a_deployed_process_refuses_to_skip_tls_verification_for_the_gateway():
    from application.deployment import DeploymentConfigurationError, check_deployment_configuration

    env = _env(AI_PROVIDER_CHAIN="gateway", **GW, AI_GATEWAY_TLS_VERIFY="false")
    with pytest.raises(DeploymentConfigurationError, match="AI_GATEWAY_TLS_VERIFY"):
        check_deployment_configuration(env)
    local = {**env, "ENVIRONMENT": "local"}
    assert check_deployment_configuration(local)["environment"] == "local"


def test_a_deployed_process_refuses_an_unauthenticated_gateway():
    from application.deployment import DeploymentConfigurationError, check_deployment_configuration

    env = _env(AI_PROVIDER_CHAIN="gateway", AI_GATEWAY_ENDPOINT="https://gw.example.com", AI_GATEWAY_AUTH="none")
    with pytest.raises(DeploymentConfigurationError, match="AI_GATEWAY_AUTH=none"):
        check_deployment_configuration(env)


def test_a_bad_ai_configuration_stops_startup_with_the_message():
    from application.deployment import DeploymentConfigurationError, check_deployment_configuration

    with pytest.raises(DeploymentConfigurationError, match="AI_GATEWAY_AUTH must be set explicitly"):
        check_deployment_configuration(_env(AI_PROVIDER_CHAIN="gateway", AI_GATEWAY_ENDPOINT="https://gw.example.com"))


def test_the_default_ai_configuration_does_not_disturb_an_existing_deployment():
    from application.deployment import check_deployment_configuration

    assert check_deployment_configuration(_env())["environment"] == "azure"


# --------------------------------------------------------------- documentation


def test_every_ai_variable_the_code_reads_is_documented():
    root = pathlib.Path(__file__).resolve().parents[2]
    docs = (root / "docs" / "architecture" / "ENV-VARS.md").read_text(encoding="utf-8")
    source = "".join(
        (root / "backend" / "application" / "ai" / name).read_text(encoding="utf-8")
        for name in ("settings.py", "gateway_settings.py")
    )
    names = set(re.findall(r'"(AI_[A-Z0-9_]+)"', source)) | set(re.findall(r"AI_MODEL_<ROLE>|AI_PROVIDER_CHAIN__<ROLE>", source))
    names |= {f"AI_MODEL_{r}" for r in ("ROUTER", "NARRATOR", "ANALYSIS")}
    missing = sorted(n for n in names if n not in docs and not n.startswith("AI_MODEL_<") and not n.startswith("AI_PROVIDER_CHAIN__<"))
    assert not missing, f"undocumented in docs/architecture/ENV-VARS.md: {missing}"
