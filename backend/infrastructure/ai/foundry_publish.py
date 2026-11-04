"""Publishing prompt agents to Foundry, idempotently. [AI-02]

Foundry agent versions are immutable, so `create_version` ALWAYS creates. Startup
runs on every restart, deploy and scale-out, and with `minReplicas: 0` each cold
start used to mint a fresh version of every agent, forever. Reusing the newest
version when its definition is identical keeps registration idempotent; a changed
prompt or model still publishes a new version, which is what immutability is for.

A pinned version (`AI_AGENT_VERSION_PINS`) bypasses "latest" entirely: it is
fetched, not created, so a rollback is a setting and never a deploy.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from domain.ai import AgentSpec, supports_temperature

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishedAgent:
    """One agent as published: the catalog entry the runtime binds to."""

    name: str
    version: str
    agent_id: str
    portal_url: str
    model: str
    published_name: str


def portal_url_for(project_endpoint: str, agent_id: str) -> str:
    """A deep link into the Foundry portal for the boot log."""
    match = re.match(r"https://([^.]+)\.services\.ai\.azure\.com/api/projects/([^/]+)", project_endpoint)
    if not match:
        return "https://ai.azure.com/"
    account, project = match.group(1), match.group(2)
    return f"https://ai.azure.com/build/agents?wsid=/projects/{project}&account={account}#{agent_id}"


def definitions_match(existing: object, model: str, instructions: str) -> bool:
    """Would publishing this definition produce anything new?"""
    current = getattr(existing, "definition", None) or existing
    return (
        str(getattr(current, "model", "")) == model
        and str(getattr(current, "instructions", "")) == instructions
    )


def latest_version(project_client: Any, name: str) -> Any | None:
    """The newest published version of an agent, or None if it has none."""
    try:
        versions = list(project_client.agents.list_versions(name))
    except Exception:  # noqa: BLE001 - an unreadable list is "no version"; create_version decides
        return None

    def _key(version: object) -> int:
        try:
            return int(str(getattr(version, "version", "0")))
        except ValueError:
            return 0

    return max(versions, key=_key) if versions else None


def _definition(model: str, instructions: str, temperature: float | None):
    from azure.ai.projects.models import PromptAgentDefinition

    kwargs: dict[str, Any] = {"model": model, "instructions": instructions}
    bare = model.rsplit("/", 1)[-1]
    if temperature is not None and supports_temperature(bare):
        kwargs["temperature"] = temperature
    return PromptAgentDefinition(**kwargs)


def publish_agent(
    project_client: Any, project_endpoint: str, spec: AgentSpec, *, model: str, published_name: str,
    pin: str | None = None,
) -> PublishedAgent:
    """Publish (or reuse, or fetch the pinned version of) one agent."""
    if pin:
        info = project_client.agents.get_version(published_name, pin)
        log.info("Pinned Foundry agent version: %s v%s", published_name, pin)
    else:
        existing = latest_version(project_client, published_name)
        if existing is not None and definitions_match(existing, model, spec.instructions):
            info = existing
            log.info("Reusing Foundry agent version: %s v%s", published_name, getattr(existing, "version", "?"))
        else:
            info = project_client.agents.create_version(
                published_name, definition=_definition(model, spec.instructions, spec.temperature),
            )
    agent_id = getattr(info, "id", None) or getattr(info, "agent_id", "") or published_name
    return PublishedAgent(
        name=spec.name, version=str(getattr(info, "version", "1")), agent_id=agent_id,
        portal_url=portal_url_for(project_endpoint, agent_id), model=model, published_name=published_name,
    )
