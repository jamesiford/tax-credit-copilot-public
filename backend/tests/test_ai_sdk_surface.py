"""The SDK symbols the AI adapters use, pinned. [AI-01]

A version bump should fail HERE, with a message naming the symbol, rather than at
runtime in a deployed app. These tests deliberately check only what this product
calls — import paths, constructor keywords, enum members — not the SDKs'
whole surface: a broad snapshot would fail on harmless additions and be ignored.

When a test here fails after a bump, read the SDK changelog, fix the one adapter
that uses the symbol (infrastructure/ai/**), and update the expectation with the
reason in docs/m365-channel/DECISIONS.md.
"""
from __future__ import annotations

import inspect

import pytest

pytest.importorskip("agent_framework_foundry")


def _params(callable_) -> set[str]:
    return set(inspect.signature(callable_).parameters)


def test_foundry_agent_takes_the_keywords_the_runtime_passes():
    """`FoundryAgent(project_endpoint=, agent_name=, agent_version=, credential=)`."""
    from agent_framework_foundry import FoundryAgent

    assert {"project_endpoint", "agent_name", "agent_version", "credential"} <= _params(FoundryAgent.__init__)


def test_foundry_agent_run_streams():
    """`agent.run(prompt, stream=True)` is the one call every pipeline makes."""
    from agent_framework_foundry import FoundryAgent

    params = _params(FoundryAgent.run)
    assert {"messages", "stream"} <= params


def test_the_stream_yields_updates_that_expose_text():
    """The adapter reads `.text` off each update; the type must still carry it."""
    from agent_framework import AgentResponseUpdate

    assert "text" in {n for n in dir(AgentResponseUpdate) if not n.startswith("_")}


def test_project_client_and_prompt_agent_definition_import():
    from azure.ai.projects import AIProjectClient
    from azure.ai.projects.models import PromptAgentDefinition

    assert "endpoint" in _params(AIProjectClient.__init__) and "credential" in _params(AIProjectClient.__init__)
    definition = PromptAgentDefinition(model="m", instructions="i")
    assert definition.model == "m" and definition.instructions == "i"


def test_agent_versions_api_still_has_the_three_calls_the_catalog_makes():
    from azure.ai.projects.operations import AgentsOperations

    for name in ("create_version", "list_versions", "get_version"):
        assert callable(getattr(AgentsOperations, name)), name
    assert {"agent_name", "definition"} <= _params(AgentsOperations.create_version)
    assert "agent_name" in _params(AgentsOperations.list_versions)


def test_prompt_agent_definition_accepts_temperature():
    from azure.ai.projects.models import PromptAgentDefinition

    assert PromptAgentDefinition(model="m", instructions="i", temperature=0.2).temperature == 0.2


def test_default_azure_credential_has_the_token_call_the_gateway_auth_uses():
    from azure.identity import DefaultAzureCredential

    assert callable(DefaultAzureCredential.get_token)


def test_opentelemetry_api_has_the_tracer_and_meter_entry_points():
    from opentelemetry import metrics, trace

    assert callable(trace.get_tracer) and callable(metrics.get_meter)


def test_azure_monitor_distro_exposes_configure():
    """Takes `**kwargs`, one of which is `connection_string` (see telemetry.py)."""
    from azure.monitor.opentelemetry import configure_azure_monitor

    assert callable(configure_azure_monitor)
    assert "kwargs" in _params(configure_azure_monitor)


def test_httpx_has_the_streaming_and_mock_transport_surface():
    """The gateway adapter streams with `Client.stream`; tests use `MockTransport`."""
    import httpx

    assert callable(httpx.Client.stream) and callable(httpx.AsyncClient.stream)
    assert callable(httpx.MockTransport)
    assert {"timeout", "verify", "transport"} <= _params(httpx.AsyncClient.__init__)
