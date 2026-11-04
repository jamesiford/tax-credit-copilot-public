"""Each writer source denies when it cannot answer, and says so. [RM-03, CH-04]

"Is this person a writer?" is asked of an allow-list table and of Graph. Either can fail. A
source that cannot answer never grants, and its failure is not allowed to look like an ordinary
"no": it is logged as `writer_check_failed` naming the source, with the type of the error and
nothing else (no oid, no message).
"""
from __future__ import annotations

import logging

import httpx
import pytest

from application import channel_wiring, writer_alert
from application.writer_alert import EVENT, LOGGER_NAME, denial_counts
from infrastructure.auth.writers import DenyOnFailure, EitherEntitlement, EntraGroupEntitlement

OID = "00000000-0000-0000-0000-0000000000bb"
GROUP = "00000000-0000-0000-0000-0000000000aa"
SECRET = "graph said: user 00000000-0000-0000-0000-0000000000bb is unknown"


@pytest.fixture(autouse=True)
def _fresh():
    writer_alert.reset_denial_counts()
    yield
    writer_alert.reset_denial_counts()
    channel_wiring.set_writer_entitlement(None)
    channel_wiring.set_writer_repository(None)


class Says:
    def __init__(self, answer: bool) -> None:
        self.answer, self.asked = answer, 0

    def is_writer(self, oid: str) -> bool:
        self.asked += 1
        return self.answer


class Broken:
    def is_writer(self, oid: str) -> bool:
        raise ConnectionError(SECRET)


def events(caplog):
    return [r for r in caplog.records if r.name == LOGGER_NAME]


def assert_logged_without_payload(caplog, source: str):
    (record,) = events(caplog)
    assert record.levelno == logging.ERROR and record.getMessage().startswith(EVENT)
    assert (record.writer_source, record.error_type, record.decision) == (source, "ConnectionError", "deny")
    assert OID not in record.getMessage() and "unknown" not in record.getMessage() and record.exc_info is None


# ---------------------------------------------------------------- the allow-list


def test_an_allow_list_that_cannot_be_read_denies_and_is_logged(caplog):
    with caplog.at_level(logging.DEBUG):
        assert DenyOnFailure(Broken(), "allowlist").is_writer(OID) is False
    assert_logged_without_payload(caplog, "allowlist")
    assert denial_counts() == {"allowlist": 1}


def test_a_working_source_passes_its_answer_through_untouched(caplog):
    with caplog.at_level(logging.DEBUG):
        assert DenyOnFailure(Says(True), "allowlist").is_writer(OID) is True
        assert DenyOnFailure(Says(False), "allowlist").is_writer(OID) is False
    assert events(caplog) == [] and denial_counts() == {}


def test_a_truthy_non_bool_answer_is_a_bool_never_something_else_that_could_grant():
    assert DenyOnFailure(type("S", (), {"is_writer": lambda self, oid: "yes"})(), "x").is_writer(OID) is True
    assert DenyOnFailure(type("S", (), {"is_writer": lambda self, oid: None})(), "x").is_writer(OID) is False


def test_the_wired_allow_list_denies_when_its_table_is_down(monkeypatch, caplog):
    monkeypatch.delenv("CHANNEL_WRITER_SOURCE", raising=False)
    channel_wiring.set_writer_entitlement(None)
    channel_wiring.set_writer_repository(Broken())
    with caplog.at_level(logging.DEBUG):
        assert channel_wiring.get_writer_entitlement().is_writer(OID) is False
    assert_logged_without_payload(caplog, "allowlist")


# ------------------------------------------------------------------- either


def test_a_broken_source_neither_grants_nor_hides_the_others(caplog):
    with caplog.at_level(logging.DEBUG):
        assert EitherEntitlement((Broken(), Says(True))).is_writer(OID) is True
    assert_logged_without_payload(caplog, "Broken")


def test_every_source_broken_is_a_denial_logged_once_per_source(caplog):
    with caplog.at_level(logging.DEBUG):
        assert EitherEntitlement((Broken(), Broken())).is_writer(OID) is False
    assert denial_counts() == {"Broken": 2} and len(events(caplog)) == 2


def test_the_first_yes_stops_the_search():
    first, second = Says(True), Says(True)
    assert EitherEntitlement((first, second)).is_writer(OID) is True
    assert (first.asked, second.asked) == (1, 0)


# --------------------------------------------------------------- Entra group


def entitlement(handler) -> EntraGroupEntitlement:
    return EntraGroupEntitlement(
        GROUP, token_provider=lambda: "token", client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, json={"error": "down"}),
        lambda r: httpx.Response(200, json={"value": "not a list"}),
        lambda r: httpx.Response(200, content=b"<html>"),
        lambda r: (_ for _ in ()).throw(httpx.ConnectError("no route")),
    ],
    ids=["500", "malformed", "not-json", "unreachable"],
)
def test_a_group_check_that_fails_denies_and_is_logged_by_name(handler, caplog):
    with caplog.at_level(logging.DEBUG):
        assert entitlement(handler).is_writer(OID) is False
    (record,) = events(caplog)
    assert record.writer_source == "entra_group" and record.decision == "deny"
    assert denial_counts() == {"entra_group": 1}


def test_a_failed_group_check_is_not_cached_so_the_next_request_asks_again(caplog):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500) if len(calls) == 1 else httpx.Response(200, json={"value": [GROUP]})

    source = entitlement(handler)
    with caplog.at_level(logging.DEBUG):
        assert source.is_writer(OID) is False
        assert source.is_writer(OID) is True
    assert len(calls) >= 2 and len(events(caplog)) == 1
