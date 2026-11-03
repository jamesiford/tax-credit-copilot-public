"""The Graph display-name lookup: fail-soft, cached, single-flight, quiet. [CH-15a]

Graph is a fake (`httpx.MockTransport`) and the clock is a test's, so nothing reaches a
network and nothing waits. What is pinned is the request path's contract: a person's
name when Graph gives one, `None` for every kind of failure, a cache that spares Graph
and expires, and a log that never holds a name.
"""
from __future__ import annotations

import logging
import threading
import time

import httpx
import pytest

from application.display_names import PLACEHOLDER_NAME, ResolvedPerson, needs_resolution
from application.identity import ActingUser
from infrastructure.auth.graph_people import GraphDisplayNameResolver

OID = "bbbbbbbb-0000-4000-8000-000000000002"
OTHER = "cccccccc-0000-4000-8000-000000000003"
BODY = {"displayName": "Pat Example", "userPrincipalName": "pat@example.test"}


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Rig:
    """A resolver over a scripted Graph; `calls` records what was asked of it."""

    def __init__(self, handler=None, **resolver_args) -> None:
        self.calls: list[httpx.Request] = []
        self.clock = Clock()
        self.handler = handler or (lambda request: httpx.Response(200, json=BODY))
        client = httpx.Client(transport=httpx.MockTransport(self._answer))
        self.resolver = GraphDisplayNameResolver(
            token_provider=lambda: "graph-token", client=client, clock=self.clock, **resolver_args)

    def _answer(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        return self.handler(request)


# ------------------------------------------------------------------ what is asked


def test_a_success_returns_the_name_and_upn_and_asks_for_only_those_two_fields():
    rig = Rig()
    assert rig.resolver.resolve(OID) == ResolvedPerson("Pat Example", "pat@example.test")
    (request,) = rig.calls
    assert request.method == "GET" and request.url.path == f"/v1.0/users/{OID}"
    assert request.url.query == b"$select=displayName,userPrincipalName"
    assert request.headers["authorization"] == "Bearer graph-token"


def test_the_request_has_a_two_second_timeout_by_default():
    resolver = GraphDisplayNameResolver(token_provider=lambda: "t")
    assert resolver.client.timeout == httpx.Timeout(2.0)


@pytest.mark.parametrize("oid", ["", "not-a-guid", "../me", f"{OID}/memberOf", f"{OID}?x=1"])
def test_a_value_that_is_not_a_guid_never_reaches_graph(oid):
    rig = Rig()
    assert rig.resolver.resolve(oid) is None
    assert rig.calls == []


def test_a_directory_with_only_one_field_still_answers():
    rig = Rig(lambda r: httpx.Response(200, json={"displayName": "  ", "userPrincipalName": "pat@example.test"}))
    assert rig.resolver.resolve(OID) == ResolvedPerson(None, "pat@example.test")


def test_an_over_long_name_is_cut_to_what_the_api_accepts():
    rig = Rig(lambda r: httpx.Response(200, json={"displayName": "N" * 500}))
    assert len(rig.resolver.resolve(OID).display_name) == 256


# ------------------------------------------------------------------ fail-soft


def _timeout(request):
    raise httpx.ReadTimeout("slow", request=request)


def _refused(request):
    raise httpx.ConnectError("nope", request=request)


@pytest.mark.parametrize("handler", [
    lambda r: httpx.Response(404, json={"error": {"code": "Request_ResourceNotFound"}}),
    lambda r: httpx.Response(403, json={"error": {"code": "Forbidden"}}),
    lambda r: httpx.Response(500, text="boom"),
    lambda r: httpx.Response(200, text="<html>not json</html>"),
    lambda r: httpx.Response(200, json=["a", "list"]),
    lambda r: httpx.Response(200, json={}),
    lambda r: httpx.Response(200, json={"displayName": 7, "userPrincipalName": None}),
    _timeout,
    _refused,
], ids=["404", "403", "500", "not-json", "list", "empty", "wrong-types", "timeout", "unreachable"])
def test_every_failure_is_none_and_never_raises(handler):
    assert Rig(handler).resolver.resolve(OID) is None


def test_a_token_that_cannot_be_had_is_none():
    def no_token() -> str:
        raise RuntimeError("no credential")

    resolver = GraphDisplayNameResolver(token_provider=no_token, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=BODY))))
    assert resolver.resolve(OID) is None


def test_a_failure_warns_with_the_oid_and_the_error_type_and_nothing_else(caplog):
    rig = Rig(lambda r: httpx.Response(403, json={"error": {"message": "Pat Example pat@example.test"}}))
    with caplog.at_level(logging.DEBUG):
        rig.resolver.resolve(OID)
        Rig(BODY and (lambda r: httpx.Response(200, json=BODY))).resolver.resolve(OTHER)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "display-name" in r.getMessage()]
    assert warnings and OID in warnings[0].getMessage()
    everything = " ".join(r.getMessage() for r in caplog.records)
    assert "Pat Example" not in everything and "pat@example.test" not in everything


def test_a_success_logs_no_name_either(caplog):
    with caplog.at_level(logging.DEBUG):
        Rig().resolver.resolve(OID)
    assert "Pat Example" not in caplog.text and "pat@example.test" not in caplog.text


# --------------------------------------------------------------------- caching


def test_an_answer_is_cached_for_a_day_then_asked_again():
    rig = Rig()
    rig.resolver.resolve(OID)
    rig.clock.now += 24 * 3600 - 1
    rig.resolver.resolve(OID)
    assert len(rig.calls) == 1
    rig.clock.now += 2
    rig.resolver.resolve(OID)
    assert len(rig.calls) == 2


def test_no_answer_is_cached_for_five_minutes_only():
    rig = Rig(lambda r: httpx.Response(404, json={}))
    assert rig.resolver.resolve(OID) is None
    rig.clock.now += 299
    assert rig.resolver.resolve(OID) is None
    assert len(rig.calls) == 1
    rig.clock.now += 2
    rig.resolver.resolve(OID)
    assert len(rig.calls) == 2


def test_a_grant_made_since_a_failure_is_noticed_after_the_negative_window():
    answers = iter([httpx.Response(404, json={}), httpx.Response(200, json=BODY)])
    rig = Rig(lambda r: next(answers))
    assert rig.resolver.resolve(OID) is None
    rig.clock.now += 301
    assert rig.resolver.resolve(OID).display_name == "Pat Example"


def test_the_cache_is_per_person_and_case_insensitive():
    rig = Rig()
    rig.resolver.resolve(OID)
    rig.resolver.resolve(OID.upper())
    rig.resolver.resolve(OTHER)
    assert len(rig.calls) == 2


def test_the_cache_is_bounded_and_drops_the_least_recently_used():
    rig = Rig(max_entries=2)
    ids = [f"dddddddd-0000-4000-8000-00000000000{n}" for n in range(3)]
    for oid in ids:
        rig.resolver.resolve(oid)
    assert len(rig.calls) == 3
    rig.resolver.resolve(ids[2])  # still held
    rig.resolver.resolve(ids[1])  # still held
    assert len(rig.calls) == 3
    rig.resolver.resolve(ids[0])  # evicted: asked again
    assert len(rig.calls) == 4


# ------------------------------------------------------------------ concurrency


def test_concurrent_requests_for_one_person_make_one_graph_call():
    entered, release = threading.Event(), threading.Event()

    def slow(request):
        entered.set()
        release.wait(5)
        return httpx.Response(200, json=BODY)

    rig = Rig(slow)
    results: list[ResolvedPerson | None] = []
    threads = [threading.Thread(target=lambda: results.append(rig.resolver.resolve(OID))) for _ in range(8)]
    threads[0].start()
    assert entered.wait(5)
    for thread in threads[1:]:
        thread.start()
    time.sleep(0.2)  # the other seven are waiting on the leader, not calling Graph
    release.set()
    for thread in threads:
        thread.join(5)
    assert len(rig.calls) == 1
    assert results == [ResolvedPerson("Pat Example", "pat@example.test")] * 8


def test_a_failed_leader_gives_its_followers_the_same_none():
    entered, release = threading.Event(), threading.Event()

    def slow_failure(request):
        entered.set()
        release.wait(5)
        return httpx.Response(500)

    rig = Rig(slow_failure)
    results: list[ResolvedPerson | None] = []
    threads = [threading.Thread(target=lambda: results.append(rig.resolver.resolve(OID))) for _ in range(4)]
    threads[0].start()
    entered.wait(5)
    for thread in threads[1:]:
        thread.start()
    time.sleep(0.1)
    release.set()
    for thread in threads:
        thread.join(5)
    assert results == [None] * 4 and len(rig.calls) == 1


# ------------------------------------------------ the stale-token fix is reused


def test_a_token_that_predates_the_grant_is_refreshed_once_through_the_shared_client():
    from infrastructure.auth.graph_client import GraphTokenProvider

    class Credential:
        def __init__(self) -> None:
            self.asked = 0

        def get_token(self, scope, **kwargs):
            self.asked += 1
            return type("T", (), {"token": f"token-{self.asked}"})()

    answers = iter([
        httpx.Response(403, json={"error": {"code": "Authorization_RequestDenied"}}),
        httpx.Response(200, json=BODY),
    ])
    seen: list[str] = []

    def handler(request):
        seen.append(request.headers["authorization"])
        return next(answers)

    credential = Credential()
    resolver = GraphDisplayNameResolver(
        token_provider=GraphTokenProvider(credential_factory=lambda: credential),
        client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert resolver.resolve(OID).display_name == "Pat Example"
    assert seen == ["Bearer token-1", "Bearer token-2"]


# ------------------------------------------------------------- the placeholder rule


@pytest.mark.parametrize("name, expected", [
    (None, True), ("", True), ("   ", True), (PLACEHOLDER_NAME, True), ("(Name Not Provided)", True),
    ("Pat Writer", False),
])
def test_only_a_missing_or_placeholder_name_needs_a_lookup(name, expected):
    assert needs_resolution(ActingUser(oid=OID, display_name=name)) is expected
