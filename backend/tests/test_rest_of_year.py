"""WI-19: "she has to work this many hours per week for the rest of the year."

Two halves that must agree: the Near the line row states what the rest of the
year needs, and the Employee lever in What-if applies it. The last tests are
the contract — on real synthetic payroll, applying exactly the figure the row
states must flip the employee in the certified engine, and a little less must
not.
"""
from __future__ import annotations

from datetime import date

import pytest

from application.queries.simulate_employee import (
    EmployeeSimulationNotAvailable, apply_rest_of_year,
)
from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
from data.source.to_bcs import source_to_bcs_rows
from domain.calculation.floors import StatutoryFloors
from domain.calculation.onezero import run_min_max_method
from domain.calculation.proximity import assess_employee, rest_of_year
from tools.credit_math import load_pack_one_zero, resolve_statutory_floors

FLOORS = resolve_statutory_floors("GA_JTC", 2025)


def _weekly(hours: float, wage: float, weeks: range, start=date(2025, 1, 6)):
    from datetime import timedelta

    out = []
    for n in weeks:
        s = start + timedelta(days=7 * n)
        e = s + timedelta(days=6)
        out.append({"pay_period_start": s.isoformat(), "pay_period_end": e.isoformat(),
                    "hours": hours, "wages": hours * wage})
    return out


# ------------------------------------------------------------- the reading


def test_a_small_full_year_gap_is_a_bigger_rest_of_year_one():
    """34 hrs/wk for 34 weeks: 1 hr/wk short on the year, far more per week after 31 Aug."""
    reading = rest_of_year(_weekly(34.0, 25.0, range(34)), floors=FLOORS,
                           as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
    assert reading["state"] == "open"
    assert reading["binding"] == "hours"
    assert reading["additional_weekly_hours"] > 1.0
    assert reading["remaining_pay_periods"] == pytest.approx(round(reading["weeks_remaining"]), abs=1)
    # And the figure really does clear the floor over the year.
    total = reading["hours_to_date"] + reading["needed_weekly_hours"] * reading["weeks_remaining"]
    # Weeks are reported to two places, so allow for that rounding here.
    assert total / (reading["weeks_to_date"] + reading["weeks_remaining"]) >= 35.0 - 0.005


def test_someone_on_pace_needs_nothing():
    reading = rest_of_year(_weekly(38.0, 25.0, range(34)), floors=FLOORS,
                           as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
    assert reading["state"] == "on_pace"


def test_a_closed_year_says_so():
    reading = rest_of_year(_weekly(34.0, 25.0, range(34)), floors=FLOORS,
                           as_of=date(2025, 12, 31), year_end=date(2025, 12, 31))
    assert reading == {"state": "closed", "note": "The year is closed."}


def test_below_the_threshold_rate_a_raise_is_the_lever():
    """40 hrs at $15 clears hours and fails $680: more hours is the wrong advice."""
    reading = rest_of_year(_weekly(40.0, 15.0, range(34)), floors=FLOORS,
                           as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
    assert reading["binding"] == "wages"
    assert reading["rate_limited"] is True
    assert reading["hourly_rate_to_qualify"] > 15.0
    assert reading["exceeds_plausible_week"] is True


def test_nothing_after_the_checkpoint_is_read():
    """On 31 August the rest of the year has not happened."""
    early = _weekly(34.0, 25.0, range(34))
    later = early + _weekly(60.0, 25.0, range(34, 51))
    a = rest_of_year(early, floors=FLOORS, as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
    b = rest_of_year(later, floors=FLOORS, as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
    assert a == b


# ------------------------------------------------ the two halves agree


@pytest.fixture(scope="module")
def cascade_2025():
    rows = [
        r for r in source_to_bcs_rows(build_synthetic_dataset(SYNTHETIC_CLIENTS[0]))
        if r["Work_State"] == "GA" and r["Pay_Date"][:4] == "2025"
    ]
    kwargs = dict(tax_year=2025, analysis_start_month=date(2025, 1, 1),
                  pack=load_pack_one_zero("GA", tax_year=2025),
                  fiscal_window=(date(2025, 1, 1), date(2025, 12, 31)))
    result = run_min_max_method(rows, **kwargs)
    floors = resolve_statutory_floors("GA_JTC", 2025)
    eligible = {str(e["Employee_ID"]) for e in result.eligible_employees}
    near = sorted(
        (assess_employee(a, floors=floors) for a in result.all_averages if str(a["Employee_ID"]) not in eligible),
        key=lambda a: a["additional_weekly_hours"] if a["additional_weekly_hours"] is not None else 99,
    )
    target = next(
        a for a in near
        if a["failure_mode"] == "hours_only" and a["weeks_worked"] > 45
        and rest_of_year(_periods(rows, str(a["employee_id"])), floors=floors,
                         as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))["state"] == "open"
    )
    return rows, kwargs, floors, str(target["employee_id"])


def _periods(rows, employee_id):
    return [
        {"pay_period_start": r["Pay_Period_Start"], "pay_period_end": r["Pay_Period_End"],
         "hours": r["Hours_Worked"], "wages": r["Gross_Wages"], "pay_date": r.get("Pay_Date")}
        for r in rows if str(r["Employee_ID"]) == employee_id
    ]


def _eligible(result, employee_id):
    return any(str(e["Employee_ID"]) == employee_id for e in result.eligible_employees)


def test_the_stated_figure_flips_the_employee_in_the_engine(cascade_2025):
    rows, kwargs, floors, emp = cascade_2025
    reading = rest_of_year(_periods(rows, emp), floors=floors,
                           as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
    assert reading["state"] == "open"
    moved, applied = apply_rest_of_year(rows, emp, as_of=date(2025, 8, 31),
                                        extra_weekly_hours=reading["additional_weekly_hours"])
    assert not _eligible(run_min_max_method(rows, **kwargs), emp)
    assert _eligible(run_min_max_method(moved, **kwargs), emp), (emp, reading, applied)


def test_a_little_less_than_the_figure_does_not(cascade_2025):
    rows, kwargs, floors, emp = cascade_2025
    reading = rest_of_year(_periods(rows, emp), floors=floors,
                           as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
    short = max(0.0, reading["additional_weekly_hours"] - 0.5)
    moved, _ = apply_rest_of_year(rows, emp, as_of=date(2025, 8, 31), extra_weekly_hours=short)
    assert not _eligible(run_min_max_method(moved, **kwargs), emp)


def test_only_that_employee_and_only_after_the_checkpoint_moves(cascade_2025):
    rows, _kwargs, _floors, emp = cascade_2025
    moved, _ = apply_rest_of_year(rows, emp, as_of=date(2025, 8, 31), extra_weekly_hours=2.0)
    for old, new in zip(rows, moved):
        if str(old["Employee_ID"]) != emp or old["Pay_Period_End"] <= "2025-08-31":
            assert old is new


def test_no_open_periods_is_a_closed_year(cascade_2025):
    rows, _kwargs, _floors, emp = cascade_2025
    with pytest.raises(EmployeeSimulationNotAvailable, match="closed"):
        apply_rest_of_year(rows, emp, as_of=date(2025, 12, 31), extra_weekly_hours=1.0)

def test_an_open_year_projects_the_periods_it_has_not_reached(cascade_2025):
    """TY2026: payroll stops at the checkpoint. The remaining periods are
    projected on the employee's own cadence, labelled, and the stated figure
    still flips the verdict in the engine."""
    rows, kwargs, floors, emp = cascade_2025
    to_date = [r for r in rows if str(r.get("Pay_Date") or "")[:10] <= "2025-08-31"]
    reading = rest_of_year(_periods(to_date, emp), floors=floors,
                           as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
    assert reading["state"] == "open"
    with pytest.raises(EmployeeSimulationNotAvailable, match="closed"):
        apply_rest_of_year(to_date, emp, as_of=date(2025, 8, 31), extra_weekly_hours=1.0)

    moved, applied = apply_rest_of_year(
        to_date, emp, as_of=date(2025, 8, 31),
        extra_weekly_hours=reading["additional_weekly_hours"], window_end=date(2025, 12, 31),
    )
    projected = [r for r in moved if r.get("_Projected")]
    assert projected and applied["periods_projected"] == len(projected)
    assert {str(r["Employee_ID"]) for r in projected} == {emp}
    assert all(r["Pay_Date"] <= "2025-12-31" and r["Pay_Period_End"] > "2025-08-31" for r in projected)
    assert all(r["_Source_Payroll_Id"] is None for r in projected)
    assert moved[: len(to_date)] == to_date
    assert _eligible(run_min_max_method(moved, **kwargs), emp), (emp, reading, applied)


# ------------------------------------------------ a stack of employees (28 Sep)


def _open_hours_only(rows, kwargs, floors, n):
    """The first `n` hours-only near misses whose rest of year is open."""
    result = run_min_max_method(rows, **kwargs)
    eligible = {str(e["Employee_ID"]) for e in result.eligible_employees}
    near = sorted(
        (assess_employee(a, floors=floors) for a in result.all_averages if str(a["Employee_ID"]) not in eligible),
        key=lambda a: a["additional_weekly_hours"] if a["additional_weekly_hours"] is not None else 99,
    )
    picked = []
    for a in near:
        emp = str(a["employee_id"])
        if a["failure_mode"] != "hours_only" or a["weeks_worked"] <= 45:
            continue
        reading = rest_of_year(_periods(rows, emp), floors=floors,
                               as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
        if reading["state"] == "open" and not reading["rate_limited"]:
            picked.append((emp, reading))
        if len(picked) == n:
            return picked
    pytest.skip(f"fewer than {n} open hours-only near misses in the fixture")


def test_a_stack_flips_every_employee_in_it_in_one_engine_run(cascade_2025):
    rows, kwargs, floors, _emp = cascade_2025
    picked = _open_hours_only(rows, kwargs, floors, 3)
    moved = rows
    for emp, reading in picked:
        moved, _ = apply_rest_of_year(moved, emp, as_of=date(2025, 8, 31),
                                      extra_weekly_hours=reading["suggested_additional_weekly_hours"])
    after = run_min_max_method(moved, **kwargs)
    for emp, _reading in picked:
        assert _eligible(after, emp), emp
    stacked = {emp for emp, _ in picked}
    for old, new in zip(rows, moved):
        if str(old["Employee_ID"]) not in stacked:
            assert old is new


def _rate_limited(rows, kwargs, floors):
    """An eligible full-timer, re-paid at $15/hr: clears hours, fails $680/wk."""
    result = run_min_max_method(rows, **kwargs)
    target = next(
        str(a["Employee_ID"]) for a in result.all_averages
        if 38 <= float(a["avg_weekly_hours"]) <= 42 and float(a.get("weeks_worked") or 0) > 45
    )
    repaid = [
        {**r, "Gross_Wages": float(r["Hours_Worked"] or 0) * 15.0} if str(r["Employee_ID"]) == target else r
        for r in rows
    ]
    return repaid, target


def test_a_raise_is_a_lever_and_the_suggested_one_flips_the_verdict(cascade_2025):
    rows, kwargs, floors, _emp = cascade_2025
    repaid, emp = _rate_limited(rows, kwargs, floors)
    assert not _eligible(run_min_max_method(repaid, **kwargs), emp)
    reading = rest_of_year(_periods(repaid, emp), floors=floors,
                           as_of=date(2025, 8, 31), year_end=date(2025, 12, 31))
    assert reading["rate_limited"] is True
    assert reading["suggested_hourly_raise"] > 0
    # The hours lever alone would ask for an implausible week; the pair does not.
    assert reading["suggested_additional_weekly_hours"] < reading["additional_weekly_hours"]

    moved, applied = apply_rest_of_year(
        repaid, emp, as_of=date(2025, 8, 31),
        extra_weekly_hours=reading["suggested_additional_weekly_hours"],
        hourly_raise=reading["suggested_hourly_raise"],
    )
    assert applied["projected_rate"] == pytest.approx(applied["rate"] + reading["suggested_hourly_raise"], abs=0.011)
    assert _eligible(run_min_max_method(moved, **kwargs), emp), (reading, applied)

    short, _ = apply_rest_of_year(
        repaid, emp, as_of=date(2025, 8, 31),
        extra_weekly_hours=reading["suggested_additional_weekly_hours"],
        hourly_raise=max(0.0, reading["suggested_hourly_raise"] - 0.5),
    )
    assert not _eligible(run_min_max_method(short, **kwargs), emp)


def test_a_raise_leaves_the_closed_periods_as_paid(cascade_2025):
    rows, kwargs, floors, _emp = cascade_2025
    repaid, emp = _rate_limited(rows, kwargs, floors)
    moved, _ = apply_rest_of_year(repaid, emp, as_of=date(2025, 8, 31), extra_weekly_hours=0.0, hourly_raise=3.0)
    for old, new in zip(repaid, moved):
        if old["Pay_Period_End"] <= "2025-08-31":
            assert old is new


def test_the_stack_query_refuses_what_it_cannot_mean():
    from application.queries.simulate_employee import EmployeeChange, MAX_STACK, SimulateEmployeeQuery

    one = EmployeeChange("a", additional_weekly_hours=1.0)
    with pytest.raises(ValueError, match="at least one"):
        SimulateEmployeeQuery(client_id=2001, tax_year=2025, changes=())
    with pytest.raises(ValueError, match="twice"):
        SimulateEmployeeQuery(client_id=2001, tax_year=2025, changes=(one, one))
    with pytest.raises(ValueError, match="at most"):
        SimulateEmployeeQuery(client_id=2001, tax_year=2025, changes=tuple(
            EmployeeChange(f"t{i}") for i in range(MAX_STACK + 1)
        ))
    with pytest.raises(ValueError, match="hourly_raise"):
        EmployeeChange("a", hourly_raise=-1.0)
    with pytest.raises(ValueError, match="additional_weekly_hours"):
        EmployeeChange("a", additional_weekly_hours=41.0)


@pytest.fixture
def stack_wired(monkeypatch, cascade_2025):
    """The handler against the fixture payroll, with no Gold behind it."""
    from contextlib import nullcontext
    from types import SimpleNamespace

    import application.queries._client_run as client_run
    import application.wiring as wiring

    rows, kwargs, floors, _emp = cascade_2025
    run = SimpleNamespace(
        rows=rows, program_code="GA_JTC",
        window=SimpleNamespace(begin=date(2025, 1, 1), end=date(2025, 12, 31)),
        engine_kwargs=lambda: kwargs,
    )
    monkeypatch.setattr(client_run, "resolve_client_run", lambda **_kw: run)

    class _Reader:
        def scope(self):
            return nullcontext()

        def unit_years(self, client_id, *, method, limit):
            return [], 0

    monkeypatch.setattr(wiring, "get_gold_reader", lambda: _Reader())
    return rows, kwargs, floors


def test_the_handler_answers_for_every_employee_in_the_stack(stack_wired):
    from application.queries.simulate_employee import (
        EmployeeChange, SimulateEmployeeQuery, handle_simulate_employee,
    )
    from tools.tokens import record_token

    rows, kwargs, floors = stack_wired
    picked = _open_hours_only(rows, kwargs, floors, 2)
    changes = tuple(
        EmployeeChange(record_token(2001, "GA_JTC", 2025, emp),
                       additional_weekly_hours=reading["suggested_additional_weekly_hours"])
        for emp, reading in picked
    )
    answer = handle_simulate_employee(SimulateEmployeeQuery(client_id=2001, tax_year=2025, changes=changes))

    assert [e["record_token"] for e in answer["employees"]] == [c.record_token for c in changes]
    assert answer["summary"] == {"employees": 2, "became_eligible": 2, "lost_eligibility": 0, "locations_moved": 0}
    for entry in answer["employees"]:
        assert entry["before"]["eligible"] is False and entry["after"]["eligible"] is True
        assert entry["worksite_id"] in entry["worksites"]
        assert entry["tier_source"] == "unassigned"  # no Gold row behind the fixture
    assert "All 2 changes are applied together" in answer["method_note"]
    # A closed year is priced by the engine; there is no run-rate to state.
    assert answer["client"]["run_rate"] is None


def test_a_record_the_client_year_does_not_hold_is_refused(stack_wired):
    from application.queries.simulate_employee import (
        EmployeeChange, SimulateEmployeeQuery, handle_simulate_employee,
    )

    with pytest.raises(EmployeeSimulationNotAvailable, match="1 of the 1"):
        handle_simulate_employee(SimulateEmployeeQuery(
            client_id=2001, tax_year=2025, changes=(EmployeeChange("nope", additional_weekly_hours=1.0),),
        ))


# ------------------------------------------------------------ the endpoint


def test_the_endpoint_takes_a_stack_and_refuses_a_malformed_one(client, monkeypatch):
    seen = {}

    def fake(query):
        seen["query"] = query
        return {"employees": [], "summary": {"employees": len(query.changes)}}

    import api.simulate as endpoint

    monkeypatch.setattr(endpoint, "get_mediator", lambda: type("M", (), {"send": staticmethod(fake)})())

    body = {"client_id": 2001, "tax_year": 2026, "employees": [
        {"record_token": "a", "additional_weekly_hours": 1.5},
        {"record_token": "b", "hourly_raise": 2.25},
    ]}
    ok = client.post("/api/simulate/employee", json=body)
    assert ok.status_code == 200, ok.text
    changes = seen["query"].changes
    assert [(c.record_token, c.additional_weekly_hours, c.hourly_raise) for c in changes] == [
        ("a", 1.5, 0.0), ("b", 0.0, 2.25),
    ]

    duplicate = {**body, "employees": [{"record_token": "a"}, {"record_token": "a"}]}
    assert client.post("/api/simulate/employee", json=duplicate).status_code == 422
    assert client.post("/api/simulate/employee", json={**body, "employees": []}).status_code == 422
    negative = {**body, "employees": [{"record_token": "a", "hourly_raise": -1}]}
    assert client.post("/api/simulate/employee", json=negative).status_code == 422


def test_a_near_the_line_row_names_where_they_work_most():
    from application.queries.get_proximity import _where_they_work

    periods = [
        {"worksite_id": "GA_GA-001", "hours": 20.0},
        {"worksite_id": "GA_GA-013", "hours": 50.0},
        {"worksite_id": "GA_GA-013", "hours": 10.0},
    ]
    where = _where_they_work(periods, client_id=2001, tax_year=2021)
    assert where["worksite_id"] == "GA_GA-013"
    assert where["worksites"] == ["GA_GA-001", "GA_GA-013"]
    # GA-013 was bottom-40 in TY2021 (WI-18): the row reads the year it is about.
    assert where["designation"] == "T1 B40"
    assert where["tier_source"] == "prototype"
    assert _where_they_work([], client_id=2001, tax_year=2021) == {}


def test_one_function_gives_every_list_the_same_rest_of_year(monkeypatch):
    """Near the line, a location's near-the-floor list and the walk all pre-fill
    the stack from `attach_rest_of_year`, so the three cannot disagree."""
    from types import SimpleNamespace

    import application.wiring as wiring
    from application.queries.get_proximity import attach_rest_of_year

    periods = {"tok": [
        {"worksite_id": "GA_GA-016", "pay_period_start": p["pay_period_start"], "pay_period_end": p["pay_period_end"],
         "pay_date": p["pay_period_end"], "hours": p["hours"], "wages": p["wages"]}
        for p in _weekly(34.0, 25.0, range(34))
    ]}

    class _Reader:
        def cohort_periods(self, client_id, *, tax_year, run_id, tokens):
            assert tokens == ["tok", "absent"]
            return periods

    monkeypatch.setattr(wiring, "get_gold_reader", lambda: _Reader())
    resolved = SimpleNamespace(floors=FLOORS, window=SimpleNamespace(end=date(2025, 12, 31)))
    rows = [{"record_token": "tok"}, {"record_token": "absent"}]
    attach_rest_of_year(rows, client_id=2001, tax_year=2025, run_id="r", resolved=resolved, as_of=date(2025, 8, 31))

    assert rows[0]["rest_of_year"] == rest_of_year(
        periods["tok"], floors=FLOORS, as_of=date(2025, 8, 31), year_end=date(2025, 12, 31),
    )
    assert rows[0]["worksite_id"] == "GA_GA-016"
    assert "rest_of_year" not in rows[1]


def test_a_closed_year_gives_a_location_list_no_rest_of_year(monkeypatch):
    from types import SimpleNamespace

    import application.queries._client_run as client_run
    from api.trend import _with_rest_of_year

    monkeypatch.setattr(client_run, "resolve_statute", lambda **_k: SimpleNamespace(
        floors=FLOORS, window=SimpleNamespace(end=date(2025, 12, 31)),
    ))
    rows = [{"record_token": "tok"}]
    _with_rest_of_year(rows, client_id=2001, state="GA", tax_year=2024, run={"run_id": "r"})
    assert rows == [{"record_token": "tok"}]
