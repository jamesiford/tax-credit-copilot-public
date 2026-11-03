"""Writer entitlement adapters. [CH-04]

`WriterEntitlement.is_writer(oid)` answers one question — may this person change
what the business believes — and three sources can answer it:

- the allow-list in `tcc_ops.channel_user` (the `WriterRepository` itself
  satisfies the port, so it needs no adapter),
- membership of one Entra group, asked of Microsoft Graph,
- either.

Every adapter FAILS CLOSED. A Graph outage, a 403 for a missing permission or a
malformed reply means "not a writer": denying a legitimate writer for a minute is
an inconvenience, granting a non-writer is a change on a filed return.

The Graph call itself goes through `graph_client.GraphClient`, which refreshes a
token that predates a permission grant and retries once [CH-15e]; a refusal that
survives the retry is still a denial.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx

from application.identity import WriterEntitlement
from infrastructure.auth.graph_client import GRAPH_BASE, GRAPH_SCOPE, GraphClient, GraphTokenProvider  # noqa: F401 - GRAPH_SCOPE re-exported

logger = logging.getLogger(__name__)

GRAPH_URL = GRAPH_BASE + "/users/{oid}/checkMemberGroups"

#: Long enough to spare Graph one call per request, short enough that removing
#: someone from the group takes effect within a minute.
CACHE_SECONDS = 60.0


def default_token_provider() -> Callable[[], str]:
    """A Graph token from the process identity (Managed Identity deployed, `az login` locally)."""
    return GraphTokenProvider()


@dataclass
class EntraGroupEntitlement:
    """A writer is a member of `group_id`, per Graph `checkMemberGroups`."""

    group_id: str
    token_provider: Callable[[], str] = field(default_factory=default_token_provider)
    client: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=5.0))
    clock: Callable[[], float] = time.monotonic
    cache_seconds: float = CACHE_SECONDS

    def __post_init__(self) -> None:
        if not self.group_id:
            raise ValueError("an Entra group entitlement needs a group id")
        self._cache: dict[str, tuple[float, bool]] = {}
        self._lock = threading.Lock()

    def is_writer(self, user_oid: str) -> bool:
        now = self.clock()
        with self._lock:
            hit = self._cache.get(user_oid)
        if hit and now - hit[0] < self.cache_seconds:
            return hit[1]
        answer = self._ask_graph(user_oid)
        if answer is None:
            return False  # not cached: the next request asks again
        with self._lock:
            self._cache[user_oid] = (now, answer)
        return answer

    def _ask_graph(self, user_oid: str) -> bool | None:
        # built per call: the provider and client are plain attributes a caller may swap
        graph = GraphClient(self.token_provider, self.client)
        try:
            response = graph.request("POST", GRAPH_URL.format(oid=user_oid), json={"groupIds": [self.group_id]})
            response.raise_for_status()
            groups = response.json().get("value")
            if not isinstance(groups, list):
                raise ValueError("Graph reply has no value list")
            return self.group_id.lower() in {str(g).lower() for g in groups}
        except Exception as exc:  # noqa: BLE001 - every failure denies
            logger.warning("writer group check failed, denying: %s", type(exc).__name__)
            return None


@dataclass
class EitherEntitlement:
    """A writer if ANY source says so. Order is cost: the cheap local list first."""

    sources: tuple[WriterEntitlement, ...]

    def is_writer(self, user_oid: str) -> bool:
        for source in self.sources:
            try:
                if source.is_writer(user_oid):
                    return True
            except Exception as exc:  # noqa: BLE001 - a broken source must not grant, nor hide the others
                logger.warning("writer source failed, treating as no: %s", type(exc).__name__)
        return False
