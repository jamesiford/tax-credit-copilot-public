"""The agent roster as data. [AI-02]

Replaces eleven near-identical `build()` bodies: an agent module now exports an
`AgentSpec`, and everything that used to be done per module — publishing,
version reuse, runtime construction — is done once, from this registry, by the
provider that serves it.
"""
from __future__ import annotations

from collections.abc import Iterable

from domain.ai import AgentSpec


class UnknownAgent(KeyError):
    """No agent of that name is on the roster."""


#: Every agent the portal chat's full pipelines need. A gap in this set means the
#: scripted stream rather than a half-working answer, because a partial roster
#: hides WHICH agent is missing.
CHAT_PIPELINE_AGENTS = (
    "OrchestratorAgent", "PayrollIngestAgent", "HeadcountAgent", "CreditRulesAgent",
    "CreditDiscoveryAgent", "ReportingAgent", "ClientSituationAgent",
)


class SpecRegistry:
    """Name -> spec. Duplicate names are refused: the catalog keys on name, so a
    duplicate would silently replace another agent's prompt."""

    def __init__(self, specs: Iterable[AgentSpec]) -> None:
        self._by_name: dict[str, AgentSpec] = {}
        for spec in specs:
            if spec.name in self._by_name:
                raise ValueError(f"duplicate agent name {spec.name!r}")
            self._by_name[spec.name] = spec

    def get(self, name: str) -> AgentSpec:
        try:
            return self._by_name[name]
        except KeyError:
            raise UnknownAgent(name) from None

    def names(self) -> tuple[str, ...]:
        return tuple(self._by_name)

    def __iter__(self):
        return iter(self._by_name.values())

    def __len__(self) -> int:
        return len(self._by_name)
