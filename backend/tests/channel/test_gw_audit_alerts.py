"""Through the gateway: a failed audit write alerts, and a read still cannot go unaccounted. [RM-03]

Each trail has its own failure. The opening event of a read is a gate (nothing is called, so a
person's rows are never served unrecorded); the closing event cannot undo an answer but is
never silent; a narration's two rows each raise their own alert.
"""
from __future__ import annotations

import logging

import pytest

from application import audit_alert
from application.audit_alert import LOGGER_NAME, failure_counts
from gateway_harness import agent_headers
from test_gw_data_lanes import ARGS as EMPLOYEE_ARGS, SECRET_TOKEN, employee_rows
from test_gw_narration import URL as NARRATION_URL, report

CALL = "/channel/v1/tools/client_situation"
DATA_CALL = "/channel/v1/tools/data_query"


@pytest.fixture(autouse=True)
def _fresh_counts():
    audit_alert.reset_failure_counts()
    yield
    audit_alert.reset_failure_counts()


def alerts(caplog):
    return [r for r in caplog.records if r.name == LOGGER_NAME]


def break_audit(gateway, monkeypatch, *, phases=None):
    real = gateway.audit.append

    def append(event):
        if phases is None or event.phase in phases:
            raise RuntimeError("store down: client 1001")
        return real(event)

    monkeypatch.setattr(gateway.audit, "append", append)


def test_an_employee_level_read_is_not_made_when_its_audit_cannot_be_written(gateway, fake_api, monkeypatch, caplog):
    fake_api.replies["data_query"] = (200, employee_rows())
    break_audit(gateway, monkeypatch)
    with caplog.at_level(logging.DEBUG):
        response = gateway.client.post(DATA_CALL, json={"args": EMPLOYEE_ARGS}, headers=agent_headers())
    assert response.status_code == 503 and response.json()["error"]["code"] == "audit_unavailable"
    assert fake_api.calls == [] and SECRET_TOKEN not in response.text
    assert [(r.audit_source, r.fatal) for r in alerts(caplog)] == [("channel_audit", True)]
    assert failure_counts()["channel_audit"] == 1


def test_a_closing_event_that_fails_alerts_and_the_answer_stands(gateway, fake_api, monkeypatch, caplog):
    break_audit(gateway, monkeypatch, phases={"end"})
    with caplog.at_level(logging.DEBUG):
        response = gateway.client.post(CALL, json={"args": {"client_id": 2001}}, headers=agent_headers())
    assert response.status_code == 200 and len(fake_api.calls) == 1
    assert [(r.audit_operation, r.fatal) for r in alerts(caplog)] == [("end", False)]


def test_a_refusal_whose_record_cannot_be_written_still_refuses_and_alerts(tmp_path, monkeypatch, caplog):
    from gateway_harness import FakeApi, build_gateway

    gw = build_gateway(tmp_path, api=FakeApi(), rate_limit_per_minute=1)
    assert gw.client.post(CALL, json={"args": {"client_id": 2001}}, headers=agent_headers()).status_code == 200
    break_audit(gw, monkeypatch)
    with caplog.at_level(logging.DEBUG):
        blocked = gw.client.post(CALL, json={"args": {"client_id": 2001}}, headers=agent_headers())
    assert blocked.status_code == 429, "the refusal stands even though its record could not be written"
    assert any(r.audit_source == "channel_audit" for r in alerts(caplog))


def test_the_gateways_own_entitlement_check_denies_and_logs_when_it_cannot_answer(tmp_path, caplog):
    from application import writer_alert
    from gateway_harness import build_gateway

    writer_alert.reset_denial_counts()
    gw = build_gateway(tmp_path)

    class Broken:
        def is_writer(self, oid):
            raise ConnectionError("graph said: no")

    gw.services.pipeline._entitlement = Broken()
    commit = {"args": {"client_id": 2001, "program_code": "GA_JTC", "scope": "in_scope"}}
    with caplog.at_level(logging.DEBUG):
        response = gw.client.post("/channel/v1/tools/engagement_set_commit", json=commit, headers=agent_headers())
    assert response.status_code == 403
    (record,) = [r for r in caplog.records if r.name == "tcc.writer_check"]
    assert record.writer_source == "gateway_check" and writer_alert.denial_counts() == {"gateway_check": 1}
    writer_alert.reset_denial_counts()


def test_a_narration_report_that_cannot_be_filed_is_a_503_and_alerts_twice_over(gateway, monkeypatch, caplog):
    break_audit(gateway, monkeypatch)
    with caplog.at_level(logging.DEBUG):
        reply = gateway.client.post(NARRATION_URL, json=report(), headers=agent_headers())
    assert reply.status_code == 503 and reply.json()["error"]["code"] == "audit_unavailable"
    assert sorted(r.audit_source for r in alerts(caplog)) == ["channel_audit", "narration"]


def test_a_narrations_agent_row_that_cannot_be_written_alerts_and_is_reported(gateway, monkeypatch, caplog):
    def down(_action):
        raise RuntimeError("actions store down")

    monkeypatch.setattr(gateway.actions, "append", down)
    with caplog.at_level(logging.DEBUG):
        reply = gateway.client.post(NARRATION_URL, json=report(), headers=agent_headers())
    assert reply.status_code == 200 and reply.json()["agent_action_recorded"] is False
    assert sorted(r.audit_source for r in alerts(caplog)) == ["agent_audit", "narration"]
    assert not any("actions store down" in r.getMessage() for r in alerts(caplog))
