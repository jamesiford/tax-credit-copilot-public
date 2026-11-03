"""Narration as one service. [AI-02, AI-07]

Pipelines ask for "this agent's answer to this prompt"; this resolves the agent
from the roster and the providers from the router and streams. It is the single
place cross-cutting model concerns attach, so no pipeline can forget them: today the
prompt-injection screen, in front of the provider chain.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any

from application.ai.router import ModelRouter
from application.ai.safety.injection import PromptInjectionGuard
from application.ai.specs import SpecRegistry
from domain.ai import ModelEvent, ModelRole, PromptInjectionBlocked, ProviderStatus

log = logging.getLogger(__name__)


class NarrationService:
    """Resolves an agent and its provider chain, screens the prompt, and streams the answer."""

    def __init__(
        self, specs: SpecRegistry, router: ModelRouter, injection_guard: PromptInjectionGuard | None = None,
        telemetry: Any = None,
    ) -> None:
        self._specs, self._router = specs, router
        self._guard, self._telemetry = injection_guard, telemetry

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

    def _screen(self, agent_name: str, prompt: str) -> None:
        """Refuse to send a prompt that tries to instruct the model. Logs rule names, never text."""
        if self._guard is None:
            return
        verdict = self._guard.scan(prompt)
        if verdict.flagged:
            log.warning("prompt for %s not sent: injection rules %s", agent_name, ",".join(verdict.rules))
            if self._telemetry is not None:
                self._telemetry.count("ai.injection_blocked", agent=agent_name)
            raise PromptInjectionBlocked(verdict.rules)

    async def stream(self, agent_name: str, prompt: str, *, role: ModelRole | None = None) -> AsyncIterator[ModelEvent]:
        self._screen(agent_name, prompt)
        spec = self._specs.get(agent_name)
        async for event in self._router.chain(role or spec.role).stream(spec, prompt):
            yield event

    def statuses(self) -> list[ProviderStatus]:
        return self._router.statuses()

    @property
    def agent_count(self) -> int:
        return len(self._specs)
