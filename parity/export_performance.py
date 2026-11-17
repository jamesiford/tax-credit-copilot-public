"""Golden vectors for ``performance.py``, ``reconciliation.py`` and ``rollups.py`` under ``domain/calculation`` (stage DS5).

``run_performance_dashboard`` is called over: the committed synthetic payroll (the shape ``api/forecast.py`` feeds it), every
edge dataset of ``scenarios.py`` (null/empty/bad cells, duplicates, leap days, extreme values, half-cent ties, unicode ids),
rows built so an employee's ratio sits on both sides of the green/yellow/red edges, floors of every kind, margins and
per-job amounts of every kind (including the ones ``round()`` refuses), and a seeded random batch.

``reconcile_methods`` is called with ``OneZeroResult`` values built from the five fields it reads (the arguments record
exactly those): real engine runs (the synthetic payroll, the gapped employee of ``test_onezero.py``, edge and random
datasets, runs of two different row sets so the methods disagree), hand-built results at every threshold, and a seeded batch.

The two rollups are called over the matrix ``test_ga_depth.py`` builds, real engine matrices, hand-built rows (missing and
falsy keys, short and mistyped ``months``, colliding field names, non-BMP keys, rounding ties) and a seeded batch.

Usage: python parity/export_performance.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import engine_io  # noqa: E402
import golden_rec as gr  # noqa: E402
import scenarios as sc  # noqa: E402
from domain.calculation import onezero as oz  # noqa: E402
from domain.calculation import performance, reconciliation, rollups  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "performance.jsonl.gz"
SEED = 20261116
INF = float("inf")
NAN = float("nan")


def nxt(x: float, up: bool = True) -> float:
    return math.nextafter(x, INF if up else -INF)


# --------------------------------------------------------------------------- performance


def pack_args(hours, wages, citation="cit", included=None, excluded=None) -> dict:
    p = {"min_weekly_hours": hours, "min_weekly_wages": wages, "citation": citation}
    if included is not None:
        p["included_pay_codes"] = included
    if excluded is not None:
        p["excluded_pay_codes"] = excluded
    return p


def perf(rec: gr.Recorder, rows, tax_year, pack, **kw) -> None:
    args = {"rows": rows, "tax_year": tax_year, "pack": pack, **kw}

    def run():
        return performance.run_performance_dashboard(rows, tax_year=tax_year, pack=engine_io.build_pack(pack), **kw)

    rec.call("run_performance_dashboard", args, run)


def one_row(ee, ws, pps, ppe, pay, hrs, wages, **extra):
    return sc.row(ee, ws, pps, ppe, pay, hrs, wages, **extra)


def boundary_rows(year: int) -> list[list[dict]]:
    """Single-employee datasets whose weekly average lands on, and one ulp either side of, the colour edges."""
    out = []
    cases = []
    for floor_h, floor_w in ((35.0, 686.0), (35, 686), (32.0, 636.0)):
        for margin in (0.05, 0.1):
            hi, lo = 1.0 + margin, 1.0 - margin
            for edge_h in (floor_h * hi, floor_h * lo):
                for h in (nxt(edge_h, False), edge_h, nxt(edge_h)):
                    cases.append((h, floor_w * 2.0))
            for edge_w in (floor_w * hi, floor_w * lo):
                for w in (nxt(edge_w, False), edge_w, nxt(edge_w)):
                    cases.append((floor_h * 2.0, w))
    for h, w in cases:
        # an 8-day inclusive span (start..end is 7 days) gives exactly one week, so the average is the hours themselves
        out.append([one_row("E1", "GA_A", f"{year}-01-01", f"{year}-01-08", f"{year}-01-13", h, w, Job_Title="Cook")])
    return out


def perf_cases(rec: gr.Recorder, rng: random.Random) -> None:
    csv_all = sc.csv_rows()
    csv_t = sc.typed(csv_all)
    ga_pack = sc.load_pack("GA", 2025)
    ga_floor = pack_args(ga_pack["min_weekly_hours"], ga_pack["min_weekly_wages"], ga_pack.get("citation", ""),
                         ga_pack.get("included_pay_codes"), ga_pack.get("excluded_pay_codes"))
    for year in (2024, 2025):
        ga_rows = [r for r in csv_t if r["Worksite_ID"].startswith("GA_")]
        perf(rec, ga_rows, year, ga_floor, per_job_usd=3500.0)
        perf(rec, ga_rows, year, ga_floor)
        perf(rec, ga_rows, year, ga_floor, yellow_margin=0.1, per_job_usd=3500)
        perf(rec, csv_t, year, pack_args(35.0, 686.0), yellow_margin=0.0, per_job_usd=2500.5)
    perf(rec, [r for r in csv_all if r["Worksite_ID"].startswith("TN_")], 2025, pack_args(30, 500), per_job_usd=1500.5)
    perf(rec, csv_all, 2025, ga_floor, per_job_usd=3500.0)  # untyped (string) hours and wages, as the CSV loader hands them over
    # --- edge datasets x floors
    floors = [pack_args(35.0, 686.0), pack_args(35, 686), pack_args(0, 0), pack_args(0.0, 0.0), pack_args(-1.0, -5.0),
              pack_args(1e300, 1e300), pack_args(5e-324, 5e-324), pack_args(35.0, 0.0), pack_args(0.0, 686.0),
              pack_args(35.0, 686.0, "ünïcode §", included=["Regular"], excluded=["Mileage"]),
              pack_args(35.0, 686.0, included=["Overtime"]), pack_args(35.0, 686.0, excluded=["Regular"])]
    for name, rows in sc.edge_datasets().items():
        for i, fl in enumerate(floors):
            if i < 3 or i % 3 == 0:
                perf(rec, rows, 2024, fl)
        perf(rec, rows, 2023, floors[0])
        perf(rec, rows, 2024, floors[0], yellow_margin=0.5, per_job_usd=1e20)
    # --- job titles, worksites and ids in odd shapes
    titles = [one_row(f"E{i}", "GA_A", "2024-01-01", "2024-01-08", "2024-01-13", 40.0, 800.0, Job_Title=t)
              for i, t in enumerate(["Cook", None, "", 7, 2.5, "ünï", "\U00010000"])]
    perf(rec, titles, 2024, pack_args(35.0, 686.0), per_job_usd=10.0)
    perf(rec, [one_row("E1", None, "2024-01-01", "2024-01-08", "2024-01-13", 40.0, 800.0),
               one_row("E2", None, "2024-01-01", "2024-01-08", "2024-01-13", 20.0, 100.0)], 2024, pack_args(35.0, 686.0))
    perf(rec, [{k: v for k, v in one_row("E1", "GA_A", "2024-01-01", "2024-01-08", "2024-01-13", 40.0, 800.0).items() if k != "Worksite_ID"}], 2024, pack_args(35.0, 686.0))
    perf(rec, [{k: v for k, v in one_row("E1", "GA_A", "2024-01-01", "2024-01-08", "2024-01-13", 40.0, 800.0).items() if k != "Employee_ID"}], 2024, pack_args(35.0, 686.0))
    perf(rec, [], 2024, pack_args(35.0, 686.0))
    # --- spans: one day, same day, reversed, long, many periods
    for pps, ppe in (("2024-03-01", "2024-03-01"), ("2024-03-02", "2024-03-01"), ("2024-03-01", "2024-03-02"), ("2024-01-01", "2024-12-31"),
                     ("2024-02-28", "2024-03-01"), ("2024-02-29", "2024-03-07")):
        perf(rec, [one_row("E1", "GA_A", pps, ppe, "2024-04-01", 40.0, 800.0)], 2024, pack_args(35.0, 686.0), per_job_usd=99.5)
    perf(rec, [one_row("E1", "GA_A", f"2024-{m:02d}-01", f"2024-{m:02d}-28", f"2024-{m:02d}-29", 120.0 + m, 2400.0 + m) for m in range(1, 13)], 2024, pack_args(35.0, 686.0))
    perf(rec, [one_row("E1", "GA_A", "2024-02-01", "2024-02-28", "2024-02-29", 100.0, 2000.0),
               one_row("E1", "GA_A", "2024-01-01", "2024-01-31", "2024-02-01", 100.0, 2000.0)], 2024, pack_args(35.0, 686.0))
    # --- the colour edges
    for rows in boundary_rows(2024) + boundary_rows(2025):
        for fl in (pack_args(35.0, 686.0), pack_args(35, 686), pack_args(32.0, 636.0)):
            perf(rec, rows, 2024 if rows[0]["Pay_Date"].startswith("2024") else 2025, fl)
    for h in (35.0, 36.75, nxt(36.75), nxt(36.75, False), 33.25, nxt(33.25), nxt(33.25, False), 0.0, 1e-9):
        for margin in (0.05, 0.0, 0.5, 1.0, -0.2, 0.1, 0.05000000000000001, 1, 0, INF, NAN, -INF):
            perf(rec, [one_row("E1", "GA_A", "2024-01-01", "2024-01-08", "2024-01-13", h, 900.0)], 2024, pack_args(35.0, 686.0), yellow_margin=margin, per_job_usd=3500.0)
    # --- two-decimal ties on the binary value (exactly representable eighths), for the averages and the gaps
    for h in (0.125, 0.375, 35.125, 35.375, 36.625, 100.875, 2.675, 1.005, 0.015, 34.995, 686.125, 33.125):
        for w in (686.125, 700.375, 0.625, 1000.875, 12.0):
            perf(rec, [one_row("E1", "GA_A", "2024-01-01", "2024-01-08", "2024-01-13", h, w)], 2024, pack_args(35.0, 686.0), per_job_usd=100.0)
    # --- per-job amounts that round() treats in their own ways
    yellow = [one_row("E1", "GA_A", "2024-01-01", "2024-01-08", "2024-01-13", 36.0, 720.0)]
    for pj in (0.0, 0, 0.5, 1.5, 2.5, 3.5, -0.5, -1.5, 3500.0, 3500, 3499.5, 3499.5000000000005, 1e15 + 0.5, 1e16, 1e20, 1e300, -1e20,
               2 ** 62, 5e-324, NAN, INF, -INF, 0.49999999999999994):
        perf(rec, yellow, 2024, pack_args(35.0, 686.0), per_job_usd=pj)
        perf(rec, [one_row("E9", "GA_A", "2024-01-01", "2024-01-08", "2024-01-13", 100.0, 5000.0)], 2024, pack_args(35.0, 686.0), per_job_usd=pj)
    # --- seeded random
    for i in range(160):
        rows = sc.random_dataset(rng)
        for r in rows:
            if rng.random() < 0.3:
                r["Job_Title"] = rng.choice(["Cook", "Ünï", None, "", 3])
        ty = rng.choice([2023, 2024, 2025])
        fl = pack_args(rng.choice([35.0, 35, 32.0, 37.5, 30, 20.0]), rng.choice([686.0, 686, 636.0, 0.0, 0, 700.0, 680.5]),
                       included=rng.choice([None, None, ["Regular", "Overtime", "Bonus", "Commission"], ["Regular"]]),
                       excluded=rng.choice([None, None, ["Mileage"], ["Bonus", "Mileage"]]))
        kw = {}
        if rng.random() < 0.6:
            kw["yellow_margin"] = rng.choice([0.05, 0.1, 0.2, 0.0, 0.5, 0.01])
        if rng.random() < 0.6:
            kw["per_job_usd"] = rng.choice([3500.0, 0.0, 1200.5, 2500, 0.5, 1.5])
        perf(rec, rows, ty, fl, **kw)


# --------------------------------------------------------------------------- reconciliation


def build_result(method: str, a: dict) -> oz.OneZeroResult:
    return oz.OneZeroResult(
        method=method, tax_year=2025, analysis_start_month=date(2025, 1, 1), months=[], total_hours_and_wages=[],
        eligible_employees=[dict(e) for e in a["eligible_employees"]], employee_unit_matrix=[],
        summary=[{"Worksite_ID": s["Worksite_ID"], "month_totals": list(s["month_totals"])} for s in a["summary"]],
        average_headcount=dict(a["average_headcount"]), annual_average=a["annual_average"],
    )


def result_args(res: oz.OneZeroResult) -> dict:
    return {
        "summary": [{"Worksite_ID": r["Worksite_ID"], "month_totals": r["month_totals"]} for r in res.summary],
        "average_headcount": dict(res.average_headcount),
        "eligible_employees": [{"Employee_ID": r["Employee_ID"], "weeks_worked": r["weeks_worked"]} for r in res.eligible_employees],
        "annual_average": res.annual_average,
    }


def recon(rec: gr.Recorder, pp: dict, mm: dict, **kw) -> None:
    args = {"pp": pp, "mm": mm, **kw}
    rec.call("reconcile_methods", args, lambda: _recon_out(reconciliation.reconcile_methods(build_result("pay_period", pp), build_result("min_max", mm), **kw)))


def _recon_out(report) -> dict:
    return {f: getattr(report, f) for f in reconciliation.ReconciliationReport.__dataclass_fields__}


def gapped_rows(ee: str, unit: str, fein: str = "22-2222222") -> list[dict]:
    rows = []
    for m in range(1, 11):
        last = date(2025, m + 1, 1) - timedelta(days=1)
        pps = last - timedelta(days=11)
        ppe = last + timedelta(days=2)
        rows.append({"Tax_Year": 2025, "Employee_ID": ee, "Worksite_ID": unit, "Pay_Period_Start": pps.isoformat(), "Pay_Period_End": ppe.isoformat(),
                     "Pay_Date": (ppe + timedelta(days=5)).isoformat(), "Hours_Worked": 80.0, "Gross_Wages": 2000.0, "Job_Title": "x", "Entity_FEIN": fein, "Pay_Code": "Regular"})
    return rows


def engine_runs(rows: list[dict], pack: dict, year: int = 2025):
    p = engine_io.build_pack(pack)
    start = date(year, 1, 1)
    return (oz.run_pay_period_method(rows, tax_year=year, analysis_start_month=start, pack=p),
            oz.run_min_max_method(rows, tax_year=year, analysis_start_month=start, pack=p))


def real_pairs(rng: random.Random) -> list[tuple[list[dict], list[dict], dict, int]]:
    """(rows for pay period, rows for min max, pack, year): the same rows, and sometimes different ones."""
    csv_t = sc.typed(sc.csv_rows())
    ga = [r for r in csv_t if r["Worksite_ID"].startswith("GA_")]
    out = [(ga, ga, sc.BASE_PACK, 2025), (csv_t, csv_t, sc.BASE_PACK, 2025), (csv_t, csv_t, sc.BASE_PACK, 2024)]
    gap = gapped_rows("EGAP", "GA_TEST_UNIT")
    out += [(gap, gap, sc.BASE_PACK, 2025), (gap + ga, gap + ga, sc.BASE_PACK, 2025), (ga, gap, sc.BASE_PACK, 2025)]
    out += [(ga, ga[: len(ga) // 2], sc.BASE_PACK, 2025), (ga[::2], ga, sc.BASE_PACK, 2025), (ga, [], sc.BASE_PACK, 2025), ([], ga, sc.BASE_PACK, 2025)]
    for name, rows in sc.edge_datasets().items():
        out.append((rows, rows, sc.BASE_PACK, 2024))
    for _ in range(50):
        a = sc.random_dataset(rng)
        out.append((a, a if rng.random() < 0.6 else sc.random_dataset(rng), sc.with_pack(min_weekly_hours=rng.choice([35.0, 20.0, 30]), min_weekly_wages=rng.choice([686.0, 400.0, 0.0])), rng.choice([2023, 2024, 2025])))
    return out


def recon_real(rec: gr.Recorder, rng: random.Random) -> None:
    for pp_rows, mm_rows, pack, year in real_pairs(rng):
        try:
            pp = engine_runs(pp_rows, pack, year)[0]
            mm = engine_runs(mm_rows, pack, year)[1]
        except Exception:  # an engine error is not what this module is about; the engine goldens cover it
            continue
        for tol in (None, 0.0, 1.5, 0.5):
            kw = {} if tol is None else {"donut_hole_tolerance_weeks": tol}
            recon(rec, result_args(pp), result_args(mm), **kw)


def unit(ws, totals, avg=None):
    return {"Worksite_ID": ws, "month_totals": totals, "avg": avg}


def make(units: list[tuple], employees: list[tuple], annual: float) -> dict:
    return {
        "summary": [{"Worksite_ID": u[0], "month_totals": u[1]} for u in units],
        "average_headcount": {u[0]: u[2] for u in units if len(u) > 2 and u[2] is not None},
        "eligible_employees": [{"Employee_ID": e[0], "weeks_worked": e[1]} for e in employees],
        "annual_average": annual,
    }


def recon_hand(rec: gr.Recorder, rng: random.Random) -> None:
    flat = lambda v: [v] * 12  # noqa: E731
    tol = 0.01
    base = 10.0
    edge = base + tol  # the invariant tolerance as the double it is
    cases = []
    for pp_avg in (nxt(edge, False), edge, nxt(edge), base, base - 1.0, base + 5.0, NAN, INF, -0.0):
        cases.append((make([("A", flat(1.0), pp_avg)], [], 5.0), make([("A", flat(1.0), base)], [], 5.0)))
    for pp_m in (nxt(1.0 + tol, False), 1.0 + tol, nxt(1.0 + tol), 1.5, 0.5, NAN, -0.0, INF):
        tot = [1.0] * 12
        tot[3] = pp_m
        tot[7] = 2.0
        cases.append((make([("A", tot, 12.0)], [], 5.0), make([("A", flat(1.0), 1.0)], [], 4.0)))
    # units on one side only, in both orders, with unicode ordering
    cases.append((make([("B", flat(1.0), 1.0)], [], 1.0), make([("A", flat(2.0), 2.0)], [], 2.0)))
    cases.append((make([("é", flat(1.0), 1.0), ("Z", flat(1.0), 1.0), ("\U00010000", flat(1.0), 1.0), ("\uffff", flat(1.0), 1.0)], [], 1.0), make([], [], 0.0)))
    cases.append((make([], [], 0.0), make([], [], 0.0)))
    cases.append((make([], [], 0.0), make([("a", flat(1.0), 1.0), ("A", flat(1.0), 1.0), ("a ", flat(1.0), 1.0)], [], 1.0)))
    # a unit without an average: the default is the int 0
    cases.append((make([("A", flat(1.0))], [], 0.0), make([("A", flat(2.0), 1.0)], [], 1.0)))
    cases.append((make([("A", flat(1.0), 2.0)], [], 0.0), make([("A", flat(2.0))], [], 1.0)))
    cases.append((make([("A", flat(1.0)), ("B", flat(0.0))], [], 0.0), make([("A", flat(2.0)), ("C", flat(1.0))], [], 1.0)))
    # duplicates and short or long month lists
    d1 = make([("A", flat(1.0), 1.0), ("A", flat(3.0), 3.0)], [("e1", 10.0), ("e1", 20.0)], 2.0)
    cases.append((d1, make([("A", flat(2.0), 2.0)], [("e1", 5.0)], 2.0)))
    cases.append((make([("A", [1.0] * 11, 1.0)], [], 1.0), make([("A", flat(1.0), 1.0)], [], 1.0)))
    cases.append((make([("A", flat(1.0), 1.0)], [], 1.0), make([("A", [1.0] * 11, 1.0)], [], 1.0)))
    cases.append((make([("A", [1.0] * 13, 1.0)], [], 1.0), make([("A", [2.0] * 14, 1.0)], [], 1.0)))
    cases.append((make([("A", [], 1.0)], [], 1.0), make([("A", flat(1.0), 1.0)], [], 1.0)))
    cases.append((make([("A", [NAN] + [1.0] * 11, 1.0)], [], 1.0), make([("A", flat(1.0), 1.0)], [], 1.0)))
    cases.append((make([("A", [-0.0] * 12, 0.0)], [], -0.0), make([("A", [0.0] * 12, 0.0)], [], 0.0)))
    # donut hole at the tolerance edge, ties and unicode ids
    for tol_w in (1.5, 0.0, 1.0, 2.0, 1.14):
        for pw in (nxt(10.0 + tol_w, False), 10.0 + tol_w, nxt(10.0 + tol_w), 10.0, 50.0, NAN, INF):
            cases.append((make([], [("e1", pw), ("e2", 52.0)], 1.0), make([], [("e1", 10.0), ("e2", 50.86), ("e3", 1.0)], 1.0)))
    cases.append((make([], [("b", 52.0), ("a", 52.0), ("é", 52.0), ("\U00010000", 52.0), ("\uffff", 52.0), ("B", 52.0), ("10", 52.0), ("9", 52.0)], 1.0),
                  make([], [("b", 1.0), ("a", 1.0), ("é", 1.0), ("\U00010000", 1.0), ("\uffff", 1.0), ("B", 1.0), ("10", 1.0), ("9", 1.0), ("z", 1.0)], 1.0)))
    cases.append((make([], [("a", 1.0)], 1.0), make([], [("b", 1.0)], 1.0)))
    cases.append((make([], [], 1.0), make([], [("b", 1.0)], 1.0)))
    cases.append((make([], [("only", 52.0)], 1.0), make([], [], 1.0)))
    for pw, mw in ((12.125, 10.0), (10.375, 8.0), (0.625, 0.0), (2.675, 0.0), (1.005, 0.0), (52.0, 50.86), (12.135, 10.0), (3.5, 0.0)):
        cases.append((make([], [("e1", pw)], 1.0), make([], [("e1", mw)], 1.0)))
    # annual averages: rounding of the difference
    for a, b in ((100.005, 100.0), (0.125, 0.0), (2.675, 0.0), (1.005, 0.0), (1e300, 1e300), (NAN, 1.0), (INF, INF), (INF, 1.0), (-0.0, 0.0), (0.0, 0.0),
                 (494.25, 410.13), (5e-324, 0.0), (1.0000000000000002, 1.0), (0.015, 0.0), (-0.015, 0.0), (1e22, 1.0)):
        cases.append((make([], [], a), make([], [], b)))
    for pp, mm in cases:
        for kw in ({}, {"donut_hole_tolerance_weeks": 0.0}, {"donut_hole_tolerance_weeks": 1.5}, {"donut_hole_tolerance_weeks": -1.0}, {"donut_hole_tolerance_weeks": INF},
                   {"donut_hole_tolerance_weeks": NAN}):
            if kw and rng.random() < 0.6:
                continue
            recon(rec, pp, mm, **kw)
    # seeded random
    ids = ["e%02d" % i for i in range(30)] + ["Ünï", "\U00010000x", "e1"]
    units = ["GA_A", "GA_B", "GA_é", "TN_C", "SC_D", "GA_\U00010000", "ga_a", "GA_A "]
    for _ in range(700):
        def side(is_pp: bool) -> dict:
            us = rng.sample(units, rng.randint(0, len(units)))
            ulist = []
            for u in us:
                tots = [round(rng.choice([0.0, 0.5, 1.0, 2.0, 3.5, 10.0]) + rng.uniform(-0.01, 0.02) * rng.choice([0, 1, 1]), 2) for _ in range(12)]
                avg = round(sum(tots) / 12.0 + rng.choice([0.0, 0.0, 0.01, 0.011, -0.5, 1.0, 0.0099999]), 2)
                ulist.append((u, tots, avg if rng.random() < 0.92 else None))
            es = rng.sample(ids, rng.randint(0, 14))
            elist = [(e, rng.choice([52.0, 50.86, 48.0, 26.0, 12.5, 51.5, 53.0, 0.0, round(rng.uniform(0, 60), 2)])) for e in es]
            return make(ulist, elist, round(rng.uniform(0, 500), 2) if rng.random() < 0.9 else rng.choice([0.0, 100.0, 100.005]))
        recon(rec, side(True), side(False), **({} if rng.random() < 0.6 else {"donut_hole_tolerance_weeks": rng.choice([0.0, 0.5, 1.0, 1.5, 2.0, 10.0])}))


# --------------------------------------------------------------------------- rollups


def roll1(rec, matrix, field):
    rec.call("rollup_matrix_by_field", {"matrix": matrix, "field": field}, lambda: rollups.rollup_matrix_by_field(matrix, field))


def roll2(rec, matrix, a, b):
    rec.call("rollup_matrix_by_two_fields", {"matrix": matrix, "field_a": a, "field_b": b}, lambda: rollups.rollup_matrix_by_two_fields(matrix, a, b))


def mrow(ws, fein, months, **extra):
    r = {"Employee_ID": extra.pop("ee", "E1"), "Worksite_ID": ws, "Entity_FEIN": fein}
    r.update(extra)
    r["months"] = months
    return r


def rollup_cases(rec: gr.Recorder, rng: random.Random) -> None:
    ga = [{"Worksite_ID": "GA_A", "Entity_FEIN": "58-1", "months": [1] * 12}, {"Worksite_ID": "GA_A", "Entity_FEIN": "58-2", "months": [1] * 12},
          {"Worksite_ID": "GA_B", "Entity_FEIN": "58-1", "months": [1] * 12}]
    roll2(rec, ga, "Worksite_ID", "Entity_FEIN")
    for f in ("Worksite_ID", "Entity_FEIN", "Missing", ""):
        roll1(rec, ga, f)
    # real matrices
    for rows, pack, year in ((sc.typed(sc.csv_rows()), sc.BASE_PACK, 2025), (sc.typed(sc.csv_rows()), sc.BASE_PACK, 2024)):
        pp, mm = engine_runs(rows, pack, year)
        for res in (pp, mm):
            for f in ("Worksite_ID", "Entity_FEIN", "Employee_ID"):
                roll1(rec, res.employee_unit_matrix, f)
            roll2(rec, res.employee_unit_matrix, "Worksite_ID", "Entity_FEIN")
            roll2(rec, res.employee_unit_matrix, "Entity_FEIN", "Worksite_ID")
    for name, rows in sc.edge_datasets().items():
        try:
            pp, mm = engine_runs(rows, sc.BASE_PACK, 2024)
        except Exception:
            continue
        for res in (pp, mm):
            roll1(rec, res.employee_unit_matrix, "Worksite_ID")
            roll1(rec, res.employee_unit_matrix, "Entity_FEIN")
            roll2(rec, res.employee_unit_matrix, "Worksite_ID", "Entity_FEIN")
    # empty and falsy keys
    roll1(rec, [], "Worksite_ID")
    roll2(rec, [], "Worksite_ID", "Entity_FEIN")
    falsy = [mrow(None, "", [1.0] * 12), mrow("", None, [0.5] * 12), mrow("GA_A", "(unattributed)", [1.0] * 12), mrow("(unattributed)", "x", [2.0] * 12),
             {"Worksite_ID": 0, "Entity_FEIN": False, "months": [1.0] * 12}, {"months": [3.0] * 12}]
    roll1(rec, falsy, "Worksite_ID")
    roll1(rec, falsy, "Entity_FEIN")
    roll2(rec, falsy, "Worksite_ID", "Entity_FEIN")
    roll2(rec, falsy, "Entity_FEIN", "Worksite_ID")
    # field names that collide with the output keys
    base = [mrow("GA_A", "58-1", [1.0, 0.5] * 6), mrow("GA_B", "58-2", [0.0] * 12), mrow("GA_A", "58-1", [1] * 12)]
    for a, b in (("Worksite_ID", "Worksite_ID"), ("total", "Entity_FEIN"), ("Worksite_ID", "total"), ("month_totals", "average_headcount"),
                 ("average_headcount", "month_totals"), ("Missing", "Missing2"), ("", "")):
        roll2(rec, [dict(r, total="t", month_totals="m", average_headcount="h") for r in base], a, b)
    roll1(rec, [dict(r, total="t") for r in base], "total")
    # ordering by code point, not UTF-16
    keys = ["b", "B", "a", "é", "Z", "\U00010000", "\uffff", "\ud7ff", "\ue000", "10", "9", "", " ", "(unattributed)", "(", "ÿ", "Ā"]
    uni = [mrow(k, k[::-1], [float(i)] * 12) for i, k in enumerate(keys)]
    roll1(rec, uni, "Worksite_ID")
    roll2(rec, uni + [mrow(k, "z" + k, [1.0] * 12) for k in keys], "Worksite_ID", "Entity_FEIN")
    # rounding and accumulation order
    ties = [mrow("A", "x", [0.125, 0.375, 2.675, 1.005, 0.015, 0.025, 0.035, 0.045, 0.055, -0.125, -0.0, 5e-324]),
            mrow("A", "x", [0.1, 0.2, 0.3, 0.7, 0.1, 0.2, 0.3, 0.7, 1e16, -1e16, 0.1, 0.1]),
            mrow("B", "x", [-0.001] * 12), mrow("C", "x", [0.005] * 12), mrow("D", "x", [1e308, 1e308] * 6), mrow("E", "x", [NAN] * 12),
            mrow("F", "x", [INF] + [0.0] * 11), mrow("G", "x", [INF, -INF] + [0.0] * 10), mrow("H", "x", [1 << 53, 1, 1, 1] + [0] * 8), mrow("I", "x", [True, False] * 6)]
    roll1(rec, ties, "Worksite_ID")
    roll2(rec, ties, "Worksite_ID", "Entity_FEIN")
    for m in (list(range(12)), [10 ** 400] + [0] * 11, [-(10 ** 400)] + [0] * 11, [2 ** 63] + [0] * 11, [-(2 ** 63)] * 12, [2 ** 53 + 1] + [0] * 11):
        roll1(rec, [mrow("A", "x", m)], "Worksite_ID")
    # mistyped or short months and missing keys
    bad = [[1.0] * 11, [], [1.0] * 13, [None] + [1.0] * 11, ["1"] + [1.0] * 11, [[1.0]] + [1.0] * 11, [{"a": 1}] + [1.0] * 11, [1.0] * 11 + [None]]
    for m in bad:
        roll1(rec, [mrow("A", "x", m)], "Worksite_ID")
        roll2(rec, [mrow("A", "x", m)], "Worksite_ID", "Entity_FEIN")
    roll1(rec, [{"Worksite_ID": "A"}], "Worksite_ID")
    roll2(rec, [{"Worksite_ID": "A"}], "Worksite_ID", "Entity_FEIN")
    # seeded random
    wss = ["GA_A", "GA_B", "TN_C", "", None, "GA_é", "ga_a", "\U00010000", "(unattributed)"]
    feins = ["58-1", "58-2", "", None, "99-9", "é"]
    for _ in range(500):
        n = rng.randint(0, 25)
        mat = []
        for _ in range(n):
            months = [rng.choice([0, 1, 0.5, 1.0, 0.0, round(rng.uniform(0, 1), 3), 2, -0.5]) for _ in range(12)]
            mat.append(mrow(rng.choice(wss), rng.choice(feins), months, ee=rng.choice(["E1", "E2", "E3", None])))
        roll1(rec, mat, rng.choice(["Worksite_ID", "Entity_FEIN", "Employee_ID", "Missing"]))
        roll2(rec, mat, *rng.choice([("Worksite_ID", "Entity_FEIN"), ("Entity_FEIN", "Worksite_ID"), ("Worksite_ID", "Employee_ID"), ("Worksite_ID", "Worksite_ID")]))


# --------------------------------------------------------------------------- build


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    rec = gr.Recorder()
    perf_cases(rec, rng)
    recon_real(rec, rng)
    recon_hand(rec, rng)
    rollup_cases(rec, rng)
    return gr.serialise(rec, {}, seed, oracle.stamp())


if __name__ == "__main__":
    raise SystemExit(gr.main("performance", DEFAULT_OUT, SEED, build))
