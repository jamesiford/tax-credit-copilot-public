"""One employee's derivation, for a client-year that is not the certified one.

This exists because of a specific, quiet failure. `record_token` is a SHA-256
over (account, programme, year, employee), and the sealed workspace resolves it
from an index it builds once — for account 1001 in TY2023. Every per-client view
mints tokens the same way, correctly, and every one of them opened a 404 for any
other client-year. The token was never wrong; nothing served it.

So the tests that matter are the crossing ones: a token minted by the population
read resolves here, and a token minted for a DIFFERENT year does not silently
resolve to somebody.
"""
from __future__ import annotations

import os
from datetime import date

import pytest

from application.queries._client_run import ClientRunNotAvailable
from application.queries.get_eligibility import GetEligibilityQuery
from application.queries.get_employee_drill import GetEmployeeDrillQuery
from tools.tokens import record_token

_YEAR = 2025


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


def _a_live_token(mediator, tax_year=2023, account_id=1001):
    """A real handle from the live population read, for the reference client.

    Taken from the population read rather than minted here: the account is PART
    of the token, and the point of this test is that the two paths agree about
    it.
    """
    page = mediator.send(GetEligibilityQuery(
        tax_year=tax_year, state="GA", account_id=account_id, limit=1,
    ))
    return page["rows"][0]


def test_a_handle_is_required():
    with pytest.raises(ValueError, match="record_token is required"):
        GetEmployeeDrillQuery(record_token="  ", tax_year=_YEAR, state="GA")


class _DrillReader:
    """A stand-in for the Gold reader, so the drill's SHAPE tests stay offline.

    The drill used to replay the local CSV, which made it testable without
    Fabric and cost a full payroll load plus two engine passes per click in
    production. Reading Gold removed that cost and with it the offline path, so
    the shape is pinned here and the real join stays a live test.
    """

    def __init__(self, *, verdicts=None, segments=None, periods=None, run=True):
        self._run = {
            "run_id": "run-1",
            "fiscal_year_begin": date(2024, 8, 1),
            "fiscal_year_end": date(2025, 7, 31),
        } if run else None
        self._verdicts = verdicts if verdicts is not None else [
            {
                "method": "min_max", "employee_id": "E1", "weeks_worked": 52.0,
                "total_hours": 2080.0, "total_wages": 52000.0,
                "avg_weekly_hours": 40.0, "avg_weekly_wages": 1000.0,
                "eligible": True, "weight": 1.0, "days": 365,
                "first_start": date(2024, 8, 1), "last_end": date(2025, 7, 31),
            },
            {
                "method": "pay_period", "employee_id": "E1", "weeks_worked": 50.0,
                "total_hours": 2080.0, "total_wages": 52000.0,
                "avg_weekly_hours": 41.6, "avg_weekly_wages": 1040.0,
                "eligible": True, "weight": 1.0, "days": 350,
                "first_start": date(2024, 8, 1), "last_end": date(2025, 7, 31),
            },
        ]
        self._segments = segments or []
        self._periods = periods if periods is not None else [{
            "worksite_id": "GA_1", "entity_fein": "58-0000000", "job_title": "Server",
            "pay_period_start": date(2024, 8, 1), "pay_period_end": date(2024, 8, 14),
            "pay_date": date(2024, 8, 20), "pay_frequency_code": "BW",
            "hours": 80.0, "wages": 2000.0, "pay_code": "Regular",
            "selection_decision": "fiscal_window",
        }]

    def employee_drill(self, client_id, *, tax_year, record_token):
        if record_token != _KNOWN_TOKEN:
            return {"run": self._run, "verdicts": [], "segments": [], "periods": [],
                    "month_ends": []}
        return {
            "run": self._run, "verdicts": self._verdicts,
            "segments": self._segments, "periods": self._periods,
            "month_ends": _STORED_MONTH_ENDS,
        }


_KNOWN_TOKEN = "a" * 24
# What the run wrote: the window opens 1 Aug on a stub, so the run measures
# from 31 Aug. A derivation from `fiscal_year_begin` would start at 31 Jul.
_STORED_MONTH_ENDS = [
    "2024-08-31", "2024-09-30", "2024-10-31", "2024-11-30", "2024-12-31", "2025-01-31",
    "2025-02-28", "2025-03-31", "2025-04-30", "2025-05-31", "2025-06-30", "2025-07-31",
]


@pytest.fixture
def stub_reader():
    from application.wiring import set_gold_reader

    set_gold_reader(_DrillReader())
    yield
    set_gold_reader(None)


def test_a_handle_resolves_to_one_employee(stub_reader):
    """The join the sealed path could not make for any client but one."""
    from application.wiring import get_mediator

    drill = get_mediator().send(GetEmployeeDrillQuery(
        record_token=_KNOWN_TOKEN, tax_year=_YEAR, state="GA", account_id=1001,
    ))

    assert drill["employee_id"] == "E1"
    assert drill["basis"] == "per_client"
    assert drill["tax_year"] == _YEAR
    assert drill["step1"]["min_max"]["denominator_weeks"] == 52.0
    assert drill["step1"]["pay_period"]["denominator_weeks"] == 50.0


def test_a_client_is_required_because_a_handle_only_resolves_where_it_was_minted():
    from application.wiring import get_mediator

    with pytest.raises(ClientRunNotAvailable, match="client is required"):
        get_mediator().send(GetEmployeeDrillQuery(
            record_token=_KNOWN_TOKEN, tax_year=_YEAR, state="GA",
        ))


def test_an_unknown_handle_is_declined_rather_than_matched_to_somebody(stub_reader):
    from application.wiring import get_mediator

    with pytest.raises(ClientRunNotAvailable):
        get_mediator().send(GetEmployeeDrillQuery(
            record_token="0" * 24, tax_year=_YEAR, state="GA", account_id=1001,
        ))


def test_the_drill_names_the_window_rows_it_does_not_hold(stub_reader):
    """A REAL capability loss, and it has to be said rather than implied.

    The old path re-read the payroll and marked every paycheck the fiscal
    window excluded. Gold stores only the rows the run consumed, so those are
    gone — and "why is this person short a month" was exactly what they
    answered. Named here rather than left as a silently shorter list.
    """
    from application.wiring import get_mediator

    drill = get_mediator().send(GetEmployeeDrillQuery(
        record_token=_KNOWN_TOKEN, tax_year=_YEAR, state="GA", account_id=1001,
    ))

    assert {r["selection_decision"] for r in drill["raw_source_rows"]} == {"included"}
    assert any("EXCLUDED" in item for item in drill["not_available"])


def test_contested_months_are_absent_not_empty(stub_reader):
    """The matrix is deduped before it is stored, so a contest leaves no trace.

    An empty list beside a populated panel reads as "we checked and found
    none", which is a different and stronger claim than "not held".
    """
    from application.wiring import get_mediator

    drill = get_mediator().send(GetEmployeeDrillQuery(
        record_token=_KNOWN_TOKEN, tax_year=_YEAR, state="GA", account_id=1001,
    ))

    assert drill["onezero"]["overlap_flags"] == []
    assert any("contested" in item.lower() for item in drill["not_available"])


def test_the_drill_names_what_it_cannot_show(stub_reader):
    """An empty Access panel would read as 'we checked and found none'."""
    from application.wiring import get_mediator

    drill = get_mediator().send(GetEmployeeDrillQuery(
        record_token=_KNOWN_TOKEN, tax_year=_YEAR, state="GA", account_id=1001,
    ))

    assert "access_differences" not in drill
    assert any("Access" in item for item in drill["not_available"])
    assert len(drill["not_available"]) >= 3


def test_the_drill_agrees_with_the_population_read_about_eligibility(monkeypatch):
    """Two reads of one employee must not disagree about whether they qualify.

    This is now a GOLD-versus-ENGINE check, and worth more than it was. The
    population is read from `employee_eligibility`; the drill still replays the
    certified methods. If the run wrote something the engine no longer produces,
    this is where it surfaces.
    """
    _requires_fabric()
    # `conftest.py` pins DATA_SOURCE=csv for the suite. The population reads
    # Gold and does not care, but the drill still loads payroll — and under csv
    # the fiscal window is an assumed CALENDAR year, which holds no 2023 rows
    # for this client.
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    from application.wiring import get_mediator

    mediator = get_mediator()
    population = mediator.send(GetEligibilityQuery(
        tax_year=2023, state="GA", account_id=1001, limit=1,
    ))
    row = population["rows"][0]
    drill = mediator.send(GetEmployeeDrillQuery(
        record_token=row["record_token"], tax_year=2023, state="GA", account_id=1001,
    ))

    for method in ("min_max", "pay_period"):
        if row[method]["weeks"] is None:
            assert drill["step1"][method] is None
            continue
        assert drill["step1"][method]["eligible"] == row[method]["eligible"]
        assert drill["step1"][method]["denominator_weeks"] == row[method]["weeks"]


def test_payroll_outside_the_window_is_shown_and_marked():
    """Superseded — see `test_the_drill_names_the_window_rows_it_does_not_hold`.

    Gold holds only the rows the run consumed, so the excluded ones cannot be
    shown here any more. Kept as a named skip rather than deleted, because the
    capability was real and the loss is the thing worth remembering.
    """
    pytest.skip("excluded rows are not held in Gold; the drill names the gap instead")


def test_the_drill_names_what_it_cannot_show_live():
    """The same statement, against the real warehouse."""
    _requires_fabric()
    from application.wiring import get_mediator

    mediator = get_mediator()
    row = _a_live_token(mediator)
    drill = mediator.send(GetEmployeeDrillQuery(
        record_token=row["record_token"], tax_year=2023, state="GA",
        account_id=1001,
    ))

    assert "access_differences" not in drill
    assert any("Access" in item for item in drill["not_available"])
    assert len(drill["not_available"]) >= 3


def test_the_drill_months_are_the_runs_stored_month_ends(stub_reader):
    """Read, never re-derived from the window begin.

    The live join below caught the derivation one month out from the matrix
    for Candle Bottle, whose fiscal year opens on a stub.
    """
    from application.wiring import get_mediator

    drill = get_mediator().send(GetEmployeeDrillQuery(
        record_token=_KNOWN_TOKEN, tax_year=_YEAR, state="GA", account_id=1001,
    ))

    assert drill["onezero"]["months"] == _STORED_MONTH_ENDS


def test_the_drill_and_the_matrix_agree_on_the_months(monkeypatch):
    """The One/Zero tabs render month columns; they must be the same twelve."""
    from application.queries.get_onezero_matrix import GetOneZeroMatrixQuery
    from application.wiring import get_mediator

    # The matrix is read from Gold now and the drill still replays the engine,
    # so this is a gold-versus-engine agreement check and needs a client whose
    # run exists. Its value went up: the two paths could genuinely diverge.
    _requires_fabric()
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")

    mediator = get_mediator()
    population = mediator.send(GetEligibilityQuery(
        tax_year=2023, state="GA", account_id=1001, limit=1,
    ))
    drill = mediator.send(GetEmployeeDrillQuery(
        record_token=population["rows"][0]["record_token"],
        tax_year=2023, state="GA", account_id=1001,
    ))
    matrix = mediator.send(GetOneZeroMatrixQuery(
        tax_year=2023, state="GA", account_id=1001,
    ))

    assert drill["onezero"]["months"] == matrix["months"]


def test_the_reference_client_resolves_for_its_certified_year(monkeypatch):
    _requires_fabric()
    monkeypatch.setenv("DATA_SOURCE", "lakehouse")
    from application.wiring import get_mediator

    mediator = get_mediator()
    body = mediator.send(
        GetEligibilityQuery(tax_year=2023, state="GA", account_id=1001, limit=1)
    )
    row = body["rows"][0]

    drill = mediator.send(GetEmployeeDrillQuery(
        record_token=row["record_token"], tax_year=2023, state="GA", account_id=1001,
    ))
    assert drill["employee_id"] == row["employee_id"]


def test_the_walk_carries_the_rest_of_year_and_where_they_work(stub_reader):
    """29 Sep: the walk can add this person to a What-if stack, so it carries
    the same rest-of-year reading Near the line does, and the location."""
    from application.wiring import get_mediator

    drill = get_mediator().send(GetEmployeeDrillQuery(
        record_token=_KNOWN_TOKEN, tax_year=_YEAR, state="GA", account_id=1001,
    ))

    assert drill["rest_of_year"]["state"] in {"open", "on_pace", "closed", "no_payroll_to_date"}
    assert drill["where"]["worksite_id"] == "GA_1"
    assert drill["where"]["worksites"] == ["GA_1"]
