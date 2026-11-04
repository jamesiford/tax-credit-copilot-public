"""The agent roster. [AI-02, RM-11]

`agents/agents.json` is the single source of truth for which agents ship and how each is
published (name, instructions file, model role, temperature, tools). Add an agent by adding
an entry there, its prompt under `agents/prompts/`, and a module under `backend/agents/`
that holds its display profile and calls `build_spec`; there is no second list to keep in step.

This module imports NO SDK. Publishing and running an agent is the provider's job
(`infrastructure/ai/`), driven by the specs this roster yields.
"""
from __future__ import annotations

from domain.ai import AgentSpec, supports_temperature

from .roster import agent_modules

#: Kept under its old name: callers and tests import it from here.
_supports_temperature = supports_temperature


def list_agent_modules():
    """Every agent module, in the order `agents.json` lists them."""
    return agent_modules()


def all_specs() -> list[AgentSpec]:
    """The roster as data, for the spec registry and the catalog."""
    return [module.SPEC for module in list_agent_modules()]
