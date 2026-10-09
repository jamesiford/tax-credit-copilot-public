"""WI-21, saved: a chosen base year is recorded, audited, and used by the next run.

The preview re-priced a block and saved nothing. This pins the saved half:
append-only history in `tcc_ops.manual_override`, the replay honouring a
saved base where the payroll supports it (and saying where every base came
from), and a recalculation that cannot pile up runs for one client.
"""
from __future__ import annotations

import threading
import time
from contextlib import nullcontext
from datetime import date, datetime, timedelta

import pytest

from application.commands import set_base_year as sb
from application.commands.run_client_calculation import _base_year_for
from domain.warehouse import ManualOverride, base_year_key
from infrastructure.persistence.memory_overrides import InMemoryManualOverrideRepository

T0 = datetime(2026, 9, 24, 18, 0, 0)


def _row(n, year, *, client=2001, unit="GA_GA-010", at=0):
    return ManualOverride(
        override_id=f"o{n}", run_id="r1", client_id=client, scope="unit",
        target_key=base_year_key("GA_JTC", unit), field_changed="base_year",
        value_before=None, value_after=None if year is None else str(year),
        reason_code=None, justification_text=None, created_by="test",
        created_at=T0 + timedelta(seconds=at),
    )


# --------------------------------------------------------- the store


def test_the_latest_choice_wins_and_a_clear_removes_it():
    repo = InMemoryManualOverrideRepository()
    repo.record(_row(1, 2022, at=0))
    repo.record(_row(2, 2023, at=1))
    assert repo.base_years(2001, "GA_JTC") == {"GA_GA-010": 2023}
    repo.record(_row(3, None, at=2))
    assert repo.base_years(2001, "GA_JTC") == {}
    # Append-only: the history keeps every decision, including the reversal.
    assert [r.value_after for r in repo.history(2001)] == ["2022", "2023", None]


def test_a_choice_belongs_to_one_client_and_one_programme():
    repo = InMemoryManualOverrideRepository()
    repo.record(_row(1, 2022, client=2001))
    assert repo.base_years(2003, "GA_JTC") == {}
    assert repo.base_years(2001, "SC_JTC") == {}


def test_scope_is_policed_because_fabric_will_not_police_it():
    with pytest.raises(ValueError):
        ManualOverride(**{**_row(1, 2022).__dict__, "scope": "client"})


# --------------------------------------------------------- the replay


def _years(*complete, partial=()):
    out = {y: {"months_with_headcount": 12} for y in complete}
    out.update({y: {"months_with_headcount": 5} for y in partial})
    return out


def _infer(unit_years, reachable_by_year):
    return min(y for y, u in unit_years.items() if u["months_with_headcount"] >= reachable_by_year.get(y, 12))


def test_a_saved_base_is_used_and_labelled():
    years = _years(2020, 2021, 2022)
    assert _base_year_for("GA_GA-010", years, {}, {"GA_GA-010": 2022}, _infer) == (2022, "override")


def test_without_a_saved_base_the_run_infers_as_it_always_has():
    years = _years(2020, 2021, 2022)
    assert _base_year_for("GA_GA-010", years, {}, {}, _infer) == (2020, "inferred")


def test_a_saved_base_the_payroll_no_longer_supports_is_not_honoured_silently(caplog):
    years = _years(2020, 2022, partial=(2021,))
    assert _base_year_for("GA_GA-010", years, {}, {"GA_GA-010": 2021}, _infer) == (2020, "inferred")
    assert _base_year_for("GA_GA-010", years, {}, {"GA_GA-010": 2019}, _infer) == (2020, "inferred")
    assert "not a complete year" in caplog.text


def test_a_complete_year_before_a_saved_base_is_not_a_shortfall():
    """Found live: Northwind GA-003 saved at TY2022 wrote TY2020-21 as Below
    minimum — two red years that were never measured."""
    from tools.unit_trend import STATUS_BEFORE_BASE, STATUS_PARTIAL, unit_status

    assert unit_status(tax_year=2020, base_year=2022, qualified=False,
                       months_with_headcount=12, months_reachable=11) == STATUS_BEFORE_BASE
    # A partial year before the base is still, first, a partial year.
    assert unit_status(tax_year=2020, base_year=2022, qualified=False,
                       months_with_headcount=5, months_reachable=11) == STATUS_PARTIAL
    # Unchanged for every year after the base.
    assert unit_status(tax_year=2023, base_year=2022, qualified=False,
                       months_with_headcount=12, months_reachable=11) == "below_minimum"


def test_the_gold_row_flags_a_saved_base_as_overridden():
    from types import SimpleNamespace

    from tools.gold_projection import UNIT_YEAR_MASTER_COLUMNS, unit_year_master_row

    stair = SimpleNamespace(net_new=3.0, threshold=2.0, qualified=True, eligible_jobs=3.0,
                            high_water_mark=15.0, new_jobs_created=3.0, backfilled=False,
                            annual_credit_usd=10500.0, per_job_usd=3500.0)
    trend = SimpleNamespace(base_average_headcount=12.0, base_year_overridden=False,
                            high_water_mark_overridden=False, tranche_years=5)
    row = unit_year_master_row(
        client_id=2001, worksite_id="GA_GA-010", entity_fein=None, program_code="GA_JTC",
        method="min_max", tax_year=2023, stair=stair, trend=trend,
        unit_year={"average_headcount": 15.0, "months_with_headcount": 12}, base_year=2022,
        base_year_source="override", months_reachable=12, declined=False, decline_reason=None,
        threshold_source="rule_pack", status="above_minimum", tier=1, designation="T1",
        tier_source="prototype", run_id="r2", appended_at=T0,
    )
    as_dict = dict(zip(UNIT_YEAR_MASTER_COLUMNS, row))
    assert as_dict["base_year_source"] == "override"
    assert as_dict["base_year_overridden"] in (1, True)


# --------------------------------------------------------- the command


class _Reader:
    def __init__(self, rows):
        self.rows = rows

    def scope(self):
        return nullcontext()

    def latest_run(self, client_id):
        return {"run_id": "run-before"}

    def unit_years(self, client_id, *, method, limit):
        return self.rows, len(self.rows)


GOLD = [
    {"worksite_id": "GA_GA-010", "tax_year": 2020, "is_base_year": True, "months_with_headcount": 11, "months_reachable": 11},
    {"worksite_id": "GA_GA-010", "tax_year": 2021, "is_base_year": False, "months_with_headcount": 5, "months_reachable": 11},
    {"worksite_id": "GA_GA-010", "tax_year": 2022, "is_base_year": False, "months_with_headcount": 11, "months_reachable": 11},
]


@pytest.fixture
def wired(monkeypatch):
    import application.wiring as wiring

    repo = InMemoryManualOverrideRepository()
    monkeypatch.setattr(wiring, "get_gold_reader", lambda: _Reader(GOLD))
    monkeypatch.setattr(wiring, "get_override_repository", lambda: repo)
    return repo


def _set(**kw):
    params = dict(client_id=2001, worksite_id="GA_GA-010", base_year=2022, recalculate=False,
                  actor="james", justification="reviewer's example")
    params.update(kw)
    return sb.handle_set_base_year(sb.SetBaseYearCommand(**params))


def test_saving_records_who_what_why_and_what_it_replaced(wired):
    answer = _set()
    assert answer["recorded"] is True
    [row] = wired.history(2001)
    assert (row.target_key, row.field_changed, row.value_before, row.value_after) == (
        "GA_JTC:GA_GA-010", "base_year", "2020", "2022",
    )
    assert (row.created_by, row.justification_text, row.run_id) == ("james", "reviewer's example", "run-before")
    assert wired.base_years(2001, "GA_JTC") == {"GA_GA-010": 2022}


def test_saving_the_same_year_twice_records_nothing_the_second_time(wired):
    _set()
    assert _set()["recorded"] is False
    assert len(wired.history(2001)) == 1


def test_clearing_is_a_new_row_not_a_delete(wired):
    _set()
    answer = _set(base_year=None)
    assert answer["recorded"] is True
    assert wired.base_years(2001, "GA_JTC") == {}
    assert len(wired.history(2001)) == 2


def test_a_partial_or_absent_year_cannot_be_saved(wired):
    with pytest.raises(sb.BaseYearNotAllowed, match="partial"):
        _set(base_year=2021)
    with pytest.raises(sb.BaseYearNotAllowed, match="no TY2019"):
        _set(base_year=2019)
    assert wired.history(2001) == []


def test_it_goes_through_the_mediator_and_is_audited(wired):
    from application.wiring import get_mediator

    get_mediator().send(sb.SetBaseYearCommand(client_id=2001, worksite_id="GA_GA-010", base_year=2022,
                                              recalculate=False, actor="james"))
    assert wired.base_years(2001, "GA_JTC") == {"GA_GA-010": 2022}


# --------------------------------------------------------- the recalculation


def test_saves_during_a_run_queue_one_more_run_not_one_each(monkeypatch):
    import application.wiring as wiring

    runs = []
    gate = threading.Event()

    class _Mediator:
        def send(self, command):
            runs.append(command.client_id)
            gate.wait(timeout=5)

    monkeypatch.setattr(wiring, "get_mediator", lambda: _Mediator())
    assert sb._recalculate_in_background(9001, 2025, "GA", "t") is True
    assert sb._recalculate_in_background(9001, 2025, "GA", "t") is False
    assert sb._recalculate_in_background(9001, 2025, "GA", "t") is False
    gate.set()
    for _ in range(100):
        if not sb.recalculation_running(9001):
            break
        time.sleep(0.05)
    assert runs == [9001, 9001], "the queued saves share ONE follow-up run"



# --------------------------------------------------------- an open year


def test_an_open_year_is_read_on_its_closed_months_and_never_priced():
    from types import SimpleNamespace

    from application.commands.run_client_calculation import _open_year_reading
    from application.open_year import is_open

    assert is_open(date(2026, 12, 31), on=date(2026, 9, 24)) is True
    assert is_open("2025-12-31", on=date(2026, 9, 24)) is False

    trend = SimpleNamespace(base_average_headcount=10.0, final_high_water_mark=14.0, per_job_usd=3500.0)
    on_track = _open_year_reading({"average_headcount": 13.0}, trend, {"threshold": 2.0, "per_job_usd": 3500.0}, 2.0)
    assert (on_track.net_new, on_track.qualified) == (3.0, True)
    # Nothing is claimable until the year closes.
    assert on_track.annual_credit_usd == 0.0 and on_track.eligible_jobs == 0.0
    short = _open_year_reading({"average_headcount": 11.0}, trend, {"threshold": 2.0}, 2.0)
    assert short.qualified is False
