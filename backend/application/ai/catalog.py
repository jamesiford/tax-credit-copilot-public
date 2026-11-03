"""One catalog over every provider's catalog. [AI-02]

More than one provider can publish agents (native Foundry and a connection-backed
one). The app asks one question — "is this agent ready?" — and this answers it
across all of them, so `main.py` warms one thing and `/api/health` reports one
thing.
"""
from __future__ import annotations

from collections.abc import Sequence

from application.ai.ports import AgentCatalog, CatalogEntry
from domain.ai import ProviderStatus


class CompositeCatalog:
    """An `AgentCatalog` that delegates to a list of them."""

    def __init__(self, catalogs: Sequence[AgentCatalog] = ()) -> None:
        self._catalogs = list(catalogs)

    def add(self, catalog: AgentCatalog) -> None:
        self._catalogs.append(catalog)

    def warm(self) -> None:
        for catalog in self._catalogs:
            catalog.warm()

    def has(self, agent_name: str) -> bool:
        return any(c.has(agent_name) for c in self._catalogs)

    def version_of(self, agent_name: str) -> str | None:
        return next((v for c in self._catalogs if (v := c.version_of(agent_name))), None)

    def entries(self) -> Sequence[CatalogEntry]:
        return [e for c in self._catalogs for e in c.entries()]

    def status(self) -> ProviderStatus:
        statuses = [c.status() for c in self._catalogs]
        if not statuses:
            return ProviderStatus("catalog", "disabled", "no catalog-backed provider is configured")
        state = "ready" if all(s.state == "ready" for s in statuses) else (
            "degraded" if any(s.state in ("ready", "degraded") for s in statuses) else statuses[0].state
        )
        return ProviderStatus("catalog", state, "; ".join(f"{s.name}={s.state}" for s in statuses))
