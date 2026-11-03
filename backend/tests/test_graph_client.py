"""The shared Graph client: a token that predates a grant is refreshed once, and the answer stays fail-closed. [CH-15e]

Live (3 Nov): the group-membership check stayed denied for about a day after
`GroupMember.Read.All` was granted, because the cached token predated the grant. These
tests drive that story with a fake Graph that accepts only a fresh token.
"""
from __future__ import annotations

import httpx
import pytest

from infrastructure.auth.graph_client import (
    GraphClient,
    GraphTokenProvider,
    is_stale_token_denial,
)
from infrastructure.auth.writers import EntraGroupEntitlement

GROUP_ID = "00000000-0000-0000-0000-0000000000aa"
USER_OID = "00000000-0000-0000-0000-0000000000bb"
DENIED = {"error": {"code": "Authorization_RequestDenied", "message": "Insufficient privileges to complete the operation."}}


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class _Tokens:
    """A provider whose first token is stale; `invalidate` swaps in the fresh one."""

    def __init__(self, clock=None, cooldown=60.0):
        self.current, self.invalidations = "stale", 0
        self._provider = GraphTokenProvider(credential_factory=self, clock=clock or _Clock(), cooldown_seconds=cooldown)

    def __call__(self):  # the credential factory: returns itself, as a credential
        return self

    def get_token(self, scope, **kwargs):
        if kwargs.get("claims"):
            self.current = "fresh"
        return type("T", (), {"token": self.current})()


class _FakeGraph:
    """Accepts only the token named `valid`; counts and records what it saw."""

    def __init__(self, valid="fresh", denial=DENIED, status=403):
        self.valid, self.denial, self.status, self.seen = valid, denial, status, []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        token = request.headers["authorization"].removeprefix("Bearer ")
        self.seen.append(token)
        if token == self.valid:
            return httpx.Response(200, json={"value": [GROUP_ID]})
        return httpx.Response(self.status, json=self.denial)


def _entitlement(graph: _FakeGraph, tokens) -> EntraGroupEntitlement:
    return EntraGroupEntitlement(
        GROUP_ID, token_provider=tokens._provider, client=httpx.Client(transport=httpx.MockTransport(graph)),
    )


def test_a_403_then_a_refreshed_token_grants():
    graph, tokens = _FakeGraph(), _Tokens()
    assert _entitlement(graph, tokens).is_writer(USER_OID) is True
    assert graph.seen == ["stale", "fresh"]


def test_a_401_is_retried_once_too():
    graph, tokens = _FakeGraph(denial={"error": {"code": "InvalidAuthenticationToken"}}, status=401), _Tokens()
    assert _entitlement(graph, tokens).is_writer(USER_OID) is True
    assert graph.seen == ["stale", "fresh"]


def test_a_refusal_that_survives_the_retry_stays_closed_and_is_not_retried_again():
    graph, tokens = _FakeGraph(valid="never"), _Tokens()
    assert _entitlement(graph, tokens).is_writer(USER_OID) is False
    assert len(graph.seen) == 2


def test_a_permanent_denial_does_not_force_a_fresh_token_on_every_call():
    clock = _Clock()
    graph, tokens = _FakeGraph(valid="never"), _Tokens(clock)
    group = _entitlement(graph, tokens)
    group.is_writer(USER_OID)
    assert len(graph.seen) == 2
    group.is_writer(USER_OID)  # inside the cool-down: one call, no refresh
    assert len(graph.seen) == 3
    clock.now += 61
    group.is_writer(USER_OID)
    assert len(graph.seen) == 5


@pytest.mark.parametrize(
    "status, body",
    [(403, {"error": {"code": "Forbidden"}}), (404, DENIED), (500, {}), (429, {})],
    ids=["unrelated-403", "404", "500", "429"],
)
def test_only_a_stale_token_shaped_refusal_is_retried(status, body):
    graph, tokens = _FakeGraph(denial=body, status=status), _Tokens()
    assert _entitlement(graph, tokens).is_writer(USER_OID) is False
    assert graph.seen == ["stale"]


def test_a_plain_callable_cannot_refresh_so_it_is_refused_once():
    graph = _FakeGraph()
    client = GraphClient(lambda: "stale", httpx.Client(transport=httpx.MockTransport(graph)))
    assert client.request("GET", "https://graph.example/x").status_code == 403
    assert graph.seen == ["stale"]


def test_the_request_carries_the_bearer_and_the_body():
    seen = {}

    def handler(request):
        seen.update(auth=request.headers["authorization"], url=str(request.url), body=request.content)
        return httpx.Response(200, json={})

    GraphClient(lambda: "t", httpx.Client(transport=httpx.MockTransport(handler))).request(
        "GET", "https://graph.example/users/x", params={"$select": "displayName"},
    )
    assert seen["auth"] == "Bearer t" and "select=displayName" in seen["url"]


@pytest.mark.parametrize(
    "response, expected",
    [
        (httpx.Response(401), True),
        (httpx.Response(403, json=DENIED), True),
        (httpx.Response(403, json={"error": "Authorization_RequestDenied"}), True),
        (httpx.Response(403, text="not json"), False),
        (httpx.Response(403, json={"error": {"code": "Forbidden"}}), False),
        (httpx.Response(200), False),
    ],
)
def test_what_counts_as_a_stale_token_denial(response, expected):
    assert is_stale_token_denial(response) is expected


def test_the_default_credential_is_built_lazily_and_asked_normally_until_invalidated():
    built, asked = [], []

    class Credential:
        def get_token(self, scope, **kwargs):
            asked.append(kwargs)
            return type("T", (), {"token": "t"})()

    provider = GraphTokenProvider(credential_factory=lambda: built.append(1) or Credential())
    assert built == []
    provider(), provider()
    assert built == [1] and asked == [{}, {}]
    assert provider.invalidate() is True
    provider()
    assert asked[-1].get("claims")
    provider()
    assert asked[-1] == {}


def test_a_credential_that_rejects_claims_is_rebuilt_and_asked_plainly():
    built = []

    class Picky:
        def get_token(self, scope, **kwargs):
            if kwargs.get("claims"):
                raise RuntimeError("no claims here")
            return type("T", (), {"token": "plain"})()

    provider = GraphTokenProvider(credential_factory=lambda: built.append(1) or Picky())
    provider()
    provider.invalidate()
    assert provider() == "plain" and len(built) == 2


def test_invalidation_is_rate_limited_by_the_clock():
    clock = _Clock()
    provider = GraphTokenProvider(credential_factory=object, clock=clock, cooldown_seconds=60)
    assert provider.invalidate() is True
    assert provider.invalidate() is False
    clock.now += 60
    assert provider.invalidate() is True
