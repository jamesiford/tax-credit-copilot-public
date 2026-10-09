"""Shared factory: chat-client wiring + agent registration in Foundry."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

from agent_framework_foundry import FoundryAgent
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition
from azure.identity import DefaultAzureCredential

log = logging.getLogger(__name__)


@dataclass
class AgentRecord:
    name: str
    agent: FoundryAgent
    agent_id: str
    version: str
    portal_url: str
    profile: dict = field(default_factory=dict)


@dataclass
class AgentRegistry:
    project_endpoint: str
    model: str
    by_name: dict[str, AgentRecord] = field(default_factory=dict)

    def add(self, record: AgentRecord) -> None:
        self.by_name[record.name] = record

    def __getitem__(self, name: str) -> AgentRecord:
        return self.by_name[name]

    def __iter__(self):
        return iter(self.by_name.values())


def _portal_url_for(project_endpoint: str, agent_id: str) -> str:
    m = re.match(r"https://([^.]+)\.services\.ai\.azure\.com/api/projects/([^/]+)", project_endpoint)
    if not m:
        return "https://ai.azure.com/"
    account, project = m.group(1), m.group(2)
    return f"https://ai.azure.com/build/agents?wsid=/projects/{project}&account={account}#{agent_id}"


def _supports_temperature(model: str) -> bool:
    """GPT-5 agent deployments reject legacy sampling parameters."""
    return not model.strip().lower().startswith("gpt-5")


def _definitions_match(existing: object, model: str, instructions: str) -> bool:
    """Would publishing this definition produce anything new?"""
    current = getattr(existing, "definition", None) or existing
    return (
        str(getattr(current, "model", "")) == model
        and str(getattr(current, "instructions", "")) == instructions
    )


def _latest_version(project_client: AIProjectClient, name: str):
    """The newest published version of an agent, or None if it has none.

    Agent versions are immutable, so `create_version` always creates. Called on
    every startup that is exactly what it does — and with `minReplicas: 0` the
    container scales to zero, so each cold start minted a fresh version of all
    nine agents, forever. Reusing an identical definition keeps registration
    idempotent; a changed prompt still publishes a new version, which is the
    behaviour the immutability is for.
    """
    try:
        versions = list(project_client.agents.list_versions(name))
    except Exception:
        return None
    if not versions:
        return None

    def _key(v: object) -> int:
        try:
            return int(str(getattr(v, "version", "0")))
        except ValueError:
            return 0

    return max(versions, key=_key)


def register_agent(
    *,
    project_client: AIProjectClient,
    project_endpoint: str,
    credential: DefaultAzureCredential,
    model: str,
    name: str,
    instructions: str,
    temperature: float | None = None,
    profile: dict | None = None,
) -> AgentRecord:
    """Publish a PromptAgent directly via the Foundry v2 SDK and return a
    FoundryAgent runtime wrapper for invocation.

    No tools are registered with Foundry — the Python orchestrator runs tools
    itself and feeds structured results into each agent's prompt at invocation
    time. This keeps tax math 100% in Python and prevents the model from
    inventing numbers.
    """
    definition_kwargs: dict = {"model": model, "instructions": instructions}
    if temperature is not None and _supports_temperature(model):
        definition_kwargs["temperature"] = temperature
    definition = PromptAgentDefinition(**definition_kwargs)

    existing = _latest_version(project_client, name)
    if existing is not None and _definitions_match(existing, model, instructions):
        version_info = existing
        log.info("Reusing Foundry agent version: %s v%s", name, getattr(existing, "version", "?"))
    else:
        version_info = project_client.agents.create_version(name, definition=definition)

    agent_id = getattr(version_info, "id", None) or getattr(version_info, "agent_id", "") or name
    version = str(getattr(version_info, "version", "1"))

    foundry_agent = FoundryAgent(
        project_endpoint=project_endpoint,
        agent_name=name,
        agent_version=version,
        credential=credential,
    )
    portal = _portal_url_for(project_endpoint, agent_id)
    log.info("Registered Foundry agent: %s (id=%s, version=%s)", name, agent_id, version)
    log.info("  -> %s", portal)
    return AgentRecord(
        name=name,
        agent=foundry_agent,
        agent_id=agent_id,
        version=version,
        portal_url=portal,
        profile=profile or {},
    )


def list_agent_modules():
    """Single source of truth for which agent modules ship in the prototype.

    Adding a 7th agent only requires (a) creating a new module under
    backend/agents/ that exports NAME, INSTRUCTIONS, AGENT_PROFILE, build()
    and (b) appending it here. The Agent Workbench page picks it up
    automatically via /api/agents.
    """
    from . import (  # noqa: PLC0415 — deferred to avoid circular import
        orchestrator,
        payroll_ingest,
        headcount,
        credit_rules,
        credit_discovery,
        client_situation,
        page_summary,
        reporting,
        rules_ingestion,
        exception_report,
        legislative_monitor,
    )
    return [
        orchestrator,
        payroll_ingest,
        headcount,
        credit_rules,
        credit_discovery,
        client_situation,
        page_summary,
        reporting,
        rules_ingestion,
        exception_report,
        legislative_monitor,
    ]


def build_all() -> AgentRegistry:
    """Register all agents in Foundry. Each call to build_all() creates a
    new *version* of each named agent; the latest version is what we invoke.

    The set of agents is discovered from `list_agent_modules()` so adding a
    new agent only requires creating the module and appending it there.
    """
    endpoint = os.environ["FOUNDRY_PROJECT_ENDPOINT"]
    model = os.getenv("FOUNDRY_MODEL", "gpt-5.4-mini")
    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=endpoint, credential=credential)

    registry = AgentRegistry(project_endpoint=endpoint, model=model)

    for module in list_agent_modules():
        record = module.build(
            project_client=project_client,
            project_endpoint=endpoint,
            credential=credential,
            model=model,
        )
        registry.add(record)

    return registry
