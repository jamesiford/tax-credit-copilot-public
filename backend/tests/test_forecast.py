"""[N2] FCST-01 — run-rate forecast tests."""
from __future__ import annotations


def test_n2_forecast_endpoint_shape(client):
    r = client.get("/api/forecast/2025?state=GA")
    assert r.status_code == 200
    body = r.json()
    assert body["tax_year"] == 2025
    assert body["as_of"] == "2025-08-31"  # default ~8 months in
    ga = next(s for s in body["states"] if s["state"] == "GA")
    assert ga["_roadmap_tag"] == "N2"
    assert ga["months_elapsed"] == 8
    # Projection + finish-line invariants.
    assert ga["projected_average_headcount"] == ga["ytd_average_headcount"]
    assert ga["finish_line_headcount"] >= ga["prior_year_average_headcount"]
    assert ga["gap_to_finish"] >= 0
    assert "run-rate" in ga["method_note"].lower()


def test_n2_forecast_custom_as_of_changes_months_elapsed(client):
    early = client.get("/api/forecast/2025?state=GA&as_of=2025-03-31").json()
    ga_early = next(s for s in early["states"] if s["state"] == "GA")
    assert ga_early["months_elapsed"] == 3


def test_n2_forecast_invalid_as_of_422(client):
    assert client.get("/api/forecast/2025?as_of=not-a-date").status_code == 422


# ---------------------------------------------------------------------------
# The denominator, counted against the run's own months
# ---------------------------------------------------------------------------


def _august_year() -> list[str]:
    """A fiscal year opening in August, as `run_method_summary.month_ends` holds it."""
    return [
        "2023-08-31", "2023-09-30", "2023-10-31", "2023-11-30", "2023-12-31",
        "2024-01-31", "2024-02-29", "2024-03-31", "2024-04-30", "2024-05-31",
        "2024-06-30", "2024-07-31",
    ]


def test_months_elapsed_counts_the_runs_own_month_ends():
    """"All we have to do is change the denominator from 12 months to 8 or 9."

    Counted off the run's month ends, not off 1 January. For a client whose
    fiscal year opens in August, 31 December is month FIVE — counting from the
    calendar makes it twelve and the average is then divided by more than two
    times the months that have actually closed.
    """
    from datetime import date
    from application.queries.get_in_year_progress import _months_elapsed_from

    assert _months_elapsed_from(_august_year(), date(2023, 12, 31)) == 5
    assert _months_elapsed_from(_august_year(), date(2024, 3, 31)) == 8


def test_months_elapsed_floors_at_one_and_caps_at_the_series():
    from datetime import date
    from application.queries.get_in_year_progress import _months_elapsed_from

    # Before the first month closes. Zero would divide by zero downstream.
    assert _months_elapsed_from(_august_year(), date(2023, 8, 1)) == 1
    # Long after the year ended.
    assert _months_elapsed_from(_august_year(), date(2030, 1, 1)) == 12
    # A run that recorded no month ends still has to answer.
    assert _months_elapsed_from([], date(2024, 3, 31)) == 1


def test_an_open_year_does_not_count_a_month_its_payroll_has_not_reached(monkeypatch):
    """TY2026: payroll stops at 31 August, so nothing spans the 31 August month
    end. Counting it put a zero into the to-date average."""
    from datetime import date
    from application import open_year
    from application.queries.get_in_year_progress import _closed_months

    months = [f"2026-{m:02d}-28" for m in range(1, 13)]
    aug = date(2026, 8, 31)
    monkeypatch.setattr(open_year, "today", lambda: date(2026, 9, 24))
    assert _closed_months(months, [7, 8, 9, 10, 11], aug) == 7
    # A hole INSIDE the year is a real zero, not a month still to come.
    assert _closed_months(months, [3, 8, 9, 10, 11], aug) == 8
    # Once the year closes the pay calendar is a fact, not the future.
    monkeypatch.setattr(open_year, "today", lambda: date(2027, 3, 1))
    assert _closed_months(months, [7, 8, 9, 10, 11], aug) == 8


def test_the_forecast_prefers_a_supplied_average_over_a_replay():
    """Both averages were written by the run; re-deriving them cost two replays.

    Supplying them must bypass the payroll entirely — the empty row lists here
    are what proves it, because a replay over them would produce zero.
    """
    from datetime import date
    from tools.forecast import project_state_year_end

    projected = project_state_year_end(
        "GA", 2023, [], [], as_of=date(2024, 3, 31),
        ytd_average_headcount=410.13,
        prior_average_headcount=375.53,
    )
    assert projected is not None
    assert projected["ytd_average_headcount"] == 410.13
    assert projected["prior_year_average_headcount"] == 375.53
    assert projected["projected_average_headcount"] == 410.13


def test_the_reported_denominator_is_the_one_the_average_used():
    """The average is a sum over N months; the note must say the same N.

    The YTD average moved to the run's real month ends while the projection
    kept deriving `months_elapsed` from 1 January — so the reference client
    reported an average over eight months beside a note claiming twelve. The
    denominator IS the view; a wrong one there is not a cosmetic defect.
    """
    from datetime import date
    from tools.forecast import project_state_year_end

    projected = project_state_year_end(
        "GA", 2023, [], [], as_of=date(2024, 3, 31),
        months_elapsed=8,
        ytd_average_headcount=488.38,
        prior_average_headcount=0.0,
    )
    assert projected is not None
    assert projected["months_elapsed"] == 8
    assert "8 month" in projected["method_note"]


def test_n2_forecast_all_states_sorted_by_projected_credit(client):
    body = client.get("/api/forecast/2025").json()
    credits = [s["projected_annual_credit_usd"] for s in body["states"]]
    assert credits == sorted(credits, reverse=True)
    assert body["estimated_credit_total_usd"] == sum(credits)


# ---------------------------------------------------------------------------
# [T5 · ROADMAP-V] TN greenfield "how am I doing" ramp
# ---------------------------------------------------------------------------


def _tn_greenfield_rows(n: int = 30, unit: str = "TN_NASH_HQ", fein: str = "62-1111111") -> list[dict]:
    """A greenfield Nashville HQ: `n` full-time employees present all of 2025,
    monthly pay periods that cover each month-end. No prior-year rows (base = 0)."""
    from datetime import date, timedelta

    rows: list[dict] = []
    for i in range(n):
        ee = f"TNE{i:03d}"
        for m in range(1, 13):
            pps = date(2025, m, 1)
            ppe = (date(2025, m + 1, 1) - timedelta(days=1)) if m < 12 else date(2025, 12, 31)
            rows.append({
                "Tax_Year": 2025, "Employee_ID": ee, "Worksite_ID": unit,
                "Pay_Period_Start": pps.isoformat(), "Pay_Period_End": ppe.isoformat(),
                "Pay_Date": ppe.isoformat(),  # in-year (cash-basis) paycheck date
                "Hours_Worked": 172.0, "Gross_Wages": 4300.0,
                "Job_Title": "HQ Staff", "Entity_FEIN": fein, "Pay_Code": "Regular",
            })
    return rows


def test_t5_tn_greenfield_ramp_forecast():
    """The greenfield HQ pitch: forecast a zero-baseline Tennessee HQ. Prior-year
    average is 0 (nothing there before), so all projected headcount is net-new,
    and once the run-rate clears TN's finish line the forecast reads on-track."""
    from datetime import date
    from tools.forecast import project_state_year_end

    rows = _tn_greenfield_rows(30)
    res = project_state_year_end("TN", 2025, rows, prior_rows=[], as_of=date(2025, 12, 31))
    assert res is not None
    assert res["prior_year_average_headcount"] == 0.0            # greenfield base
    assert res["projected_average_headcount"] >= 25              # cleared the finish line
    assert res["projected_net_new"] == res["projected_average_headcount"]  # all net-new
    assert res["finish_line_headcount"] == res["threshold"]      # base 0 + threshold
    assert res["on_track"] is True
    assert res["gap_to_finish"] == 0.0
