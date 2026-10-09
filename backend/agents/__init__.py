"""Foundry agent registry.

Each specialist agent module exports `build(ctx)` which:
  1. Constructs a local AF `Agent` with the Foundry chat client + tools + instructions.
  2. Calls `to_prompt_agent()` then `project_client.agents.create_version()` to publish.
  3. Returns a `FoundryAgent` bound to the published version, ready for `.run_stream()`.

`backend.agents.factory.build_all()` wires the project client + model, calls each
agent's `build()` in order, and returns the populated registry + a list of
(name, agent_id, version, portal_url) tuples for the boot-log deep links.
"""
from .factory import AgentRecord, AgentRegistry, build_all

__all__ = ["AgentRecord", "AgentRegistry", "build_all"]
