"""Narration as one service. [AI-02]

Pipelines ask for "this agent's answer to this prompt"; this resolves the agent
from the roster and the providers from the router and streams. It is the single
place cross-cutting model concerns (injection guard, output policy, budgets) are
attached, so no pipeline can forget them.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Iterable

from application.ai.router import ModelRouter
from application.ai.specs import SpecRegistry
from domain.ai import ModelEvent, ModelRole, ProviderStatus


class NarrationService:
    def __init__(self, specs: SpecRegistry, router: ModelRouter) -> None:
        self._specs, self._router = specs, router

    def available(self, agent_names: Iterable[str]) -> bool:
        """True when every named agent has at least one provider ready to run it.

        Callers use this to choose the scripted stub over a half-working
        pipeline: a partial roster hides which agent is missing.
        """
        try:
            return all(
                self._router.chain(self._specs.get(n).role).ready_for(n) for n in agent_names
            )
        except KeyError:
            return False

    def stream(self, agent_name: str, prompt: str, *, role: ModelRole | None = None) -> AsyncIterator[ModelEvent]:
        spec = self._specs.get(agent_name)
        return self._router.chain(role or spec.role).stream(spec, prompt)

    def statuses(self) -> list[ProviderStatus]:
        return self._router.statuses()

    @property
    def agent_count(self) -> int:
        return len(self._specs)
