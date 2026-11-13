"""The run no longer assumes Georgia: the state is derived from data, with a deprecated fallback. [ADR-013, F04.6]"""
from __future__ import annotations

import logging
import warnings

import pytest

import application.source_ports as source_ports
from api.trend import BaseYearRequest, ClientRunRequest
from application.commands.run_client_calculation import RunClientCalculationCommand
from application.commands.set_base_year import SetBaseYearCommand, resolved
from application.program_defaults import calculable_states, derive_run_state, pick_state


class _Scope:
    def __init__(self, states):
        self.states = states


def _payroll_states(monkeypatch, states):
    monkeypatch.setattr(source_ports, "payroll_scope", lambda account_id: _Scope(states))


def test_the_requests_and_the_command_no_longer_default_to_georgia():
    assert ClientRunRequest(year=2023).state is None
    assert BaseYearRequest().state is None
    assert RunClientCalculationCommand(client_id=1, tax_year=2023).state is None
    assert SetBaseYearCommand(client_id=1, worksite_id="GA_GA-001", base_year=2020).state is None


def test_only_states_with_an_authored_year_are_calculable():
    assert calculable_states() == ["GA"]
    assert calculable_states(2023) == ["GA"] and calculable_states(2018) == []


def test_the_state_comes_from_the_payroll_the_client_holds(monkeypatch):
    _payroll_states(monkeypatch, ["TX", "GA"])
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert derive_run_state(5, 2023) == "GA"
    assert pick_state(["NY", "TX"], 2023) is None


def test_the_program_chosen_is_logged_so_the_choice_is_visible(monkeypatch, caplog):
    _payroll_states(monkeypatch, ["TX", "GA"])
    with caplog.at_level(logging.INFO, logger="application.program_defaults"):
        derive_run_state(5, 2023)
    assert "state derived from payroll: GA (GA_JTC)" in caplog.text


def test_a_location_read_takes_its_state_from_the_location_then_the_registry(monkeypatch):
    from application.program_defaults import state_for_location

    _payroll_states(monkeypatch, ["GA"])
    assert state_for_location(1, "GA_GA-010", 2023) == "GA" and state_for_location(1, "x", 2023, "ny") == "NY"
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert state_for_location(1, "unprefixed", 2023) == "GA"


def test_a_named_state_is_never_second_guessed(monkeypatch):
    _payroll_states(monkeypatch, ["GA"])
    assert derive_run_state(5, 2023, "ny") == "NY"


def test_nothing_derivable_falls_back_with_a_deprecation_warning(monkeypatch, caplog):
    _payroll_states(monkeypatch, ["NY"])
    with caplog.at_level(logging.WARNING), pytest.warns(DeprecationWarning, match="deprecated"):
        assert derive_run_state(5, 2023) == "GA"
    assert "falling back to 'GA' (GA_JTC)" in caplog.text


def test_an_unreadable_footprint_also_falls_back_visibly(monkeypatch):
    def boom(account_id):
        raise RuntimeError("source down")

    monkeypatch.setattr(source_ports, "payroll_scope", boom)
    with pytest.warns(DeprecationWarning):
        assert derive_run_state(5, 2023) == "GA"


def test_the_base_year_state_and_program_come_from_the_location(monkeypatch):
    _payroll_states(monkeypatch, [])
    cmd = resolved(SetBaseYearCommand(client_id=1, worksite_id="GA_GA-010", base_year=2020))
    assert (cmd.state, cmd.program_code) == ("GA", "GA_JTC")
    explicit = resolved(SetBaseYearCommand(client_id=1, worksite_id="x", base_year=2020, state="ny"))
    assert (explicit.state, explicit.program_code) == ("NY", "NY_EXCELSIOR")
