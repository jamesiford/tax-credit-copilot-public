"""Golden vectors for ``domain/calculation/proximity.py`` (stage DS3, proximity family).

Every public and private function of the module is called over a scenario matrix: every input the Python tests use
(``test_proximity.py``, ``test_rest_of_year.py``) plus boundaries on both sides of each floor, half-cent amounts, missing
and ``None`` fields, recorded-verdict variants, part-time fractional weights, tie-heavy cohorts, ``population`` overrides,
unusual ``limit`` and ``decimals`` values, non-finite and huge numbers, and seeded random batches.

Line format (JSONL, gzip, mtime 0): ``{"k":"call","id":n,"fn":name,"args":{...},"out":tree}`` or
``{"k":"call",...,"err":"TypeName","msg":str(exception)}``. The text is ``json.dumps`` output: ints stay ints, floats are
``repr`` (round-trips bit for bit), non-finite floats are ``NaN``/``Infinity`` (read with the port's ``PyJson.Loads``,
never ``System.Text.Json``). A ``date`` is the tagged object ``{"$date": "YYYY-MM-DD"}``.

Usage: python parity/export_proximity.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
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

from domain.calculation import proximity as prox  # noqa: E402
from domain.calculation.floors import StatutoryFloors  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "proximity.jsonl.gz"
SEED = 20261114
INF = float("inf")
NAN = float("nan")


def floors_of(code: str, year: int, hours, wages) -> StatutoryFloors:
    return StatutoryFloors(code, year, hours, wages, {}, {}, code.lower() + ".json")


def _floors_args(f: StatutoryFloors) -> dict:
    return {"program_code": f.program_code, "tax_year": f.tax_year, "min_hours": f.min_weekly_hours, "min_wages": f.min_weekly_wages}


def enc(x):
    """JSON-able view: dates are tagged, tuples become lists, floors become their four fields."""
    if isinstance(x, date):
        return {"$date": x.isoformat()}
    if isinstance(x, StatutoryFloors):
        return _floors_args(x)
    if isinstance(x, dict):
        return {k: enc(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [enc(v) for v in x]
    return x


def dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


class Recorder:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.counts: dict[str, int] = {}
        self.errors = 0

    def call(self, fn: str, args: dict) -> None:
        text_in = dumps(enc(args))
        try:
            out = getattr(prox, fn)(**args)
        except Exception as e:  # the exception type and message are part of the contract
            self.errors += 1
            rec = {"k": "call", "id": len(self.lines), "fn": fn, "err": type(e).__name__, "msg": str(e)}
        else:
            rec = {"k": "call", "id": len(self.lines), "fn": fn, "out": out}
        self.counts[fn] = self.counts.get(fn, 0) + 1
        self.lines.append((text_in, rec))

def avg(employee_id, hours, wages, weeks=52.0):
    """The row shape the Python tests use (banker's ``round``, kept on purpose)."""
    return {
        "Employee_ID": employee_id, "total_hours": hours, "total_wages": wages, "weeks_worked": weeks,
        "avg_weekly_hours": round(hours / weeks, 2), "avg_weekly_wages": round(wages / weeks, 2),
    }


def raw(employee_id, **fields):
    return {"Employee_ID": employee_id, **fields}


def real_floors() -> list[StatutoryFloors]:
    from tools.credit_math import resolve_statutory_floors
    return [resolve_statutory_floors("GA_JTC", y) for y in (2021, 2023, 2024, 2025)]


def synthetic_floors() -> list[StatutoryFloors]:
    return [
        floors_of("GA_JTC", 2023, 35, 636),            # ints: output type must stay int
        floors_of("XX_DEMO", 2030, 32.5, 700.25),
        floors_of("SC_JOBS", 2024, 35.0, 0.0),
        floors_of("ZERO_H", 2024, 0, 636.0),           # falsy hours floor: no threshold rate
        floors_of("ZERO_H", 2024, 0.0, 0),
        floors_of("NEG", 2024, -5.0, -100.0),
        floors_of("BIG", 2024, 1e300, 1e300),
        floors_of("TINY", 2024, 5e-324, 5e-324),
        floors_of("Ga_Mixed", 2024, 20.0, 360.0),
    ]


# --------------------------------------------------------------------------------------------------------- rows

def test_rows() -> list[dict]:
    """Every row the Python tests build, verbatim."""
    rows = [
        avg("E1", 2080, 52000), avg("E2", 1560, 39000), avg("E3", 2080, 31200), avg("E4", 1560, 23400),
        avg("E5", 2080, 31200), avg("E6", 1560, 39000), avg("E7", 1040, 12480), avg("E8", 0, 5000),
        avg("A", 2080, 52000), avg("B", 1560, 39000), avg("C", 2080, 31200), avg("D", 1560, 23400),
        avg("far", 1560, 23400), avg("near", 2080, 31200), avg("mid", 1560, 39000), avg("x", 1560, 23400),
        avg("straddler", 2080, 34000), avg("PT", 1300, 33800), avg("FT", 2080, 52000), avg("drifted", 2080, 52000),
        avg("near", 1716, 42900), avg("thin-on-wages", 70 * 52, 637 * 52), avg("safe", 45 * 52, 2250 * 52),
        avg("a", 36 * 52, 700 * 52), avg("roomy", 40 * 52, 900 * 52), avg("thin", 35.5 * 52, 700 * 52),
        avg("x", 20 * 52, 300 * 52), avg("tok", 1, 1),
    ]
    for weekly_hours in [h / 2 for h in range(0, 101)]:
        for rate in (7.25, 12.0, 18.17, 25.0, 40.0, 80.0):
            rows.append(avg("probe", weekly_hours * 52.0, weekly_hours * rate * 52.0, 52.0))
    pt = avg("PT", 1300, 33800)
    pt["eligible"] = True
    rows.append(pt)
    return rows


def verdict_variants() -> list[dict]:
    out = []
    base = [avg("V", 2080, 52000), avg("V", 1560, 39000), avg("V", 1560, 23400), avg("V", 1300, 33800)]
    for b in base:
        for verdict in (True, False, None, 0, 1, "", "no", "yes", 0.0, [], [1], 2):
            r = dict(b)
            r["eligible"] = verdict
            out.append(r)
        out.append(dict(b))  # key absent
    return out


def edge_rows() -> list[dict]:
    rows: list[dict] = []
    nxt = lambda v, d: __import__("math").nextafter(v, d)  # noqa: E731
    # both sides of each floor (GA 2023: 35 hours, $636)
    for h in (34.0, 34.99, 34.995, 34.9999999999, nxt(35.0, 0.0), 35.0, nxt(35.0, 99.0), 35.004, 35.005, 35.01, 36.0):
        for w in (635.0, 635.99, 635.995, nxt(636.0, 0.0), 636.0, nxt(636.0, 1e9), 636.004, 636.005, 637.0):
            rows.append(raw(f"b{h}/{w}", total_hours=h * 52, total_wages=w * 52, weeks_worked=52.0, avg_weekly_hours=h, avg_weekly_wages=w))
    # half-cent and tie amounts that make banker's versus half-up rounding differ
    for v in (0.125, 0.375, 2.675, 1.005, 2.5, 0.5, 1.5, 0.045, 0.055, 1e-7, 1.0000000000000002, 33.335, 34.665, 12345678.125):
        rows.append(raw("tie", total_hours=v * 100, total_wages=v * 1000, weeks_worked=v * 10, avg_weekly_hours=v * 5, avg_weekly_wages=v * 50))
        rows.append(raw("tie2", total_hours=v, total_wages=v, weeks_worked=v, avg_weekly_hours=30 + v, avg_weekly_wages=600 + v))
    # missing fields, None fields, zero and negative values
    rows += [
        {}, {"Employee_ID": None}, raw("n", total_hours=None, total_wages=None, weeks_worked=None, avg_weekly_hours=None, avg_weekly_wages=None),
        raw("z", total_hours=0, total_wages=0, weeks_worked=0, avg_weekly_hours=0, avg_weekly_wages=0),
        raw("zf", total_hours=0.0, total_wages=0.0, weeks_worked=0.0, avg_weekly_hours=0.0, avg_weekly_wages=0.0),
        raw("nz", total_hours=-0.0, total_wages=-0.0, weeks_worked=-0.0, avg_weekly_hours=-0.0, avg_weekly_wages=-0.0),
        raw("neg", total_hours=-10.0, total_wages=-500.0, weeks_worked=-3.0, avg_weekly_hours=-1.0, avg_weekly_wages=-50.0),
        raw("w0", total_hours=100.0, total_wages=1000.0, weeks_worked=0, avg_weekly_hours=10.0, avg_weekly_wages=100.0),
        raw("w0b", total_hours=100.0, total_wages=1000.0, weeks_worked=None, avg_weekly_hours=10.0, avg_weekly_wages=100.0),
        raw("h0w", total_hours=0, total_wages=900.0, weeks_worked=10.0, avg_weekly_hours=0.0, avg_weekly_wages=90.0),
        raw("hneg", total_hours=-5.0, total_wages=900.0, weeks_worked=10.0, avg_weekly_hours=30.0, avg_weekly_wages=90.0),
        raw("rneg", total_hours=100.0, total_wages=-900.0, weeks_worked=10.0, avg_weekly_hours=40.0, avg_weekly_wages=-90.0),
        raw("wz", total_hours=100.0, total_wages=0.0, weeks_worked=10.0, avg_weekly_hours=40.0, avg_weekly_wages=0.0),
        raw("hrsfail_wageok", total_hours=1000.0, total_wages=90000.0, weeks_worked=50.0, avg_weekly_hours=20.0, avg_weekly_wages=1800.0),
        raw("both_norate", total_hours=0.0, total_wages=0.0, weeks_worked=50.0, avg_weekly_hours=0.0, avg_weekly_wages=0.0),
        raw("wagesonly_norate", total_hours=0.0, total_wages=0.0, weeks_worked=50.0, avg_weekly_hours=40.0, avg_weekly_wages=10.0),
        raw("wagesonly_negrate", total_hours=10.0, total_wages=-100.0, weeks_worked=50.0, avg_weekly_hours=40.0, avg_weekly_wages=10.0),
        raw("wagesonly_zerorate", total_hours=10.0, total_wages=0.0, weeks_worked=50.0, avg_weekly_hours=40.0, avg_weekly_wages=10.0),
        raw("hoursonly_norate_weeks0", total_hours=0.0, total_wages=0.0, weeks_worked=0.0, avg_weekly_hours=10.0, avg_weekly_wages=700.0),
        raw("weights", total_hours=1, total_wages=1, weeks_worked=1, avg_weekly_hours=36, avg_weekly_wages=700, weight=0),
        raw("weights", total_hours=1, total_wages=1, weeks_worked=1, avg_weekly_hours=36, avg_weekly_wages=700, weight=0.0),
        raw("weights", total_hours=1, total_wages=1, weeks_worked=1, avg_weekly_hours=36, avg_weekly_wages=700, weight=0.5),
        raw("weights", total_hours=1, total_wages=1, weeks_worked=1, avg_weekly_hours=36, avg_weekly_wages=700, weight=None),
        raw("weights", total_hours=1, total_wages=1, weeks_worked=1, avg_weekly_hours=36, avg_weekly_wages=700, weight=-0.5),
        raw("weights", total_hours=1, total_wages=1, weeks_worked=1, avg_weekly_hours=36, avg_weekly_wages=700, weight=2),
        raw("weights", total_hours=1, total_wages=1, weeks_worked=1, avg_weekly_hours=36, avg_weekly_wages=700, weight=True),
        raw("weights", total_hours=1, total_wages=1, weeks_worked=1, avg_weekly_hours=36, avg_weekly_wages=700, weight=NAN),
        raw("weights", total_hours=1, total_wages=1, weeks_worked=1, avg_weekly_hours=36, avg_weekly_wages=700, weight="0.25"),
    ]
    # employee id and token shapes
    for emp in ("e", "é", "\U0001F600", "10", "9", 10, 9, 10.0, None, True, False, 12345678901234567890, 1e22, 1e-7):
        rows.append(dict(avg("x", 1560, 23400), Employee_ID=emp, record_token="tok-" + str(emp)))
    r = avg("x", 1560, 23400)
    del r["Employee_ID"]
    rows.append(r)
    rows.append(dict(avg("x", 1560, 23400), record_token=None))
    # types: bool, str, huge, tiny, non-finite
    for v in (True, False, "35.5", "abc", " 12 ", "1_0", "", "inf", "nan", "0", [], [1], {}, 10 ** 400, -(10 ** 400), 10 ** 25, 2 ** 53 + 1):
        for field in ("total_hours", "total_wages", "weeks_worked", "avg_weekly_hours", "avg_weekly_wages"):
            rows.append(dict(avg("t", 1560, 23400), **{field: v}))
    for v in (1e308, -1e308, 5e-324, 1e-320, INF, -INF, NAN, 1.7976931348623157e308):
        for field in ("total_hours", "total_wages", "weeks_worked", "avg_weekly_hours", "avg_weekly_wages"):
            rows.append(dict(avg("t", 1560, 23400), **{field: v}))
    rows.append(raw("allbig", total_hours=1e308, total_wages=1e308, weeks_worked=1e-300, avg_weekly_hours=1e308, avg_weekly_wages=1e308))
    rows.append(raw("allnan", total_hours=NAN, total_wages=NAN, weeks_worked=NAN, avg_weekly_hours=NAN, avg_weekly_wages=NAN))
    rows.append(raw("allinf", total_hours=INF, total_wages=INF, weeks_worked=INF, avg_weekly_hours=INF, avg_weekly_wages=INF))
    return rows


def random_rows(rng: random.Random, n: int) -> list[dict]:
    rows = []
    for i in range(n):
        weeks = rng.choice([52.0, 52, 26.5, 10.0, 1.0, 0.0, 53.14, 4.43, rng.uniform(0.1, 60)])
        hrs_pw = rng.choice([0, 5, 20, 30, 34.5, 35, 35.5, 36, 40, 45, 60, rng.uniform(0, 70)])
        rate = rng.choice([0, 7.25, 12.0, 15.0, 18.17, 18.1714, 18.18, 25.0, 40.0, rng.uniform(5, 90)])
        th = round(hrs_pw * weeks, rng.choice([0, 1, 2, 3, 6]))
        tw = round(th * rate, rng.choice([0, 2, 2, 3, 6]))
        row = {"Employee_ID": rng.choice([f"E{i}", i, f"E{i % 7}", None, str(i % 5)]),
               "total_hours": th, "total_wages": tw, "weeks_worked": weeks,
               "avg_weekly_hours": round(th / weeks, 2) if weeks else rng.choice([0.0, None, 12.5]),
               "avg_weekly_wages": round(tw / weeks, 2) if weeks else rng.choice([0.0, None, 700.0])}
        if rng.random() < 0.3:
            row["eligible"] = rng.choice([True, False, None, 0, 1])
        if rng.random() < 0.25:
            row["weight"] = rng.choice([0.5, 1.0, 0, None, 0.25, 0.75, 1, 0.1, 0.2, 0.3])
        if rng.random() < 0.3:
            row["record_token"] = f"t{rng.randrange(1000)}"
        for k in list(row):
            if k not in ("Employee_ID",) and rng.random() < 0.03:
                if rng.random() < 0.5:
                    del row[k]
                else:
                    row[k] = None
        rows.append(row)
    return rows


# ------------------------------------------------------------------------------------------------ rest of year

def weekly(hours: float, wage: float, weeks, start=date(2025, 1, 6)) -> list[dict]:
    out = []
    for n in weeks:
        s = start + timedelta(days=7 * n)
        out.append({"pay_period_start": s.isoformat(), "pay_period_end": (s + timedelta(days=6)).isoformat(), "hours": hours, "wages": hours * wage})
    return out


def cadence(days: int, n: int, hours: float, wage: float, start=date(2025, 1, 1), lag=None, as_date=False) -> list[dict]:
    out = []
    for i in range(n):
        s = start + timedelta(days=days * i)
        e = s + timedelta(days=days - 1)
        p = {"pay_period_start": s if as_date else s.isoformat(), "pay_period_end": e if as_date else e.isoformat(), "hours": hours, "wages": round(hours * wage, 2)}
        if lag is not None:
            pd = e + timedelta(days=lag)
            p["pay_date"] = pd if as_date else pd.isoformat()
        out.append(p)
    return out


def synthetic_periods() -> list[list[dict]]:
    from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
    from data.source.to_bcs import source_to_bcs_rows
    rows = [r for r in source_to_bcs_rows(build_synthetic_dataset(SYNTHETIC_CLIENTS[0])) if r["Work_State"] == "GA" and r["Pay_Date"][:4] == "2025"]
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(str(r["Employee_ID"]), []).append({
            "pay_period_start": r["Pay_Period_Start"], "pay_period_end": r["Pay_Period_End"],
            "hours": r["Hours_Worked"], "wages": r["Gross_Wages"], "pay_date": r.get("Pay_Date")})
    return [by[k] for k in sorted(by)][:60]


def roy_scenarios(rec: Recorder, rng: random.Random, floors_list: list[StatutoryFloors]) -> None:
    ga25 = floors_list[3]
    asof = [date(2025, 8, 31), date(2025, 6, 30), date(2025, 12, 30), date(2025, 12, 31), date(2026, 1, 5), date(2025, 1, 5), date(2025, 1, 12), date(2025, 2, 28), date(2025, 10, 15)]
    year_ends = [date(2025, 12, 31), date(2025, 12, 28), date(2026, 3, 31)]
    series = {
        "w34": weekly(34.0, 25.0, range(34)), "w38": weekly(38.0, 25.0, range(34)), "w40_15": weekly(40.0, 15.0, range(34)),
        "w34_then60": weekly(34.0, 25.0, range(34)) + weekly(60.0, 25.0, range(34, 51)), "w0hours": weekly(0.0, 25.0, range(20)),
        "w0wages": weekly(40.0, 0.0, range(20)), "w_zero_both": weekly(0.0, 0.0, range(20)), "w1": weekly(34.0, 25.0, range(1)),
        "w52": weekly(35.0, 20.0, range(52)), "w_rate_low_hours_ok": weekly(36.0, 17.0, range(30)),
        "bi": cadence(14, 18, 68.0, 20.0, lag=5), "bi_nolag": cadence(14, 18, 68.0, 20.0), "semi": cadence(15, 12, 75.0, 22.0, lag=3),
        "month": cadence(30, 8, 150.0, 20.0, lag=10), "bi_date": cadence(14, 18, 66.0, 21.0, lag=4, as_date=True),
        "neglag": cadence(14, 18, 68.0, 20.0, lag=-3), "biglag": cadence(14, 18, 60.0, 20.0, lag=40),
        "empty": [], "w_halfcent": weekly(34.995, 18.125, range(34)),
    }
    for name, periods in series.items():
        for floors in (ga25, floors_list[1], floors_list[2]):
            for as_of in asof:
                for year_end in year_ends[:2] if name != "w34" else year_ends:
                    for method in ("min_max", "pay_period"):
                        rec.call("rest_of_year", {"periods": periods, "floors": floors, "as_of": as_of, "year_end": year_end, "method": method})
    base = series["w34"]
    for decimals in (0, 1, 3, 4):
        for key in ("w34", "w40_15", "bi", "w38"):
            rec.call("rest_of_year", {"periods": series[key], "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31), "decimals": decimals})
    for method in ("min_max", "pay_period", "other", "", None):
        rec.call("rest_of_year", {"periods": base, "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31), "method": method})
    for f in synthetic_floors():
        for key in ("w34", "w40_15", "w0hours", "bi"):
            rec.call("rest_of_year", {"periods": series[key], "floors": f, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
    # string dates, mixed shapes and errors
    iso = lambda d: d.isoformat()  # noqa: E731
    for as_of in ("2025-08-31", "2025-08-31T23:59:59", "20250831", "2025-W35-7", "2025-8-31", "nope", "", None, 20250831, "2025-13-01", "2025-02-30"):
        for year_end in ("2025-12-31", date(2025, 12, 31), "bad", None):
            rec.call("rest_of_year", {"periods": base, "floors": ga25, "as_of": as_of, "year_end": year_end})
    p0 = base[0]
    for mutate in (
        lambda p: {k: v for k, v in p.items() if k != "pay_period_start"},
        lambda p: {k: v for k, v in p.items() if k != "pay_period_end"},
        lambda p: {**p, "hours": None}, lambda p: {**p, "wages": None}, lambda p: {k: v for k, v in p.items() if k != "hours"},
        lambda p: {**p, "hours": "x"}, lambda p: {**p, "hours": "12"}, lambda p: {**p, "wages": -50.0}, lambda p: {**p, "hours": -5.0},
        lambda p: {**p, "pay_period_start": "garbage"}, lambda p: {**p, "pay_period_end": None},
        lambda p: {**p, "pay_period_end": date(2025, 1, 12), "pay_period_start": "2025-01-06"},
        lambda p: {**p, "pay_period_end": "2025-01-12T00:00:00", "pay_period_start": "2025-01-06T08:00:00"},
        lambda p: {**p, "pay_date": "2025-01-20"}, lambda p: {**p, "pay_date": "xx"}, lambda p: {**p, "pay_date": ""}, lambda p: {**p, "pay_date": None},
        lambda p: {**p, "pay_date": date(2025, 1, 19)}, lambda p: {**p, "pay_date": 7}, lambda p: {**p, "hours": INF}, lambda p: {**p, "hours": NAN}, lambda p: {**p, "wages": 1e308},
    ):
        rec.call("rest_of_year", {"periods": [mutate(p0)] + base[1:], "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
        rec.call("rest_of_year", {"periods": [mutate(p0)], "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31), "method": "pay_period"})
    # reversed / inverted / duplicated / unsorted periods; a one-day period; a negative-length period (loops until the date range ends)
    rec.call("rest_of_year", {"periods": list(reversed(base)), "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
    rec.call("rest_of_year", {"periods": base + base, "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
    shuffled = list(base)
    rng.shuffle(shuffled)
    rec.call("rest_of_year", {"periods": shuffled, "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31), "method": "pay_period"})
    rec.call("rest_of_year", {"periods": [{"pay_period_start": "2025-08-01", "pay_period_end": "2025-08-01", "hours": 8.0, "wages": 160.0}], "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
    rec.call("rest_of_year", {"periods": [{"pay_period_start": "2025-08-04", "pay_period_end": "2025-08-02", "hours": 8.0, "wages": 160.0}], "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
    rec.call("rest_of_year", {"periods": [{"pay_period_start": "2025-08-01", "pay_period_end": "2025-08-31", "hours": 160.0, "wages": 3200.0}], "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
    rec.call("rest_of_year", {"periods": [{"pay_period_start": "2025-08-01", "pay_period_end": "2025-08-31", "hours": 160.0, "wages": 3200.0}], "floors": ga25, "as_of": date(2025, 8, 30), "year_end": date(2025, 12, 31)})
    rec.call("rest_of_year", {"periods": [{"pay_period_start": "2025-08-01", "pay_period_end": "2025-08-14"}], "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
    # the real synthetic payroll, as the tests read it
    for periods in synthetic_periods():
        for as_of in (date(2025, 8, 31), date(2025, 5, 31), date(2025, 11, 30)):
            for method in ("min_max", "pay_period"):
                rec.call("rest_of_year", {"periods": periods, "floors": ga25, "as_of": as_of, "year_end": date(2025, 12, 31), "method": method})
        to_date = [p for p in periods if str(p.get("pay_date") or "")[:10] <= "2025-08-31"]
        rec.call("rest_of_year", {"periods": to_date, "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
        repaid = [{**p, "wages": float(p["hours"] or 0) * 15.0} for p in periods]
        rec.call("rest_of_year", {"periods": repaid, "floors": ga25, "as_of": date(2025, 8, 31), "year_end": date(2025, 12, 31)})
    # seeded random cadences
    for _ in range(700):
        days = rng.choice([7, 7, 14, 14, 15, 28, 30, 1, 10])
        n = rng.randint(1, 40)
        hours = rng.choice([0.0, 10.0, 24.5, 34.0, 36.0, 40.0, 70.0, 80.0, rng.uniform(1, 100)])
        wage = rng.choice([0.0, 7.25, 15.0, 18.17, 25.0, rng.uniform(5, 60)])
        lag = rng.choice([None, 0, 3, 5, 7, -2, 21])
        start = date(2025, 1, 1) + timedelta(days=rng.randint(-30, 120))
        periods = cadence(days, n, hours * days / 7, wage, start=start, lag=lag, as_date=rng.random() < 0.3)
        rec.call("rest_of_year", {"periods": periods, "floors": rng.choice(floors_list + synthetic_floors()[:3]), "as_of": date(2025, 1, 1) + timedelta(days=rng.randint(30, 400)),
                                  "year_end": rng.choice(year_ends), "method": rng.choice(["min_max", "pay_period"]), "decimals": rng.choice([2, 2, 2, 0, 1, 3])})


# ------------------------------------------------------------------------------------------------------ cohorts

BANDS = [5.0, 0.0, 1.0, 2.5, 5, 10.0, 20.0, 40.0, 100.0, -1.0, 0.5, INF, NAN, 1e-9]
LIMITS = [None, 0, 1, 2, 3, 10, -1, -3, 1000]
POPULATIONS = [
    None, {}, {"evaluated": 10080, "eligible": 539, "ineligible": 9541, "failure_modes": {"hours_only": 7000, "wages_only": 41, "both": 2500}},
    {"evaluated": 5, "eligible": 2, "ineligible": 3, "failure_modes": {}}, {"evaluated": 5.9, "eligible": 2.2, "ineligible": 3.7, "failure_modes": {"both": 1, "none": 2}},
    {"evaluated": 5, "eligible": 2, "ineligible": 3}, {"evaluated": 5, "eligible": 2, "failure_modes": {}}, {"eligible": 2},
    {"evaluated": None, "eligible": 2, "ineligible": 3, "failure_modes": {}}, {"evaluated": "7", "eligible": "2", "ineligible": "3", "failure_modes": {"b": 1, "a": 2}},
    {"evaluated": True, "eligible": False, "ineligible": 0, "failure_modes": {"z": 1, "a": 2, "m": 3}}, {"evaluated": 0, "eligible": 0, "ineligible": 0, "failure_modes": {}},
    {"evaluated": 3, "eligible": 1, "ineligible": 2, "failure_modes": None}, {"evaluated": NAN, "eligible": 1, "ineligible": 2, "failure_modes": {}},
    {"evaluated": 1e30, "eligible": 10 ** 30, "ineligible": -4, "failure_modes": {"hours_only": 1.5}},
]


def tie_rows() -> list[dict]:
    """Many employees with the same lever so only the id tie-break orders them."""
    rows = []
    for emp in ["b", "a", "B", "10", "9", 10, 9, "é", "e", None, "None", "\U0001F600", "\uffff", "aa", "a", ""]:
        rows.append(avg(emp, 1560, 39000))
    for emp in ["z", "y", "x", 3, 20]:
        rows.append(avg(emp, 2080, 31200))
    return rows


def cohort_inputs(rng: random.Random) -> list[list[dict]]:
    sets = [
        [avg("A", 2080, 52000), avg("B", 1560, 39000), avg("C", 2080, 31200), avg("D", 1560, 23400)],
        [avg("far", 1560, 23400), avg("near", 2080, 31200), avg("mid", 1560, 39000)],
        [avg("near", 2080, 31200), avg("far", 1560, 23400)],
        [avg(f"E{i}", 2080, 52000) for i in range(5)],
        [avg("a", 2080, 31200), avg("b", 1560, 39000), avg("c", 1560, 23400), avg("d", 1040, 12480)],
        [avg(f"E{i}", 1560, 23400) for i in range(50)],
        [avg("near", 1716, 42900)],
        [avg("roomy", 40 * 52, 900 * 52), avg("thin", 35.5 * 52, 700 * 52)],
        [dict(avg("a", 36 * 52, 700 * 52), weight=0.5), avg("b", 36 * 52, 700 * 52)],
        [avg("x", 20 * 52, 300 * 52)], [], tie_rows(), tie_rows()[::-1],
        [dict(avg(f"ok{i}", 1560, 23400), eligible=False) for i in range(3)] + [dict(avg("drifted", 2080, 52000), eligible=False)],
        [dict(avg("PT", 1300, 33800), eligible=True), avg("PT2", 1300, 33800)],
        [dict(avg(i, 1800 + i, 40000), eligible=rng.choice([True, False]), weight=rng.choice([0.5, 1.0, 0.75, 0, None])) for i in range(30)],
        [dict(avg("x", 2080, 52000), eligible=False), dict(avg("y", 2080, 52000), eligible=0)],
        edge_rows()[:200], verdict_variants(),
    ]
    for _ in range(60):
        sets.append(random_rows(rng, rng.randint(1, 80)))
    # fractional part-time weights: a band whose jobs sum with float noise
    for weights in ([0.1] * 10, [0.1, 0.2, 0.3], [0.5, 0.25, 0.125] * 4, [1.0, 0.1, 0.7, 0.2], [0.3333333333333333] * 7, [1e16, 1.0, -1e16], [0.1] * 3 + [1], [1, 0.1, 0.1]):
        sets.append([dict(avg(f"w{i}", 36 * 52, 700 * 52), weight=w) for i, w in enumerate(weights)])
    return sets


def cohort_scenarios(rec: Recorder, rng: random.Random, floors_list: list[StatutoryFloors]) -> None:
    ga23 = floors_list[1]
    sets = cohort_inputs(rng)
    for rows in sets:
        for floors in (ga23, floors_list[2], synthetic_floors()[0]):
            rec.call("near_miss_cohort", {"averages": rows, "floors": floors, "within_weekly_hours": 5.0})
            rec.call("near_miss_cohort", {"averages": rows, "floors": floors, "within_weekly_hours": 20.0})
            rec.call("fragile_cohort", {"averages": rows, "floors": floors, "within_weekly_hours": 5.0})
            rec.call("fragile_cohort", {"averages": rows, "floors": floors, "within_weekly_hours": 10.0})
            rec.call("band_curve", {"averages": rows, "floors": floors})
        rec.call("near_miss_cohort", {"averages": rows, "floors": ga23})
        rec.call("fragile_cohort", {"averages": rows, "floors": ga23})
    for _ in range(900):
        rows = rng.choice(sets)
        floors = rng.choice(floors_list + synthetic_floors())
        kwargs = {"within_weekly_hours": rng.choice(BANDS), "limit": rng.choice(LIMITS), "decimals": rng.choice([2, 2, 2, 0, 1, 3, 4, -1]), "population": rng.choice(POPULATIONS)}
        rec.call("near_miss_cohort", {"averages": rows, "floors": floors, **kwargs})
        rec.call("fragile_cohort", {"averages": rows, "floors": floors, **kwargs})
    for _ in range(150):
        rows = rng.choice(sets)
        bands = rng.choice([(1.0, 2.0, 5.0, 10.0), (0.0,), (), (5, 10), (10.0, 5.0), (INF,), (-1.0, 0.5), (1.5, 2.5, 100.0), (NAN, 5.0)])
        rec.call("band_curve", {"averages": rows, "floors": rng.choice(floors_list + synthetic_floors()), "bands": list(bands), "decimals": rng.choice([2, 0, 1, 3])})
    rec.call("band_curve", {"averages": [], "floors": ga23})
    rec.call("band_curve", {"averages": sets[1], "floors": ga23, "bands": []})


def single_scenarios(rec: Recorder, rng: random.Random, floors_list: list[StatutoryFloors]) -> None:
    rows = test_rows() + verdict_variants() + edge_rows() + random_rows(rng, 900)
    syn = synthetic_floors()
    for i, row in enumerate(rows):
        floors = floors_list[1] if i % 3 == 0 else floors_list[(i // 3) % len(floors_list)]
        rec.call("assess_employee", {"average": row, "floors": floors})
        rec.call("fragility", {"average": row, "floors": floors})
        if i % 4 == 0:
            rec.call("assess_employee", {"average": row, "floors": syn[i % len(syn)], "decimals": rng.choice([0, 1, 2, 3, 4, -1, -2])})
            rec.call("fragility", {"average": row, "floors": syn[(i + 1) % len(syn)], "decimals": rng.choice([0, 1, 2, 3, 4, -1])})
    rate_cases = [(0, 0), (0.0, 5000.0), (-1.0, 5.0), (1.0, 0.0), (10.0, 181.7), (1e-320, 1.0), (5e-324, 1e308), (INF, 1.0), (NAN, 1.0), (1.0, NAN), (35.0, 636.0), (3, 7)]
    for h, w in rate_cases:
        rec.call("_rate", {"total_hours": h, "total_wages": w})
    for h in (0, 1, 7.25, 100.5, 1e-9):
        for w in (0, 1, 636.0, 1e12, -3.0):
            rec.call("_rate", {"total_hours": h, "total_wages": w})


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    rec = Recorder()
    fl = real_floors()
    single_scenarios(rec, rng, fl)
    cohort_scenarios(rec, rng, fl)
    roy_scenarios(rec, rng, fl)
    meta = {"k": "meta", "seed": seed, "calls": len(rec.lines), "errors": rec.errors, "counts": rec.counts,
            "plausible_weekly_hours": prox.PLAUSIBLE_WEEKLY_HOURS, "band_curve_hours": list(prox.BAND_CURVE_HOURS), **oracle.stamp()}
    lines = [dumps(meta)]
    for text_in, rec_line in rec.lines:
        body = dumps(rec_line)
        lines.append(body[:-1] + ',"args":' + text_in + "}")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, compresslevel=9) as gz:
        gz.write(("\n".join(lines) + "\n").encode("ascii"))
    return buf.getvalue()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    data = build(args.seed)
    if args.check:
        ok = args.out.exists() and args.out.read_bytes() == data
        print("proximity golden is current" if ok else "STALE proximity golden", file=sys.stderr)
        return 0 if ok else 1
    args.out.write_bytes(data)
    print(f"wrote {args.out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
