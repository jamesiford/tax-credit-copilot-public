"""Prompt agents whose model is reached through a Foundry model connection. [AI-03]

BYOM: Foundry Agent Service calls a model served by a gateway the customer has
connected to the project. The agent's model name takes the form
`<connection-name>/<model-name>`.

Limits that come with this path (Learn, "Bring your own model / AI gateway in
Foundry Agent Service"), stated here so nobody discovers them in production:

- prompt agents ONLY — the hosted MAF orchestrator does not use BYOM;
- the gateway must implement the OpenAI-compatible chat-completions API; the
  Responses API is not supported through BYOM;
- not supported with the Microsoft Copilot harness;
- the model is a non-Microsoft product: content filters and data-handling terms
  are the customer's to review (see `OutputPolicy`).

Agents are published under `<Name>-byom` so a project can hold both a native and a
connection-backed version of the same agent without them overwriting each other's
"latest".
"""
from __future__ import annotations

from collections.abc import Iterable

from application.ai.settings import AiConfigurationError, AiSettings
from domain.ai import AgentSpec
from infrastructure.ai.foundry_prompt_agents import FoundryAgentCatalog, FoundryAgentRuntime

PROVIDER = "foundry_connection"
SUFFIX = "-byom"


def connection_model(settings: AiSettings, spec: AgentSpec) -> str:
    """`<connection>/<model>` for this agent's role."""
    if not settings.connection_name:
        raise AiConfigurationError("AI_FOUNDRY_CONNECTION_NAME is not set")
    return f"{settings.connection_name}/{settings.model_for(spec.role, PROVIDER)}"


def build_connection_runtime(settings: AiSettings, specs: Iterable[AgentSpec], **overrides) -> FoundryAgentRuntime:
    """A runtime over a catalog that publishes connection-backed agents."""
    catalog = FoundryAgentCatalog(
        settings, specs, model_for=lambda spec: connection_model(settings, spec),
        variant=(PROVIDER, SUFFIX), **overrides,
    )
    return FoundryAgentRuntime(catalog)
