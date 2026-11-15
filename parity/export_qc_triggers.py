"""Golden vectors for ``tools/qc.py`` and ``tools/triggers.py`` (stage DS7, ingestion family).

Every function of both modules is called over a scenario matrix: every input ``tests/test_ingestion.py`` (the scraggly line keys) and ``tests/test_triggers.py`` use,
the threshold boundaries on both sides (wages 49.99/50/50.01 against hours 3.99/4/4.01; a spike of 4/5/6 and 9/10/11 employees; a wage rise just under, exactly at and just over
the percentage), integer and float thresholds including 0, negative, NaN and infinity, every ``Tax_Year`` spelling ``int()`` accepts or refuses, every date spelling
``date.fromisoformat`` accepts or refuses, month and leap-day boundaries for the test of twos, duplicate pay lines, unicode and astral identifiers (code point ordering and
two-character state prefixes), cells of every type ``float()`` accepts or refuses, missing keys, and seeded random batches. Realistic inputs are the committed synthetic payroll
``backend/data/payroll_pay_periods.csv`` read as strings, exactly as ``PayPeriodCsvAdapter`` yields it; the first call (``_payroll``) carries those rows and later calls refer to a
selection of them with ``{"$payroll": {...}}`` (``year``, ``prefix``, ``max_employees``) inside a ``rows`` list that may also hold literal rows.

Set ordering: ``triggers`` builds sets of strings and sorts them before they are observable, and ``qc`` uses none, so the output must not depend on ``PYTHONHASHSEED``;
``--prove-hash-seeds`` (also run by ``--check``) rebuilds the whole golden in subprocesses under several seeds and requires identical bytes. A mixed ``None``/text FEIN set would sort
with an order-dependent ``TypeError`` message and is deliberately NOT generated (finding CQ-04).

Line format (JSONL, gzip, mtime 0), as ``golden_rec``; a call may carry ``"trail": {"title", "citation"}`` and then records ``{"result", "trail"}`` with the whole trail
(evidence hash included). A big list is ``{"$digest", "n"}``. Usage: python parity/export_qc_triggers.py [--check] [--prove-hash-seeds] [--out FILE] [--seed N]
"""
from __future__ import annotations

import csv
import hashlib
import os
import random
import subprocess
import sys
from pathlib import Path

os.environ["DATA_SOURCE"] = "csv"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import golden_rec as gr  # noqa: E402
from domain.calculation.trail import TrailRecorder, reset_recorder, set_recorder  # noqa: E402
from tools import qc  # noqa: E402
from tools import triggers as tr  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "qc_triggers.jsonl.gz"
SEED = 20261123
CSV_PATH = BACKEND / "data" / "payroll_pay_periods.csv"
INF, NAN = float("inf"), float("nan")
PAYROLL = list(csv.DictReader(CSV_PATH.open(newline="", encoding="utf-8")))
HASH_SEEDS = ("0", "1", "2", "7", "42", "4294967295", "random")


# ------------------------------------------------------------------------------------------------ tag resolution

def select(sel: dict) -> list[dict]:
    out = [r for r in PAYROLL if (not sel.get("prefix") or r["Worksite_ID"].startswith(sel["prefix"])) and (sel.get("year") is None or r["Tax_Year"] == sel["year"])]
    if sel.get("max_employees") is not None:
        keep: list = []
        for r in out:
            if r["Employee_ID"] not in keep:
                keep.append(r["Employee_ID"])
        keep = set(keep[: sel["max_employees"]])
        out = [r for r in out if r["Employee_ID"] in keep]
    return out


def rows_of(x):
    """A ``rows`` argument: literal rows and ``{"$payroll": selection}`` parts, flattened in order."""
    out: list = []
    for part in x:
        if isinstance(part, dict) and len(part) == 1 and "$payroll" in part:
            out.extend(select(part["$payroll"]))
        else:
            out.append(part)
    return out


def digest(items: list) -> dict:
    return {"$digest": hashlib.sha256(gr.dumps(items).encode("ascii")).hexdigest(), "n": len(items)}


def dispatch(fn: str, a: dict):
    kw = {k: a[k] for k in ("state", "min_wages", "min_hours", "headcount_spike_min", "wage_increase_min_pct") if k in a}
    if fn == "_payroll":
        return PAYROLL
    if fn == "pay_line_keys":
        keys = qc.pay_line_keys(rows_of(a["rows"]))
        return digest(keys) if a.get("digest") else keys
    if fn == "_line_content":
        return qc._line_content(a["row"])
    if fn == "_month_key":
        return qc._month_key(a["pay_date"])
    if fn == "_filter":
        return qc._filter(rows_of(a["rows"]), a["tax_year"], a.get("state"))
    if fn == "detect_test_of_twos":
        return qc.detect_test_of_twos(rows_of(a["rows"]), tax_year=a["tax_year"], **kw)
    if fn == "detect_scraggly_pay_periods":
        return qc.detect_scraggly_pay_periods(rows_of(a["rows"]), tax_year=a["tax_year"], **kw)
    if fn == "run_exception_report":
        return qc.run_exception_report(rows_of(a["rows"]), tax_year=a["tax_year"], **kw)
    if fn == "detect_triggers":
        return tr.detect_triggers(rows_of(a["prior_rows"]), rows_of(a["current_rows"]), **kw)
    raise KeyError(fn)


def run(fn: str, args: dict) -> dict:
    spec = args.get("trail")
    recorder = TrailRecorder(title=spec["title"], citation=spec["citation"]) if spec is not None else None
    token = set_recorder(recorder) if recorder is not None else None
    try:
        result = dispatch(fn, args)
    finally:
        if token is not None:
            reset_recorder(token)
    out = {"result": result}
    if recorder is not None:
        out["trail"] = recorder.to_dict()
    return out


class Rec(gr.Recorder):
    def call(self, fn: str, args: dict, run_unused=None) -> None:
        super().call(fn, args, lambda: run(fn, args))


def call(rec, fn, args):
    rec.call(fn, args)


# ------------------------------------------------------------------------------------------------ rows

def line(**over):
    """``test_ingestion._line``."""
    row = {"Employee_ID": "E1", "Worksite_ID": "GA_X", "Tax_Year": 2025, "Pay_Period_Start": "2025-03-01", "Pay_Period_End": "2025-03-07", "Pay_Date": "2025-03-10", "Pay_Code": "REG",
           "Hours_Worked": 40.0, "Gross_Wages": 800.0}
    row.update(over)
    return row


def trow(emp, unit, hours=40, wages=800, fein="FEIN_1"):
    """``test_triggers._row``."""
    return {"Tax_Year": 2025, "Employee_ID": emp, "Worksite_ID": unit, "Pay_Period_Start": "2025-01-01", "Pay_Period_End": "2025-01-07", "Pay_Date": "2025-01-12", "Hours_Worked": hours,
            "Gross_Wages": wages, "Entity_FEIN": fein, "Job_Title": "x", "Pay_Code": "Regular"}


DATES = ["2025-03-10", "2025-03-10T08:00:00", "20250310", "2025-W11-1", "2025-13-01", "2025-02-30", "2024-02-29", "2023-02-29", "", " ", "None", " 2025-03-10", "2025-3-10", "２０２５-03-10", "0001-01-01",
         "9999-12-31", "2025-03-10abc", "2025-01", None, 20250310, 20250310.0, "2025-03-10\n", "2025-12-31", "2026-01-01", "2024-12-31"]
NUMBERS = ["40", 40, 40.5, "", None, "0", 0, 0.0, "abc", " 12 ", "1e3", "nan", "inf", "-inf", "1_0", True, False, [], [1], {}, "٣٤", -0.0, -5, "-0.24", 1e308, 10**18, 2**70, 3.99, 4, 4.0, 4.01, 49.99, 50, 50.0, 50.01]
YEARS = ["2025", 2025, 2025.9, " 2025 ", "2025.0", None, "", "abc", True, NAN, INF, 2024, "2024", 0, "0", -1, 10**20, "٢٠٢٥"]
IDS = ["E1", "E2", "E10", "e1", "Éa", "日本", "\U0001f600", "\ufb01", 7, 7.5, True, None, "", " ", "E 1", "x|y", "E1\u0000"]


# ------------------------------------------------------------------------------------------------ qc scenarios

def key_scenarios(rec, rng):
    base, stray = line(), line(Gross_Wages=-0.24, Hours_Worked=0.0)
    call(rec, "pay_line_keys", {"rows": []})
    call(rec, "pay_line_keys", {"rows": [base]})
    call(rec, "pay_line_keys", {"rows": [base, stray, line(Pay_Code="BONUS")]})
    call(rec, "pay_line_keys", {"rows": [base, base]})
    call(rec, "pay_line_keys", {"rows": [base, base, stray, base, stray]})
    call(rec, "pay_line_keys", {"rows": [base, stray]})
    call(rec, "pay_line_keys", {"rows": [stray, base]})
    call(rec, "pay_line_keys", {"rows": [line(Employee_ID="102400664", Gross_Wages=-0.24, Hours_Worked=0.0)]})
    for field in ("Employee_ID", "Worksite_ID", "Tax_Year", "Pay_Code"):
        for value in IDS + [2025, "2025"]:
            call(rec, "_line_content", {"row": line(**{field: value})})
    for field in ("Pay_Period_Start", "Pay_Period_End", "Pay_Date"):
        for value in DATES:
            call(rec, "_line_content", {"row": line(**{field: value})})
    for field in ("Hours_Worked", "Gross_Wages"):
        for value in NUMBERS:
            call(rec, "_line_content", {"row": line(**{field: value})})
    for value in (0.00005, 0.00015, 0.00025, 1.00005, 123456789.123456789, 1e22, 1e-7, 2.5, 0.125, 0.0625):
        call(rec, "_line_content", {"row": line(Hours_Worked=value, Gross_Wages=value)})
    call(rec, "_line_content", {"row": {}})
    call(rec, "_line_content", {"row": {"Employee_ID": 0, "Worksite_ID": False, "Pay_Code": ""}})
    call(rec, "pay_line_keys", {"rows": [{"Employee_ID": "E1"}, {}]})
    for sel in ({"year": "2025"}, {"year": "2024", "prefix": "GA_"}, {"prefix": "TN_", "max_employees": 5}, {}):
        call(rec, "pay_line_keys", {"rows": [{"$payroll": sel}], "digest": True})
        call(rec, "pay_line_keys", {"rows": [{"$payroll": sel}, {"$payroll": sel}], "digest": True})
    for _ in range(60):
        call(rec, "pay_line_keys", {"rows": [random_line(rng) for _ in range(rng.randint(0, 8))]})


def random_line(rng):
    row = line(Employee_ID=rng.choice(["E1", "E2", 3, "é"]), Worksite_ID=rng.choice(["GA_X", "GA_Y", "TN_Z", "NC_W"]), Pay_Code=rng.choice(["REG", "BONUS", "", None]),
               Hours_Worked=rng.choice([40.0, 0.0, 3.99, 4.0, "12", None, 7.77]), Gross_Wages=rng.choice([800.0, -0.24, 49.99, 50.0, "100.5", None, 0, 1e-3]),
               Pay_Date=rng.choice(["2025-03-10", "2025-03-31", "2025-04-01", "2025-03-10T09:00", "2024-12-31"]), Tax_Year=rng.choice([2025, "2025", 2024]))
    if rng.random() < 0.08:
        del row[rng.choice(["Employee_ID", "Pay_Code", "Hours_Worked", "Gross_Wages", "Pay_Date", "Worksite_ID", "Tax_Year"])]
    return row


def helper_scenarios(rec):
    for value in DATES:
        call(rec, "_month_key", {"pay_date": value})
    for ty in YEARS:
        for state in (None, "GA"):
            call(rec, "_filter", {"rows": [line(Tax_Year=ty), line(Tax_Year=2025)], "tax_year": 2025, "state": state})
    call(rec, "_filter", {"rows": [{"Employee_ID": "E1"}], "tax_year": 0})
    call(rec, "_filter", {"rows": [{"Employee_ID": "E1"}], "tax_year": 2025})
    for state in (None, "", "GA", "ga", "Ga", "G", "GA_", "TN", "\u00df", "i", "\u0130", "NC", "ZZ"):
        rows = [line(Worksite_ID=w) for w in ("GA_X", "ga_x", "GA_", "GA", "TN_Y", "NC_Z", "G", "\u00dfA_1", "SSA_1", "i_1", "I_1", "", None, 5)]
        call(rec, "_filter", {"rows": [r for r in rows if r["Worksite_ID"] is not None and not isinstance(r["Worksite_ID"], int)], "tax_year": 2025, "state": state})
        call(rec, "_filter", {"rows": rows, "tax_year": 2025, "state": state})


def twos_rows():
    a = lambda emp, unit, date, w=100.0, h=10.0: line(Employee_ID=emp, Worksite_ID=unit, Pay_Date=date, Gross_Wages=w, Hours_Worked=h)  # noqa: E731
    yield "same-month-two-units", [a("E1", "GA_A", "2025-03-01"), a("E1", "GA_B", "2025-03-31")]
    yield "same-unit-twice", [a("E1", "GA_A", "2025-03-01"), a("E1", "GA_A", "2025-03-31")]
    yield "month-boundary", [a("E1", "GA_A", "2025-03-31"), a("E1", "GA_B", "2025-04-01")]
    yield "leap-day", [a("E1", "GA_A", "2024-02-29", ), a("E1", "GA_B", "2024-02-01")]
    yield "three-units", [a("E1", "GA_C", "2025-03-01", 0.1, 0.1), a("E1", "GA_A", "2025-03-02", 0.2, 0.2), a("E1", "GA_B", "2025-03-03", 0.3, 0.3), a("E1", "GA_A", "2025-03-04", 0.7, 0.7)]
    yield "sort-order", [a(e, u, "2025-03-05") for e in ("E10", "E2", "e1", "\u00c9a", "\U0001f600", "\ufb01", "E1") for u in ("GA_B", "GA_a", "GA_A")]
    yield "months-order", [a("E1", u, d) for d in ("2025-12-01", "2025-02-01", "2025-11-30") for u in ("GA_B", "GA_A")]
    yield "rounding", [a("E1", "GA_A", "2025-03-01", 2.675, 1.005), a("E1", "GA_A", "2025-03-02", 0.005, 0.015), a("E1", "GA_B", "2025-03-03", 1e15, 1e-9)]
    yield "no-pay-date", [{k: v for k, v in a("E1", "GA_A", "x").items() if k != "Pay_Date"}, a("E1", "GA_B", "1900-01-20")]
    yield "int-ids", [a(7, "GA_A", "2025-03-01"), a(7, "GA_B", "2025-03-02"), a("7", "GA_C", "2025-03-03")]
    yield "none-ids", [a(None, "GA_A", "2025-03-01"), a("None", "GA_B", "2025-03-02")]
    yield "other-year", [a("E1", "GA_A", "2025-03-01"), dict(a("E1", "GA_B", "2025-03-02"), Tax_Year=2024)]
    yield "nan-wages", [a("E1", "GA_A", "2025-03-01", NAN, 1.0), a("E1", "GA_B", "2025-03-02", 1.0, INF)]
    yield "empty", []
    yield "state-mix", [a("E1", "GA_A", "2025-03-01"), a("E1", "TN_A", "2025-03-02"), a("E2", "TN_A", "2025-03-02"), a("E2", "TN_B", "2025-03-03")]
    yield "bad-date", [a("E1", "GA_A", "not-a-date")]
    yield "bad-wages", [dict(a("E1", "GA_A", "2025-03-01"), Gross_Wages="abc")]
    yield "bad-hours", [dict(a("E1", "GA_A", "2025-03-01"), Hours_Worked=[1])]
    yield "none-pay-date", [a("E1", "GA_A", None)]


def twos_scenarios(rec, rng):
    for _, rows in twos_rows():
        for state in (None, "GA", "ga", "TN", ""):
            call(rec, "detect_test_of_twos", {"rows": rows, "tax_year": 2025, **({"state": state} if state is not None else {})})
        call(rec, "run_exception_report", {"rows": rows, "tax_year": 2025, "trail": {"title": "qc", "citation": "c"}})
    for sel in ({"year": "2025", "max_employees": 40}, {"year": "2024", "prefix": "GA_"}, {"year": "2025", "prefix": "TN_"}, {}):
        call(rec, "detect_test_of_twos", {"rows": [{"$payroll": sel}], "tax_year": 2025})
        call(rec, "detect_test_of_twos", {"rows": [{"$payroll": sel}, line(Employee_ID="E00001", Worksite_ID="NY_X", Tax_Year="2025", Pay_Date="2025-03-04")], "tax_year": 2025, "state": "NY"})
    # the same employee at two real units in a month
    extra = [{**PAYROLL[0], "Worksite_ID": "TX_OTHER", "Tax_Year": "2024"}, {**PAYROLL[1], "Worksite_ID": "TX_OTHER", "Tax_Year": "2024"}]
    call(rec, "detect_test_of_twos", {"rows": [{"$payroll": {"year": "2024", "max_employees": 3}}, *extra], "tax_year": 2024})
    call(rec, "detect_test_of_twos", {"rows": [{"$payroll": {"year": "2024", "max_employees": 3}}, *extra], "tax_year": 2024, "state": "tx"})
    for _ in range(80):
        rows = [random_line(rng) for _ in range(rng.randint(0, 12))]
        call(rec, "detect_test_of_twos", {"rows": rows, "tax_year": rng.choice([2025, 2024]), **({"state": rng.choice(["GA", "tn"])} if rng.random() < 0.4 else {})})


def scraggly_scenarios(rec, rng):
    wages = (49.99, 50.0, 50.01, 0.0, -0.24, -100, 1e-9, 0.005, 2.675)
    hours = (3.99, 4.0, 4.01, 0.0, -1.0, 0.005, 1.005)
    call(rec, "detect_scraggly_pay_periods", {"rows": [line(Gross_Wages=w, Hours_Worked=h) for w in wages for h in hours], "tax_year": 2025})
    call(rec, "detect_scraggly_pay_periods", {"rows": [line(Gross_Wages=w, Hours_Worked=h) for w in wages for h in hours], "tax_year": 2025, "min_wages": 50, "min_hours": 4})
    for mw in (0, -1, 50, 50.0, 100, NAN, INF, -INF, 1e308, 10**18, 2**62, 0.0, 50.01):
        for mh in (0, 4, 4.0, NAN, INF, 1e-9, -0.5):
            call(rec, "detect_scraggly_pay_periods", {"rows": [line(Gross_Wages=w, Hours_Worked=h) for w, h in ((49.99, 3.99), (50.0, 4.0), (-1.0, 0.0), (10.0, 100.0))], "tax_year": 2025, "min_wages": mw, "min_hours": mh})
    call(rec, "detect_scraggly_pay_periods", {"rows": [line(Gross_Wages=-0.24, Hours_Worked=0.0)] * 3 + [line(Gross_Wages=-0.24, Hours_Worked=0.0, Pay_Code="BONUS")], "tax_year": 2025, "state": "GA"})
    for ty in YEARS[:6]:
        call(rec, "detect_scraggly_pay_periods", {"rows": [line(Tax_Year=ty, Gross_Wages=1.0, Hours_Worked=1.0)], "tax_year": 2025})
    for value in NUMBERS:
        call(rec, "detect_scraggly_pay_periods", {"rows": [line(Gross_Wages=value, Hours_Worked=1.0)], "tax_year": 2025})
        call(rec, "detect_scraggly_pay_periods", {"rows": [line(Gross_Wages=1.0, Hours_Worked=value)], "tax_year": 2025})
    for value in DATES + IDS:
        call(rec, "detect_scraggly_pay_periods", {"rows": [line(Pay_Date=value, Pay_Period_Start=value, Pay_Period_End=value, Employee_ID=value, Worksite_ID=value, Gross_Wages=1.0, Hours_Worked=1.0)], "tax_year": 2025})
    call(rec, "detect_scraggly_pay_periods", {"rows": [{"Tax_Year": 2025, "Gross_Wages": 1.0}], "tax_year": 2025})
    call(rec, "detect_scraggly_pay_periods", {"rows": [{"Tax_Year": 2025}], "tax_year": 2025})
    for min_wages, min_hours in ((500, 40), (3000, 90), (2500.5, 80.5)):
        for sel in ({"year": "2025", "max_employees": 30}, {"year": "2024", "prefix": "GA_"}):
            call(rec, "detect_scraggly_pay_periods", {"rows": [{"$payroll": sel}], "tax_year": int(sel["year"]), "min_wages": min_wages, "min_hours": min_hours})
            call(rec, "detect_scraggly_pay_periods", {"rows": [{"$payroll": sel}], "tax_year": int(sel["year"]), "state": "GA", "min_wages": min_wages, "min_hours": min_hours})
    for _ in range(120):
        rows = [random_line(rng) for _ in range(rng.randint(0, 12))]
        call(rec, "detect_scraggly_pay_periods", {"rows": rows, "tax_year": rng.choice([2025, 2024]), "min_wages": rng.choice([50.0, 50, 100, 1.0]), "min_hours": rng.choice([4.0, 4, 10, 1.0])})


def report_scenarios(rec, rng):
    trail = {"title": "Exception report", "citation": "QC"}
    clean = [line()]
    dirty = [line(Gross_Wages=-0.24, Hours_Worked=0.0), line(Employee_ID="E2"), line(Employee_ID="E2", Worksite_ID="GA_Y")]
    for rows in ([], clean, dirty):
        for state in (None, "GA", "ga", "", "TN"):
            for extra in ({}, {"min_wages": 50, "min_hours": 4}, {"min_wages": 1000.5, "min_hours": 80}, {"min_wages": NAN}):
                args = {"rows": rows, "tax_year": 2025, **extra}
                if state is not None:
                    args["state"] = state
                call(rec, "run_exception_report", args)
                call(rec, "run_exception_report", {**args, "trail": trail})
    call(rec, "run_exception_report", {"rows": [line(Gross_Wages="abc")], "tax_year": 2025, "trail": trail})
    call(rec, "run_exception_report", {"rows": [line(Tax_Year=None)], "tax_year": 2025, "trail": trail})
    for sel in ({"year": "2025", "max_employees": 25}, {"year": "2024"}):
        call(rec, "run_exception_report", {"rows": [{"$payroll": sel}], "tax_year": int(sel["year"]), "min_wages": 2000, "min_hours": 80, "trail": trail})
        call(rec, "run_exception_report", {"rows": [{"$payroll": sel}], "tax_year": int(sel["year"]), "state": "GA"})
    for _ in range(60):
        rows = [random_line(rng) for _ in range(rng.randint(0, 10))]
        call(rec, "run_exception_report", {"rows": rows, "tax_year": 2025, "state": rng.choice(["GA", "tn", ""]), "min_wages": rng.choice([50.0, 50, 100]), "min_hours": rng.choice([4.0, 4, 20]), "trail": trail})


# ------------------------------------------------------------------------------------------------ trigger scenarios

def trigger_scenarios(rec, rng):
    emp = lambda n, unit="GA_ATL_HQ", **kw: [trow(f"E{i:03}", unit, **kw) for i in range(n)]  # noqa: E731
    call(rec, "detect_triggers", {"prior_rows": [], "current_rows": []})
    for prior_n, curr_n in ((3, 8), (3, 13), (3, 6), (0, 4), (0, 5), (0, 9), (0, 10), (0, 11), (5, 10), (10, 5), (3, 3), (3, 7), (3, 12)):
        for spike in (None, 2, 5, 5.0, 4.5, 5.5, 10, 0, -1, NAN, INF, 1e30, 3, 6):
            args = {"prior_rows": emp(prior_n), "current_rows": emp(curr_n)}
            if spike is not None:
                args["headcount_spike_min"] = spike
            call(rec, "detect_triggers", args)
    base = trow("E1", "GA_ATL_HQ", 40, 800)
    for wages, thr in ((880, None), (881, None), (879.99, None), (900, None), (840, None), (840, 0.03), (800, 0), (799, 0), (700, -0.5), (900, NAN), (900, INF), (1e308, None), (880, 0.1), (880, 0.1000001),
                       (880, 1), (1760, 1), (1759.99, 1), (840, 0.05), (840, 0.0500001), (822.5, 0.025)):
        args = {"prior_rows": [base], "current_rows": [trow("E1", "GA_ATL_HQ", 40, wages)]}
        if thr is not None:
            args["wage_increase_min_pct"] = thr
        call(rec, "detect_triggers", args)
    for ph, pw, ch, cw in ((0, 0, 40, 800), (40, 800, 0, 0), (40, 0, 40, 800), (40, -800, 40, 800), (40, 800, 40, -800), (0.0, 800, 40, 800), (3, 100.5, 7, 333.33), (0.001, 1e-3, 1e-3, 1.5e-3), (1e-320, 1.0, 1.0, 1.0),
                       (40, 800, 40, 800), (1e308, 1e308, 1.0, 1e308), (3.0, 7.0, 3.0, 9.0), (7, 70, 7, 77), (7, 70, 7, 76.99), (12.5, 100, 12.5, 112.5)):
        call(rec, "detect_triggers", {"prior_rows": [trow("E1", "GA_A", ph, pw)], "current_rows": [trow("E1", "GA_A", ch, cw)]})
    for value in NUMBERS:
        call(rec, "detect_triggers", {"prior_rows": [trow("E1", "GA_A", value, 800)], "current_rows": [trow("E1", "GA_A", 40, value)]})
        call(rec, "detect_triggers", {"prior_rows": [trow("E1", "GA_A", 40, 800)], "current_rows": [trow("E1", "GA_A", value, 900)]})
    for fein_prior, fein_curr in ((["F1"], ["F1", "F2"]), (["F1"], ["F1"]), (["F2"], ["F1", "F2", "F10", "f3", "\u00c9", "\U0001f600", "\ufb01"]), ([], ["F1"]), (["F1"], []), ([""], ["", "F1"]),
                                  (["F1"], [""]), ([], [""]), (["F1"], ["F1", "F1", "F2", "F2"]), (["\u00e9"], ["e", "E", "\u00e9", "\u00c9"]), (["a"], ["b", "B", "a", "A", "_", "~"])):
        prior = [trow(f"P{i}", "GA_A", fein=f) for i, f in enumerate(fein_prior)]
        current = [trow(f"C{i}", rng.choice(["GA_A", "TX_B", "NC_C"]), fein=f) for i, f in enumerate(fein_curr)]
        call(rec, "detect_triggers", {"prior_rows": prior, "current_rows": current})
    call(rec, "detect_triggers", {"prior_rows": [trow("E1", "GA_A", fein="F1")], "current_rows": [trow("E1", "GA_A", fein=None)]})
    call(rec, "detect_triggers", {"prior_rows": [trow("E1", "GA_A", fein=None)], "current_rows": [trow("E1", "GA_A", fein=None)]})
    call(rec, "detect_triggers", {"prior_rows": [], "current_rows": [{**trow("E1", "GA_A"), "Entity_FEIN": 7}]})
    call(rec, "detect_triggers", {"prior_rows": [], "current_rows": [{k: v for k, v in trow("E1", "GA_A").items() if k != "Entity_FEIN"}]})
    call(rec, "detect_triggers", {"prior_rows": [], "current_rows": [trow("E1", "", fein="F9"), trow("E2", "G", fein="F9")]})
    call(rec, "detect_triggers", {"prior_rows": [], "current_rows": [{k: v for k, v in trow("E1", "GA_A", fein="F9").items() if k != "Worksite_ID"}]})
    # the state hint of a new FEIN is the first of the sorted states over that FEIN's rows
    call(rec, "detect_triggers", {"prior_rows": [], "current_rows": [trow("E1", "TX_A", fein="F9"), trow("E2", "GA_B", fein="F9"), trow("E3", "NC_C", fein="F9"), trow("E4", "G", fein="F9")]})
    for prior_units, curr_units in ((["GA_A"], ["GA_A", "TX_B"]), (["GA_A", "TX_B"], ["GA_A"]), ([], ["Z"]), ([], ["ZZ"]), (["GA_A"], ["GB_A", "GA_Z"]), ([], ["\u65e5\u672c_A", "\U0001f600\U0001f601_B", "\u00c9a", "\u00e9a", "\ufb01x"]),
                                    (["GA_A"], ["", "X", "XY", "XYZ"]), (["A"], ["A"]), (["ga_a"], ["GA_A"])):
        call(rec, "detect_triggers", {"prior_rows": [trow(f"P{i}", u) for i, u in enumerate(prior_units)], "current_rows": [trow(f"C{i}", u) for i, u in enumerate(curr_units)]})
    # errors, in the order Python meets them
    good = [trow("E1", "GA_A")]
    call(rec, "detect_triggers", {"prior_rows": [{k: v for k, v in trow("E1", "GA_A").items() if k != "Employee_ID"}], "current_rows": []})
    call(rec, "detect_triggers", {"prior_rows": [], "current_rows": [{k: v for k, v in trow("E1", "GA_A").items() if k != "Employee_ID"}]})
    call(rec, "detect_triggers", {"prior_rows": [{**trow("E1", "GA_A"), "Worksite_ID": None}], "current_rows": good})
    call(rec, "detect_triggers", {"prior_rows": good, "current_rows": [{**trow("E1", "GA_A"), "Worksite_ID": 5}]})
    call(rec, "detect_triggers", {"prior_rows": good, "current_rows": [{**trow("E1", "GA_A"), "Worksite_ID": 5.5}]})
    call(rec, "detect_triggers", {"prior_rows": good, "current_rows": [{**trow("E1", "GA_A"), "Worksite_ID": True}]})
    call(rec, "detect_triggers", {"prior_rows": good, "current_rows": [{**trow("E1", "GA_A"), "Worksite_ID": 5, "Hours_Worked": "abc"}]})
    call(rec, "detect_triggers", {"prior_rows": good, "current_rows": [{**trow("E1", "GA_A"), "Worksite_ID": 5, "Employee_ID": None, "Gross_Wages": [1]}]})
    call(rec, "detect_triggers", {"prior_rows": [{"Employee_ID": "E1"}], "current_rows": [{"Employee_ID": "E1", "Worksite_ID": "GA_A"}]})
    for ids in ((1, 1.0, True), (1, "1"), ("a", "a"), (None, None), (None, "None")):
        call(rec, "detect_triggers", {"prior_rows": [], "current_rows": [trow(i, "GA_A") for i in ids]})
        call(rec, "detect_triggers", {"prior_rows": [trow("E0", "GA_A")], "current_rows": [trow(i, "GA_A") for i in ids * 4]})
        call(rec, "detect_triggers", {"prior_rows": [], "current_rows": [trow(i, "GA_A") for i in ids], "headcount_spike_min": 1})
    real_2024, real_2025 = {"$payroll": {"year": "2024"}}, {"$payroll": {"year": "2025"}}
    for prior, current in ((real_2024, real_2025), (real_2025, real_2024), (real_2024, real_2024)):
        for kw in ({}, {"headcount_spike_min": 1}, {"headcount_spike_min": 2, "wage_increase_min_pct": 0.001}, {"wage_increase_min_pct": -1}, {"headcount_spike_min": 50}):
            call(rec, "detect_triggers", {"prior_rows": [prior], "current_rows": [current], **kw})
    for prefix in ("GA_", "TN_", "NY_", "TX_", "CO_"):
        call(rec, "detect_triggers", {"prior_rows": [{"$payroll": {"year": "2024", "prefix": prefix}}], "current_rows": [{"$payroll": {"year": "2025"}}], "headcount_spike_min": 3})
    call(rec, "detect_triggers", {"prior_rows": [{"$payroll": {"year": "2024", "prefix": "GA_", "max_employees": 8}}], "current_rows": [{"$payroll": {"year": "2025", "max_employees": 60}}, trow("N1", "ZZ_NEW", fein="99-9999999")]})
    for _ in range(250):
        prior = [random_trow(rng) for _ in range(rng.randint(0, 12))]
        current = [random_trow(rng) for _ in range(rng.randint(0, 14))]
        args = {"prior_rows": prior, "current_rows": current}
        if rng.random() < 0.4:
            args["headcount_spike_min"] = rng.choice([1, 2, 3, 5, 2.5])
        if rng.random() < 0.4:
            args["wage_increase_min_pct"] = rng.choice([0.0, 0.01, 0.05, 0.1, 0.5])
        call(rec, "detect_triggers", args)


def random_trow(rng):
    return trow(rng.choice(["E1", "E2", "E3", "E4", "E5", "E6", "E7", 8, "é"]), rng.choice(["GA_A", "GA_B", "TN_C", "NC_D", "TX_E", "ZZ_F", "G", ""]), hours=rng.choice([0, 20, 40, 40.5, 12.25, "30", None]),
                wages=rng.choice([0, 400, 800, 880.5, 1000, "700", None, -5]), fein=rng.choice(["F1", "F2", "F3", "", "F4"]))


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    rec = Rec()
    call(rec, "_payroll", {})
    key_scenarios(rec, rng)
    helper_scenarios(rec)
    twos_scenarios(rec, rng)
    scraggly_scenarios(rec, rng)
    report_scenarios(rec, rng)
    trigger_scenarios(rec, rng)
    return gr.serialise(rec, {"payroll_rows": len(PAYROLL)}, seed, oracle.stamp())


def prove_hash_seeds(seed: int) -> int:
    """Rebuild the golden under several ``PYTHONHASHSEED`` values and require the same bytes (sets of text are hash-ordered)."""
    expected = hashlib.sha256(build(seed)).hexdigest()
    for hash_seed in HASH_SEEDS:
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        done = subprocess.run([sys.executable, __file__, "--digest", "--seed", str(seed)], env=env, capture_output=True, text=True, check=True)
        if done.stdout.strip() != expected:
            print(f"OUTPUT DEPENDS ON PYTHONHASHSEED={hash_seed}", file=sys.stderr)
            return 1
    print(f"identical under PYTHONHASHSEED in {HASH_SEEDS}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if "--digest" in sys.argv:
        print(hashlib.sha256(build(int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else SEED)).hexdigest())
        raise SystemExit(0)
    seed_arg = int(sys.argv[sys.argv.index("--seed") + 1]) if "--seed" in sys.argv else SEED
    proving = "--prove-hash-seeds" in sys.argv or "--check" in sys.argv
    if "--prove-hash-seeds" in sys.argv:
        sys.argv.remove("--prove-hash-seeds")
    status = prove_hash_seeds(seed_arg) if proving else 0
    raise SystemExit(status or gr.main("qc_triggers", DEFAULT_OUT, SEED, build))
