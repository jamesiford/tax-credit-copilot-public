"""Cross-check: does flex_rules.py agree with the production engine?

Runs both implementations over the same rows and reports any disagreement. The
portable module is only worth having if it produces what the engine produces —
this is the evidence, and it is the thing to re-run whenever either side moves.

Uses the public pay-period fixture in the repo, not the private reference
dataset, so it runs on any clone. The rules exercised are identical either way.

    cd backend && ../.venv/Scripts/python.exe ../docs/data/portable-rules/crosscheck.py
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Locate the repo's backend. Works both in place (docs/data/portable-rules) and
# from an extracted zip, provided the repo is somewhere findable.
def _find_backend() -> Path | None:
    candidates = [
        _HERE.parents[2] / "backend",                       # in the repo
        Path(r"C:\Projects\GitHub\tax-credit-copilot\backend"),
    ]
    env = os.getenv("TCC_BACKEND")
    if env:
        candidates.insert(0, Path(env))
    for candidate in candidates:
        if (candidate / "domain" / "calculation" / "onezero.py").exists():
            return candidate
    return None


_BACKEND = _find_backend()
if _BACKEND is None:
    print(
        "Cannot find the tax-credit-copilot backend.\n\n"
        "This script compares the portable rules against the production engine,\n"
        "so it needs the repo. Set TCC_BACKEND to the backend directory:\n\n"
        "    set TCC_BACKEND=C:\\path\\to\\tax-credit-copilot\\backend\n\n"
        "flex_rules.py itself has no such dependency — run `python flex_rules.py`\n"
        "for the self-check, which needs nothing but the standard library."
    )
    raise SystemExit(2)

sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_HERE))

import flex_rules as fr  # noqa: E402
from domain.calculation.onezero import (  # noqa: E402
    OneZeroMethodology,
    OneZeroPack,
    run_min_max_method,
    run_pay_period_method,
)

FIXTURE = _BACKEND / "data" / "payroll_pay_periods.csv"
TAX_YEAR = 2025
STATE_PREFIX = "GA_"


def load_rows() -> list[dict]:
    with FIXTURE.open(newline="", encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle)]
    return [
        r for r in rows
        if str(r.get("Worksite_ID", "")).startswith(STATE_PREFIX)
        and str(r.get("Pay_Date", ""))[:4] == str(TAX_YEAR)
    ]


def engine_pack() -> OneZeroPack:
    """The certified v7 methodology, matching tests/certified.py."""
    return OneZeroPack(
        min_weekly_hours=35.0,
        min_weekly_wages=636.0,
        wage_basis="all_remuneration",
        geographic_granularity="unit",
        pt_aggregation=False,
        headcount_unit_field="Worksite_ID",
        citation="O.C.G.A. 48-7-40",
        tax_year=TAX_YEAR,
        methodology=OneZeroMethodology(
            minimum_pay_period_days=7,
            short_periods_excluded_from_numerator=False,
            pay_period_denominator_mode="actual_span",
            min_max_span_mode="exclusive_days",
            count_zero_hour_periods=True,
            average_decimals=2,
            exclude_off_cycle_periods=False,
        ),
    )


def portable_result(raw: list[dict]) -> dict[str, dict]:
    """Run the portable rules end to end."""
    rows = [
        {
            "employee_id": r["Employee_ID"],
            "unit_id": r.get("Worksite_ID", ""),
            "fein": r.get("Entity_FEIN", ""),
            "pay_period_start": r["Pay_Period_Start"],
            "pay_period_end": r["Pay_Period_End"],
            "pay_date": r["Pay_Date"],
            "pay_frequency": r.get("Pay_Frequency", ""),
            "hours": r.get("Hours_Worked", 0),
            "wages": r.get("Gross_Wages", 0),
        }
        for r in raw
    ]

    collapsed, _ = fr.collapse_duplicates(rows)
    totals = fr.employee_totals(collapsed)

    by_employee: dict[str, list[dict]] = defaultdict(list)
    for row in collapsed:
        by_employee[row["employee_id"]].append(row)

    out: dict[str, dict] = {}
    for employee_id, employee_totals in totals.items():
        emp_rows = by_employee[employee_id]

        mm_weeks, _ = fr.min_max_weeks(emp_rows)
        pp_weeks, _ = fr.period_weeks(emp_rows)

        out[employee_id] = {
            "min_max": fr.test_eligibility(employee_totals, mm_weeks),
            "pay_period": fr.test_eligibility(employee_totals, pp_weeks),
        }
    return out


def main() -> int:
    if not FIXTURE.exists():
        print(f"fixture missing: {FIXTURE}")
        return 2

    raw = load_rows()
    print(f"fixture rows (GA, TY{TAX_YEAR}): {len(raw):,}")
    if not raw:
        print("no rows matched — nothing to compare")
        return 2

    pack = engine_pack()
    analysis_start = date(TAX_YEAR, 1, 31)

    engine_mm = run_min_max_method(
        raw, tax_year=TAX_YEAR, analysis_start_month=analysis_start, pack=pack,
    )
    engine_pp = run_pay_period_method(
        raw, tax_year=TAX_YEAR, analysis_start_month=analysis_start, pack=pack,
    )
    portable = portable_result(raw)

    failures: list[str] = []

    # 1. Employee population must match.
    engine_emps = {r["Employee_ID"] for r in engine_mm.all_averages}
    portable_emps = set(portable)
    if engine_emps != portable_emps:
        only_engine = sorted(engine_emps - portable_emps)[:5]
        only_portable = sorted(portable_emps - engine_emps)[:5]
        failures.append(
            f"employee population differs: engine {len(engine_emps)}, "
            f"portable {len(portable_emps)}; engine-only {only_engine}, "
            f"portable-only {only_portable}"
        )
    print(f"employees: engine {len(engine_emps):,}  portable {len(portable_emps):,}")

    # 2. Per-employee weeks and averages, Min-Max.
    mm_mismatch = 0
    for rec in engine_mm.all_averages:
        emp = rec["Employee_ID"]
        if emp not in portable:
            continue
        got = portable[emp]["min_max"]
        engine_weeks = Decimal(str(rec["weeks_worked"]))
        portable_weeks = fr.round_half_up(got["denominator_weeks"], 2)
        if engine_weeks != portable_weeks:
            mm_mismatch += 1
            if mm_mismatch <= 3:
                failures.append(
                    f"min_max weeks {emp}: engine {engine_weeks}, portable {portable_weeks}"
                )
    if mm_mismatch:
        failures.append(f"min_max weeks mismatched for {mm_mismatch} employees")
    print(f"min_max weeks compared: {len(engine_mm.all_averages):,}  mismatched: {mm_mismatch}")

    # 3. Eligible counts, both methods.
    engine_mm_eligible = len(engine_mm.eligible_employees)
    engine_pp_eligible = len(engine_pp.eligible_employees)
    portable_mm_eligible = sum(1 for v in portable.values() if v["min_max"]["eligible"])
    portable_pp_eligible = sum(1 for v in portable.values() if v["pay_period"]["eligible"])

    print(f"min_max eligible:    engine {engine_mm_eligible:,}  portable {portable_mm_eligible:,}")
    print(f"pay_period eligible: engine {engine_pp_eligible:,}  portable {portable_pp_eligible:,}")

    if engine_mm_eligible != portable_mm_eligible:
        failures.append(
            f"min_max eligible differs: engine {engine_mm_eligible}, portable {portable_mm_eligible}"
        )
    if engine_pp_eligible != portable_pp_eligible:
        failures.append(
            f"pay_period eligible differs: engine {engine_pp_eligible}, portable {portable_pp_eligible}"
        )

    print()
    if failures:
        print("DISAGREEMENT")
        for line in failures:
            print(f"  - {line}")
        return 1

    print("AGREES — portable rules match the engine on every compared value")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
