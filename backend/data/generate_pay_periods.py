"""Generate a pay-period-grain synthetic payroll dataset shaped to the
Silver Record Layout (the partner's published 16-field schema).

Run from `backend/`:

    python data/generate_pay_periods.py

Writes `data/payroll_pay_periods.csv` with the **11 required** BCS fields.
The 5 PII-sensitive optional fields (Last Name, First Name, SSN, Last Hire
Date, Term Date) are intentionally OMITTED — that omission is itself a
demonstration of the "PII never leaves the database"
principle that the engine, the agents, and the deliverables all enforce.

Silver Record Layout (from the partner's business-framing overview):

| Field           | Required | Generated? |
| ---             | ---      | ---        |
| Tax Year        | Yes      | YES        |
| EmployeeID      | Yes      | YES        |
| Last Name       | No       | omitted (PII) |
| First Name      | No       | omitted (PII) |
| SSN             | No       | omitted (PII) |
| Job Title       | Yes      | YES        |
| Worksite ID     | Yes      | YES        |
| Pay Period Start| Yes      | YES        |
| Pay Period End  | Yes      | YES        |
| Pay Date        | Yes      | YES        |
| Entity FEIN     | Yes      | YES        |
| Last Hire Date  | No       | omitted (PII) |
| Term Date       | No       | omitted (PII) |
| Hours Worked    | Yes      | YES        |
| Gross Wages     | Yes      | YES        |
| Pay Code        | Yes      | YES        |

Source-of-truth: this generator READS the existing employee roster from
`data/payroll.csv` so the One/Zero engine and the federal new-hire count operate
on consistent identities (same EE_ID, state, county, wage). It then layers
pay-period grain on top with realistic pay frequencies and assigns each
employee to a worksite (or to multiple worksites for the GA cross-unit
movement scenario that validates the Min Max method).

Tax-year coverage:
  - Full calendar year 2024 (Jan 1 -> Dec 31) -> the PRIOR-YEAR BASELINE. Only
    established states (GA, NY, SC — employees hired before 2025) have rows
    here; the Phase-A expansion states (NC/TN/FL/OH/CO/VA/TX) hired entirely in
    2025 so they correctly have NO 2024 history (they are genuinely net-new).
    This is what makes the 2025 net-new calculation real: continuing operations
    net against their 2024 Average Headcount; brand-new sites count in full.
  - Full calendar year 2025 (Jan 1 -> Dec 31) -> the primary One/Zero fixture.
  - The retroactive scan replays both years; 2024 is the base/establishment
    year (no 2023 prior in the dataset), 2025 nets against 2024.

Deterministic seed -> same output every run.
"""
from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SEED = 20260530
HERE = Path(__file__).resolve().parent
PAYROLL_CSV = HERE / "payroll.csv"
OUT_CSV = HERE / "payroll_pay_periods.csv"

# Tax-year coverage: tuple of (tax_year, start, end) windows.
TAX_YEAR_WINDOWS: list[tuple[int, date, date]] = [
    (2024, date(2024, 1, 1), date(2024, 12, 31)),   # Full 2024 - prior-year baseline (established states only)
    (2025, date(2025, 1, 1), date(2025, 12, 31)),   # Full 2025 - primary fixture
]

# Pay frequency mix (fraction of employees on each cycle).
# Real-world: bi-weekly dominates; weekly common for hourly; semi-monthly for
# salaried; monthly is rare.
FREQUENCY_MIX = {
    "biweekly": 0.55,
    "weekly": 0.30,
    "semimonthly": 0.12,
    "monthly": 0.03,
}

FEIN_BY_STATE = {
    "GA": "58-1234567",
    "NY": "13-7654321",
    "SC": "57-2345678",
    "TX": "75-3456789",
    "NC": "56-4567890",
    "TN": "62-5678901",
    "FL": "59-6789012",
    "OH": "31-7890123",
    "CO": "84-8901234",
    "VA": "54-9012345",
}

# Per-WORKSITE FEIN overrides — model the real-world case the partner raised where one
# state's footprint spans MULTIPLE legal entities. MeridianCore's Savannah DC is
# a separate operating subsidiary ("MeridianCore Distribution GA, Inc.", a second
# Georgia FEIN); the rest of Georgia is the parent ("MeridianCore Logistics
# LLC"). This is what exercises the legal-entity slicing (CALC-06 / I1) and the
# entity-combination treatment (I2): GA permits combination, so the two FEINs are
# tested together; a state that PROHIBITED combination would test each alone.
# Worksites NOT listed here fall back to FEIN_BY_STATE.
FEIN_BY_WORKSITE = {
    "GA_SAV_DC": "58-2233445",   # MeridianCore Distribution GA, Inc. (subsidiary)
}

# Human-readable legal-entity names, surfaced by the engine/UI for the FEIN
# breakdown. Keyed by FEIN.
ENTITY_NAME_BY_FEIN = {
    "58-1234567": "MeridianCore Logistics LLC",
    "58-2233445": "MeridianCore Distribution GA, Inc.",
}


def _fein_for(state: str, worksite: str) -> str:
    """Resolve the FEIN for a worksite, honoring per-worksite overrides."""
    return FEIN_BY_WORKSITE.get(worksite, FEIN_BY_STATE.get(state, "00-0000000"))


# Weeks per pay period, matching the One/Zero engine's
# `tools.onezero._frequency_weeks_per_period`. Used ONLY for the designed
# near-miss employees so that hours_per_period = target_avg_weekly × wpp makes
# the engine compute exactly the intended average weekly hours (the engine
# divides total hours by num_periods × wpp). For normal employees the looser
# calendar-day scaling is fine because their hours are random anyway.
_ENGINE_WEEKS_PER_PERIOD = {
    "weekly": 1.0,
    "biweekly": 2.0,
    "semimonthly": 52 / 24,
    "monthly": 52 / 12,
}



# Per-state worksite roster (matches site_ids in data/sites.py). A subset of
# employees in each state is randomly distributed across these units; one GA
# employee gets the multi-unit-rotation pattern from the partner's canonical EE
# 61200202 example so the Min Max method has the right test surface.
WORKSITES_BY_STATE = {
    "GA": ["GA_ATL_HQ", "GA_SAV_DC", "GA_MAC_OPS", "GA_CUM_OPS"],
    "NY": ["NY_NYC_OFC", "NY_BKN_HUB"],
    "SC": ["SC_CHS_PORT", "SC_GVL_FAC"],
    "TX": ["TX_AUS_TECH", "TX_HOU_HUB", "TX_DAL_GW"],
    "NC": ["NC_CLT_DC", "NC_RDU_OFC"],
    "TN": ["TN_BNA_DC", "TN_MEM_DC"],
    "FL": ["FL_JAX_C2C", "FL_MIA_REG"],
    "OH": ["OH_CMH_PORT", "OH_CIN_HUB"],
    "CO": ["CO_DEN_OFC"],
    "VA": ["VA_IAD_HUB"],
}

# Plausible job titles by wage_type / annual_wage bucket. Required field per
# the BCS layout, used for operational dashboard filtering.
JOB_TITLES = {
    "hourly_low": ["Warehouse Associate", "Forklift Operator", "Package Handler", "Picker/Packer"],
    "hourly_high": ["Lead Warehouse Tech", "Maintenance Tech", "Yard Coordinator", "Quality Inspector"],
    "salaried_low": ["Operations Coordinator", "Shift Supervisor", "Logistics Analyst", "HR Generalist"],
    "salaried_high": ["Site Manager", "Director of Operations", "Regional Manager", "VP Logistics"],
}

# Special-case employee that mirrors the partner's EE 61200202 multi-unit Min Max
# fixture. Picks a real GA employee from payroll.csv (mid-range) and overrides
# their unit assignment to rotate across 3 GA units with the canonical date
# windows so `tests/test_onezero_min_max_fixture.py` can assert row-for-row.
CANONICAL_MIN_MAX_EE_ID = "E00200"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class Employee:
    employee_id: str
    state: str
    county: str
    wage_type: str
    annual_wage: int
    hire_date: date | None
    term_date: date | None
    primary_unit: str
    frequency: str  # weekly | biweekly | semimonthly | monthly
    job_title: str
    # Deterministic near-miss override: when set, the employee's target weekly
    # hours are pinned to this value instead of the random pick. Used to seed a
    # handful of SC employees just below the 32-hr threshold so the monthly
    # per-employee "lever" beat (UX-03 / J3) always renders a concrete
    # "add N hrs/wk to convert this part-timer to a full head" recommendation.
    target_hours_override: float | None = None


def _parse_iso(s: str) -> date | None:
    s = (s or "").strip()
    if not s:
        return None
    return date.fromisoformat(s)


def _pick_frequency(rng: random.Random, wage_type: str) -> str:
    # Hourly leans toward weekly/biweekly; salaried leans toward biweekly/semimonthly.
    if wage_type == "hourly":
        mix = {"weekly": 0.45, "biweekly": 0.50, "semimonthly": 0.05, "monthly": 0.0}
    else:
        mix = {"weekly": 0.15, "biweekly": 0.55, "semimonthly": 0.25, "monthly": 0.05}
    r = rng.random()
    cum = 0.0
    for freq, w in mix.items():
        cum += w
        if r <= cum:
            return freq
    return "biweekly"


def _pick_job_title(rng: random.Random, wage_type: str, annual_wage: int) -> str:
    if wage_type == "hourly":
        bucket = "hourly_high" if annual_wage >= 75_000 else "hourly_low"
    else:
        bucket = "salaried_high" if annual_wage >= 80_000 else "salaried_low"
    return rng.choice(JOB_TITLES[bucket])


def _periods_for_frequency(freq: str, window_start: date, window_end: date) -> list[tuple[date, date, date]]:
    """Yield (PayPeriodStart, PayPeriodEnd, PaycheckDate) for the frequency
    over [window_start, window_end]. PaycheckDate lands ~7 days after PPE."""
    periods: list[tuple[date, date, date]] = []
    # Anchor each frequency to a stable calendar boundary so the same employee
    # ends up on the same pay-period grid regardless of where their hire date
    # falls in the year.
    if freq == "weekly":
        # First Monday on/after window_start. PPE = PPS + 6 days.
        anchor = window_start - timedelta(days=window_start.weekday())  # Monday <= window_start
        cur = anchor
        while cur <= window_end:
            pps = cur
            ppe = cur + timedelta(days=6)
            pd = ppe + timedelta(days=5)
            if ppe >= window_start:
                periods.append((pps, ppe, pd))
            cur += timedelta(days=7)
    elif freq == "biweekly":
        anchor = window_start - timedelta(days=window_start.weekday())
        cur = anchor
        while cur <= window_end:
            pps = cur
            ppe = cur + timedelta(days=13)
            pd = ppe + timedelta(days=5)
            if ppe >= window_start:
                periods.append((pps, ppe, pd))
            cur += timedelta(days=14)
    elif freq == "semimonthly":
        # 1st-15th and 16th-end every month.
        year = window_start.year
        month = window_start.month
        while True:
            pps_a = date(year, month, 1)
            ppe_a = date(year, month, 15)
            pd_a = ppe_a + timedelta(days=5)
            # 16th to last day of month
            if month == 12:
                ppe_b = date(year, 12, 31)
            else:
                ppe_b = date(year, month + 1, 1) - timedelta(days=1)
            pps_b = date(year, month, 16)
            pd_b = ppe_b + timedelta(days=5)
            for pps, ppe, pd in [(pps_a, ppe_a, pd_a), (pps_b, ppe_b, pd_b)]:
                if pps <= window_end and ppe >= window_start:
                    periods.append((pps, ppe, pd))
            month += 1
            if month > 12:
                month = 1
                year += 1
            if date(year, month, 1) > window_end:
                break
    elif freq == "monthly":
        year = window_start.year
        month = window_start.month
        while True:
            pps = date(year, month, 1)
            if month == 12:
                ppe = date(year, 12, 31)
            else:
                ppe = date(year, month + 1, 1) - timedelta(days=1)
            pd = ppe + timedelta(days=5)
            if pps <= window_end and ppe >= window_start:
                periods.append((pps, ppe, pd))
            month += 1
            if month > 12:
                month = 1
                year += 1
            if date(year, month, 1) > window_end:
                break
    return periods


def _load_employees(rng: random.Random) -> list[Employee]:
    """Read the existing 337-employee roster from payroll.csv and assign a
    primary worksite + pay frequency + job title to each.

    The canonical Min Max fixture employee (`CANONICAL_MIN_MAX_EE_ID`) is
    forced onto a GA unit so its unit-rotation pattern lands in the GA pack."""
    employees: list[Employee] = []
    with PAYROLL_CSV.open("r", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            state = row["location_state"]
            units = WORKSITES_BY_STATE.get(state, [])
            if not units:
                continue  # employee from a state with no site registry; skip
            primary_unit = rng.choice(units)
            wage_type = row["wage_type"]
            annual_wage = int(row["annual_wage"])
            emp = Employee(
                employee_id=row["employee_id"],
                state=state,
                county=row["location_county"],
                wage_type=wage_type,
                annual_wage=annual_wage,
                hire_date=_parse_iso(row["hire_date"]),
                term_date=_parse_iso(row.get("term_date") or ""),
                primary_unit=primary_unit,
                frequency=_pick_frequency(rng, wage_type),
                job_title=_pick_job_title(rng, wage_type, annual_wage),
            )
            # Force canonical Min Max fixture onto a GA unit.
            if emp.employee_id == CANONICAL_MIN_MAX_EE_ID and emp.state != "GA":
                # If they aren't in GA, override their state to GA so the
                # multi-unit rotation lands in the GA rule pack.
                emp.state = "GA"
                emp.county = "Fulton"
                emp.primary_unit = "GA_ATL_HQ"
                emp.frequency = "weekly"
            employees.append(emp)

    # [J3 lever beat] Deterministically seed a few South Carolina hourly
    # employees just below the 32-hr SC full-time threshold. SC has no wage
    # test and a 20–32-hr part-time band counted as 0.5, so an employee at
    # ~30–31 hrs is a half-head today; "add 1–2 hrs/wk to clear 32 and count as
    # a full head" is the concrete monthly lever the demo showcases. Pin the
    # first three SC hourly employees (file order) to 30.5 / 31.0 / 31.5 hrs so
    # the recommendation is guaranteed, not seed-luck.
    sc_targets = [30.5, 31.0, 31.5]
    sc_hourly = [e for e in employees if e.state == "SC" and e.wage_type == "hourly"]
    for emp, target in zip(sc_hourly, sc_targets):
        emp.target_hours_override = target

    return employees


def _emit_periods(
    rng: random.Random,
    emp: Employee,
    tax_year: int,
    window_start: date,
    window_end: date,
) -> list[dict]:
    """Generate pay-period rows for one employee within one tax-year window."""
    # Clip the active window by hire/term dates.
    active_start = max(window_start, emp.hire_date or window_start)
    active_end = min(window_end, emp.term_date or window_end)
    if active_start > active_end:
        return []

    # Special unit assignment for the canonical Min Max fixture: rotate across
    # 3 GA units within the 2025 tax year (mirrors the partner's EE 61200202 pattern,
    # shifted to our window so it lands in calendar year 2025):
    #   Unit GA_MAC_OPS  Dec 23 2024 -> Feb 16 2025
    #   Unit GA_SAV_DC   Feb 17 2025 -> Dec 7 2025
    #   Unit GA_ATL_HQ   Dec 15 2025 -> Dec 21 2025
    # We generate weekly pay periods that fall within each segment.
    if emp.employee_id == CANONICAL_MIN_MAX_EE_ID and tax_year == 2025:
        return _emit_canonical_min_max_periods(emp, tax_year)

    # Hourly rate baseline. annual_wage / (52 * 40) gives hourly equivalent.
    hourly_rate = emp.annual_wage / (52 * 40)
    # Target hours per week (40 for salaried by design; varies for hourly).
    # IMPORTANT: we ALWAYS consume the same rng draws regardless of whether a
    # near-miss override is set, so seeding a few SC employees never perturbs
    # the random sequence (and therefore the numbers) of any other employee.
    if emp.wage_type == "salaried":
        base_target_hours = 40.0
    else:
        base_target_hours = rng.choice([40.0, 40.0, 40.0, 38.0, 36.0, 32.0, 28.0])
    # Designed near-miss (e.g. SC just-below-32 lever beat) overrides the value
    # but NOT the draw above.
    target_weekly_hours = emp.target_hours_override if emp.target_hours_override is not None else base_target_hours

    rows: list[dict] = []
    periods = _periods_for_frequency(emp.frequency, active_start, active_end)
    for pps, ppe, pd in periods:
        # Number of weeks in this pay period.
        period_weeks = (ppe - pps).days / 7.0
        if period_weeks <= 0:
            period_weeks = 1.0
        # Always draw the noise factor (preserves rng sequence); near-miss
        # employees ignore it so they stay deterministically just below 32.
        noise = rng.uniform(0.96, 1.04)
        if emp.target_hours_override is not None:
            # Hours per period = target avg weekly × engine weeks-per-period, so
            # the One/Zero engine computes exactly `target_hours_override` as the
            # average weekly hours (it divides total hours by num_periods × wpp).
            wpp = _ENGINE_WEEKS_PER_PERIOD.get(emp.frequency, 1.0)
            hours = round(target_weekly_hours * wpp, 2)
        else:
            hours = round(target_weekly_hours * period_weeks * noise, 2)
        wages = round(hours * hourly_rate, 2)
        rows.append({
            "Tax_Year": tax_year,
            "Employee_ID": emp.employee_id,
            "Job_Title": emp.job_title,
            "Worksite_ID": emp.primary_unit,
            "Pay_Period_Start": pps.isoformat(),
            "Pay_Period_End": ppe.isoformat(),
            "Pay_Date": pd.isoformat(),
            "Entity_FEIN": _fein_for(emp.state, emp.primary_unit),
            "Hours_Worked": hours,
            "Gross_Wages": wages,
            "Pay_Code": "Regular",
        })
        # 6% chance of an OT pay-code line on hourly employees. We ALWAYS draw
        # the same rng values to preserve the sequence, but suppress the OT row
        # for near-miss employees so their weekly hours stay clean (OT hours
        # would otherwise tip them over the threshold and ruin the lever beat).
        if emp.wage_type == "hourly":
            ot_roll = rng.random()
            if ot_roll < 0.06:
                ot_hours = round(rng.uniform(2.0, 8.0), 2)
                ot_wages = round(ot_hours * hourly_rate * 1.5, 2)
                if emp.target_hours_override is None:
                    rows.append({
                        "Tax_Year": tax_year,
                        "Employee_ID": emp.employee_id,
                        "Job_Title": emp.job_title,
                        "Worksite_ID": emp.primary_unit,
                        "Pay_Period_Start": pps.isoformat(),
                        "Pay_Period_End": ppe.isoformat(),
                        "Pay_Date": pd.isoformat(),
                        "Entity_FEIN": _fein_for(emp.state, emp.primary_unit),
                        "Hours_Worked": ot_hours,
                        "Gross_Wages": ot_wages,
                        "Pay_Code": "Overtime",
                    })

    return rows


def _emit_canonical_min_max_periods(emp: Employee, tax_year: int) -> list[dict]:
    """Hand-built pay periods for the canonical Min Max fixture employee.

    Mirrors the partner's EE 61200202 example (three units, three time windows) but
    shifted into calendar 2025 so it lands in the same fixture tax year as
    the rest of the dataset. The exact dates here drive the row-for-row
    assertions in `tests/test_onezero_min_max_fixture.py`.
    """
    rate = emp.annual_wage / (52 * 40)
    rows: list[dict] = []

    def _weekly_periods(unit: str, start: date, end: date) -> None:
        # Anchor on the segment start; weekly pay periods of 7 days.
        cur = start
        while cur <= end:
            pps = cur
            ppe = min(cur + timedelta(days=6), end)
            pd = ppe + timedelta(days=5)
            hours = 40.0
            wages = round(hours * rate, 2)
            rows.append({
                "Tax_Year": tax_year,
                "Employee_ID": emp.employee_id,
                "Job_Title": emp.job_title,
                "Worksite_ID": unit,
                "Pay_Period_Start": pps.isoformat(),
                "Pay_Period_End": ppe.isoformat(),
                "Pay_Date": pd.isoformat(),
                "Entity_FEIN": _fein_for("GA", unit),
                "Hours_Worked": hours,
                "Gross_Wages": wages,
                "Pay_Code": "Regular",
            })
            cur = ppe + timedelta(days=1)

    # Segment 1: GA_MAC_OPS  Dec 23 2024 -> Feb 16 2025 (clip to 2025 window).
    _weekly_periods("GA_MAC_OPS", date(2025, 1, 6), date(2025, 2, 16))
    # Segment 2: GA_SAV_DC   Feb 17 2025 -> Dec 7 2025.
    _weekly_periods("GA_SAV_DC", date(2025, 2, 17), date(2025, 12, 7))
    # Segment 3: GA_ATL_HQ   Dec 15 2025 -> Dec 21 2025  (Month 12 special-rule case).
    _weekly_periods("GA_ATL_HQ", date(2025, 12, 15), date(2025, 12, 21))
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    rng = random.Random(SEED)
    employees = _load_employees(rng)
    print(f"Loaded {len(employees)} employees from {PAYROLL_CSV.name}.")

    all_rows: list[dict] = []
    for tax_year, win_start, win_end in TAX_YEAR_WINDOWS:
        ty_rows = 0
        for emp in employees:
            rows = _emit_periods(rng, emp, tax_year, win_start, win_end)
            all_rows.extend(rows)
            ty_rows += len(rows)
        print(f"  Tax year {tax_year}: {ty_rows:,} pay-period rows.")

    fieldnames = [
        "Tax_Year", "Employee_ID", "Job_Title", "Worksite_ID",
        "Pay_Period_Start", "Pay_Period_End", "Pay_Date",
        "Entity_FEIN", "Hours_Worked", "Gross_Wages", "Pay_Code",
    ]
    with OUT_CSV.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"Wrote {len(all_rows):,} rows to {OUT_CSV.name}.")
    print(
        f"Anonymity check: emitted {len(fieldnames)} required BCS fields; "
        f"5 optional PII fields (Last Name, First Name, SSN, Last Hire Date, "
        f"Term Date) omitted by design."
    )


if __name__ == "__main__":
    main()
