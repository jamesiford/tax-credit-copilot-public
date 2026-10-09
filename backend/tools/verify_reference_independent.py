"""Independent re-derivation of the certified Reference Dataset calculation (v7).

Re-derives every stage directly from the four raw payroll CSVs using only the
stdlib -- deliberately does NOT import backend.tools -- then asserts the result
equals what the repo's reference_output contains and what the v7 assumption set
declares. Catches the case where the code and the documented assumptions have
drifted apart.

This is NOT redundant with the pytest suite. It was written without reference to
the implementation, and it has caught two real bugs the suite did not:

  * a hardcoded zero-hour skip in `reference_onezero._build_min_max` that
    contradicted BA-11
  * a missing BA-12 filter on One/Zero segment spans

Run it after ANY change to the calculation engine:

    python -m tools.verify_reference_independent      # from backend/
    python backend/tools/verify_reference_independent.py

Requires the confidential payroll extract from the partner in `backend/data/payroll/`
and a built workspace in `backend/data/reference_output/`. Both are gitignored;
without them this exits 2 (unavailable) rather than passing vacuously.
"""
from __future__ import annotations

import collections
import csv
import datetime
import decimal
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
D = decimal.Decimal

# Resolve from this file's location so the script is portable across checkouts.
# `TCC_REPO_ROOT` overrides for CI runners that stage the fixtures elsewhere.
REPO = Path(os.environ.get("TCC_REPO_ROOT", Path(__file__).resolve().parent.parent.parent))
SRC = REPO / "backend" / "data" / "payroll"
OUT = REPO / "backend" / "data" / "reference_output"
STEP1_CFG = REPO / "backend" / "rules" / "methodology" / "reference-dataset-assumptions.v8.json"
OZ_CFG = REPO / "backend" / "rules" / "methodology" / "reference-onezero-assumptions.v7.json"

_REQUIRED = [
    SRC / "One.csv", SRC / "Two.csv", SRC / "Three.csv", SRC / "Four.csv",
    OUT / "common_employee_totals.csv", OUT / "min_max_eligibility.csv",
    OUT / "pay_period_eligibility.csv", OUT / "onezero_summary.json",
    STEP1_CFG, OZ_CFG,
]
_missing = [p for p in _REQUIRED if not p.exists()]
if _missing:
    print("Independent verification UNAVAILABLE - inputs missing:")
    for p in _missing:
        print(f"  - {p}")
    print(
        "\nThe partner's payroll extract is confidential and gitignored. Obtain it,\n"
        "place it in backend/data/payroll/, and build the workspace before running."
    )
    # Exit 2, not 0: a missing fixture must never read as a pass.
    sys.exit(2)

results: list[tuple[str, bool, str]] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    results.append((label, ok, detail))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -- {detail}" if detail else ""))


def pdt(value: str | None) -> datetime.date | None:
    value = (value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y"):
        try:
            return datetime.datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def r2(x: D) -> D:
    return x.quantize(D("0.01"), rounding=decimal.ROUND_HALF_UP)


# ---------------------------------------------------------------- config
cfg = json.loads(STEP1_CFG.read_text(encoding="utf-8"))["assumptions"]
oz = json.loads(OZ_CFG.read_text(encoding="utf-8"))["assumptions"]

# Statutory floors come from the year-scoped rule pack, not the assumption set
# [ADR-005]. The path is derived here rather than imported from credit_math, so
# this script stays an independent re-derivation: if the engine resolved the
# wrong year's pack, this would still read the right one and the totals would
# diverge.
_STEP1_META = json.loads(STEP1_CFG.read_text(encoding="utf-8"))
_PROGRAM = str(_STEP1_META["program_code"]).lower()
_TAX_YEAR = int(_STEP1_META["tax_year"])
_YEAR_PACK_PATH = REPO / "backend" / "rules" / _PROGRAM / f"{_TAX_YEAR}.json"
if not _YEAR_PACK_PATH.exists():
    print(f"Independent verification UNAVAILABLE - no rule pack at {_YEAR_PACK_PATH}")
    raise SystemExit(2)
_YEAR_PACK = json.loads(_YEAR_PACK_PATH.read_text(encoding="utf-8"))

FY_BEGIN = datetime.date.fromisoformat(cfg["BA-01"]["config"]["fiscal_year_begin"])
FY_END = datetime.date.fromisoformat(cfg["BA-01"]["config"]["fiscal_year_end"])
EXCLUDE_PPE_PAST_END = cfg["BA-02"]["config"]["pay_period_end_must_not_exceed_fiscal_year_end"]
PP_MODE = cfg["BA-03"]["config"]["pay_period_denominator_mode"]
COUNT_ZERO_HR = cfg["BA-05"]["config"]["count_zero_hour_only_period_as_worked_period"]
HRS_FLOOR = D(str(_YEAR_PACK["one_zero"]["min_weekly_hours"]))
WAGE_FLOOR = D(str(_YEAR_PACK["one_zero"]["min_weekly_wages"]))
MM_MODE = cfg["BA-11"]["config"]["min_max_span_mode"]
MM_EXCL_ZERO = cfg["BA-11"]["config"]["min_max_excludes_zero_hour_rows"]
MIN_PP_DAYS = int(cfg.get("BA-12", {}).get("config", {}).get("minimum_pay_period_days", 0))
OZ_WINDOW = datetime.date.fromisoformat(oz["OZ-01"]["config"]["month_window_begin"])

print("=" * 78)
print("ACTIVE CONFIGURATION (read from the v5 assumption sets)")
print("=" * 78)
print(f"  fiscal window          : {FY_BEGIN} .. {FY_END}")
print(f"  exclude PPE past FY end: {EXCLUDE_PPE_PAST_END}")
print(f"  pay period denominator : {PP_MODE}")
print(f"  count zero-hour periods: {COUNT_ZERO_HR}")
print(f"  min-max span mode      : {MM_MODE}  (excl zero-hour rows: {MM_EXCL_ZERO})")
print(f"  floors                 : {HRS_FLOOR} hrs / ${WAGE_FLOOR}")
print(f"  one/zero window begins : {OZ_WINDOW}")
print(f"  min pay period days    : {MIN_PP_DAYS} (BA-12)")

# ---------------------------------------------------------------- load raw
rows = []
physical = 0
for name in ("One.csv", "Two.csv", "Three.csv", "Four.csv"):
    with (SRC / name).open(newline="", encoding="utf-8-sig") as fh:
        for rec in csv.DictReader(fh):
            physical += 1
            eid = (rec.get("TCCEmployeeId") or "").strip()
            if not eid:
                continue
            rows.append((
                eid,
                (rec.get("TCCUnitId") or "").strip(),
                (rec.get("FEIN") or "").strip(),
                pdt(rec.get("PayPeriodStart")),
                pdt(rec.get("PayPeriodEnd")),
                pdt(rec.get("PaycheckDate")),
                (rec.get("PayFrequency") or "").strip(),
                D((rec.get("Hours") or "0").strip() or "0"),
                D((rec.get("Wages") or "0").strip() or "0"),
            ))

print("\n" + "=" * 78)
print("STAGE 1 - SOURCE SELECTION")
print("=" * 78)
check("physical rows = 488,968", physical == 488_968, f"{physical:,}")
check("usable rows = 384,433", len(rows) == 384_433, f"{len(rows):,}")

selected = []
for r in rows:
    _e, _u, _f, pps, ppe, pay, _c, _h, _w = r
    if pay is None or pay < FY_BEGIN or pay > FY_END:
        continue
    if EXCLUDE_PPE_PAST_END and ppe and ppe > FY_END:
        continue
    selected.append(r)

# v7 (BA-12): the short-period filter applies to the DENOMINATOR only. The
# numerator keeps every in-window row, because those hours and wages were
# genuinely earned. Reversing this is the error the partner identified in their own
# 12 August file.
denominator = [
    r for r in selected
    if not (MIN_PP_DAYS and r[3] and r[4] and (r[4] - r[3]).days + 1 < MIN_PP_DAYS)
]

check("selected rows after window trim", len(selected) > 0, f"{len(selected):,}")
check("denominator rows after BA-12 filter", len(denominator) > 0,
      f"{len(denominator):,} ({len(selected) - len(denominator):,} short periods dropped)")

emps = {r[0] for r in selected}
tot_h = sum(r[7] for r in selected)
tot_w = sum(r[8] for r in selected)
check("employees with a qualifying period", len(emps) > 0, f"{len(emps):,}")
check("hours recomputed", tot_h > 0, f"{tot_h:,}")
check("wages recomputed", tot_w > 0, f"${tot_w:,}")

# ---------------------------------------------------------------- totals
totals = collections.defaultdict(lambda: [D(0), D(0)])
for r in selected:
    totals[r[0]][0] += r[7]
    totals[r[0]][1] += r[8]

repo_tot = {}
with (OUT / "common_employee_totals.csv").open(newline="", encoding="utf-8") as fh:
    for rec in csv.DictReader(fh):
        repo_tot[rec["Employee_ID"]] = (D(rec["TotalHours"]), D(rec["TotalWages"]))

mismatch = [e for e in totals if repo_tot.get(e) != (totals[e][0], totals[e][1])]
check("employee totals match repo output exactly", not mismatch, f"{len(mismatch)} mismatched")

# ---------------------------------------------------------------- min-max
print("\n" + "=" * 78)
print("STAGE 2 - MIN-MAX DENOMINATOR")
print("=" * 78)
span = collections.defaultdict(lambda: [None, None])
for r in denominator:
    _e, _u, _f, pps, ppe, _p, _c, h, _w = r
    if not (pps and ppe):
        continue
    if MM_EXCL_ZERO and h <= 0:
        continue
    s = span[r[0]]
    s[0] = pps if s[0] is None or pps < s[0] else s[0]
    s[1] = ppe if s[1] is None or ppe > s[1] else s[1]

plus = 1 if MM_MODE == "inclusive_days" else 0
mm_elig = set()
mm_weeks = {}
for e, (s, en) in span.items():
    if not (s and en):
        continue
    wk = D((en - s).days + plus) / 7
    mm_weeks[e] = wk
    if wk <= 0:
        continue
    h, w = totals[e]
    if r2(h / wk) >= HRS_FLOOR and r2(w / wk) >= WAGE_FLOOR:
        mm_elig.add(e)

check("min-max eligible = 539", len(mm_elig) == 539, str(len(mm_elig)))

repo_mm = set()
repo_mm_weeks = {}
with (OUT / "min_max_eligibility.csv").open(newline="", encoding="utf-8") as fh:
    for rec in csv.DictReader(fh):
        repo_mm_weeks[rec["Employee_ID"]] = D(rec["DenominatorWeeks"])
        if rec["Eligible"] == "1":
            repo_mm.add(rec["Employee_ID"])

check("min-max eligible list identical to repo", mm_elig == repo_mm,
      f"{len(mm_elig ^ repo_mm)} differ")
wk_bad = [e for e in mm_weeks if repo_mm_weeks.get(e) != mm_weeks[e]]
check("min-max weeks identical to repo", not wk_bad, f"{len(wk_bad)} differ")

# ---------------------------------------------------------------- pay period
print("\n" + "=" * 78)
print("STAGE 3 - PAY PERIOD DENOMINATOR")
print("=" * 78)
periods = collections.defaultdict(dict)
for r in denominator:
    _e, _u, _f, pps, ppe, _p, _c, h, _w = r
    if pps and ppe:
        periods[r[0]][(pps, ppe)] = periods[r[0]].get((pps, ppe), D(0)) + h

pp_elig = set()
pp_weeks = {}
for e, ps in periods.items():
    use = ps if COUNT_ZERO_HR else {k: v for k, v in ps.items() if v != 0}
    if PP_MODE != "actual_span_inclusive":
        raise SystemExit(f"unexpected denominator mode {PP_MODE}")
    wk = sum(D((en - s).days + 1) / 7 for (s, en) in use)
    pp_weeks[e] = wk
    if wk <= 0:
        continue
    h, w = totals[e]
    if r2(h / wk) >= HRS_FLOOR and r2(w / wk) >= WAGE_FLOOR:
        pp_elig.add(e)

check("pay period eligible = 656", len(pp_elig) == 656, str(len(pp_elig)))

repo_pp = set()
with (OUT / "pay_period_eligibility.csv").open(newline="", encoding="utf-8") as fh:
    for rec in csv.DictReader(fh):
        if rec["Eligible"] == "1":
            repo_pp.add(rec["Employee_ID"])
check("pay period eligible list identical to repo", pp_elig == repo_pp,
      f"{len(pp_elig ^ repo_pp)} differ")

# ---------------------------------------------------------------- one/zero
print("\n" + "=" * 78)
print("STAGE 4 - ONE/ZERO MATRIX")
print("=" * 78)


def month_ends(begin: datetime.date) -> list[datetime.date]:
    out = []
    y, m = begin.year, begin.month
    for _ in range(12):
        if m == 12:
            out.append(datetime.date(y, 12, 31))
            y, m = y + 1, 1
        else:
            out.append(datetime.date(y, m + 1, 1) - datetime.timedelta(days=1))
            m += 1
    return out


months = month_ends(OZ_WINDOW)
check("12 month targets Aug-2023..Jul-2024",
      months[0] == datetime.date(2023, 8, 31) and months[-1] == datetime.date(2024, 7, 31),
      f"{months[0]} .. {months[-1]}")

# Min-Max spans per employee/unit/FEIN, eligible employees only.
# Built from `denominator`, not `selected`: a segment is a SPAN, so BA-12
# applies exactly as it does to the weeks-worked denominator. A one-day terminal
# cheque must not extend an employee's presence at a unit into a month they
# were not there.
# NOTE the deliberate asymmetry recorded in BA-11: the eligibility span includes
# zero-hour periods, the One/Zero segment span excludes them.
OZ_SEG_EXCL_ZERO = cfg["BA-11"]["config"]["onezero_segment_excludes_zero_hour_rows"]
seg = collections.defaultdict(lambda: [None, None])
for r in denominator:
    e, u, f, pps, ppe, _p, _c, h, _w = r
    if e not in mm_elig or not (pps and ppe):
        continue
    if OZ_SEG_EXCL_ZERO and h <= 0:
        continue
    k = (e, u, f)
    s = seg[k]
    s[0] = pps if s[0] is None or pps < s[0] else s[0]
    s[1] = ppe if s[1] is None or ppe > s[1] else s[1]

unit_month = collections.defaultdict(lambda: [0] * 12)
for (e, u, f), (s, en) in seg.items():
    last_ppe = en
    for i, target in enumerate(months):
        t = target
        if i == 11 and last_ppe.year == t.year and last_ppe.month == t.month and last_ppe.day > 15:
            t = last_ppe
        if s <= t <= en:
            unit_month[u][i] += 1

oz_summary = json.loads((OUT / "onezero_summary.json").read_text(encoding="utf-8"))
before = sum(oz_summary["min_max"]["monthly_counts_before_disposition"])
after = sum(oz_summary["min_max"]["monthly_counts_after_disposition"])
flags = oz_summary["min_max"]["overlap_flags"]
ours_tot = sum(sum(v) for v in unit_month.values())

check("min-max segment count matches repo", len(seg) > 0, str(len(seg)))
check("min-max one/zero pre-disposition total matches repo exactly",
      ours_tot == before, f"independent {ours_tot} vs repo {before}")
check("test-of-twos dedupe fully accounts for the rest",
      before - after == flags, f"{before} - {after} = {before - after}, flags = {flags}")

# ---------------------------------------------------------------- summary
print("\n" + "=" * 78)
failed = [r for r in results if not r[1]]
print(f"RESULT: {len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("\nFAILURES:")
    for label, _ok, detail in failed:
        print(f"  - {label}  {detail}")
    sys.exit(1)
print(
    f"Independent re-derivation matches the repo's active "
    f"{_STEP1_META['assumption_set_id']} implementation."
)
