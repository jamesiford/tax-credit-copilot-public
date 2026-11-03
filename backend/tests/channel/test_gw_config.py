"""Gateway settings and the refusal to start misconfigured. [CH-06]

There is no unauthenticated mode to turn on: the gateway has no `AUTH_MODE=none`, and a
deployed one does not start on a non-durable store. A misconfiguration names every
problem at once and raises before the app exists.
"""
from __future__ import annotations

import importlib
import sys

import pytest

from channel.app import create_app
from channel.config import GatewayConfigurationError, load_settings
from gateway_harness import API_AUDIENCE, GATEWAY_AUDIENCE, ORCHESTRATOR_APP, TENANT

ENV = {"TENANT_ID": TENANT, "GATEWAY_AUDIENCE": GATEWAY_AUDIENCE, "API_BASE_URL": "https://api.example.test/",
       "API_AUDIENCE": API_AUDIENCE}


def test_the_minimal_environment_loads_with_safe_defaults():
    s = load_settings(ENV)
    assert (s.tenant_id, s.api_base_url, s.gateway_audience) == (TENANT, "https://api.example.test", GATEWAY_AUDIENCE)
    assert s.rate_limit_per_minute == 60 and s.request_timeout_seconds == 30.0
    assert s.debug_whoami is False and s.allowed_caller_app_ids == () and s.deployed is False
    assert s.api_scope == f"{API_AUDIENCE}/.default"


def test_the_request_timeout_sits_just_above_the_apis_own():
    from application.capabilities.invoke import DEFAULT_TIMEOUT_SECONDS

    assert load_settings(ENV).request_timeout_seconds > DEFAULT_TIMEOUT_SECONDS


@pytest.mark.parametrize("missing", sorted(ENV))
def test_each_required_setting_is_required(missing):
    env = {k: v for k, v in ENV.items() if k != missing}
    with pytest.raises(GatewayConfigurationError, match=missing):
        load_settings(env)


def test_every_problem_is_named_at_once():
    with pytest.raises(GatewayConfigurationError) as raised:
        load_settings({"AUTH_MODE": "none", "ENVIRONMENT": "prod", "CHANNEL_STORE": "sqlite"})
    text = str(raised.value)
    for needle in ("TENANT_ID", "GATEWAY_AUDIENCE", "AUTH_MODE", "CHANNEL_STORE"):
        assert needle in text


@pytest.mark.parametrize("environment", [{}, {"ENVIRONMENT": "prod", "DATA_CLASSIFICATION": "synthetic"}], ids=["local", "deployed"])
def test_the_gateway_has_no_unauthenticated_mode(environment):
    with pytest.raises(GatewayConfigurationError, match="no unauthenticated mode"):
        load_settings({**ENV, **environment, "AUTH_MODE": "none"})
    assert load_settings({**ENV, **environment, "AUTH_MODE": "entra"})


def test_a_deployed_gateway_needs_the_durable_store():
    with pytest.raises(GatewayConfigurationError, match="not durable"):
        load_settings({**ENV, "ENVIRONMENT": "prod", "CHANNEL_STORE": "sqlite"})
    with pytest.raises(GatewayConfigurationError, match="not durable"):
        load_settings({**ENV, "ENVIRONMENT": "prod", "CHANNEL_STORE": "memory"})
    assert load_settings({**ENV, "ENVIRONMENT": "prod", "CHANNEL_STORE": "warehouse"}).channel_store == "warehouse"
    assert load_settings({**ENV, "ENVIRONMENT": "prod"}).channel_store == "warehouse", "durable by default once deployed"
    assert load_settings({**ENV, "CHANNEL_STORE": "sqlite"}).channel_store == "sqlite", "local may use a file"


def test_the_tenant_must_be_a_guid():
    with pytest.raises(GatewayConfigurationError, match="GUID"):
        load_settings({**ENV, "TENANT_ID": "contoso"})


@pytest.mark.parametrize("name, value", [("CHANNEL_RATE_LIMIT_PER_MINUTE", "0"), ("CHANNEL_RATE_LIMIT_PER_MINUTE", "many"),
                                          ("CHANNEL_REQUEST_TIMEOUT_SECONDS", "0"), ("CHANNEL_REQUEST_TIMEOUT_SECONDS", "slow")])
def test_a_bad_number_is_refused_not_defaulted(name, value):
    with pytest.raises(GatewayConfigurationError, match=name):
        load_settings({**ENV, name: value})


def test_the_allow_list_and_the_debug_switch_parse():
    s = load_settings({**ENV, "CHANNEL_ALLOWED_CALLER_APP_IDS": f" {ORCHESTRATOR_APP.upper()} , other-app ,", "CHANNEL_DEBUG_WHOAMI": "True"})
    assert s.allowed_caller_app_ids == (ORCHESTRATOR_APP, "other-app") and s.debug_whoami is True
    assert load_settings({**ENV, "CHANNEL_ALLOWED_CALLER_APP_IDS": ""}).allowed_caller_app_ids == ()


def test_the_app_will_not_build_without_settings(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(GatewayConfigurationError):
        create_app()


def test_the_entry_point_does_not_bind_when_misconfigured(monkeypatch):
    for name in ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setitem(sys.modules, "channel.main", None)
    monkeypatch.delitem(sys.modules, "channel.main")
    with pytest.raises(GatewayConfigurationError):
        importlib.import_module("channel.main")
    assert "channel.main" not in sys.modules


def test_the_entry_point_builds_when_configured(monkeypatch):
    for name, value in ENV.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delitem(sys.modules, "channel.main", raising=False)
    module = importlib.import_module("channel.main")
    assert module.app.title == "Tax Credit Copilot channel gateway"
    sys.modules.pop("channel.main", None)


def test_the_gateway_serves_no_docs_or_schema(tmp_path):
    from gateway_harness import build_gateway

    gw = build_gateway(tmp_path)
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert gw.client.get(path).status_code == 404
