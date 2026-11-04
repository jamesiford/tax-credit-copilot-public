"""Read the one list of specialist prompt agents. [RM-11, ADR-004]

`agents/agents.json` is the only place an agent's name, instructions file, model role,
temperature and tools are declared. Before this, each of twelve modules declared them
beside its display profile and the roster was a hand-kept import list, so the answer to
"what do we publish to Foundry" was twelve files and a function. A reviewer now reads one
file, and a test fails if a second place declares any of it.

Publishing is unchanged: this module only builds the `AgentSpec`s that
`infrastructure/ai/foundry_publish.py` already publishes (`create_version`, immutable
versions, reuse of an identical definition).

The list holds a model ROLE, not a deployment name: the model is a setting
(`AI_MODEL_<ROLE>`), so a customer changes it without a code edit and the repository never
names a deployment. `tools` must be empty, because agents narrate and tools calculate.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from types import ModuleType

from domain.ai import AgentSpec, ModelRole

from ._prompts import load_instructions

ROSTER_FILE = Path(__file__).with_name("agents.json")
PROMPT_DIR = Path(__file__).with_name("prompts")
_FIELDS = frozenset({"module", "name", "prompt", "role", "temperature", "tools"})


class RosterError(ValueError):
    """`agents.json` cannot be used. Raised on import, not at the first publish."""


@dataclass(frozen=True)
class AgentDeclaration:
    """One agent as declared: everything the publisher needs except the profile the page shows."""

    module: str
    name: str
    prompt: str
    role: ModelRole
    temperature: float | None
    tools: tuple[str, ...] = ()


@dataclass(frozen=True)
class Roster:
    """The declared agents in publishing order, and the prompt files deliberately not agents."""

    agents: tuple[AgentDeclaration, ...]
    excluded_prompts: dict[str, str]

    def by_module(self, module: str) -> AgentDeclaration:
        for declaration in self.agents:
            if declaration.module == module:
                return declaration
        raise RosterError(f"agents.json declares no agent for module {module!r}")


def _role(raw: dict) -> ModelRole:
    try:
        return ModelRole(raw["role"])
    except ValueError as exc:
        raise RosterError(f"{raw['name']}: role must be one of {[r.value for r in ModelRole]}") from exc


def _temperature(raw: dict) -> float | None:
    value = raw["temperature"]
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 2):
        raise RosterError(f"{raw['name']}: temperature is null or a number from 0 to 2")
    return value


def _declaration(raw: object) -> AgentDeclaration:
    if not isinstance(raw, dict) or set(raw) != _FIELDS:
        raise RosterError(f"an agent entry has exactly the fields {sorted(_FIELDS)}: {raw!r}")
    if not all(isinstance(raw[key], str) and raw[key].strip() for key in ("module", "name", "prompt")):
        raise RosterError(f"module, name and prompt are non-empty strings: {raw!r}")
    role, temperature = _role(raw), _temperature(raw)
    if raw["tools"] != []:
        raise RosterError(f"{raw['name']}: agents hold no tools (ADR-004); `tools` must be []")
    return AgentDeclaration(raw["module"], raw["name"], raw["prompt"], role, temperature, ())


def _unique(declarations: tuple[AgentDeclaration, ...]) -> None:
    for field in ("module", "name", "prompt"):
        values = [getattr(d, field) for d in declarations]
        if len(values) != len(set(values)):
            raise RosterError(f"two agents share a {field}: {sorted(v for v in values if values.count(v) > 1)}")


def _prompt_stems() -> set[str]:
    return {path.stem for path in PROMPT_DIR.glob("*.md")}


def _check_prompts(declarations: tuple[AgentDeclaration, ...], excluded: dict[str, str]) -> None:
    """Every prompt file is an agent's or is excluded with a reason, and nothing points at a missing one."""
    present, used = _prompt_stems(), {d.prompt for d in declarations}
    if used - present:
        raise RosterError(f"agents.json names a prompt with no file: {sorted(used - present)}")
    if set(excluded) & used or set(excluded) - present or not all(str(r).strip() for r in excluded.values()):
        raise RosterError("excluded_prompts must name existing, unused prompt files, each with a reason")
    if present - used - set(excluded):
        raise RosterError(f"prompt files that are neither an agent's nor excluded: {sorted(present - used - set(excluded))}")


@lru_cache(maxsize=None)
def load_roster(path: Path = ROSTER_FILE) -> Roster:
    """Parse and validate the list. Fails loudly: a malformed roster must not publish half an estate."""
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("format") != 1 or not isinstance(document.get("agents"), list):
        raise RosterError("agents.json must be format 1 with an `agents` list")
    declarations = tuple(_declaration(raw) for raw in document["agents"])
    _unique(declarations)
    excluded = document.get("excluded_prompts", {})
    _check_prompts(declarations, excluded)
    return Roster(declarations, dict(excluded))


def build_spec(module: str, profile: dict) -> AgentSpec:
    """The `AgentSpec` for the agent whose display profile lives in `agents/<module>.py`."""
    declaration = load_roster().by_module(module)
    return AgentSpec(
        name=declaration.name, instructions=load_instructions(declaration.prompt), role=declaration.role,
        temperature=declaration.temperature, profile=profile,
    )


def agent_modules(roster: Roster | None = None) -> list[ModuleType]:
    """Every agent module, in the order `agents.json` lists them."""
    return [import_module(f"{__package__}.{d.module}") for d in (roster or load_roster()).agents]
