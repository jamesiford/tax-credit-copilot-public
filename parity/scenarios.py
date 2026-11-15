"""Scenario matrix for the golden exporter and the fuzz seed corpus.

Deterministic (seeded). Every scenario is a *request* in the schema documented in
``engine_io``; the exporter attaches the oracle's response as ``expected``.

Datasets are stored once (``datasets`` section) and referenced by name so the
committed synthetic CSV (about 9.5k rows) is not repeated per scenario. Rows carry
only the columns the engine's outputs use: Employee_ID, Worksite_ID, Entity_FEIN,
Pay_Period_Start, Pay_Period_End, Pay_Date, Hours_Worked, Gross_Wages, Pay_Code,
Work_State. A key that is absent stays absent (the engine treats absent, null and
empty differently).
"""
from __future__ import annotations

import csv
import random
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

KNOWN = ["Employee_ID", "Worksite_ID", "Entity_FEIN", "Pay_Period_Start", "Pay_Period_End", "Pay_Date",
         "Hours_Worked", "Gross_Wages", "Pay_Code", "Work_State"]
SEED = 20261114
CSV_PATH = BACKEND / "data" / "payroll_pay_periods.csv"


def iso(d: date) -> str:
    return d.isoformat()


def row(ee, ws, pps, ppe, pay, hrs, wages, code="Regular", fein="58-1234567", **extra) -> dict:
    r = {"Employee_ID": ee, "Worksite_ID": ws, "Entity_FEIN": fein, "Pay_Period_Start": pps, "Pay_Period_End": ppe,
         "Pay_Date": pay, "Hours_Worked": hrs, "Gross_Wages": wages, "Pay_Code": code}
    r.update(extra)
    return {k: r[k] for k in KNOWN if k in r}


def csv_rows() -> list[dict]:
    with CSV_PATH.open(encoding="utf-8") as fh:
        return [{k: r[k] for k in KNOWN if k in r} for r in csv.DictReader(fh)]


def typed(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        r = dict(r)
        r["Hours_Worked"] = float(r["Hours_Worked"])
        r["Gross_Wages"] = float(r["Gross_Wages"])
        out.append(r)
    return out


def load_pack(code: str, year: int | None) -> dict | None:
    """The production OneZeroPack for a programme code and year, as scenario parameters (ingestion disabled)."""
    from tools import credit_math as cm
    import tools.rules_ingestion as ri
    ri.ingested_one_zero = lambda *a, **k: None  # the ingested config is local state and must not reach goldens
    p = cm.load_pack_one_zero(code, year)
    if p is None:
        return None
    return pack_dict(p)


def pack_dict(p) -> dict:
    from dataclasses import asdict
    d = asdict(p)
    for k in ("pt_band_hours", "included_pay_codes", "excluded_pay_codes"):
        if d.get(k) is not None:
            d[k] = list(d[k])
    return d


BASE_PACK = {"min_weekly_hours": 35.0, "min_weekly_wages": 686.0, "citation": "synthetic", "measuring_date": "last_day"}


def with_pack(**kw) -> dict:
    p = dict(BASE_PACK)
    p.update(kw)
    return p


def edge_datasets() -> dict[str, list[dict]]:
    d: dict[str, list[dict]] = {}
    d["empty"] = []
    d["single_row"] = [row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0)]
    d["null_and_empty_cells"] = [
        row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", None, 700.0),
        row("E1", "GA_A", "2024-01-08", "2024-01-14", "2024-01-19", "", ""),
        row("E1", "GA_A", "2024-01-15", "2024-01-21", "2024-01-26", "40", "700.5"),
        row("E1", "GA_A", "2024-01-22", "2024-01-28", "2024-02-02", " 40.25 ", 1),
        row("E1", "GA_A", "2024-01-29", "2024-02-04", "2024-02-09", 40, 700),
        row("E2", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", "1_0.5", "1e2"),
    ]
    d["bad_hours_text"] = [row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", "forty", 700.0)]
    d["missing_pay_date_key"] = [{k: v for k, v in row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0).items() if k != "Pay_Date"}]
    d["empty_pay_date"] = [row("E1", "GA_A", "2024-01-01", "2024-01-07", "", 40.0, 700.0)]
    d["null_pay_date"] = [row("E1", "GA_A", "2024-01-01", "2024-01-07", None, 40.0, 700.0)]
    d["bad_pay_date_text"] = [row("E1", "GA_A", "2024-01-01", "2024-01-07", "01/12/2024", 40.0, 700.0)]
    d["datetime_suffix_dates"] = [row("E1", "GA_A", "2024-01-01T00:00:00", "2024-01-07T00:00:00", "2024-01-12T08:30:00", 40.0, 700.0),
                                  row("E1", "GA_A", "2024-01-08", "2024-01-14", "2024-01-19 08:30", 40.0, 700.0)]
    d["compact_and_week_dates"] = [row("E1", "GA_A", "20240101", "20240107", "20240112", 40.0, 700.0),
                                   row("E1", "GA_A", "2024-W02-1", "2024-W02-7", "2024-01-19", 40.0, 700.0)]
    d["duplicates_collapse"] = [
        row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 20.005, 350.005),
        row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 20.0, 350.0),
        row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 0.1, 0.2),
        row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-14", 5.0, 5.0, code="Overtime"),
        row("E1", "GA_B", "2024-01-01", "2024-01-07", "2024-01-12", 5.0, 5.0),
        row("E2", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", -3.5, -100.0),
    ]
    d["negative_adjustments"] = [
        row("E1", "GA_A", "2024-01-01", "2024-01-14", "2024-01-19", 80.0, 1400.0),
        row("E1", "GA_A", "2024-01-15", "2024-01-28", "2024-02-02", -10.0, -200.0),
        row("E1", "GA_A", "2024-01-29", "2024-02-11", "2024-02-16", 70.0, 1500.0),
        row("E2", "GA_A", "2024-01-01", "2024-01-14", "2024-01-19", -80.0, -1400.0),
    ]
    d["leap_and_month_end"] = [
        row("E1", "GA_A", "2024-02-26", "2024-03-03", "2024-03-08", 40.0, 700.0),
        row("E1", "GA_A", "2024-02-29", "2024-02-29", "2024-02-29", 8.0, 140.0),
        row("E1", "GA_A", "2024-01-25", "2024-01-31", "2024-02-02", 40.0, 700.0),
        row("E1", "GA_A", "2024-03-01", "2024-03-31", "2024-04-05", 160.0, 2800.0),
        row("E1", "GA_A", "2024-04-01", "2024-04-30", "2024-05-03", 160.0, 2800.0),
        row("E2", "GA_A", "2023-12-31", "2024-01-06", "2024-01-10", 40.0, 700.0),
        row("E2", "GA_A", "2024-12-26", "2025-01-01", "2025-01-03", 40.0, 700.0),
    ]
    d["short_periods"] = [row("E1", "GA_A", f"2024-03-{1 + k:02d}", f"2024-03-{1 + k + (k % 3):02d}", "2024-04-05", 8.0, 150.0) for k in range(0, 12, 2)] + [
        row("E1", "GA_A", "2024-04-01", "2024-04-07", "2024-04-12", 40.0, 700.0),
        row("E1", "GA_A", "2024-04-08", "2024-04-14", "2024-04-19", 40.0, 700.0),
        row("E1", "GA_A", "2024-04-15", "2024-04-15", "2024-04-19", 8.0, 140.0),
        row("E1", "GA_A", "2024-04-30", "2024-04-29", "2024-05-03", 8.0, 140.0),
    ]
    d["extreme_values"] = [
        row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 1e18, 1e18),
        row("E2", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 1e-300, 5e-324),
        row("E3", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 1e300, 1.0),
        row("E4", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 0.0, 0.0),
    ]
    d["huge_values_overflow_quantize"] = [row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 1e300, 1e300)]
    d["half_cent_ties"] = [
        row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 34.995, 685.995),
        row("E2", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 34.985, 685.985),
        row("E3", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 35.005, 686.005),
        row("E4", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 34.9949999999, 685.9949999999),
        row("E5", "GA_A", "2024-01-01", "2024-01-14", "2024-01-19", 69.99, 1371.99),
        row("E6", "GA_A", "2024-01-01", "2024-01-14", "2024-01-19", 70.0, 1372.0),
        row("E7", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 0.125, 0.375),
        row("E8", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 2.675, 1.005),
    ]
    d["multi_unit_same_month"] = [
        row("E1", "GA_A", "2024-01-01", "2024-02-04", "2024-02-09", 175.0, 3500.0),
        row("E1", "GA_B", "2024-01-15", "2024-02-18", "2024-02-23", 175.0, 3500.0),
        row("E1", "GA_C", "2024-02-05", "2024-03-10", "2024-03-15", 175.0, 3500.0),
        row("E2", "GA_B", "2024-01-01", "2024-03-31", "2024-04-05", 600.0, 12000.0),
        row("E3", "GA_A", "2024-01-01", "2024-03-31", "2024-04-05", 600.0, 12000.0, fein="99-9999999"),
    ]
    d["unicode_ids_and_units"] = [
        row("E10", "GA_é", "2024-01-01", "2024-03-31", "2024-04-05", 600.0, 12000.0),
        row("E9", "GA_E", "2024-01-01", "2024-03-31", "2024-04-05", 600.0, 12000.0),
        row("E\U00010000", "GA_\U00010000", "2024-01-01", "2024-03-31", "2024-04-05", 600.0, 12000.0),
        row("E\uffff", "GA_\uffff", "2024-01-01", "2024-03-31", "2024-04-05", 600.0, 12000.0),
        row("e1", "ga_z", "2024-01-01", "2024-03-31", "2024-04-05", 600.0, 12000.0),
        row("ß", "GA_ß", "2024-01-01", "2024-03-31", "2024-04-05", 600.0, 12000.0),
    ]
    d["work_state_variants"] = [
        row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0, Work_State="ga"),
        row("E2", "XX_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0, Work_State="  Ga  "),
        row("E3", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0, Work_State=""),
        row("E4", "tn_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0, Work_State=None),
        row("E5", "T_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0),
        row("E6", "TNN_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0),
        row("E7", "É_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0),
        row("E8", "", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0),
        row("E9", None, "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0),
        row("E10", "_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0),
        row("E11", "NC", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0),
        row("E12", "GA_", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0),
        row("E13", "ß_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0),
        row("E14", "GA_A", "2024-01-01", "2024-01-07", "garbage", 40.0, 700.0, Work_State="GA"),
        row("E15", "GA_A", "2024-01-01", "2024-01-07", "2023-12-31", 40.0, 700.0, Work_State="GA"),
        row("E16", "GA_A", "2024-01-01", "2024-01-07", "2024-12-31", 40.0, 700.0, Work_State="GA"),
        row("E17", "GA_A", "2024-01-01", "2024-01-07", "2025-01-01", 40.0, 700.0, Work_State="GA"),
        row("E18", "GA_A", "2024-01-01", "2024-01-07", "", 40.0, 700.0, Work_State="GA"),
    ]
    d["no_pay_code_key_and_null"] = [
        {k: v for k, v in row("E1", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0).items() if k != "Pay_Code"},
        row("E2", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0, code=None),
        row("E3", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0, code="Mileage"),
        row("E4", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0, code="Bonus"),
        row("E5", "GA_A", "2024-01-01", "2024-01-07", "2024-01-12", 40.0, 700.0, code="Unknown"),
    ]
    d["entity_null_and_missing"] = [
        {k: v for k, v in row("E1", "GA_A", "2024-01-01", "2024-12-31", "2025-01-05", 2000.0, 40000.0).items() if k != "Entity_FEIN"},
        row("E2", "GA_A", "2024-01-01", "2024-12-31", "2025-01-05", 2000.0, 40000.0, fein=None),
        row("E3", "GA_A", "2024-01-01", "2024-12-31", "2025-01-05", 2000.0, 40000.0, fein=""),
    ]
    return d


PERIOD_KINDS = ["weekly", "biweekly", "semimonthly", "monthly", "mixed"]


def make_periods(rng: random.Random, start: date, n: int, kind: str) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    cur = start
    for _ in range(n):
        if kind == "mixed":
            k = rng.choice(["weekly", "biweekly", "semimonthly", "monthly", "short", "long"])
        else:
            k = kind
        if k == "weekly":
            end = cur + timedelta(days=6)
        elif k == "biweekly":
            end = cur + timedelta(days=13)
        elif k == "semimonthly":
            end = date(cur.year, cur.month, 15) if cur.day <= 15 else (date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1) - timedelta(days=1))
            if end < cur:
                end = cur + timedelta(days=14)
        elif k == "monthly":
            end = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1) - timedelta(days=1)
        elif k == "short":
            end = cur + timedelta(days=rng.randint(0, 3))
        else:
            end = cur + timedelta(days=rng.randint(30, 40))
        out.append((cur, end))
        cur = end + timedelta(days=1)
    return out


def random_dataset(rng: random.Random) -> list[dict]:
    n_emp = rng.randint(1, 9)
    units = rng.sample(["GA_A", "GA_B", "TN_C", "SC_D", "GA_é", "GA_Z9", "NC_X"], rng.randint(1, 3))
    codes = ["Regular", "Regular", "Regular", "Overtime", "Bonus", "Mileage", "Commission"]
    kind = rng.choice(PERIOD_KINDS)
    start = date(2023, 1, 1) + timedelta(days=rng.randint(0, 540))
    rows: list[dict] = []
    for e in range(n_emp):
        ee = rng.choice([f"E{e:03d}", f"E{e}", f"x{e}", f"É{e}"])
        n_per = rng.randint(1, 60)
        first = start + timedelta(days=rng.randint(0, 120))
        avg_h = rng.choice([8.0, 20.0, 31.9, 32.0, 34.0, 34.99, 34.995, 35.0, 35.005, 40.0, 44.5, 0.0])
        avg_w = rng.choice([0.0, 150.0, 635.99, 636.0, 679.995, 680.0, 686.0, 700.0, 1000.0, 2500.5])
        unit_pool = rng.sample(units, rng.randint(1, len(units)))
        unit = rng.choice(unit_pool)
        for pps, ppe in make_periods(rng, first, n_per, kind):
            if rng.random() < 0.08:
                unit = rng.choice(unit_pool)
            weeks = ((ppe - pps).days + 1) / 7.0
            h = round(max(0.0, avg_h * weeks + rng.uniform(-1.5, 1.5)), rng.choice([2, 2, 2, 3]))
            w = round(max(0.0, avg_w * weeks + rng.uniform(-30, 30)), 2)
            if rng.random() < 0.03:
                h, w = None, ""
            if rng.random() < 0.04:
                h = str(h)
            pay = ppe + timedelta(days=rng.randint(0, 9))
            rows.append(row(ee, unit, iso(pps), iso(ppe), iso(pay), h, w, code=rng.choice(codes), fein=rng.choice(["58-1", "99-2", ""])))
            if rng.random() < 0.04:  # duplicate line, as a second pay-code line in one period
                rows.append(row(ee, unit, iso(pps), iso(ppe), iso(pay), round(rng.uniform(0, 5), 2), round(rng.uniform(0, 100), 2), code=rng.choice(codes)))
    rng.shuffle(rows) if rng.random() < 0.3 else None
    return rows


def random_pack(rng: random.Random) -> dict:
    p = with_pack(
        min_weekly_hours=rng.choice([35.0, 35, 32.0, 37.5, 30, 20.0]),
        min_weekly_wages=rng.choice([686.0, 686, 636.0, 0.0, 0, 700.0, 680.5]),
        measuring_date=rng.choice(["last_day", "last_day", "last_day", "15", "1", "31", "28", "0", "-3", "abc", "", " 20 ", "1_5", "١٥", "99", "15.5"]),
        entity_combination=rng.choice(["permitted", "required", "prohibited"]),
        geographic_granularity=rng.choice(["unit", "county", "statewide"]),
        pt_aggregation=rng.random() < 0.3,
    )
    if rng.random() < 0.3:
        p["pt_band_hours"] = rng.choice([[20.0, 32.0], [20, 32], [25.5, 34.9], [0, 35]])
        p["pt_weight"] = rng.choice([0.5, 0.5, 0.25, 0.0, 1, None])
    if rng.random() < 0.3:
        p["included_pay_codes"] = rng.choice([["Regular", "Overtime", "Bonus", "Commission"], ["Regular"], []])
    if rng.random() < 0.3:
        p["excluded_pay_codes"] = rng.choice([["Mileage"], ["Bonus", "Mileage"], []])
    m: dict[str, Any] = {}
    if rng.random() < 0.5:
        for k, vals in (("minimum_pay_period_days", [0, 1, 3, 7, 10, 14, 15]), ("short_periods_excluded_from_numerator", [True, False]),
                        ("pay_period_denominator_mode", ["actual_span", "frequency_code"]), ("min_max_span_mode", ["exclusive_days", "inclusive_days"]),
                        ("count_zero_hour_periods", [True, False]), ("average_decimals", [0, 1, 2, 2, 3, 4]),
                        ("maximum_weeks_without_review", [5.0, 10, 53.0, 100.0]), ("exclude_off_cycle_periods", [True, False])):
            if rng.random() < 0.4:
                m[k] = rng.choice(vals)
    if m:
        p["methodology"] = m
    return p


def random_run(rng: random.Random, i: int, rows: list[dict] | None = None) -> dict:
    rows = rows if rows is not None else random_dataset(rng)
    pack = random_pack(rng)
    kind = rng.choice(["calendar", "calendar", "march", "window", "window_stub"])
    ty = rng.choice([2023, 2024])
    params: dict[str, Any] = {"tax_year": ty, "pack": pack, "with_trail": rng.random() < 0.7, "trail_title": "t", "trail_citation": "c"}
    if kind == "calendar":
        params["analysis_start_month"] = f"{ty}-01-01"
        if rng.random() < 0.5:
            params["fiscal_window"] = [f"{ty}-01-01", f"{ty}-12-31"]
    elif kind == "march":
        params["fiscal_year_end_month"] = 3
        params["analysis_start_month"] = f"{ty - 1}-04-01"
    elif kind == "window":
        b = date(ty - 1, rng.randint(1, 12), 1)
        params["fiscal_window"] = [iso(b), iso(b + timedelta(days=rng.randint(340, 380)))]
        params["analysis_start_month"] = iso(date(b.year, b.month, 1))
    else:
        b = date(ty - 1, rng.randint(1, 12), rng.randint(2, 28))
        params["fiscal_window"] = [iso(b), iso(b + timedelta(days=rng.randint(340, 380)))]
        params["analysis_start_month"] = iso(date(b.year, b.month, 1))
    return {"id": f"random-{i:05d}", "op": rng.choice(["pay_period", "min_max"]), "rows": rows, "params": params}
