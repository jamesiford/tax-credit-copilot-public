"""Golden vectors for ``tools/gold_projection.py`` and ``tools/tokens.py`` (stage GP): the exact Gold rows the Warehouse stores.

Every call runs the PRODUCTION function over its inputs and records the arguments (``golden_rec.enc`` tags: ``$date``, ``$dt``, ``$dec``;
floats keep their ``repr``, non-finite as ``NaN``/``Infinity``) and either the output or the exception type and message.

A row is an ordered list of typed cells, ``["dec", "1.00"]``, ``["int", 5]``, ``["str", "x"]``, ``["date", iso]``, ``["dt", iso]``,
``["nan", "NaN"]`` for a Decimal NaN and ``["null"]``; ``["float", x]`` and ``["bool", b]`` exist only so a leak of either type would show.
The table's column tuple travels with its rows, so the replay compares names, order and types.

Scenarios: every input of ``test_gold_projection.py`` and the call sites of ``run_client_calculation.py``; the full cross product of the
``_dec`` / ``_day`` / ``_flag`` edge pools; each field of a payroll, totals, averages, matrix and summary row made missing, falsy or mistyped; seeded
random rows; ``record_token`` over unicode, big and absent ids (and a lone surrogate); ``calculation_id`` perturbing every input; ``utc_now`` over a
monkeypatched clock; and the engine pipeline (production ``run_min_max_method`` / ``run_pay_period_method`` over the committed synthetic payroll,
the spike's datasets and its seeded random runs) projected onto all five engine-grain tables, by reference to the spike's engine scenarios.

Usage: python parity/export_gold.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import hashlib
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import engine_io  # noqa: E402
import gold_cases as gc  # noqa: E402
import golden_rec as gr  # noqa: E402
import matrix  # noqa: E402
from application.open_year import open_year_reading  # noqa: E402
from domain.calculation import onezero as oz  # noqa: E402
from tools import baseyear  # noqa: E402
from tools import gold_projection as gp  # noqa: E402
from tools.tokens import record_token  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "gold.jsonl.gz"
SEED = 20261119
TABLES = {
    "employee_period_fact": gp.EMPLOYEE_PERIOD_FACT_COLUMNS,
    "employee_eligibility": gp.EMPLOYEE_ELIGIBILITY_COLUMNS,
    "onezero_matrix": gp.ONEZERO_MATRIX_COLUMNS,
    "run_method_summary": gp.RUN_METHOD_SUMMARY_COLUMNS,
    "unit_month_summary": gp.UNIT_MONTH_SUMMARY_COLUMNS,
    "unit_year_master": gp.UNIT_YEAR_MASTER_COLUMNS,
    "unit_credit_installment": gp.UNIT_CREDIT_INSTALLMENT_COLUMNS,
}
AT = datetime(2026, 3, 1, 9, 30, 15)


def cell(v) -> list:
    """The typed, JSON-able view of one cell (datetime before date: one subclasses the other)."""
    if v is None:
        return ["null"]
    if isinstance(v, bool):
        return ["bool", v]
    if isinstance(v, int):
        return ["int", v]
    if isinstance(v, D):
        return ["nan", str(v)] if v.is_nan() else ["dec", str(v)]
    if isinstance(v, str):
        return ["str", v]
    if isinstance(v, datetime):
        return ["dt", v.isoformat()]
    if isinstance(v, date):
        return ["date", v.isoformat()]
    return ["float", v]


def table_out(name: str, rows) -> dict:
    cols = TABLES[name]
    out = []
    for r in rows:
        if len(r) != len(cols):
            raise SystemExit(f"{name}: a row has {len(r)} cells for {len(cols)} columns")
        out.append([cell(v) for v in r])
    return {"table": name, "columns": list(cols), "rows": out}


def tree(x):
    """Dataclasses, namespaces and tagged scalars as plain trees for the argument record."""
    if isinstance(x, SimpleNamespace):
        return {k: tree(v) for k, v in vars(x).items()}
    if isinstance(x, (list, tuple)):
        return [tree(v) for v in x]
    return x


class Calls:
    """The recorder with the engine pipeline's digest helper."""

    def __init__(self) -> None:
        self.rec = gr.Recorder()

    def call(self, fn, args, run):
        self.rec.call(fn, args, run)

    def rows(self, fn, name, args, run):
        self.rec.call(fn, args, lambda: table_out(name, run()))


def rowset(name, rows_out) -> dict:
    cols = TABLES[name]
    return {"table": name, "columns": list(cols), "rows": [[cell(v) for v in r] for r in rows_out]}


# --------------------------------------------------------------------- scalar coercions and identity


def scalar_calls(c: Calls, rng: random.Random) -> None:
    for v in gc.dec_inputs(rng):
        for places in (2, 4):
            c.call("_dec", {"value": v, "places": places}, lambda v=v, p=places: cell(gp._dec(v, p)))
    for v in gc.day_inputs(rng):
        c.call("_day", {"value": v}, lambda v=v: cell(gp._day(v)))
    for v in gc.flag_inputs():
        c.call("_flag", {"value": v}, lambda v=v: cell(gp._flag(v)))
    for acct in gc.account_ids():
        for prog in ("GA_JTC", "", "ga\u00e9", "a\0b"):
            for year in (2023, 0, -1, 10**20):
                for emp in gc.employee_ids():
                    args = {"account_id": acct, "program_code": prog, "tax_year": year, "employee_id": emp}
                    c.call("record_token", args, lambda a=args: record_token(a["account_id"], a["program_code"], a["tax_year"], a["employee_id"]))


def utc_now_calls(c: Calls) -> None:
    class Fixed(datetime):
        fixed = None

        @classmethod
        def now(cls, tz=None):
            return cls.fixed

    instants = [
        datetime(2026, 3, 1, 9, 30, 15, 999999, tzinfo=timezone.utc), datetime(2026, 3, 1, 9, 30, 15, 0, tzinfo=timezone.utc),
        datetime(2024, 2, 29, 23, 59, 59, 500000, tzinfo=timezone.utc), datetime(2023, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc),
        datetime(1, 1, 1, 0, 0, 0, 1, tzinfo=timezone.utc), datetime(9999, 12, 31, 23, 59, 59, 999999, tzinfo=timezone.utc),
        datetime(2026, 11, 15, 12, 0, 0, 123456, tzinfo=timezone.utc),
    ]
    for inst in instants:
        def run(inst=inst):
            Fixed.fixed = inst
            saved, gp.datetime = gp.datetime, Fixed
            try:
                return cell(gp.utc_now())
            finally:
                gp.datetime = saved
        c.call("utc_now", {"now": inst}, run)


def payroll_row(**over) -> dict:
    base = {"Employee_ID": "E1", "Worksite_ID": "GA_1", "Entity_FEIN": "12-3456789", "Job_Title": "Cook", "Pay_Period_Start": "2023-01-01",
            "Pay_Period_End": "2023-01-14", "Pay_Date": "2023-01-20", "Pay_Frequency": "3", "Pay_Code": "Regular", "Hours_Worked": "68.58",
            "Gross_Wages": "1972.36"}
    base.update(over)
    return {k: v for k, v in base.items() if v is not ...}


def identity_calls(c: Calls, rng: random.Random) -> None:
    floors = {"minimum_average_weekly_hours": 35.0, "minimum_average_weekly_wages_usd": 636.0, "source": "rules/ga_jtc/2023.json"}
    base = dict(client_id=1001, program_code="GA_JTC", tax_year=2023, window_begin=date(2023, 1, 1), window_end=date(2023, 12, 31), floors=floors,
                assumption_ids=["GDS-STEP1-2026-08-25-v8"], rows=[payroll_row()])
    variants = [{}]
    for k, v in (("client_id", 1002), ("client_id", None), ("client_id", 10**25), ("program_code", "NC_JTEC"), ("program_code", ""), ("tax_year", 2024), ("tax_year", "2023"),
                 ("window_begin", date(2023, 1, 2)), ("window_begin", datetime(2023, 1, 1, 5, 6, 7)), ("window_begin", "2023-01-01"), ("window_begin", None),
                 ("window_end", date(2024, 2, 29)), ("window_end", datetime(2023, 12, 31, 1, 2, 3, 4, tzinfo=timezone.utc)), ("window_end", 20231231),
                 ("floors", {}), ("floors", {"source": None}), ("floors", {**floors, "minimum_average_weekly_wages_usd": 700.0}),
                 ("floors", {**floors, "minimum_average_weekly_hours": 35}), ("floors", {**floors, "minimum_average_weekly_hours": D("35.00")}),
                 ("floors", {**floors, "source": "r\u00e9gles"}), ("floors", {**floors, "minimum_average_weekly_hours": float("nan")}),
                 ("floors", {**floors, "minimum_average_weekly_hours": 1e16}), ("floors", {**floors, "minimum_average_weekly_hours": True}),
                 ("assumption_ids", []), ("assumption_ids", ["a", "b"]), ("assumption_ids", ["b", "a"]), ("assumption_ids", [7]), ("assumption_ids", ["a", None]),
                 ("assumption_ids", ["\ud800"]), ("assumption_ids", ["a\0b"]), ("rows", []), ("rows", [payroll_row(Gross_Wages="1972.37")]),
                 ("rows", [payroll_row(Gross_Wages=1972.36)]), ("rows", [payroll_row(Gross_Wages=D("1972.36"))]), ("rows", [payroll_row(Hours_Worked=0)]),
                 ("rows", [payroll_row(Hours_Worked=0.0)]), ("rows", [payroll_row(Hours_Worked=None)]), ("rows", [payroll_row(Hours_Worked="")]),
                 ("rows", [payroll_row(Hours_Worked=False)]), ("rows", [payroll_row(Hours_Worked=True)]), ("rows", [payroll_row(Hours_Worked=float("nan"))]),
                 ("rows", [payroll_row(Hours_Worked=float("inf"))]), ("rows", [payroll_row(Hours_Worked=1e22)]), ("rows", [payroll_row(Hours_Worked=D("0.00"))]),
                 ("rows", [payroll_row(Hours_Worked=D("-0.0"))]), ("rows", [payroll_row(Hours_Worked=D("1E+2"))]), ("rows", [payroll_row(Employee_ID="\u00e9")]),
                 ("rows", [payroll_row(Employee_ID="\ud800")]), ("rows", [payroll_row(Employee_ID=7)]), ("rows", [payroll_row(Employee_ID=None)]),
                 ("rows", [payroll_row(Pay_Date=date(2023, 1, 20))]), ("rows", [payroll_row(Pay_Date=datetime(2023, 1, 20, 1, 2, 3))]),
                 ("rows", [payroll_row(Pay_Date=datetime(2023, 1, 20, 1, 2, 3, 5))]), ("rows", [payroll_row(Worksite_ID=...)]),
                 ("rows", [payroll_row(Job_Title="not hashed"), payroll_row(Employee_ID="E2")]), ("rows", [payroll_row(), payroll_row()]),
                 ("rows", [payroll_row(Entity_FEIN=...), {}])):
        variants.append({k: v})
    for _ in range(60):
        n = rng.randint(0, 6)
        rows = [payroll_row(Employee_ID=rng.choice(gc.unicode_ids()), Hours_Worked=rng.choice([round(rng.uniform(0, 90), 2), f"{rng.uniform(0, 90):.2f}", None, 0]),
                            Gross_Wages=rng.choice([round(rng.uniform(0, 4000), 2), f"{rng.uniform(0, 4000):.2f}", "", 0.0]),
                            Pay_Code=rng.choice(["Regular", "Overtime", None, ""])) for _ in range(n)]
        variants.append({"rows": rows, "tax_year": rng.choice([2019, 2023, 2026]), "client_id": rng.choice([1001, 2000, 2003])})
    for v in variants:
        args = {**base, **v}
        c.call("calculation_id", args, lambda a=args: gp.calculation_id(**a))


# ------------------------------------------------------------------- employee-grain tables

PAYROLL_FIELDS = ["Worksite_ID", "Entity_FEIN", "Job_Title", "Pay_Frequency", "Pay_Code"]


def period_fact_calls(c: Calls, rng: random.Random) -> None:
    common = dict(client_id=1001, program_code="GA_JTC", tax_year=2023, run_id="R1")
    cases: list[list[dict]] = [[], [payroll_row()], [payroll_row(Gross_Wages=0.1 + 0.2)], [payroll_row(), payroll_row(Employee_ID="E2", Pay_Period_Start="2023-01-15")]]
    for v in gc.dec_inputs(rng)[:140]:
        cases.append([payroll_row(Hours_Worked=v)])
        cases.append([payroll_row(Gross_Wages=v)])
    for v in gc.day_inputs(rng)[:100]:
        for field in ("Pay_Period_Start", "Pay_Period_End", "Pay_Date"):
            cases.append([payroll_row(**{field: v})])
    for v in (None, "", 0, 0.0, False, True, "x", 5, 5.5, D("0"), D("2.50"), "  ", float("nan"), "\u00e9", "a\0b", "None"):
        for field in PAYROLL_FIELDS:
            cases.append([payroll_row(**{field: v})])
            cases.append([payroll_row(**{field: ...})])
        cases.append([payroll_row(Employee_ID=v)])
    for emp in gc.employee_ids():
        cases.append([payroll_row(Employee_ID=emp)])
    cases.append([payroll_row(Employee_ID=...)])
    cases.append([payroll_row(Pay_Period_Start="2023-01-14", Pay_Period_End="2023-01-01")])
    cases.append([payroll_row(Pay_Period_Start="2024-02-29", Pay_Period_End="2024-02-29")])
    cases.append([payroll_row(Pay_Period_Start="0001-01-01", Pay_Period_End="9999-12-31")])
    cases.append([payroll_row(Pay_Period_Start=date(2023, 12, 31), Pay_Period_End=datetime(2024, 1, 1, 12))])
    for _ in range(120):
        start = date(2019, 1, 1) + timedelta(days=rng.randint(0, 2800))
        n = rng.randint(1, 5)
        cases.append([payroll_row(Employee_ID=rng.choice(gc.unicode_ids() + ["E1"]), Pay_Period_Start=start.isoformat(),
                                  Pay_Period_End=(start + timedelta(days=rng.randint(0, 40))).isoformat(),
                                  Pay_Date=rng.choice([None, "", (start + timedelta(days=rng.randint(0, 60))).isoformat()]),
                                  Hours_Worked=rng.choice([f"{rng.uniform(0, 90):.2f}", round(rng.uniform(0, 90), rng.randint(0, 4)), None, ""]),
                                  Gross_Wages=rng.choice([f"{rng.uniform(0, 6000):.2f}", round(rng.uniform(0, 6000), rng.randint(0, 4)), None, ""]))
                      for _ in range(n)])
    for rows in cases:
        args = {"payroll": rows, **common}
        c.rows("employee_period_fact_rows", "employee_period_fact", args, lambda a=args: gp.employee_period_fact_rows(**a))
    for acct, prog, year in ((1002, "NC_JTEC", 2019), (2000, "", 2026)):
        a = {"payroll": [payroll_row()], "client_id": acct, "program_code": prog, "tax_year": year, "run_id": "R-\u00e9"}
        c.rows("employee_period_fact_rows", "employee_period_fact", a, lambda a=a: gp.employee_period_fact_rows(**a))


def average(emp="E1", **over) -> dict:
    base = {"Employee_ID": emp, "total_hours": 100, "total_wages": 5000, "first_start": "2023-01-01", "last_end": "2023-06-30", "days": 180,
            "weeks_worked": 26.0, "avg_weekly_hours": 38.5, "avg_weekly_wages": 700.0, "passed_hours": True, "passed_wages": True, "weight": 1.0, "eligible": True}
    base.update(over)
    return {k: v for k, v in base.items() if v is not ...}


def total(emp="E1", **over) -> dict:
    base = {"Employee_ID": emp, "total_hours": 100.5, "total_wages": 5000.25}
    base.update(over)
    return {k: v for k, v in base.items() if v is not ...}


def eligibility_calls(c: Calls, rng: random.Random) -> None:
    common = dict(client_id=1001, program_code="GA_JTC", tax_year=2023, method="min_max", run_id="R1")
    cases: list[tuple[list, list]] = [
        ([], []), ([total()], []), ([total()], [average()]), ([total("E1"), total("E2")], [average("E1")]),
        ([total("E1", total_hours=1, total_wages=2)], [{"Employee_ID": "E1", "eligible": True, "weight": 1.0}]),
        ([total()], [average(), average(eligible=False, weight=0.5)]), ([total()], [{}]), ([total()], [{"Employee_ID": "E1"}]),
        ([total()], [{"Employee_ID": "E1", "eligible": True}]), ([total(5)], [average("5")]), ([total(None)], [average("None")]),
        ([total("E1")], [average("E2")]), ([total("E\u00e9"), total("\u4e2d")], [average("E\u00e9"), average("\u4e2d")]),
        ([{"total_hours": 1}], []), ([total()], [{"total_hours": 1}]), ([{"Employee_ID": "E1"}], []),
    ]
    for v in gc.dec_inputs(rng)[:120]:
        for field in ("total_hours", "total_wages"):
            cases.append(([total(**{field: v})], []))
        for field in ("weeks_worked", "avg_weekly_hours", "avg_weekly_wages", "weight"):
            cases.append(([total()], [average(**{field: v})]))
    for v in gc.day_inputs(rng)[:60]:
        cases.append(([total()], [average(first_start=v)]))
        cases.append(([total()], [average(last_end=v)]))
    for v in (None, ..., 0, 1, 180, -3, 12.9, -12.9, 1e19, 3.0, float("nan"), float("inf"), -float("inf"), True, False, "12", " 12 ", "1_2", "12.5", "", "abc", D("12.9"), D("-12.9"),
              D("1E+3"), D("NaN"), D("Infinity"), 10**30, "\u0661\u0662"):
        cases.append(([total()], [average(days=v)]))
    for v in gc.flag_inputs() + [...]:
        cases.append(([total()], [average(eligible=v)]))
    for v in (None, ..., 0, 0.0, "", False, 0.5, 1, 1.0, 0.25, D("0.5"), D("0"), float("nan"), 3, "1"):
        cases.append(([total(total_hours=v, total_wages=v)], [average(weight=v)]))
    for method in ("pay_period", "", "m\u00e9thode"):
        cases.append(([total()], [average()]))
    for _ in range(120):
        n = rng.randint(1, 8)
        ids = [rng.choice(gc.unicode_ids() + [f"E{i}" for i in range(6)]) for _ in range(n)]
        totals = [total(i, total_hours=round(rng.uniform(0, 3000), rng.randint(0, 4)), total_wages=rng.choice([round(rng.uniform(0, 90000), 2), 0, None])) for i in ids]
        avgs = [average(i, weeks_worked=round(rng.uniform(1, 53), 2), avg_weekly_hours=round(rng.uniform(5, 50), 2), avg_weekly_wages=round(rng.uniform(100, 1500), 2),
                        days=rng.randint(1, 365), weight=rng.choice([1.0, 0.5, 0.0, 1.0]), eligible=rng.random() < 0.5)
                for i in ids if rng.random() < 0.8]
        cases.append((totals, avgs))
    for totals, avgs in cases:
        args = {"totals": totals, "averages": avgs, **common}
        c.rows("employee_eligibility_rows", "employee_eligibility", args, lambda a=args: gp.employee_eligibility_rows(**a))
    a = {"totals": [total()], "averages": [average()], "client_id": 2003, "program_code": "NC_JTEC", "tax_year": 2020, "method": "pay_period", "run_id": "R9"}
    c.rows("employee_eligibility_rows", "employee_eligibility", a, lambda a=a: gp.employee_eligibility_rows(**a))


def mrow(shape="mm", **over) -> dict:
    base = {"Employee_ID": "E1", "Worksite_ID": "GA_1", "Entity_FEIN": "58-1", "weight": 1.0, "months": [1.0] * 12}
    if shape == "mm":
        base.update({"first_pps": "2023-01-01", "last_ppe": "2023-12-31"})
    else:
        base.update({"Pay_Period_Start": "2023-03-01", "Pay_Period_End": "2023-03-14", "Pay_Date": "2023-03-20"})
    base.update(over)
    return {k: v for k, v in base.items() if v is not ...}


def matrix_calls(c: Calls, rng: random.Random) -> None:
    common = dict(client_id=1001, program_code="GA_JTC", tax_year=2023, method="min_max", run_id="R1")
    cases: list[list[dict]] = [[], [mrow()], [mrow("pp")], [mrow(), mrow("pp", Employee_ID="E2")], [mrow(first_pps=..., last_ppe=...)],
                               [mrow("pp", Pay_Period_Start=..., Pay_Period_End=...)], [mrow(first_pps="")], [mrow(first_pps=None, Pay_Period_Start="2023-02-01", Pay_Period_End="2023-02-28")],
                               [mrow(first_pps="2023-01-01", last_ppe=...)], [mrow(first_pps=..., last_ppe="2023-12-31")],
                               [mrow(first_pps="2023-01-01", last_ppe=None, Pay_Period_End="2023-05-05")], [mrow(Employee_ID="\u00e9\u4e2d", first_pps=...)],
                               [mrow(first_pps=..., last_ppe=..., Employee_ID="a'b")], [mrow(Employee_ID="\U0001f600", first_pps=...)]]
    for n in (0, 1, 2, 6, 11, 12, 13, 14, 20):
        cases.append([mrow(months=[round(rng.uniform(0, 1), 2) for _ in range(n)])])
    cases += [[mrow(months=None)], [mrow(months=...)], [mrow(months=[])], [mrow(months=[0] * 12)], [mrow(months=[1, 0, 1, 0.5, 0.25, 0.333, 0.005, 0.015, 0.025, 1e-9, 2, 3])]]
    for v in gc.dec_inputs(rng)[:130]:
        cases.append([mrow(months=[v] + [1.0] * 11)])
        cases.append([mrow(weight=v)])
    for v in gc.day_inputs(rng)[:70]:
        cases.append([mrow(first_pps=v)])
        cases.append([mrow("pp", Pay_Period_End=v)])
        cases.append([mrow(first_pps=..., last_ppe=..., Pay_Period_Start=v, Pay_Period_End="2023-01-31")])
    for v in (None, "", 0, False, True, "x", 5, 0.0, D("0"), "  "):
        cases.append([mrow(Worksite_ID=v)])
        cases.append([mrow(Entity_FEIN=v)])
        cases.append([mrow(Worksite_ID=...)])
    for _ in range(140):
        n = rng.randint(1, 6)
        start = date(2023, 1, 1) + timedelta(days=rng.randint(0, 200))
        cases.append([mrow(rng.choice(["mm", "pp"]), Employee_ID=rng.choice(gc.unicode_ids() + ["E1", "E2"]), Worksite_ID=rng.choice(["GA_1", "GA_\u00e9", "", None]),
                           Entity_FEIN=rng.choice(["58-1", "", None, "99-2"]), weight=rng.choice([1.0, 0.5, 0.0, 1.0]),
                           months=[rng.choice([0, 0.0, 1.0, 0.5, 1, 0.25]) for _ in range(rng.choice([12, 12, 12, 6, 13]))],
                           first_pps=start.isoformat(), last_ppe=(start + timedelta(days=rng.randint(0, 300))).isoformat())
                      for _ in range(n)])
    for rows in cases:
        args = {"matrix": rows, **common}
        c.rows("onezero_matrix_rows", "onezero_matrix", args, lambda a=args: gp.onezero_matrix_rows(**a))
    a = {"matrix": [mrow("pp")], "client_id": 2000, "program_code": "SC_JTC", "tax_year": 2021, "method": "pay_period", "run_id": "R7"}
    c.rows("onezero_matrix_rows", "onezero_matrix", a, lambda a=a: gp.onezero_matrix_rows(**a))


# ----------------------------------------------------------------------- summary-grain tables


def summary_row(ws="GA_1", **over) -> dict:
    base = {"Worksite_ID": ws, "month_totals": [10.0] * 6 + [0.0] * 6, "total": 60.0, "average_headcount": 5.0}
    base.update(over)
    return {k: v for k, v in base.items() if v is not ...}


def month_summary_calls(c: Calls, rng: random.Random) -> None:
    common = dict(client_id=1001, tax_year=2023, method="min_max", run_id="R1")
    cases: list[tuple[list, list]] = [([], []), ([], [3]), ([summary_row()], []), ([summary_row()], [10, 11]), ([summary_row()], [0]), ([summary_row(), summary_row("GA_2")], [11]),
                                      ([summary_row(month_totals=[10, 10, 10, 10, 10, 10, 0, 0, 0, 0, 0, 0], total=60.0)], [10, 11])]
    for n in (0, 1, 5, 11, 12, 13, 14):
        cases.append(([summary_row(month_totals=[round(rng.uniform(0, 30), 2) for _ in range(n)])], []))
    cases += [([summary_row(month_totals=None)], []), ([summary_row(month_totals=...)], []), ([summary_row(month_totals=[])], [])]
    for v in gc.dec_inputs(rng)[:130]:
        cases.append(([summary_row(month_totals=[v] + [1.0] * 11)], []))
        cases.append(([summary_row(total=v)], []))
        cases.append(([summary_row(average_headcount=v)], []))
    for v in gc.flag_inputs():
        cases.append(([summary_row(month_totals=[v] * 12)], []))
    for v in (None, "", 0, False, 7, 1.5, "\u00e9", D("0"), "a\0b"):
        cases.append(([summary_row(v)], []))
    cases.append(([summary_row(Worksite_ID=...)], []))
    for _ in range(120):
        n = rng.randint(1, 5)
        cases.append(([summary_row(rng.choice(["GA_1", "GA_\u00e9", "TN_2", "\u4e2d"]),
                                   month_totals=[rng.choice([0.0, 0, round(rng.uniform(0, 60), 2), round(rng.uniform(0, 60), 4)]) for _ in range(12)],
                                   total=round(rng.uniform(0, 400), 2), average_headcount=round(rng.uniform(0, 40), 2)) for _ in range(n)],
                      sorted(rng.sample(range(12), rng.randint(0, 4)))))
    for summary, unreach in cases:
        args = {"summary": summary, "unreachable": unreach, **common}
        c.rows("unit_month_summary_rows", "unit_month_summary", args, lambda a=args: gp.unit_month_summary_rows(**a))


def run_summary_calls(c: Calls, rng: random.Random) -> None:
    months = [date(2023, m, 28) for m in range(8, 13)] + [date(2024, m, 28) for m in range(1, 8)]
    flag = {"type": "multi_unit_double_count", "employee_id": "E1", "month_index": 3, "count": 2}
    base = dict(annual_average=494.25, n_eligible=656, n_totals=10236, n_matrix=40000, flags=[], months=months)
    cases = [base, {**base, "flags": [flag]}, {**base, "flags": [flag, flag, {"type": "over_53_weeks", "employee_id": "E2", "weeks": 54.5}]}, {**base, "flags": None},
             {**base, "flags": [{"employee_id": "E1"}]}, {**base, "flags": [{"type": None}]}, {**base, "flags": [{"type": "multi_unit_double_count "}]},
             {**base, "months": []}, {**base, "months": months[:1]}, {**base, "months": [datetime(2023, 8, 28, 1, 2, 3), date(2023, 9, 30)]},
             {**base, "months": [datetime(2023, 8, 28, 1, 2, 3, 500, tzinfo=timezone.utc)]}, {**base, "months": ["2023-08-28"]}, {**base, "months": [None]},
             {**base, "months": [20230828]}, {**base, "n_eligible": 0, "n_totals": 0, "n_matrix": 0}, {**base, "annual_average": None}]
    for v in gc.dec_inputs(rng)[:150]:
        cases.append({**base, "annual_average": v})
    for _ in range(40):
        cases.append({**base, "annual_average": round(rng.uniform(0, 900), rng.randint(0, 5)), "n_eligible": rng.randint(0, 900), "n_totals": rng.randint(0, 11000),
                      "flags": [dict(flag, month_index=i) for i in range(rng.randint(0, 4))] + [{"type": "over_53_weeks"}] * rng.randint(0, 2)})
    stamps = [AT, datetime(2026, 3, 1, 9, 30, 15, 123456), datetime(2026, 3, 1, 9, 30, 15, tzinfo=timezone.utc), datetime(2026, 3, 1, 9, 30, tzinfo=timezone(timedelta(hours=5, minutes=30)))]
    for i, spec in enumerate(cases):
        args = {"result": spec, "client_id": 1001, "program_code": "GA_JTC", "tax_year": 2023, "method": "min_max", "run_id": "R1", "unit_fein_rows": rng.choice([0, 101, 10**20]),
                "appended_at": stamps[i % len(stamps)]}

        def run(a=args):
            s = a["result"]
            res = SimpleNamespace(annual_average=s["annual_average"], eligible_employees=[0] * s["n_eligible"], total_hours_and_wages=[0] * s["n_totals"],
                                  employee_unit_matrix=[0] * s["n_matrix"], flags=s["flags"], months=s["months"])
            return table_out("run_method_summary", [gp.run_method_summary_row(res, **{k: v for k, v in a.items() if k != "result"})])
        c.call("run_method_summary_row", args, run)


# ------------------------------------------------------------------------- credit layer

KEY_BASE = dict(client_id=1001, worksite_id="GA_1", entity_fein="58-1234567", program_code="GA_JTC", method="min_max", tax_year=2024, base_year=2023,
                base_year_source="inferred", months_reachable=12, declined=False, decline_reason=None, threshold_source="rule_pack", status="qualified", tier="T1",
                designation="T1B40", tier_source="prototype", run_id="R1")


def stair(**over):
    base = dict(year=2024, average_headcount=52.5, base_average_headcount=40.0, net_new=12.5, threshold=2.0, qualified=True, eligible_jobs=12.5, high_water_mark=52.5,
                new_jobs_created=12.5, backfilled=False, annual_credit_usd=43750, per_job_usd=3500.0)
    base.update(over)
    return SimpleNamespace(**{k: v for k, v in base.items() if v is not ...})


def trend_ns(**over):
    ev = SimpleNamespace(creation_year=2024, jobs=12.5, per_job_usd=3500.0, tranche_years=5,
                         installments=[{"year": 2024, "jobs_maintained": 12.5, "credit_usd": 43750}, {"year": 2025, "jobs_maintained": 12.5, "credit_usd": 43750}])
    base = dict(base_average_headcount=40.0, per_job_usd=3500.0, tranche_years=5, base_year_overridden=False, high_water_mark_overridden=False, tranche_events=[ev])
    base.update(over)
    return SimpleNamespace(**base)


def master_call(c: Calls, key, stair_obj, trend_obj, unit_year, stamp=AT, series=False) -> None:
    args = {**key, "stair": tree(stair_obj), "trend": tree(trend_obj), "unit_year": unit_year, "appended_at": stamp}
    if series:
        args["series"] = True  # produced by the tranche engine over realistic headcounts: the DDL type check applies

    def run():
        return table_out("unit_year_master", [gp.unit_year_master_row(**key, stair=stair_obj, trend=trend_obj, unit_year=unit_year, appended_at=stamp)])
    c.call("unit_year_master_row", args, run)


def installment_call(c: Calls, trend_obj, years, stamp=AT, series=False) -> None:
    common = dict(client_id=1001, worksite_id="GA_1", program_code="GA_JTC", method="min_max", run_id="R1")
    args = {"trend": tree(trend_obj), "years_with_data": years, "appended_at": stamp, **common}
    if series:
        args["series"] = True
    c.call("unit_credit_installment_rows", args, lambda: table_out("unit_credit_installment", gp.unit_credit_installment_rows(trend_obj, years_with_data=years, appended_at=stamp, **common)))


def credit_edge_calls(c: Calls, rng: random.Random) -> None:
    unit_year = {"average_headcount": 52.5, "months_with_headcount": 12}
    master_call(c, KEY_BASE, stair(), trend_ns(), unit_year)
    master_call(c, KEY_BASE, None, trend_ns(), unit_year)
    master_call(c, KEY_BASE, stair(per_job_usd=...), trend_ns(), unit_year)
    master_call(c, KEY_BASE, stair(per_job_usd=0.0), trend_ns(per_job_usd=3500.5), unit_year)
    master_call(c, KEY_BASE, stair(per_job_usd=None), trend_ns(per_job_usd=None), unit_year)
    master_call(c, KEY_BASE, stair(), trend_ns(), {})
    for mwh in (None, 11, 12, 13, 0, -1, 11.999, 12.0, 12.0000001, True, False, "12", D("12"), D("11.5"), float("nan"), float("inf"), -float("inf"), 10**30):
        master_call(c, KEY_BASE, stair(), trend_ns(), {"average_headcount": 1.5, "months_with_headcount": mwh})
    for mr in (0, 1, 12, 13, -1):
        master_call(c, {**KEY_BASE, "months_reachable": mr}, stair(), trend_ns(), unit_year)
    for ah in (None, 0, 0.0, "", False, 52.5, "52.5", D("52.505"), 1e30):
        master_call(c, KEY_BASE, stair(), trend_ns(), {"average_headcount": ah, "months_with_headcount": 12})
    for ty, by in ((2023, 2023), (2022, 2023), (2024, 2023), (2023, 2022)):
        master_call(c, {**KEY_BASE, "tax_year": ty, "base_year": by}, stair(), trend_ns(), unit_year)
    for src in ("inferred", "override", "", "Override"):
        for bo in (False, True, 0, 1, None, "", "x"):
            master_call(c, {**KEY_BASE, "base_year_source": src}, stair(), trend_ns(base_year_overridden=bo, high_water_mark_overridden=bo), unit_year)
    for field in ("net_new", "threshold", "eligible_jobs", "new_jobs_created", "high_water_mark", "per_job_usd", "annual_credit_usd"):
        for v in gc.dec_inputs(rng)[:70]:
            master_call(c, KEY_BASE, stair(**{field: v}), trend_ns(), unit_year)
    for field in ("qualified", "backfilled"):
        for v in gc.flag_inputs():
            master_call(c, KEY_BASE, stair(**{field: v}), trend_ns(), unit_year)
    for field in ("base_average_headcount", "per_job_usd"):
        for v in gc.dec_inputs(rng)[:70]:
            master_call(c, KEY_BASE, stair(), trend_ns(**{field: v}), unit_year)
    for v in (5, 3, 1, 0, None, "5", 10**20):
        master_call(c, KEY_BASE, stair(), trend_ns(tranche_years=v), unit_year)
    for kv in ({"entity_fein": None}, {"declined": True, "decline_reason": "under half"}, {"status": "in_progress"}, {"tier": None, "designation": None, "tier_source": "unassigned"},
               {"worksite_id": "GA_\u00e9\u4e2d"}, {"client_id": 10**20}, {"program_code": ""}, {"threshold_source": "designation"}):
        master_call(c, {**KEY_BASE, **kv}, stair(), trend_ns(), unit_year)
    for stamp in (AT, datetime(2026, 3, 1, 9, 30, 15, 250000), datetime(2026, 3, 1, 9, 30, 15, tzinfo=timezone.utc)):
        master_call(c, KEY_BASE, stair(), trend_ns(), unit_year, stamp)
    ins = lambda y, j=1.0, u=3500: {"year": y, "jobs_maintained": j, "credit_usd": u}  # noqa: E731
    ev = lambda cy, jobs, rate, insts: SimpleNamespace(creation_year=cy, jobs=jobs, per_job_usd=rate, tranche_years=5, installments=insts)  # noqa: E731
    installment_call(c, trend_ns(tranche_events=[]), [2023])
    installment_call(c, trend_ns(), [])
    installment_call(c, trend_ns(), [2024])
    installment_call(c, trend_ns(), [2024, 2025, 2026])
    installment_call(c, trend_ns(tranche_events=[ev(2024, 3.0, 3500.0, []), ev(2025, 2.5, 4000.0, [ins(2025), ins(2026), ins(2027)])]), [2023, 2024, 2025])
    installment_call(c, trend_ns(tranche_events=[ev(2024, 3.0, 3500.0, [{"jobs_maintained": 1.0, "credit_usd": 1}])]), [2024])
    installment_call(c, trend_ns(tranche_events=[ev(2024, 3.0, 3500.0, [{"year": 2024, "credit_usd": 1}])]), [2024])
    installment_call(c, trend_ns(tranche_events=[ev(2024, 3.0, 3500.0, [{"year": 2024, "jobs_maintained": 1.0}])]), [2024])
    installment_call(c, trend_ns(tranche_events=[ev(2024, 3.0, 3500.0, [ins("2024"), ins(None)])]), [2024])
    for field, vals in (("jobs", gc.dec_inputs(rng)[:70]), ("per_job_usd", gc.dec_inputs(rng)[:70])):
        for v in vals:
            e = ev(2024, 3.0, 3500.0, [ins(2024), ins(2030)])
            setattr(e, field, v)
            installment_call(c, trend_ns(tranche_events=[e]), [2024])
    for v in gc.dec_inputs(rng)[:70]:
        installment_call(c, trend_ns(tranche_events=[ev(2024, 3.0, 3500.0, [ins(2024, v, v)])]), [2024])
    installment_call(c, trend_ns(tranche_events=[ev(2024, 1.5, 3500.0, [ins(2024)])]), [2024], datetime(2026, 3, 1, 9, 30, 15, 250000))


def credit_series_calls(c: Calls, rng: random.Random) -> None:
    """Realistic series: the production tranche engine over seeded headcounts, then every year projected, the last one sometimes open."""
    for i in range(70):
        base_year = rng.randint(2019, 2023)
        span = rng.randint(1, 6)
        years = list(range(base_year, base_year + span + 1))
        yearly = {y: round(rng.choice([rng.uniform(0, 80), rng.uniform(30, 50), 40.0, 40.005, 41.995]), 2) for y in years}
        per_job = rng.choice([3500, 3500.0, 4000.0, 1500.5, 0.0])
        by_year = {y: {"threshold": rng.choice([2.0, 5.0, 10.0]), "per_job_usd": rng.choice([3500.0, 4000.0, per_job])} for y in years} if rng.random() < 0.5 else None
        threshold = rng.choice([2.0, 5.0, 10.0, 0.5])
        trend = baseyear.compute_base_year_tranches(
            "GA", yearly, base_year=base_year, threshold=threshold, per_job_usd=per_job, tranche_years=rng.choice([5, 5, 3, 1]),
            base_average_override=rng.choice([None, None, 12.5]), high_water_mark_override=rng.choice([None, None, 30.0]), benefit_by_year=by_year)
        by = {y.year: y for y in trend.years}
        open_year = years[-1] if rng.random() < 0.3 and len(years) > 1 else None
        for y in years:
            reading = by.get(y)
            if y == open_year:
                reading = open_year_reading(yearly[y], trend, (by_year or {}).get(y, {}), threshold)
            unit_year = {"average_headcount": yearly[y], "months_with_headcount": rng.choice([12, 12, 11, 8]), "total": round(yearly[y] * 12, 2)}
            key = {**KEY_BASE, "tax_year": y, "base_year": rng.choice([base_year, base_year, base_year + 1]), "months_reachable": rng.choice([12, 12, 11]),
                   "base_year_source": rng.choice(["inferred", "override"]), "worksite_id": rng.choice(["GA_1", "GA_\u00e9", "TN_2"]),
                   "status": rng.choice(["qualified", "in_progress", "no_credit"]), "client_id": rng.choice([1001, 2000, 2003])}
            master_call(c, key, reading, trend, unit_year, series=True)
        installment_call(c, trend, [y for y in years if y != open_year], series=True)

# ------------------------------------------------------------------ the engine pipeline


def digest_of(rows_out: list) -> str:
    return hashlib.sha256(gr.dumps(rows_out).encode("ascii")).hexdigest()


def table_summary(name: str, rows, full: bool) -> dict:
    t = table_out(name, rows)
    return {"table": name, "columns": t["columns"], "n": len(t["rows"]), "digest": digest_of(t["rows"]), "rows": t["rows"] if full else None}


def pipeline_call(c: Calls, scenario: dict, rows: list[dict], full: bool) -> None:
    """One engine run projected onto the five engine-grain tables; the C# side runs ITS engine over the same request."""
    params = scenario["params"]
    try:
        result, _ = engine_io._run_method(scenario["op"], {"rows": rows, "params": params})
        unreachable = oz.unreachable_months(rows, result.months)
    except Exception:  # a scenario the engine rejects has no projection to compare
        return
    ctx = dict(client_id=1001, program_code="GA_JTC", tax_year=params["tax_year"], run_id="R-" + scenario["id"])
    method = scenario["op"]
    ref = {"id": scenario["id"], "op": method, "params": params}
    if scenario.get("dataset"):
        ref["dataset"] = scenario["dataset"]
    else:
        ref["rows"] = rows
    args = {"scenario": ref, "unreachable": unreachable, "appended_at": AT, "unit_fein_rows": len(result.summary), **ctx}

    def run():
        tables = {
            "employee_period_fact": table_summary("employee_period_fact", gp.employee_period_fact_rows(rows, **ctx), full),
            "employee_eligibility": table_summary("employee_eligibility", gp.employee_eligibility_rows(
                totals=result.total_hours_and_wages, averages=result.all_averages, method=method, **ctx), full),
            "onezero_matrix": table_summary("onezero_matrix", gp.onezero_matrix_rows(result.employee_unit_matrix, method=method, **ctx), full),
            "unit_month_summary": table_summary("unit_month_summary", gp.unit_month_summary_rows(
                result.summary, client_id=1001, tax_year=params["tax_year"], method=method, run_id=ctx["run_id"], unreachable=unreachable), full),
            "run_method_summary": table_summary("run_method_summary", [gp.run_method_summary_row(
                result, method=method, unit_fein_rows=len(result.summary), appended_at=AT, **ctx)], True),
        }
        return {"tables": tables}
    c.call("pipeline", args, run)


def pipeline_calls(c: Calls, rng: random.Random) -> None:
    datasets, scenarios = matrix.build()
    runs = [s for s in scenarios if s["op"] in ("min_max", "pay_period")]
    picked: list[tuple[dict, list[dict], bool]] = []
    seen: dict[str, int] = {}
    for s in runs:
        name = s.get("dataset") or "inline"
        seen[name] = seen.get(name, 0) + 1
        k = seen[name]
        if name == "csv":
            keep = k % 6 == 1
        elif name.startswith("csv"):
            keep = k % 8 == 1 or name in ("csv_typed", "csv_blanks", "csv_state_cells", "csv_shifted")
        elif name == "inline":
            keep = k % 4 == 1
        else:
            keep = k % 3 == 1
        if keep:
            picked.append((s, datasets[s["dataset"]] if s.get("dataset") else s["rows"], name != "csv" and not name.startswith("csv")))
    for s, rows, full in picked:
        pipeline_call(c, s, rows, full)


def columns_call(c: Calls) -> None:
    c.call("columns", {}, lambda: {name: list(cols) for name, cols in TABLES.items()})


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    c = Calls()
    columns_call(c)
    scalar_calls(c, rng)
    utc_now_calls(c)
    identity_calls(c, rng)
    period_fact_calls(c, rng)
    eligibility_calls(c, rng)
    matrix_calls(c, rng)
    month_summary_calls(c, rng)
    run_summary_calls(c, rng)
    credit_edge_calls(c, rng)
    credit_series_calls(c, rng)
    pipeline_calls(c, rng)
    meta = {"columns": {name: list(cols) for name, cols in TABLES.items()}}
    print(f"{len(c.rec.lines)} calls, {c.rec.errors} errors: {c.rec.counts}", file=sys.stderr)
    return gr.serialise(c.rec, meta, seed, oracle.stamp())


if __name__ == "__main__":
    raise SystemExit(gr.main("gold", DEFAULT_OUT, SEED, build))