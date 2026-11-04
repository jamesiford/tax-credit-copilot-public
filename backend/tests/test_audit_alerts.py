"""An audit-write failure is never silent: it raises `audit_write_failed`. [RM-03]

The three trails (the channel audit table, the narrator's agent-action table and the narration
report) each have a failure that must not stop an answer and one that must. Every one of them
lands on the dedicated logger `tcc.audit_alert` and in a per-source counter, with no payload.
What each does to the CALL is unchanged: an opening event that cannot be written refuses the
work; a closing event does not mask the result.
"""
from __future__ import annotations

import logging

import pytest

from application import audit_alert
from application.agent_audit import AgentActionRecorder, AgentInvocation
from application.audit_alert import EVENT, LOGGER_NAME, audit_write_failed, failure_counts
from application.channel_audit import AuditCall, ChannelAuditor
from application.identity import ActingUser

PAYLOAD = "client 1001 average 412.5 employee E-77"


@pytest.fixture(autouse=True)
def _fresh_counts():
    audit_alert.reset_failure_counts()
    yield
    audit_alert.reset_failure_counts()


class FailingRepository:
    """A store that is down for every write."""

    def append(self, *_a, **_k):
        raise RuntimeError(PAYLOAD)


def alerts(caplog):
    return [r for r in caplog.records if r.name == LOGGER_NAME]


# ------------------------------------------------------------------ the alert itself


def test_the_alert_is_an_error_on_its_own_logger_keyed_by_the_event_name(caplog):
    with caplog.at_level(logging.DEBUG):
        audit_write_failed("channel_audit", "begin", RuntimeError(PAYLOAD), fatal=True)
    (record,) = alerts(caplog)
    assert record.levelno == logging.ERROR and record.getMessage().startswith(EVENT)
    assert (record.audit_source, record.audit_operation, record.error_type, record.fatal) == (
        "channel_audit", "begin", "RuntimeError", True)
    assert record.event == EVENT


def test_the_alert_carries_no_payload_not_even_the_errors_message(caplog):
    with caplog.at_level(logging.DEBUG):
        audit_write_failed("agent_audit", "record", RuntimeError(PAYLOAD), fatal=False)
    (record,) = alerts(caplog)
    text = record.getMessage() + repr(record.__dict__)
    assert PAYLOAD not in text and "412.5" not in text and "E-77" not in text and record.exc_info is None


def test_every_failure_is_counted_per_source():
    audit_write_failed("channel_audit", "begin", ValueError("x"), fatal=True)
    audit_write_failed("channel_audit", "end", ValueError("x"), fatal=False)
    audit_write_failed("narration", "report", "string_error", fatal=True)
    assert failure_counts() == {"channel_audit": 2, "agent_audit": 0, "narration": 1}


def test_an_unknown_source_is_a_programming_error_not_a_quiet_alert():
    with pytest.raises(ValueError, match="unknown audit source"):
        audit_write_failed("somewhere_else", "x", "y", fatal=False)


# ------------------------------------------------------------ the channel audit trail


def call(kind="read") -> AuditCall:
    return AuditCall(tool_name="client_situation", action_kind=kind, actor=ActingUser(oid="u-1"), args={"client_id": 1})


def test_a_read_whose_event_cannot_be_written_raises_and_alerts(caplog):
    auditor = ChannelAuditor(FailingRepository())
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError):
        auditor.record_read(call())
    assert [r.audit_operation for r in alerts(caplog)] == ["read"] and alerts(caplog)[0].fatal is True


def test_an_opening_event_that_cannot_be_written_refuses_the_call_and_alerts(caplog):
    auditor = ChannelAuditor(FailingRepository())
    ran = []
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError):
        with auditor.audited(call("write_prepare")):
            ran.append("work")
    assert ran == [], "an action the platform cannot account for is not performed"
    assert [(r.audit_operation, r.fatal) for r in alerts(caplog)] == [("begin", True)]


def test_a_read_closed_through_the_wrapper_is_fail_closed_too(caplog):
    auditor = ChannelAuditor(FailingRepository())
    with caplog.at_level(logging.DEBUG), pytest.raises(RuntimeError):
        with auditor.audited(call("read")):
            pass
    assert [(r.audit_operation, r.fatal) for r in alerts(caplog)] == [("single", True)]


class FailsOnEnd:
    """Writes the `begin` row, then goes down."""

    def __init__(self) -> None:
        self.events = []

    def append(self, event):
        if event.phase == "end":
            raise RuntimeError(PAYLOAD)
        self.events.append(event)


def test_a_closing_event_that_cannot_be_written_alerts_and_does_not_mask_the_result(caplog):
    repository = FailsOnEnd()
    auditor = ChannelAuditor(repository)
    with caplog.at_level(logging.DEBUG):
        with auditor.audited(call("write_prepare")) as handle:
            handle.outcome = "ok"
    assert [e.phase for e in repository.events] == ["begin"]
    assert [(r.audit_operation, r.fatal) for r in alerts(caplog)] == [("end", False)]


def test_a_failure_building_the_event_alerts_too(caplog, monkeypatch):
    auditor = ChannelAuditor(FailsOnEnd())

    def cannot_build(*_a, **_k):
        raise KeyError("no such field")

    monkeypatch.setattr(auditor, "_event", cannot_build)
    with caplog.at_level(logging.DEBUG), pytest.raises(KeyError):
        auditor.begin_write(call("write_prepare"))
    assert alerts(caplog), "a failure before the repository is reached is a failed audit write as well"


# ---------------------------------------------------------- the agent-action trail


def invocation() -> AgentInvocation:
    return AgentInvocation(agent_name="ChannelNarratorAgent", prompt="p", output_chars=3)


def test_an_agent_action_that_cannot_be_recorded_returns_none_and_alerts(caplog):
    with caplog.at_level(logging.DEBUG):
        assert AgentActionRecorder(FailingRepository()).record(invocation()) is None
    (record,) = alerts(caplog)
    assert (record.audit_source, record.audit_operation, record.fatal) == ("agent_audit", "record", False)
    assert failure_counts()["agent_audit"] == 1


def test_a_recorded_agent_action_raises_no_alert(caplog):
    class Fine:
        def append(self, action):
            self.action = action

    with caplog.at_level(logging.DEBUG):
        assert AgentActionRecorder(Fine()).record(invocation()) is not None
    assert alerts(caplog) == [] and sum(failure_counts().values()) == 0
