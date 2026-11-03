"""Which providers exist, and how to build one. [AI-02]

Adding a provider is ONE new adapter module and ONE `register(...)` call from the
composition root — no pipeline, router or handler changes. That is the open/closed
property, and `tests/test_ai_extensibility.py` proves it by registering a fake
provider from inside the test.

A factory takes the frozen settings and returns an `AgentRuntime`. A provider
that is configured but cannot work (a missing endpoint) should raise
`AiConfigurationError` from its factory so startup says so, rather than the first
question failing.
"""
from __future__ import annotations

from collections.abc import Callable

from application.ai.ports import AgentRuntime
from application.ai.settings import AiConfigurationError, AiSettings

ProviderFactory = Callable[[AiSettings], AgentRuntime]


class ProviderRegistry:
    """Name -> factory. Re-registering a name raises: two adapters for one name
    resolve by import order, which is not a decision."""

    def __init__(self) -> None:
        self._factories: dict[str, ProviderFactory] = {}

    def register(self, name: str, factory: ProviderFactory) -> None:
        if name in self._factories:
            raise ValueError(f"provider {name!r} is already registered")
        self._factories[name] = factory

    def build(self, name: str, settings: AiSettings) -> AgentRuntime:
        try:
            factory = self._factories[name]
        except KeyError:
            raise AiConfigurationError(
                f"unknown provider {name!r}; registered: {sorted(self._factories)}"
            ) from None
        return factory(settings)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))
