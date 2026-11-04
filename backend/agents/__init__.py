"""Agent modules: one display profile per agent; the declaration is `agents.json`.

Each module exports `NAME`, `INSTRUCTIONS`, `AGENT_PROFILE` and `SPEC`, the last built by
`roster.build_spec` from the one list in `agents/agents.json` (name, prompt file, model
role, temperature, tools). `agents.factory.all_specs()` yields the roster as data; the
provider that serves an agent publishes and runs it (`infrastructure/ai/`). No agent holds
a tool: tools calculate, agents narrate.
"""
from .factory import all_specs, list_agent_modules

__all__ = ["all_specs", "list_agent_modules"]
