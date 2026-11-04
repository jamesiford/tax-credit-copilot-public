"""Chooses the providers for a job. [AI-02]

`role -> ordered providers` comes from settings (`AI_PROVIDER_CHAIN`, with
per-role overrides), so "narrator on the gateway, router on Foundry" is
configuration. Each provider is built once, on first use, and handed to
`decorate` — the hook where resilience (timeout, retry, breaker, bulkhead) and
the egress and budget guards are layered on, so the router itself stays a lookup.
"""
from __future__ import annotations

from collections.abc import Callable

from application.ai.chain import ProviderChain
from application.ai.ports import AgentRuntime
from application.ai.providers import ProviderRegistry
from application.ai.settings import AiSettings
from domain.ai import ModelRole, ProviderStatus

Decorator = Callable[[AgentRuntime, str], AgentRuntime]


class ModelRouter:
    """Builds each provider once, decorates it, and hands out the chain for a role."""

    def __init__(
        self, settings: AiSettings, registry: ProviderRegistry, decorate: Decorator | None = None,
    ) -> None:
        self._settings, self._registry = settings, registry
        self._decorate = decorate or (lambda runtime, _name: runtime)
        self._runtimes: dict[str, AgentRuntime] = {}

    def runtime(self, provider: str) -> AgentRuntime:
        if provider not in self._runtimes:
            built = self._registry.build(provider, self._settings)
            self._runtimes[provider] = self._decorate(built, provider)
        return self._runtimes[provider]

    def chain(self, role: ModelRole) -> ProviderChain:
        return ProviderChain([self.runtime(p) for p in self._settings.chain_for(role)])

    def statuses(self) -> list[ProviderStatus]:
        """Every provider in use, built if need be, so health reports what a request would meet."""
        return [self.runtime(p).status() for p in self._settings.providers_in_use]
