"""Look a person up in Microsoft Graph by object id. [CH-15a]

`GET /users/{oid}?$select=displayName,userPrincipalName`, as the process identity, with
the Graph application role `User.ReadBasic.All` (display name and UPN, nothing else).
It exists so a Teams user, whose channel supplies an object id and no name, is a person
in the audit trail and the author of a write.

Three rules, all about the request path:

- **Fail-soft.** Any error, refusal, 404, timeout or malformed reply is `None`. A name
  is a nicety; a lookup that could stop a tax consultant working would be a defect.
- **Cheap.** A 2-second timeout and a cache: 24 hours for an answer (names change
  rarely), 5 minutes for "no answer" (so a missing role is not retried on every
  message, and a role granted a moment ago is noticed soon). Bounded, thread-safe, and
  single-flight: concurrent first requests for one person make one call.
- **Quiet.** A failure is logged as a warning naming the OID and the exception type and
  nothing else. A display name or UPN is never logged.

The Graph call itself is `graph_client.GraphClient`, which refreshes a token that
predates a role grant and retries once [CH-15e]; that is the only retry, and it is
rate-limited by the client's cool-down.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any

import httpx

from application.display_names import ResolvedPerson
from infrastructure.auth.graph_client import GRAPH_BASE, GraphClient, GraphTokenProvider

logger = logging.getLogger(__name__)

USER_URL = GRAPH_BASE + "/users/{oid}?$select=displayName,userPrincipalName"
REQUEST_TIMEOUT_SECONDS = 2.0
POSITIVE_CACHE_SECONDS = 24 * 3600.0
NEGATIVE_CACHE_SECONDS = 300.0
MAX_ENTRIES = 2048
#: The API refuses an acting-user field longer than this, so a longer name is cut here.
FIELD_LIMIT = 256

_GUID = re.compile(r"^[0-9a-fA-F]{8}-([0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")


def _clean(value: Any) -> str | None:
    text = value.strip()[:FIELD_LIMIT] if isinstance(value, str) else ""
    return text or None


def _person(body: Any) -> ResolvedPerson | None:
    if not isinstance(body, dict):
        raise ValueError("Graph reply is not an object")
    person = ResolvedPerson(_clean(body.get("displayName")), _clean(body.get("userPrincipalName")))
    return person if person.display_name or person.upn else None


@dataclass
class GraphDisplayNameResolver:
    """`DisplayNameResolver` over Graph, with a bounded two-speed cache."""

    token_provider: Callable[[], str] = field(default_factory=GraphTokenProvider)
    client: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS))
    clock: Callable[[], float] = time.monotonic
    positive_seconds: float = POSITIVE_CACHE_SECONDS
    negative_seconds: float = NEGATIVE_CACHE_SECONDS
    max_entries: int = MAX_ENTRIES

    def __post_init__(self) -> None:
        self._cache: OrderedDict[str, tuple[float, ResolvedPerson | None]] = OrderedDict()
        self._inflight: dict[str, Future[ResolvedPerson | None]] = {}
        self._lock = threading.Lock()

    def resolve(self, oid: str) -> ResolvedPerson | None:
        """The person for `oid`, or None. Never raises."""
        key = oid.strip().lower()
        if not _GUID.match(key):
            return None
        with self._lock:
            hit = self._fresh(key)
            if hit is not None:
                return hit[0]
            waiting = self._inflight.get(key)
            if waiting is None:
                self._inflight[key] = mine = Future()
        if waiting is not None:
            return self._wait(waiting)
        return self._lead(key, mine)

    def _fresh(self, key: str) -> tuple[ResolvedPerson | None] | None:
        """A one-tuple holding the cached answer (which may itself be None), or None when stale."""
        held = self._cache.get(key)
        if held is None:
            return None
        stored_at, person = held
        if self.clock() - stored_at >= (self.positive_seconds if person else self.negative_seconds):
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return (person,)

    def _lead(self, key: str, flight: Future[ResolvedPerson | None]) -> ResolvedPerson | None:
        person = self._ask_graph(key)
        with self._lock:
            self._cache[key] = (self.clock(), person)
            while len(self._cache) > self.max_entries:
                self._cache.popitem(last=False)
            del self._inflight[key]
        flight.set_result(person)
        return person

    @staticmethod
    def _wait(flight: Future[ResolvedPerson | None]) -> ResolvedPerson | None:
        try:
            return flight.result(timeout=REQUEST_TIMEOUT_SECONDS * 3)
        except Exception:  # noqa: BLE001 - fail-soft: the leader's answer never arrived in time
            return None

    def _ask_graph(self, oid: str) -> ResolvedPerson | None:
        # built per call: the provider and client are plain attributes a caller may swap
        graph = GraphClient(self.token_provider, self.client)
        try:
            response = graph.request("GET", USER_URL.format(oid=oid))
            response.raise_for_status()
            return _person(response.json())
        except Exception as exc:  # noqa: BLE001 - every failure is "no name", and never raises
            logger.warning("display-name lookup failed for oid=%s: %s", oid, type(exc).__name__)
            return None
