"""A run assesses every year the client holds payroll for, not one.

Northwind rendered a single filled cell where Ironbridge and Halloway rendered
six, on a client with the same order of headcount. Nothing was thin and nothing
was declined: `run_client_calculation` asked for one tax year.

The other half is the base year. Sweeping every year means the EARLIEST one has
no year before it, which is the exact path that once produced $379,750 instead
of $39,060. A first year is its own base and shows zero net-new; a base of 0.0
beside a real headcount means that regression is back.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from api import _assess
from application.commands.run_client_calculation import RunClientCalculationCommand


class _Repo:
    def __init__(self):
        self.recorded = []

    def current(self, *args, **kwargs):
        return None

    def record(self, claim):
        self.recorded.append(claim)


def _payroll(year_headcounts: dict[int, int]) -> list[dict]:
    """Weekly pay periods across a full calendar year, per employee.

    Average Headcount is measured over the calendar year by pay date, so a year
    needs periods spread across it -- one period would average to almost nothing
    and the year would read as a collapse rather than as itself.
    """
    rows: list[dict] = []
    for year, people in year_headcounts.items():
        start = date(year, 1, 1)
        for week in range(52):
            pps = start + timedelta(days=7 * week)
            ppe = pps + timedelta(days=6)
            pay_date = ppe + timedelta(days=5)
            if pay_date.year != year:
                continue  # selection is by pay date; keep the year clean
            for person in range(people):
                rows.append({
                    "Tax_Year": year,
                    "Employee_ID": f"E{person:04d}",
                    "Worksite_ID": "GA_GA-001",
                    "Work_State": "GA",
                    "Pay_Period_Start": pps.isoformat(),
                    "Pay_Period_End": ppe.isoformat(),
                    "Pay_Date": pay_date.isoformat(),
                    "Hours_Worked": 40,
                    "Gross_Wages": 800,
                    "Entity_FEIN": "FEIN_1",
                    "Job_Title": "x",
                    "Pay_Code": "Regular",
                })
    return rows


SIX_YEARS = {2020: 30, 2021: 34, 2022: 38, 2023: 42, 2024: 46, 2025: 52}


@pytest.fixture
def swept():
    """One sweep over six years of payroll, with the claims it recorded."""
    repo = _Repo()
    result = _assess.assess_client(2999, _payroll(SIX_YEARS), repository=repo)
    # Every loop below is over cells that must exist. Without this the loops
    # pass vacuously on an empty result and prove nothing.
    assert result["assessed"], "the fixture produced no assessed cells"
    return result, repo


# --- the sweep -------------------------------------------------------------


def test_a_run_assesses_every_year_the_payroll_covers(swept):
    """Northwind's six years of Gold must not render as one cell."""
    result, repo = swept

    recorded = sorted({c.tax_year for c in repo.recorded})
    assert recorded == sorted(SIX_YEARS), (
        f"payroll covers {sorted(SIX_YEARS)} but only {recorded} were recorded"
    )
    assert len(result["assessed"]) == len(SIX_YEARS)


def test_the_run_command_sweeps_by_default():
    command = RunClientCalculationCommand(client_id=2002, tax_year=2025)

    assert command.assess_tax_years == (), (
        "empty means every payroll year; a single year here is what caused the gap"
    )


def test_a_targeted_recalculation_still_records_one_year():
    repo = _Repo()
    result = _assess.assess_client(
        2999, _payroll(SIX_YEARS), tax_years=[2024], repository=repo,
    )

    assert result["assessed"], "the targeted year produced nothing"
    assert sorted({c.tax_year for c in repo.recorded}) == [2024]


def test_the_run_command_still_accepts_a_single_year():
    command = RunClientCalculationCommand(
        client_id=2002, tax_year=2025, assess_tax_years=(2025,),
    )

    assert command.assess_tax_years == (2025,)


def test_the_run_endpoint_sweeps_unless_it_is_told_otherwise(monkeypatch):
    """The endpoint is where the narrowing happened, so pin the mapping."""
    from application import wiring
    from api.trend import ClientRunRequest, create_client_run

    sent = []

    class _Mediator:
        def send(self, command):
            sent.append(command)
            return {}

    monkeypatch.setattr(wiring, "get_mediator", lambda: _Mediator())

    create_client_run(2002, ClientRunRequest(year=2025))
    assert sent[-1].assess_tax_years == (), "omitting assess_years must sweep"

    create_client_run(2002, ClientRunRequest(year=2025, assess_years=[2025]))
    assert sent[-1].assess_tax_years == (2025,), "a named year must stay targeted"


# --- the base year, swept --------------------------------------------------


def test_no_swept_year_reports_a_zero_base_beside_a_real_headcount(swept):
    """The regression guard. A base of 0.0 makes the whole headcount net-new."""
    result, _ = swept

    checked = 0
    for cell in result["assessed"]:
        if (cell["average_headcount"] or 0) > 0:
            checked += 1
            assert cell["base_average_headcount"] != 0.0, (
                f"TY{cell['tax_year']} has headcount "
                f"{cell['average_headcount']} against a base of zero"
            )
    assert checked == len(SIX_YEARS), "every year should carry a real headcount"


def test_the_earliest_swept_year_is_its_own_base(swept):
    result, _ = swept

    earliest = min(result["assessed"], key=lambda c: c["tax_year"])
    assert earliest["tax_year"] == min(SIX_YEARS)
    assert earliest["base_average_headcount"] == earliest["average_headcount"]
    assert earliest["net_new_jobs"] == 0


def test_a_later_year_measures_against_the_year_before_it(swept):
    """Not against the earliest year, and not against nothing."""
    result, _ = swept
    by_year = {c["tax_year"]: c for c in result["assessed"]}

    for year in sorted(SIX_YEARS)[1:]:
        assert by_year[year]["base_average_headcount"] == by_year[year - 1]["average_headcount"], (
            f"TY{year} did not measure against TY{year - 1}"
        )


# --- the base year, targeted -----------------------------------------------


def test_a_single_year_assessment_computes_the_year_before_it():
    """The prior year is an INPUT. Not requesting it must not delete it.

    `run_client_calculation` sent one year, so the year before was never
    computed and the base fell back to 0.0 -- which is what turned Ironbridge's
    TY2025 figure into $379,750.
    """
    result = _assess.assess_client(
        2999, _payroll({2024: 60, 2025: 70}), tax_years=[2025], repository=_Repo(),
    )

    assert result["years"] == [2025], "only the requested year is reported"
    assert result["assessed"], "the requested year produced nothing"

    cell = result["assessed"][0]
    assert cell["base_average_headcount"] not in (0.0, None), (
        "a base of zero makes the whole headcount net-new; 2024 payroll exists"
    )
    assert cell["base_average_headcount"] != cell["average_headcount"], (
        "2025 measured against itself, so the prior year was never found"
    )


def test_the_synthetic_prior_year_is_not_reported_as_declined():
    """Pulling in year-1 must not invent a coverage gap for a year nobody asked
    about."""
    result = _assess.assess_client(
        2999, _payroll({2024: 60, 2025: 70}), tax_years=[2025], repository=_Repo(),
    )

    assert all(d["tax_year"] in (2025, None) for d in result["declined"]), (
        f"declined leaked a year nobody requested: {result['declined']}"
    )


def test_a_year_with_no_growth_records_zero_rather_than_disappearing():
    """Absent and zero must not look alike: one is a gap, the other an answer."""
    result = _assess.assess_client(
        2999, _payroll({2023: 60, 2024: 60}), repository=_Repo(),
    )

    by_year = {c["tax_year"]: c for c in result["assessed"]}
    assert 2024 in by_year, "a flat year is an answer, not an omission"
    assert by_year[2024]["net_new_jobs"] == 0
    assert float(by_year[2024]["identified_usd"] or 0) == 0.0



# --- an open year (TY2026) --------------------------------------------------


def test_an_open_year_is_declined_by_name_not_claimed(monkeypatch):
    """TY2026 is open on 24 Sep 2026. Priced over twelve months it would read
    as a year that shrank by a third and re-rank the book on eight months."""
    import application.open_year as open_year

    monkeypatch.setattr(open_year, "today", lambda: date(2026, 9, 24))
    payroll = _payroll({2025: 60}) + [
        row for row in _payroll({2026: 70}) if row["Pay_Date"] <= "2026-08-31"
    ]
    result = _assess.assess_client(2999, payroll, tax_years=[2025, 2026], repository=_Repo())

    assessed_years = {c["tax_year"] for c in result["assessed"]}
    assert 2025 in assessed_years
    assert 2026 not in assessed_years
    [declined] = [d for d in result["declined"] if d["tax_year"] == 2026]
    assert declined["reason"] == "year_in_progress"
    assert "still open" in declined["detail"]


def test_a_closed_year_is_not_mistaken_for_an_open_one(monkeypatch):
    import application.open_year as open_year

    monkeypatch.setattr(open_year, "today", lambda: date(2027, 2, 1))
    result = _assess.assess_client(2999, _payroll({2025: 60, 2026: 70}), tax_years=[2026], repository=_Repo())
    assert {c["tax_year"] for c in result["assessed"]} == {2026}
