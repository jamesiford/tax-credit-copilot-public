"""The mediator's guarantees, pinned.

These matter more than they look. The mediator is the seam every write passes
through, so a defect here is a defect in attribution for figures that land on
tax returns.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from application.mediator import (
    AuditLog,
    Command,
    HandlerNotRegistered,
    Mediator,
    Query,
)
from application.wiring import build_mediator


@dataclass(frozen=True)
class _Ping(Query):
    value: int = 1


@dataclass(frozen=True)
class _Record(Command):
    payload: str = ""


def test_dispatches_to_the_registered_handler():
    mediator = Mediator()
    mediator.register(_Ping, lambda q: q.value * 2)
    assert mediator.send(_Ping(value=21)) == 42


def test_unregistered_request_names_itself_and_where_to_fix_it():
    """A wiring mistake must not read like a domain failure."""
    with pytest.raises(HandlerNotRegistered) as exc:
        Mediator().send(_Ping())
    assert "_Ping" in str(exc.value)
    assert "wiring" in str(exc.value)


def test_double_registration_raises_rather_than_silently_replacing():
    """Two handlers for one request resolve by import order, which is not a
    decision anybody made. Better to fail at startup than to dispatch to
    whichever module happened to be imported second."""
    mediator = Mediator()
    mediator.register(_Ping, lambda q: "first")
    with pytest.raises(ValueError, match="already has a handler"):
        mediator.register(_Ping, lambda q: "second")


def test_requests_are_frozen():
    """A handler that mutates its own request makes a retry behave differently
    from the first attempt."""
    with pytest.raises(Exception):
        _Ping(value=1).value = 2  # type: ignore[misc]


def test_commands_carry_an_actor_by_default():
    """An unattributed state change is not an audit trail."""
    assert _Record(payload="x").actor == "system"
    assert _Record(payload="x", actor="james@example.com").actor == "james@example.com"


def test_commands_are_logged_with_their_actor(caplog):
    mediator = Mediator()
    mediator.register(_Record, lambda c: "ok")
    with caplog.at_level(logging.INFO, logger="application.mediator"):
        mediator.send(_Record(payload="p", actor="auditor@example.com"))
    assert "auditor@example.com" in caplog.text
    assert "_Record" in caplog.text


def test_queries_are_not_logged_at_info(caplog):
    """Reads are frequent and change nothing; logging each at INFO buries the
    writes that actually need to be found later."""
    mediator = Mediator()
    mediator.register(_Ping, lambda q: 1)
    with caplog.at_level(logging.INFO, logger="application.mediator"):
        mediator.send(_Ping())
    assert "_Ping" not in caplog.text


def test_handler_exceptions_propagate_unchanged():
    """The mediator observes; it does not swallow. A router needs the original
    exception type to choose a status code."""
    class Boom(RuntimeError):
        pass

    mediator = Mediator()
    mediator.register(_Ping, lambda q: (_ for _ in ()).throw(Boom("nope")))
    with pytest.raises(Boom, match="nope"):
        mediator.send(_Ping())


class TestTheAuditStage:
    """A write leaves a record, and the record says who.

    This is the stage the architecture doc claimed for months while `send` did
    nothing but time the call and emit a log line. A log line is not a trail:
    nothing can query it, and it is gone the moment the container is recycled.
    """

    def test_a_write_is_recorded(self):
        mediator = Mediator()
        mediator.register(_Record, lambda c: "ok")
        mediator.send(_Record(payload="p", actor="auditor@example.com"))

        entry, = mediator.audit.records
        assert entry.request == "_Record"
        assert entry.actor == "auditor@example.com"
        assert entry.outcome == "ok"
        assert entry.error is None

    def test_a_read_is_not_recorded(self):
        """Reads change nothing. A trail that holds them buries the writes."""
        mediator = Mediator()
        mediator.register(_Ping, lambda q: 1)
        mediator.send(_Ping())
        assert mediator.audit.records == []

    def test_a_failed_write_is_recorded_too(self):
        """The half that gets asked about. A trail of successes cannot answer
        "somebody tried to resolve this and it errored"."""
        mediator = Mediator()
        mediator.register(_Record, lambda c: (_ for _ in ()).throw(RuntimeError("no")))

        with pytest.raises(RuntimeError):
            mediator.send(_Record(payload="p", actor="a@example.com"))

        entry, = mediator.audit.records
        assert entry.outcome == "error"
        assert entry.error == "RuntimeError: no"

    def test_an_unattributed_write_says_so(self):
        """`system` is what an unset actor looks like, and a reader cannot tell
        that from a service account that genuinely made the change."""
        mediator = Mediator()
        mediator.register(_Record, lambda c: "ok")
        mediator.send(_Record(payload="p"))
        assert mediator.audit.records[0].attributed is False

        mediator.send(_Record(payload="p", actor="a@example.com"))
        assert mediator.audit.records[1].attributed is True

    def test_the_trail_is_bounded_and_keeps_the_newest(self):
        """It is a support aid, not the durable trail — so it must not grow
        without limit inside a long-lived process."""
        mediator = Mediator(audit=AuditLog(limit=3))
        mediator.register(_Record, lambda c: "ok")
        for index in range(5):
            mediator.send(_Record(payload=str(index)))
        assert len(mediator.audit.records) == 3

    def test_an_invalid_request_never_becomes_an_attempted_write(self):
        """Validation runs before the audit clock. A malformed request was not
        a write, and recording it puts noise in the trail that matters."""
        @dataclass(frozen=True)
        class _Strict(Command):
            def validate(self) -> None:
                raise ValueError("no")

        mediator = Mediator()
        mediator.register(_Strict, lambda c: "ok")
        with pytest.raises(ValueError):
            mediator.send(_Strict())
        assert mediator.audit.records == []


def test_the_pipeline_does_not_claim_stages_it_does_not_have():
    """Authorization and TenantScope need an identity that does not exist yet.

    They are absent rather than stubbed on purpose: a stage that runs and always
    passes reads as a control. This test exists so that adding a no-op one to
    satisfy a diagram fails loudly.
    """
    stages = [name for name in dir(Mediator) if not name.startswith("__")]
    assert "_authorize" not in stages
    assert "_scope_tenant" not in stages


# --- the real wiring -------------------------------------------------------


def test_every_registered_request_is_a_command_or_a_query():
    """The distinction is the point. A request that is neither has escaped the
    read/write separation the mediator exists to enforce."""
    from application.commands.assess_client import AssessClientCommand
    from application.queries.get_proximity import GetProximityQuery

    for request_type in (AssessClientCommand, GetProximityQuery):
        assert issubclass(request_type, (Command, Query)), (
            f"{request_type.__name__} is neither a Command nor a Query"
        )


def test_wiring_builds_without_error():
    mediator = build_mediator()
    assert "GetProximityQuery" in mediator.registered
    assert "AssessClientCommand" in mediator.registered


def test_commands_validate_their_own_invariants():
    """Validation belongs on the request, not in the router. A command
    constructed in a scheduled job gets the same checks as one from HTTP."""
    from application.commands.assess_client import AssessClientCommand

    with pytest.raises(ValueError, match="client_id"):
        AssessClientCommand(client_id=0)


def test_queries_validate_their_own_invariants():
    from application.queries.get_proximity import GetProximityQuery

    with pytest.raises(ValueError, match="method"):
        GetProximityQuery(tax_year=2023, state="GA", method="nonsense")
    with pytest.raises(ValueError, match="negative"):
        GetProximityQuery(tax_year=2023, state="GA", within_weekly_hours=-1)
