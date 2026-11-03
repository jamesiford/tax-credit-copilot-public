"""Agent modules: one per agent, each exporting a spec.

Each module exports `NAME`, `INSTRUCTIONS` (loaded from `agents/prompts/`),
`AGENT_PROFILE` and `SPEC`. `agents.factory.all_specs()` yields the roster as
data; the provider that serves an agent publishes and runs it
(`infrastructure/ai/`). No agent holds a tool: tools calculate, agents narrate.
"""
from .factory import all_specs, list_agent_modules

__all__ = ["all_specs", "list_agent_modules"]
