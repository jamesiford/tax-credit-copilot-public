"""A stored item carries a typed cause and a fixed remedy, never the raw error text. [F07.3]

The raw message can echo a request value, a host name or a row; it goes to the log. The cause is `error_dependency`.
"""
from __future__ import annotations

import logging

import pytest

from application.errors import DependencyUnavailable
from application.runs.executor import FIXED_REMEDY, classify
from domain.runs import ItemStatus

LEAK = "secret-value-4711"


def _classified(exc):
    return classify(exc, 2025, "ZZ_DEMO")


def test_a_value_error_is_stored_as_a_typed_cause_with_the_fixed_remedy_and_the_text_goes_to_the_log(caplog):
    with caplog.at_level(logging.WARNING, logger="tcc.runs"):
        outcome = _classified(ValueError(f"bad value {LEAK}"))
    assert outcome.status is ItemStatus.FAILED and outcome.error_dependency == "validation"
    assert outcome.error_message == FIXED_REMEDY["validation"] and LEAK not in outcome.error_message
    assert LEAK in caplog.text, "the raw message is kept where an operator can read it"


def test_a_dependency_failure_stores_its_remedy_and_not_its_reason():
    exc = DependencyUnavailable("claims_store", f"could not connect to host-{LEAK}", "Check the Warehouse connection.")
    outcome = _classified(exc)
    assert outcome.error_dependency == "claims_store" and outcome.error_message == "Check the Warehouse connection."
    assert LEAK not in outcome.error_message
    assert _classified(DependencyUnavailable("x_store", "r", "  ")).error_message == FIXED_REMEDY["unavailable"]


@pytest.mark.parametrize("exc, cause", [
    (TimeoutError(LEAK), "timeout"),
    (ConnectionError(LEAK), "timeout"),
    (KeyError(LEAK), "internal"),
])
def test_no_other_failure_echoes_its_message(exc, cause):
    outcome = _classified(exc)
    assert outcome.error_dependency == cause and LEAK not in (outcome.error_message or "")
    assert outcome.error_message == FIXED_REMEDY[cause]


def test_a_gold_write_failure_keeps_its_cause_and_drops_the_detail():
    from application.runs.executor import GOLD_WRITE
    from application.gold_ports import GoldWriteFailed

    outcome = _classified(GoldWriteFailed(f"more than one current run {LEAK}"))
    assert outcome.error_dependency == GOLD_WRITE and outcome.retry_once and LEAK not in outcome.error_message
    assert "section 9" in outcome.error_message


def test_an_unclassified_runtime_error_is_a_named_dependency_failure_and_never_echoes_its_text():
    outcome = _classified(RuntimeError(LEAK))
    assert outcome.status is ItemStatus.FAILED and outcome.error_dependency
    assert LEAK not in (outcome.error_message or "")
