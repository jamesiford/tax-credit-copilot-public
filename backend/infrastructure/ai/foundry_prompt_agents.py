"""Foundry prompt agents: the catalog that publishes them and the runtime that calls them. [AI-02]

`FoundryAgentCatalog` implements `AgentCatalog` — it publishes the roster in the
background so startup never waits on Foundry, tracks what is ready, and reports a
health state. `FoundryAgentRuntime` implements `AgentRuntime` — it streams one
published agent's answer. Both take their SDK touchpoints as injectable factories,
so a stub drives the same code a real project would.

Everything the SDKs raise is mapped onto the small error taxonomy
(`domain.ai`): callers decide between "try the next provider" and "give up" and
never need to know a Foundry exception type.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import AsyncIterator, Callable, Iterable, Sequence
from typing import Any

from application.ai.settings import AiSettings
from domain.ai import (
    AgentSpec, ModelAuth, ModelBadRequest, ModelEvent, ModelRateLimited, ModelUnavailable, ProviderStatus,
    StreamEnd, TextDelta,
)
from infrastructure.ai.foundry_publish import PublishedAgent, publish_agent

log = logging.getLogger(__name__)

ClientFactory = Callable[[], Any]
ModelFor = Callable[[AgentSpec], str]


def _default_client(endpoint: str) -> Any:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    return AIProjectClient(endpoint=endpoint, credential=DefaultAzureCredential())


class FoundryAgentCatalog:
    """Publishes the roster to a Foundry project and remembers what it published."""

    def __init__(
        self, settings: AiSettings, specs: Iterable[AgentSpec], *, model_for: ModelFor | None = None,
        variant: tuple[str, str] = ("foundry", ""), client_factory: ClientFactory | None = None,
        sleep: Callable[[float], None] = time.sleep, attempts: int = 5,
    ) -> None:
        """`variant` is (provider name, suffix appended to each published agent name)."""
        self._settings, self._specs = settings, tuple(specs)
        self._model_for = model_for or (lambda spec: settings.model_for(spec.role, "foundry"))
        (self.provider, self._suffix), self._sleep, self._attempts = variant, sleep, attempts
        self._client_factory = client_factory or (lambda: _default_client(settings.foundry_endpoint))
        self._entries: dict[str, PublishedAgent] = {}
        self._state, self._detail = ("warming", "") if settings.foundry_endpoint else ("disabled", "FOUNDRY_PROJECT_ENDPOINT is not set")
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def endpoint(self) -> str:
        return self._settings.foundry_endpoint

    def warm(self, *, background: bool = True) -> None:
        """Publish every agent, with backoff, without blocking the caller.

        A failure leaves the app serving the scripted path rather than failing
        startup: the engine works without a model.
        """
        if self._state == "disabled":
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            if background:
                self._thread = threading.Thread(target=self._warm_loop, name="foundry-warm", daemon=True)
                self._thread.start()
                return
        self._warm_loop()

    def _warm_loop(self) -> None:
        delay = 2.0
        for attempt in range(1, self._attempts + 1):
            try:
                self.publish_all()
                return
            except Exception as exc:  # noqa: BLE001 - any failure is retried, then reported
                self._state, self._detail = "unavailable", f"{type(exc).__name__}"
                log.warning("Foundry publish attempt %d/%d failed: %s", attempt, self._attempts, type(exc).__name__)
                if attempt < self._attempts:
                    self._sleep(delay)
                    delay = min(delay * 2, 30.0)

    def publish_all(self) -> None:
        """One blocking pass. Raises if the project cannot be reached; a single bad agent degrades."""
        client = self._client_factory()
        failed = []
        for spec in self._specs:
            try:
                self._entries[spec.name] = publish_agent(
                    client, self.endpoint, spec, model=self._model_for(spec),
                    published_name=spec.name + self._suffix, pin=self._settings.version_pins.get(spec.name),
                )
            except Exception as exc:  # noqa: BLE001
                failed.append(spec.name)
                log.error("could not publish %s: %s", spec.name, type(exc).__name__)
        if len(failed) == len(self._specs):
            raise ModelUnavailable("no agent could be published")
        self._state, self._detail = ("degraded", f"unpublished: {', '.join(failed)}") if failed else ("ready", "")
        for entry in self.entries():
            log.info("  %-24s v%-3s id=%s", entry.name, entry.version, entry.agent_id)

    def has(self, agent_name: str) -> bool:
        return agent_name in self._entries

    def entry(self, agent_name: str) -> PublishedAgent | None:
        return self._entries.get(agent_name)

    def version_of(self, agent_name: str) -> str | None:
        entry = self._entries.get(agent_name)
        return entry.version if entry else None

    def entries(self) -> Sequence[PublishedAgent]:
        return list(self._entries.values())

    def status(self) -> ProviderStatus:
        return ProviderStatus(self.provider, self._state, self._detail)


class FoundryAgentRuntime:
    """Streams one published prompt agent's answer."""

    def __init__(
        self, catalog: FoundryAgentCatalog, *, agent_factory: Callable[[PublishedAgent], Any] | None = None,
    ) -> None:
        self._catalog = catalog
        self.name = catalog.provider
        self._factory = agent_factory or self._sdk_agent
        self._agents: dict[str, Any] = {}

    @property
    def catalog(self) -> FoundryAgentCatalog:
        return self._catalog

    def _sdk_agent(self, entry: PublishedAgent) -> Any:
        from agent_framework_foundry import FoundryAgent
        from azure.identity import DefaultAzureCredential

        return FoundryAgent(
            project_endpoint=self._catalog.endpoint, agent_name=entry.published_name,
            agent_version=entry.version, credential=DefaultAzureCredential(),
        )

    def _agent(self, entry: PublishedAgent) -> Any:
        key = f"{entry.published_name}@{entry.version}"
        if key not in self._agents:
            self._agents[key] = self._factory(entry)
        return self._agents[key]

    def ready_for(self, agent_name: str) -> bool:
        return self._catalog.has(agent_name)

    def version_of(self, agent_name: str) -> str | None:
        return self._catalog.version_of(agent_name)

    def status(self) -> ProviderStatus:
        return self._catalog.status()

    async def stream(self, spec: AgentSpec, prompt: str) -> AsyncIterator[ModelEvent]:
        """Run the named Foundry agent over `prompt`; Foundry failures are mapped to the model-error taxonomy."""
        entry = self._catalog.entry(spec.name)
        if entry is None:
            raise ModelUnavailable(f"{spec.name} is not published on {self.name}")
        agent = self._agent(entry)
        try:
            async for update in agent.run(prompt, stream=True):
                text = getattr(update, "text", None) or ""
                if text:
                    yield TextDelta(text)
        except Exception as exc:  # noqa: BLE001 - map, never leak an SDK type
            raise _map_error(exc) from exc
        yield StreamEnd(
            provider=self.name, model=entry.model,
            agent_version=getattr(agent, "agent_version", None) or entry.version,
        )


def _map_error(exc: Exception) -> Exception:
    """SDK exception -> taxonomy. Status codes where there are any, else 'unavailable'."""
    response = getattr(exc, "response", None)
    status = getattr(exc, "status_code", None) or getattr(response, "status_code", None)
    if status in (401, 403):
        return ModelAuth(f"Foundry refused our credentials ({status})")
    if status == 429:
        raw = getattr(response, "headers", {}).get("retry-after") if response is not None else None
        try:
            return ModelRateLimited("Foundry is rate limiting us", float(raw) if raw else None)
        except ValueError:
            return ModelRateLimited("Foundry is rate limiting us")
    if isinstance(status, int) and 400 <= status < 500:
        return ModelBadRequest(f"Foundry rejected the request ({status})")
    return ModelUnavailable(f"Foundry call failed: {type(exc).__name__}")
