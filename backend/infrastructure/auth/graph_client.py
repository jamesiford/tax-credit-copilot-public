"""The one Microsoft Graph client the platform's identity lookups share. [CH-15e]

Two features ask Graph who someone is: the writer-group check (`writers.py`) and the
display-name lookup. They must not each hand-roll a token, a header and a failure rule,
because the failure rule is the part that went wrong live: the platform keeps the first
Graph token an identity asked for until it expires, so a role granted AFTER that first
(refused) call was not seen for about a day. A caller that kept presenting the stale
token was denied against a grant that already existed.

`GraphClient.request` therefore does one thing beyond sending: when Graph answers as a
stale token would be answered (401, or 403 `Authorization_RequestDenied` /
insufficient privileges) it asks the token provider to drop its token and sends ONCE
more. The caller still decides what a refusal means; every caller in this repo fails
CLOSED.
"""
from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GRAPH_SCOPE = "https://graph.microsoft.com/.default"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

#: A claims value is what makes the credential bypass its cache (and, on a managed
#: identity, the platform's); the content is not interpreted by that path.
_REFRESH_CLAIMS = '{"access_token":{"nbf":{"essential":true}}}'

#: A refused role is refused on every call until somebody grants it. Without a cool-down
#: each of those calls would force a fresh token, so a permanent denial would hammer the
#: token endpoint; one refresh a minute is enough to pick up a grant made since.
REFRESH_COOLDOWN_SECONDS = 60.0

_DENIED_MARKERS = ("authorization_requestdenied", "insufficient privileges")


def _default_credential() -> Any:
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential()


@dataclass
class GraphTokenProvider:
    """A Graph token from the process identity that can drop a token known to be stale.

    Callable, so it satisfies `Callable[[], str]` wherever a plain provider is accepted;
    `invalidate()` is what lets `GraphClient` recover from a pre-grant token.
    """

    credential_factory: Callable[[], Any] = _default_credential
    clock: Callable[[], float] = time.monotonic
    cooldown_seconds: float = REFRESH_COOLDOWN_SECONDS

    def __post_init__(self) -> None:
        self._credential: Any = None
        self._force_fresh = False
        self._last_invalidated: float | None = None
        self._lock = threading.Lock()

    def __call__(self) -> str:
        with self._lock:
            if self._credential is None:
                self._credential = self.credential_factory()
            credential, fresh = self._credential, self._force_fresh
            self._force_fresh = False
        if not fresh:
            return credential.get_token(GRAPH_SCOPE).token
        try:
            return credential.get_token(GRAPH_SCOPE, claims=_REFRESH_CLAIMS).token
        except Exception as exc:  # noqa: BLE001 - not every credential in the chain accepts claims
            logger.warning("credential would not bypass its cache (%s); rebuilding it", type(exc).__name__)
            with self._lock:
                self._credential = credential = self.credential_factory()
            return credential.get_token(GRAPH_SCOPE).token

    def invalidate(self) -> bool:
        """Mark the cached token stale; False inside the cool-down, when nothing changed."""
        now = self.clock()
        with self._lock:
            last = self._last_invalidated
            if last is not None and now - last < self.cooldown_seconds:
                return False
            self._last_invalidated = now
            self._force_fresh = True
        return True


def is_stale_token_denial(response: httpx.Response) -> bool:
    """Whether Graph refused in the way a token minted before a grant is refused."""
    if response.status_code == 401:
        return True
    if response.status_code != 403:
        return False
    try:
        body = response.json()
    except ValueError:
        return False
    error = body.get("error") if isinstance(body, dict) else None
    text = " ".join(str(v) for v in error.values()) if isinstance(error, dict) else str(error or "")
    return any(marker in text.lower() for marker in _DENIED_MARKERS)


@dataclass
class GraphClient:
    """Send one request to Graph with a bearer token, retrying once after a stale-token refusal.

    `token_provider` may be any zero-argument callable; the retry happens only when it
    also has an `invalidate()` (a plain callable cannot be refreshed, so it is refused
    once and the caller's fail-closed rule applies).
    """

    token_provider: Callable[[], str]
    http: httpx.Client = field(default_factory=lambda: httpx.Client(timeout=5.0))

    def request(
        self, method: str, url: str, *, json: Any = None, params: dict[str, str] | None = None,
    ) -> httpx.Response:
        """The response, never raised on: the caller decides what a status means."""
        response = self._send(method, url, json, params)
        if is_stale_token_denial(response) and self._invalidate():
            logger.warning("Graph refused the cached token (HTTP %s); refreshing it and retrying once", response.status_code)
            response = self._send(method, url, json, params)
        return response

    def _send(self, method: str, url: str, json: Any, params: dict[str, str] | None) -> httpx.Response:
        token = self.token_provider()
        return self.http.request(method, url, json=json, params=params, headers={"Authorization": "Bearer " + token})

    def _invalidate(self) -> bool:
        hook = getattr(self.token_provider, "invalidate", None)
        return bool(hook()) if callable(hook) else False
