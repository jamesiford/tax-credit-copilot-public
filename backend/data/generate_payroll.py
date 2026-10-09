"""Generate a synthetic payroll dataset for the demo.

Run from `backend/`:

    python data/generate_payroll.py

Writes `data/payroll.csv`. Deterministic — same seed = same file.

Schema:
  employee_id        E00001 ...
  hire_date          ISO-8601
  term_date          ISO-8601 or empty
  location_state     two-letter
  location_county    string
  wage_type          'hourly' | 'salaried'
  annual_wage        USD, rounded to int
  hours_by_month     18 semicolon-separated ints (0 = inactive that month)

Tuned so multiple state credits fire across the 18-month window:
  GA  — Georgia JTC (2-job threshold, Tier 1) fires clearly
  SC  — SC JTC (5-job threshold) crossed mid-window
  TN  — TN JTC (25-job EOZ threshold) crossed Q2 2025; growth wave starts early
  VA  — VA MBJF (25-job threshold) crossed Q1 2026
  NC  — NC JTEC (10-job threshold) reached by Q3 2025
  FL  — FL QTI (10-job threshold) reached Q3 2025
  OH  — OH JCTC (10-job threshold) reached Q3 2025
  CO  — CO EZ (5-job threshold) reached Q2 2025
  NY  — NY Excelsior below threshold (NY contraction story)
  TX  — no state rule pack (federal WOTC still applies)
Target total: ~300 employees.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

SEED = 20260528
random.seed(SEED)

WINDOW_START = date(2024, 12, 1)  # first month of the 18-month window
MONTHS = 18
HOURS_FULL_TIME_MONTH = 173  # ~40 hrs/wk * 4.33
HOURS_PART_TIME_MONTH = 80

# Georgia is the headline jurisdiction. ~70% of the workforce.
GA_COUNTIES = [
    "Fulton", "Gwinnett", "DeKalb", "Cobb", "Clayton",
    "Chatham", "Muscogee", "Bibb", "Richmond", "Hall",
    "Lowndes", "Glynn", "Floyd", "Dougherty", "Houston",
]

OTHER_LOCATIONS = [
    ("NY", "New York"),
    ("NY", "Kings"),
    ("NY", "Queens"),
    ("SC", "Charleston"),
    ("SC", "Greenville"),
    ("TX", "Travis"),
    ("TX", "Harris"),
    ("TX", "Dallas"),
    # New states (Phase A expansion)
    ("NC", "Mecklenburg"),
    ("NC", "Wake"),
    ("TN", "Davidson"),
    ("TN", "Shelby"),
    ("FL", "Duval"),
    ("FL", "Miami-Dade"),
    ("OH", "Franklin"),
    ("OH", "Hamilton"),
    ("CO", "Denver"),
    ("VA", "Fairfax"),
]


@dataclass
class Employee:
    employee_id: str
    hire_date: date
    term_date: date | None
    state: str
    county: str
    wage_type: str
    annual_wage: int
    hours_by_month: list[int]


def _month_floor(d: date) -> date:
    return d.replace(day=1)


def _month_index(d: date) -> int:
    """Index of month `d` within the rolling window (0..MONTHS-1), or -1 if outside."""
    months = (d.year - WINDOW_START.year) * 12 + (d.month - WINDOW_START.month)
    return months if 0 <= months < MONTHS else -1


def _make_hours(hire: date, term: date | None, wage_type: str) -> list[int]:
    """Produce a 18-month hours array with realistic ramp/partial months."""
    base = HOURS_FULL_TIME_MONTH if wage_type == "salaried" else random.choice(
        [HOURS_FULL_TIME_MONTH, HOURS_FULL_TIME_MONTH, HOURS_PART_TIME_MONTH]
    )
    hours = [0] * MONTHS
    for m in range(MONTHS):
        month_start = (WINDOW_START.replace(day=15) + timedelta(days=31 * m)).replace(day=1)
        next_month = (month_start + timedelta(days=32)).replace(day=1)
        if hire >= next_month:
            continue
        if term is not None and term < month_start:
            continue
        # Partial-month proration on hire / term months.
        active_start = max(hire, month_start)
        active_end = min(term or next_month, next_month)
        days_active = max((active_end - active_start).days, 0)
        month_days = (next_month - month_start).days
        if days_active == 0:
            continue
        fraction = days_active / month_days
        # Add light noise so the dashboard sparkline isn't flat.
        jitter = random.uniform(0.92, 1.06) if wage_type == "hourly" else 1.0
        hours[m] = int(round(base * fraction * jitter))
    return hours


def _build_population() -> list[Employee]:
    employees: list[Employee] = []
    next_id = 1

    def add(n: int, state: str, county: str, wage_band: tuple[int, int], hire_window: tuple[date, date], term_prob: float = 0.10, salaried_share: float = 0.55, term_window: tuple[date, date] | None = None) -> None:
        nonlocal next_id
        for _ in range(n):
            hire = _random_date_between(*hire_window)
            term = None
            if term_window is not None:
                # Forced termination inside an explicit window (used to model the
                # NY contraction story — a cohort that leaves in early 2025).
                term = _random_date_between(*term_window)
            elif random.random() < term_prob:
                # Term sometime after hire, biased to last 9 months for "still happening" feel.
                earliest = hire + timedelta(days=60)
                latest = WINDOW_START + timedelta(days=30 * MONTHS) - timedelta(days=1)
                if earliest < latest:
                    term = _random_date_between(earliest, latest)
            wage_type = "salaried" if random.random() < salaried_share else "hourly"
            annual_wage = random.randint(*wage_band)
            emp = Employee(
                employee_id=f"E{next_id:05d}",
                hire_date=hire,
                term_date=term,
                state=state,
                county=county,
                wage_type=wage_type,
                annual_wage=annual_wage,
                hours_by_month=[],
            )
            emp.hours_by_month = _make_hours(emp.hire_date, emp.term_date, emp.wage_type)
            employees.append(emp)
            next_id += 1

    # ---- Georgia: 140 total. Mix of legacy hires + a clear growth wave. ----
    legacy_window = (date(2022, 1, 1), WINDOW_START)
    start_2025 = (date(2025, 1, 1), date(2025, 1, 20))  # full-year-2025 cohorts (net-new vs empty 2024)
    growth_q1_2025 = (date(2025, 1, 1), date(2025, 3, 31))
    growth_q4_2025 = (date(2025, 10, 1), date(2025, 12, 31))
    growth_q2_2026 = (date(2026, 4, 1), date(2026, 5, 28))

    # Existing GA workforce.
    for county in GA_COUNTIES[:6]:
        add(14, "GA", county, wage_band=(48_000, 110_000), hire_window=legacy_window, term_prob=0.15)
    # GA growth waves (these create the "net new jobs" the GA JTC rewards).
    add(18, "GA", "Fulton",   wage_band=(55_000, 95_000),  hire_window=growth_q1_2025, term_prob=0.05)
    add(12, "GA", "Gwinnett", wage_band=(52_000, 88_000),  hire_window=growth_q4_2025, term_prob=0.04)
    add(8,  "GA", "Cobb",     wage_band=(60_000, 105_000), hire_window=growth_q2_2026, term_prob=0.02)
    add(6,  "GA", "DeKalb",   wage_band=(50_000, 85_000),  hire_window=growth_q2_2026, term_prob=0.02)

    # ---- Other existing states ----
    # NY contraction story: an established 2024 team that SHEDS headcount in early
    # 2025 (a 7-person cohort departs Jan-May 2025). 2025 Average Headcount falls
    # below 2024 -> net-new is negative -> NY Excelsior credit is correctly $0.
    add(11, "NY", "New York", wage_band=(75_000, 140_000), hire_window=legacy_window, term_prob=0.0, salaried_share=0.85)
    add(7,  "NY", "Kings",    wage_band=(68_000, 110_000), hire_window=legacy_window, term_window=(date(2025, 1, 15), date(2025, 5, 31)), salaried_share=0.85)
    add(8,  "SC", "Charleston",wage_band=(50_000, 92_000),  hire_window=growth_q4_2025,   term_prob=0.05)
    add(6,  "SC", "Greenville",wage_band=(48_000, 85_000),  hire_window=legacy_window,    term_prob=0.12)
    add(10, "TX", "Travis",    wage_band=(70_000, 130_000), hire_window=growth_q1_2025,   term_prob=0.07)
    add(6,  "TX", "Harris",    wage_band=(62_000, 110_000), hire_window=growth_q4_2025,   term_prob=0.10)
    add(4,  "TX", "Dallas",    wage_band=(65_000, 115_000), hire_window=growth_q2_2026,   term_prob=0.05)

    # ---- Phase A: New state expansions ----------------------------------------
    # IMPORTANT: The 12-month comparison baseline is month index 5 (May 2025).
    # For new state credits with high thresholds (TN=25, VA=25) to fire, all
    # employees in those states must be hired AFTER May 2025 so baseline FTE = 0
    # and net_new = current_FTE (maximising qualifying jobs above threshold).

    growth_jun_sep_2025 = (date(2025, 6, 1), date(2025, 9, 30))  # post-baseline
    growth_q1_2026 = (date(2026, 1, 1), date(2026, 3, 31))

    # Tennessee: Nashville + Memphis EOZ hub. Mid-2025 ramp (TN JTC = 25-job EOZ
    # floor). The cohort ramps in the back half of 2025, so its 2025 Average
    # Headcount sits BELOW the 25-job threshold in year one -> a watch-list /
    # "on track to qualify once annualized" opportunity, not a year-one claim.
    add(18, "TN", "Davidson", wage_band=(52_000, 95_000), hire_window=growth_jun_sep_2025, term_prob=0.04)
    add(10, "TN", "Davidson", wage_band=(50_000, 88_000), hire_window=growth_q4_2025, term_prob=0.03)
    add(8,  "TN", "Shelby",   wage_band=(48_000, 82_000), hire_window=growth_jun_sep_2025, term_prob=0.05)

    # Virginia: Northern VA hub (VA MBJF = 25-job floor). Mid-2025 ramp -> 2025
    # Average Headcount below the 25-job floor in year one (watch-list).
    add(16, "VA", "Fairfax", wage_band=(65_000, 115_000), hire_window=growth_jun_sep_2025, term_prob=0.03)
    add(12, "VA", "Fairfax", wage_band=(60_000, 105_000), hire_window=growth_q4_2025, term_prob=0.04)

    # Florida: Jacksonville + Miami — post-baseline for net_new > 10 threshold
    add(12, "FL", "Duval",      wage_band=(50_000, 88_000), hire_window=growth_jun_sep_2025, term_prob=0.05)
    add(6,  "FL", "Duval",      wage_band=(52_000, 90_000), hire_window=growth_q4_2025, term_prob=0.04)
    add(4,  "FL", "Miami-Dade", wage_band=(55_000, 95_000), hire_window=growth_q1_2026, term_prob=0.04)

    # North Carolina: Charlotte + Raleigh corridor. A large cohort lands at the
    # START of 2025 (active all twelve months) with zero 2024 history, so its
    # full-year 2025 Average Headcount clears the NC JTEC 10-job net-new floor.
    # This is the headline "discovery" win — a state the client's tax lead never
    # tracked that genuinely qualifies under the statutory engine.
    add(30, "NC", "Mecklenburg", wage_band=(55_000, 95_000), hire_window=start_2025, term_prob=0.02, salaried_share=0.85)
    add(6,  "NC", "Wake",        wage_band=(58_000, 98_000), hire_window=growth_q4_2025, term_prob=0.03, salaried_share=0.80)

    # Ohio: Columbus + Cincinnati — post-baseline for net_new > 10 threshold
    add(10, "OH", "Franklin",  wage_band=(52_000, 90_000), hire_window=growth_jun_sep_2025, term_prob=0.05)
    add(5,  "OH", "Franklin",  wage_band=(50_000, 88_000), hire_window=growth_q4_2025, term_prob=0.04)
    add(3,  "OH", "Hamilton",  wage_band=(50_000, 85_000), hire_window=growth_q1_2026, term_prob=0.04)

    # Colorado: Denver Enterprise Zone (CO EZ = 5-job floor). A start-of-2025
    # cohort active all year clears the 5-job net-new floor -> a second, smaller
    # "discovery" win alongside North Carolina.
    add(13, "CO", "Denver", wage_band=(60_000, 105_000), hire_window=start_2025, term_prob=0.02, salaried_share=0.85)

    return employees


def _random_date_between(start: date, end: date) -> date:
    span = (end - start).days
    if span <= 0:
        return start
    return start + timedelta(days=random.randint(0, span))


def write_csv(path: Path, employees: list[Employee]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "employee_id", "hire_date", "term_date",
            "location_state", "location_county",
            "wage_type", "annual_wage", "hours_by_month",
        ])
        for e in employees:
            w.writerow([
                e.employee_id,
                e.hire_date.isoformat(),
                e.term_date.isoformat() if e.term_date else "",
                e.state, e.county, e.wage_type, e.annual_wage,
                ";".join(str(h) for h in e.hours_by_month),
            ])


def main() -> None:
    employees = _build_population()
    out = Path(__file__).parent / "payroll.csv"
    write_csv(out, employees)
    print(f"Wrote {len(employees)} employees to {out}")
    # Sanity print: how many people are active in each of the 18 months per state?
    by_state: dict = {}
    for e in employees:
        by_state.setdefault(e.state, []).append(e)
    for state in sorted(by_state):
        cohort = by_state[state]
        active_by_month = [sum(1 for e in cohort if e.hours_by_month[m] > 0) for m in range(MONTHS)]
        print(f"{state} ({len(cohort)} total) active-by-month: {active_by_month}")


if __name__ == "__main__":
    main()
