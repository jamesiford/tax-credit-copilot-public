"""Golden vectors for ``tools/forecast.py`` and ``tools/simulation.py`` (stage DS6, forecast and what-if family).

Every public and private function of both modules is called over a scenario matrix: every input the Python tests use
(``test_forecast.py``, ``test_simulation.py``, ``test_simulate_unit.py``, ``test_capabilities_equivalence.py``) plus as-of dates
at every month end, year end and leap day, empty summaries, zero/negative/huge/non-finite values, hourly rates and hours either
side of each floor, unknown cities, every state and program code, mixed-type payroll cells, and seeded random batches. Realistic
inputs run the PRODUCTION engine over the committed synthetic payroll ``backend/data/payroll_pay_periods.csv``.

``portfolio.chat_state_credit`` (and ``latest_tax_year``) are called too: the simulator imports them, and their only I/O is the
payroll read, which the port models as ``IPayPeriodSource``. The payroll itself is the first call line (``fn`` ``_payroll``), so
the C# replay serves the same rows to that port.

Line format (JSONL, gzip, mtime 0), as ``golden_rec``: ``{"k":"call","id":n,"fn":name,"out":tree,"args":{...}}`` or
``{"k":"call",...,"err":"TypeName","msg":str(exception)}``. Every ``out`` is ``{"result": tree}`` plus ``"trail"`` (the whole
``TrailRecorder.to_dict()``, evidence hash included) when the arguments carry ``"trail": {"title", "citation"}``. Tagged values:
``{"$date"}``, ``{"$payroll": selection}`` (rows of the synthetic payroll), ``{"$pack": {"key", "tax_year"}}`` (a production pack)
and ``{"$pack_spec": dict}`` (a hand-built pack, ``engine_io.build_pack``). Row sets are projected to the ten columns the port
models plus ``Job_Title``, in that order.

Usage: python parity/export_forecast.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ["DATA_SOURCE"] = "csv"  # the committed synthetic payroll, exactly as tests/conftest.py pins it
sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import engine_io  # noqa: E402
import golden_rec as gr  # noqa: E402
from domain.calculation.onezero import fiscal_year_of  # noqa: E402
from domain.calculation.trail import TrailRecorder, reset_recorder, set_recorder  # noqa: E402
from infrastructure.payroll.pay_period_source import load_pay_periods  # noqa: E402
from tools import forecast as fc  # noqa: E402
from tools import portfolio as pf  # noqa: E402
from tools import program_credit as pc  # noqa: E402
from tools import simulation as sim  # noqa: E402
from tools.credit_math import STATE_TO_PACK, load_pack_one_zero  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "forecast.jsonl.gz"
SEED = 20261120
INF = float("inf")
NAN = float("nan")
KEYS = engine_io.KNOWN + ["Job_Title"]
STATES = sorted(STATE_TO_PACK)


def proj(row: dict) -> dict:
    return {k: row[k] for k in KEYS if k in row}


PAYROLL = [proj(r) for r in load_pay_periods(None)]
LOWER_TABLE: list = []


# ------------------------------------------------------------------------------------------------ tag resolution

def select(sel: dict) -> list[dict]:
    """Rows of the synthetic payroll: ``prefix`` on Worksite_ID, ``fy`` (+``fy_end``) on Pay_Date, first ``max_employees`` ids."""
    out = []
    for r in PAYROLL:
        if sel.get("prefix") and not r["Worksite_ID"].startswith(sel["prefix"]):
            continue
        if sel.get("fy") is not None and fiscal_year_of(date.fromisoformat(r["Pay_Date"][:10]), sel.get("fy_end", 12)) != sel["fy"]:
            continue
        out.append(r)
    if sel.get("max_employees") is not None:
        keep: list = []
        for r in out:
            if r["Employee_ID"] not in keep:
                keep.append(r["Employee_ID"])
        keep = set(keep[: sel["max_employees"]])
        out = [r for r in out if r["Employee_ID"] in keep]
    return out


def resolve(x):
    if isinstance(x, dict) and len(x) == 1 and "$payroll" in x:
        return select(x["$payroll"])
    if isinstance(x, dict) and len(x) == 1 and "$pack" in x:
        return load_pack_one_zero(x["$pack"]["key"], tax_year=x["$pack"]["tax_year"])
    if isinstance(x, dict) and len(x) == 1 and "$pack_spec" in x:
        return engine_io.build_pack(x["$pack_spec"])
    if isinstance(x, dict):
        return {k: resolve(v) for k, v in x.items()}
    if isinstance(x, list):
        return [resolve(v) for v in x]
    return x


def rows_digest(rows: list[dict]) -> dict:
    text = gr.dumps(rows)
    return {"$digest": hashlib.sha256(text.encode("ascii")).hexdigest(), "n": len(rows)}


# ------------------------------------------------------------------------------------------------ dispatch

def dispatch(fn: str, a: dict):
    if fn == "_months_elapsed":
        return fc._months_elapsed(a["analysis_start"], a["as_of"])
    if fn == "_ytd_average_headcount":
        return fc._ytd_average_headcount(a["summary"], a["months_elapsed"])
    if fn == "project_state_year_end":
        extra = {k: a[k] for k in ("fiscal_year_end_month", "months_elapsed", "ytd_average_headcount", "prior_average_headcount") if k in a}
        return fc.project_state_year_end(a["state"], a["tax_year"], a["rows"], a["prior_rows"], as_of=a["as_of"], **extra)
    if fn == "_resolve_location":
        return list(sim._resolve_location(a["city_or_state"]))
    if fn == "simulate_hiring":
        return sim.simulate_hiring(a["location"], a["new_hires"])
    if fn == "chat_state_credit":
        return pf.chat_state_credit(a["state"], **{k: a[k] for k in ("tax_year", "fy_end_month", "current_average", "prior_average", "program_code") if k in a})
    if fn == "latest_tax_year":
        return pf.latest_tax_year(a["fy_end_month"])
    if fn == "onezero_snapshot":
        extra = {"prior_average_headcount": a["prior_average_headcount"]} if "prior_average_headcount" in a else {}
        return sim.onezero_snapshot(a["rows"], tax_year=a["tax_year"], state=a["state"], pack=a["pack"], **extra)
    if fn == "describe_role":
        return sim.describe_role(a["weekly_hours"], a["hourly_rate"], a["pack"])
    if fn == "apply_onezero_lever":
        kw = {k: a[k] for k in ("fein", "hire_weekly_hours", "hire_hourly_rate") if k in a}
        rows, detail = sim.apply_onezero_lever(a["rows"], action=a["action"], magnitude=a["magnitude"], pack=a["pack"], state=a["state"], **kw)
        return {"rows": rows_digest(rows) if a.get("digest") else rows, "detail": detail}
    if fn == "str.lower":
        return a["s"].lower()
    if fn == "str.lower.table":
        return LOWER_TABLE[0]
    if fn == "_payroll":
        return PAYROLL
    raise KeyError(fn)


@contextlib.contextmanager
def wage_spy(args: dict):
    """Records every ``avg_program_wage`` lookup (a percentage-of-wages program reads ``data/payroll.csv``) into ``args['wage_calls']``."""
    seen: list = []
    original = pc.avg_program_wage

    def spy(key):
        value = original(key)
        seen.append([key, value])
        return value

    pc.avg_program_wage = spy
    try:
        yield
    finally:
        pc.avg_program_wage = original
        if seen:
            args["wage_calls"] = seen


def run(fn: str, args: dict) -> dict:
    spec = args.get("trail")
    recorder = TrailRecorder(title=spec["title"], citation=spec["citation"]) if spec is not None else None
    token = set_recorder(recorder) if recorder is not None else None
    try:
        with wage_spy(args):
            result = dispatch(fn, resolve(args))
    finally:
        if token is not None:
            reset_recorder(token)
    out = {"result": result}
    if recorder is not None:
        out["trail"] = recorder.to_dict()
    return out


class Rec(gr.Recorder):
    """``golden_rec.Recorder`` whose arguments are encoded AFTER the run (the run adds the wage lookups it observed)."""

    def call(self, fn: str, args: dict, run_unused=None) -> None:
        try:
            rec = {"k": "call", "id": len(self.lines), "fn": fn, "out": gr.enc(run(fn, args))}
        except Exception as e:  # the exception type and message are part of the contract
            self.errors += 1
            rec = {"k": "call", "id": len(self.lines), "fn": fn, "err": type(e).__name__, "msg": str(e)}
        self.counts[fn] = self.counts.get(fn, 0) + 1
        self.lines.append((gr.dumps(gr.enc(args)), rec))


def call(rec: gr.Recorder, fn: str, args: dict) -> None:
    rec.call(fn, args)


# ------------------------------------------------------------------------------------------------ rows

def prow(emp, start, end, hours, wages, site="GA_ATL", pay_date=None, **extra):
    r = {"Employee_ID": emp, "Worksite_ID": site, "Entity_FEIN": "58-1111111", "Pay_Period_Start": start, "Pay_Period_End": end,
         "Pay_Date": pay_date or end, "Hours_Worked": hours, "Gross_Wages": wages, "Pay_Code": "Regular"}
    r.update(extra)
    return proj(r)


def tn_greenfield(n: int = 30) -> list[dict]:
    """``test_forecast._tn_greenfield_rows``: monthly periods covering each month end, no prior year."""
    rows = []
    for i in range(n):
        for m in range(1, 13):
            pps = date(2025, m, 1)
            ppe = (date(2025, m + 1, 1) - timedelta(days=1)) if m < 12 else date(2025, 12, 31)
            rows.append(prow(f"TNE{i:03d}", pps.isoformat(), ppe.isoformat(), 172.0, 4300.0, site="TN_NASH_HQ", Job_Title="HQ Staff"))
    return rows


def test_lever_rows() -> list[dict]:
    """``test_simulate_unit``'s one-row set plus small variants over every cell type."""
    base = prow("E1", "2025-01-01", "2025-01-14", 80.0, 2000.0, site="GA_GA-016")
    sets = [[base], [], [base, prow("E2", "2025-01-01", "2025-01-14", 20.0, 300.0)],
            [prow(e, "2025-01-01", "2025-01-14", h, w) for e, h, w in (("A", 80.0, 2000.0), ("B", 60.0, 1500.0), ("C", 80.0, 2000.0), ("D", 10.0, 90.0))]]
    for hours, wages in ((80, 2000), ("80", "2000.5"), (None, 100.0), ("", 5.0), ("abc", 1.0), (" 12 ", "1_0"), ("inf", "-inf"), ("nan", 1.0), (0, 0), (-5.5, -10), (1e300, 1e300)):
        try:
            sets.append([prow("X", "2025-02-01", "2025-02-14", hours, wages)])
        except Exception:  # pragma: no cover - construction never raises
            raise
    for start, end in (("2025-01-14", "2025-01-01"), ("2025-01-01", "2025-01-01"), ("2024-02-28", "2024-03-01"), ("2025-01-01T00:00", "2025-01-14T12:00"),
                       ("bad", "2025-01-14"), ("2025-01-01", "bad"), (None, "2025-01-14"), ("2025-01-01", None), ("20250101", "20250114")):
        sets.append([prow("D", start, end, 40.0, 800.0)])
    broken = prow("M", "2025-01-01", "2025-01-14", 40.0, 800.0)
    for key in ("Employee_ID", "Pay_Period_Start", "Pay_Period_End", "Hours_Worked", "Gross_Wages"):
        sets.append([{k: v for k, v in broken.items() if k != key}, prow("N", "2025-01-01", "2025-01-14", 40.0, 800.0)])
    sets.append([prow(None, "2025-01-01", "2025-01-14", 40.0, 800.0), prow("Z", "2025-01-01", "2025-01-14", 41.0, 800.0), prow(None, "2025-01-15", "2025-01-28", 10.0, 100.0)])
    sets.append([prow(e, "2025-01-01", "2025-01-14", 40.0, 800.0) for e in "ABCDE"])  # all ties
    return sets


def random_rows(rng: random.Random, n_emp: int) -> list[dict]:
    rows = []
    for e in range(n_emp):
        for p in range(rng.randint(1, 6)):
            start = date(2025, 1, 1) + timedelta(days=14 * p + rng.randint(0, 3))
            end = start + timedelta(days=rng.choice([6, 13, 13, 14, 27, 0, -1]))
            hours = rng.choice([0.0, 10.0, 34.99, 35.0, 80.0, rng.uniform(0, 120), 72.82, 1e-9])
            wages = rng.choice([0.0, 100.0, 636.0, 2000.0, rng.uniform(0, 5000), 2061.19])
            rows.append(prow(f"R{rng.randint(0, max(1, n_emp - 1))}", start.isoformat(), end.isoformat(), hours, wages, site=rng.choice(["GA_ATL", "GA_SAV", "TN_NASH"])))
    return rows


# ------------------------------------------------------------------------------------------------ scenarios

def month_ends(start: date) -> list[date]:
    out, y, m = [], start.year, start.month
    for _ in range(12):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        out.append(date(ny, nm, 1) - timedelta(days=1))
        y, m = ny, nm
    return out


def trail(title: str = "") -> dict:
    return {"title": title, "citation": ""}


def months_scenarios(rec, rng):
    starts = [date(2023, 1, 1), date(2025, 1, 1), date(2024, 1, 1), date(2024, 2, 1), date(2023, 8, 1), date(2023, 7, 28), date(2024, 12, 1), date(2025, 7, 31),
              date(2020, 2, 29), date(1, 1, 1), date(9998, 1, 1), date(9999, 12, 1), date(2023, 12, 31), date(2024, 11, 15)]
    for start in starts:
        probes = {start}
        for off in (-400, -1, 1, 400, 1000):
            try:
                probes.add(start + timedelta(days=off))
            except OverflowError:
                pass
        try:
            for me in month_ends(start):
                probes.update({me - timedelta(days=1), me, me + timedelta(days=1)})
        except (ValueError, OverflowError):
            pass
        for d in (date(2024, 2, 29), date(2023, 2, 28), date(2023, 12, 31), date(2024, 12, 31), date(2025, 8, 31)):
            probes.add(d)
        for as_of in sorted(p for p in probes if date.min <= p <= date.max):
            call(rec, "_months_elapsed", {"analysis_start": start, "as_of": as_of})
    for _ in range(300):
        start = date(2018, 1, 1) + timedelta(days=rng.randint(0, 3000))
        call(rec, "_months_elapsed", {"analysis_start": start, "as_of": start + timedelta(days=rng.randint(-60, 500))})


def ytd_scenarios(rec, rng):
    def unit(vals):
        return {"worksite_id": "U", "month_totals": vals}

    fixed = [[], [unit([])], [unit([1.5] * 12)], [unit([float(i) for i in range(12)])], [unit(list(range(12)))], [unit([0.1] * 12), unit([0.2] * 12)],
             [unit([1e16, 1.0, -1e16] + [0.0] * 9)], [unit([1, 2.5, 3, 4.25] + [0] * 8)], [unit([NAN] + [1.0] * 11)], [unit([INF] + [1.0] * 11)],
             [unit([1.0] * 3)], [unit([1.0] * 12), unit([2.0] * 4)], [unit([488.38 / 12] * 12)], [unit([5e-324] * 12)], [unit([1e308] * 12)]]
    for summary in fixed:
        for n in (-3, -1, 0, 1, 2, 3, 8, 11, 12, 13, 24, 1000):
            call(rec, "_ytd_average_headcount", {"summary": summary, "months_elapsed": n})
    for _ in range(500):
        summary = [unit([rng.choice([rng.uniform(0, 100), round(rng.uniform(0, 100), 2), float(rng.randint(0, 50)), rng.randint(0, 50), 0.0, 1e-9, 0.1])
                         for _ in range(rng.choice([12, 12, 12, 6, 3, 0, 13]))]) for _ in range(rng.randint(0, 9))]
        call(rec, "_ytd_average_headcount", {"summary": summary, "months_elapsed": rng.randint(-1, 14)})


def project_scenarios(rec, rng):
    # test_forecast: supplied averages bypass the payroll; the denominator travels with the average.
    call(rec, "project_state_year_end", {"state": "GA", "tax_year": 2023, "rows": [], "prior_rows": [], "as_of": date(2024, 3, 31), "ytd_average_headcount": 410.13, "prior_average_headcount": 375.53})
    call(rec, "project_state_year_end", {"state": "GA", "tax_year": 2023, "rows": [], "prior_rows": [], "as_of": date(2024, 3, 31), "months_elapsed": 8, "ytd_average_headcount": 488.38, "prior_average_headcount": 0.0})
    for t in (None, trail("Pending")):
        a = {"state": "TN", "tax_year": 2025, "rows": tn_greenfield(), "prior_rows": [], "as_of": date(2025, 12, 31)}
        call(rec, "project_state_year_end", {**a, **({"trail": t} if t else {})})
    call(rec, "project_state_year_end", {"state": "TN", "tax_year": 2025, "rows": tn_greenfield(), "prior_rows": [], "as_of": date(2025, 8, 31), "fiscal_year_end_month": 12})
    keys = STATES + ["ga", "Ga", "GA_JTC", "TX", "ZZ", "", "tn", "SC", "sc_jobs"]
    for key in keys:
        for year in (2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027):
            for as_of in (date(year, 3, 31), date(year, 12, 31)):
                call(rec, "project_state_year_end", {"state": key, "tax_year": year, "rows": [], "prior_rows": [], "as_of": as_of, "months_elapsed": 5, "ytd_average_headcount": 41.5, "prior_average_headcount": 30.25, **({"trail": trail()} if year % 2 else {})})
    for key in ("GA", "TN", "SC", "NC"):
        for ytd in (0.0, 1.0, 2.0, 5.0, 10.5, 24.99, 25.0, 25.01, 30, 100, -4.0, NAN, INF, -INF, 1e-9, 1e300, 12.345, 12.355, 0.005, 0.015):
            for prior in (None, 0.0, 10.0, 40.0, 22.5, 0.0049, -3.0, 7, NAN):
                kw = {"ytd_average_headcount": ytd}
                if prior is not None:
                    kw["prior_average_headcount"] = prior
                call(rec, "project_state_year_end", {"state": key, "tax_year": 2025, "rows": [], "prior_rows": [], "as_of": date(2025, 6, 30), "months_elapsed": 6, **kw, **({"trail": trail("t")} if ytd == 25.0 else {})})
    # threshold edge: finish line against the run-rate with the 1e-9 tolerance
    for gap in (-1e-8, -1e-9, -2e-9, 0.0, 1e-9, 5e-10, 2e-9, 1e-8, 0.01):
        call(rec, "project_state_year_end", {"state": "GA", "tax_year": 2025, "rows": [], "prior_rows": [], "as_of": date(2025, 6, 30), "months_elapsed": 6, "ytd_average_headcount": 42.0 + gap, "prior_average_headcount": 40.0})
    for months in (-2, 0, 1, 12, 13, 99):
        call(rec, "project_state_year_end", {"state": "GA", "tax_year": 2025, "rows": {"$payroll": {"prefix": "GA_", "fy": 2025, "max_employees": 12}}, "prior_rows": [], "as_of": date(2025, 6, 30), "months_elapsed": months})
    # as_of drives months_elapsed when it is not supplied (calendar and shifted fiscal years)
    for fy_end in (12, 6, 7, 9, 1, 2):
        for as_of in (date(2025, 1, 31), date(2025, 2, 28), date(2024, 12, 31), date(2025, 8, 31), date(2026, 1, 1), date(2024, 2, 29), date(2020, 1, 1)):
            call(rec, "project_state_year_end", {"state": "GA", "tax_year": 2025, "rows": [], "prior_rows": [], "as_of": as_of, "fiscal_year_end_month": fy_end, "ytd_average_headcount": 50.0, "prior_average_headcount": 44.0, "trail": trail()})
    # replay over the synthetic payroll: current rows unfiltered by state (a Python quirk), prior rows filtered by Worksite_ID prefix
    for key in ("TN", "SC", "NC", "CO", "FL", "OH", "VA", "NY", "TX"):
        for as_of in (date(2025, 3, 31), date(2025, 8, 31), date(2025, 12, 31)):
            call(rec, "project_state_year_end", {"state": key, "tax_year": 2025, "rows": {"$payroll": {"prefix": key + "_", "fy": 2025}}, "prior_rows": {"$payroll": {"fy": 2024}}, "as_of": as_of,
                                                 **({"trail": trail("Pending")} if as_of.month == 8 else {})})
    call(rec, "project_state_year_end", {"state": "GA", "tax_year": 2025, "rows": {"$payroll": {"prefix": "GA_", "fy": 2025}}, "prior_rows": {"$payroll": {"prefix": "GA_", "fy": 2024}}, "as_of": date(2025, 8, 31), "trail": trail()})
    call(rec, "project_state_year_end", {"state": "GA", "tax_year": 2025, "rows": {"$payroll": {"fy": 2025}}, "prior_rows": {"$payroll": {"fy": 2024}}, "as_of": date(2025, 8, 31)})
    call(rec, "project_state_year_end", {"state": "GA", "tax_year": 2026, "rows": {"$payroll": {"prefix": "GA_", "fy": 2026}}, "prior_rows": {"$payroll": {"prefix": "GA_", "fy": 2025}}, "as_of": date(2026, 8, 31)})
    call(rec, "project_state_year_end", {"state": "TN", "tax_year": 2025, "rows": {"$payroll": {"prefix": "TN_", "fy": 2025}}, "prior_rows": [{"Employee_ID": "E", "Pay_Period_Start": "2024-01-01"}], "as_of": date(2025, 8, 31)})
    call(rec, "project_state_year_end", {"state": "TN", "tax_year": 2025, "rows": [], "prior_rows": [{"Employee_ID": "E", "Pay_Period_Start": "2024-01-01"}], "as_of": date(2025, 8, 31), "ytd_average_headcount": 3.0})
    call(rec, "project_state_year_end", {"state": "TN", "tax_year": 2025, "rows": [], "prior_rows": [{"Employee_ID": "E", "Worksite_ID": None}], "as_of": date(2025, 8, 31), "ytd_average_headcount": 3.0})
    call(rec, "project_state_year_end", {"state": "TN", "tax_year": 2025, "rows": [], "prior_rows": [], "as_of": date(2025, 8, 31)})
    call(rec, "project_state_year_end", {"state": "TN", "tax_year": 2025, "rows": [], "prior_rows": [], "as_of": date(2025, 8, 31), "prior_average_headcount": 3})
    call(rec, "project_state_year_end", {"state": "TN", "tax_year": 0, "rows": [], "prior_rows": [], "as_of": date(2025, 8, 31), "ytd_average_headcount": 3.0})
    call(rec, "project_state_year_end", {"state": "TN", "tax_year": 2025, "rows": [], "prior_rows": [], "as_of": date(2025, 8, 31), "ytd_average_headcount": 3.0, "fiscal_year_end_month": 13})
    for _ in range(300):
        key = rng.choice(keys)
        year = rng.choice([2019, 2022, 2023, 2024, 2025, 2026])
        a = {"state": key, "tax_year": year, "rows": [], "prior_rows": [], "as_of": date(year, 1, 1) + timedelta(days=rng.randint(-40, 420)),
             "fiscal_year_end_month": rng.choice([12, 12, 6, 7, 9, 3]),
             "ytd_average_headcount": rng.choice([rng.uniform(0, 120), round(rng.uniform(0, 120), 2), float(rng.randint(0, 100)), rng.randint(0, 100)])}
        if rng.random() < 0.8:
            a["prior_average_headcount"] = rng.choice([rng.uniform(0, 100), round(rng.uniform(0, 100), 2), 0.0, 40.0])
        if rng.random() < 0.5:
            a["months_elapsed"] = rng.randint(1, 12)
        if rng.random() < 0.4:
            a["trail"] = trail(rng.choice(["", "Pending", "x"]))
        call(rec, "project_state_year_end", a)


def location_scenarios(rec, rng):
    texts = list(sim._CITY_MAP) + [c.title() for c in sim._CITY_MAP] + [c.upper() for c in sim._CITY_MAP] + [f"  {c} \t" for c in sim._CITY_MAP]
    texts += ["Atlanta", "ATLANTA", "  Atlanta  ", "ga", "Ga", "GA", "ny", "xx", "tx", "1a", "!!", "a", "", " ", "\n\t", "Mars", "Tampa", "new  york", "New York City", "tysons corner", "Tysons Corner",
              "\u00a0atlanta\u00a0", "\u2003ga\u2003", "\u0130", "\u0130\u0130", "i\u0307", "\u0130a", "\u03a3", "\u0391\u03a3", "\u0391\u03a3 ", "\u03a3\u0391", "\u0391\u03a3\u0391", "\u0391.\u03a3",
              "ss", "\u00df", "\u00dfa", "\u00dfss", "\ufb01", "\u01c5", "\u01c4a", "\U0001f600", "\U0001f600\U0001f600", "a\U0001f600", "\u212a", "\u212ab", "K", "\u00c5", "\u1e9e", "\u1e9ea", "\u0149", "\u1f88"]
    for t in texts:
        call(rec, "_resolve_location", {"city_or_state": t})
    call(rec, "_resolve_location", {"city_or_state": None})
    for _ in range(300):
        alphabet = "aAbBzZ \t\u00dfi\u0130\u0131\u03a3\u03c3\u212a\U0001f600.'1-"
        call(rec, "_resolve_location", {"city_or_state": "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 4)))})
    # str.lower: every code point whose lower() differs from itself, and the context rules of final sigma
    table = [[cp, [ord(c) for c in chr(cp).lower()]] for cp in range(0x110000) if not 0xD800 <= cp <= 0xDFFF and chr(cp).lower() != chr(cp)]
    LOWER_TABLE.append(table)
    call(rec, "str.lower.table", {})
    for s in ["\u03a3", "a\u03a3", "a\u03a3b", "a\u03a3 ", "a\u03a3.", "a.\u03a3", "a.\u03a3.b", "a\u03a3\u0301", "\u0391\u03a3\u03a3", "\u03a3\u03a3", " \u03a3", "a \u03a3", "a'\u03a3", "a\u00ad\u03a3", "\u0391\u03a3\u00b7\u0391", "1\u03a3", "\u03a31",
              "\u0391\u03a3\u0301\u0391", "A\u2019\u03a3", "\u0391\u03a3\u02b0", "\u0130\u03a3", "\U0001d400\u03a3", "\u0391\u03a3\u1d00"]:
        call(rec, "str.lower", {"s": s})


def hiring_scenarios(rec, rng):
    cities = list(sim._CITY_MAP) + ["Mars", "Tampa", "CO", "ny", "tx", "TX", "", "ga", "Nashville", "Houston", "atlanta"]
    for city in cities:
        for hires in (25, -25, 1, -1, 10, -10, 500, -500, 1000, -1000, 3, 100):
            call(rec, "simulate_hiring", {"location": city, "new_hires": hires})
    for city in ("Atlanta", "Nashville", "Houston", "Charlotte", "Mars", "ny", "Denver"):
        for hires in (25, -25, 7, -500, 0):
            call(rec, "simulate_hiring", {"location": city, "new_hires": hires, "trail": trail(rng.choice(["", "Pending", "x"]))})
    for loc in ("Atlanta", "Houston"):
        call(rec, "simulate_hiring", {"location": loc, "new_hires": 0})
    call(rec, "simulate_hiring", {"location": None, "new_hires": 5})
    call(rec, "simulate_hiring", {"location": None, "new_hires": -5, "trail": trail()})
    for state in STATES + ["TX", "ga", "ZZ", ""]:
        for opts in ({}, {"tax_year": 2024}, {"tax_year": 2025}, {"tax_year": 2023}, {"tax_year": 2026}, {"tax_year": 2025, "fy_end_month": 6}, {"tax_year": 2025, "fy_end_month": 9},
                     {"current_average": 61.0, "prior_average": 40.0}, {"current_average": 61, "prior_average": None}, {"current_average": 12.5}, {"current_average": 61.0, "prior_average": 0.0, "program_code": "GA_JTC"},
                     {"tax_year": 2025, "program_code": "SC_JOBS"}, {"current_average": 61.0, "prior_average": 40.0, "tax_year": 2025, "program_code": "TN_JTC"}):
            if state in ("GA", "TN", "") or opts.get("current_average") is not None or state in ("TX", "ZZ") or rng.random() < 0.35:
                call(rec, "chat_state_credit", {"state": state, **opts, **({"trail": trail("Pending")} if opts.get("tax_year") == 2025 else {})})
    for fy_end in range(1, 13):
        call(rec, "latest_tax_year", {"fy_end_month": fy_end})


# ------------------------------------------------------------------------------------------------ snapshot, role, lever

def pack_specs() -> list[dict]:
    base = {"min_weekly_hours": 35.0, "min_weekly_wages": 636.0}
    return [base, {"min_weekly_hours": 35, "min_weekly_wages": 636}, {"min_weekly_hours": 32.5, "min_weekly_wages": 700.25}, {"min_weekly_hours": 32.0, "min_weekly_wages": 0.0, "pt_band_hours": [20.0, 32.0], "pt_weight": 0.5},
            {"min_weekly_hours": 0, "min_weekly_wages": 0}, {"min_weekly_hours": 20.0, "min_weekly_wages": 636.5}, {"min_weekly_hours": 1e6, "min_weekly_wages": 1234567.891},
            {"min_weekly_hours": 0.00001, "min_weekly_wages": 0.5}, {"min_weekly_hours": 123456.7, "min_weekly_wages": 1500.5}, {"min_weekly_hours": 1234567.0, "min_weekly_wages": 1e15},
            {"min_weekly_hours": 35.0, "min_weekly_wages": 680.0, "included_pay_codes": ["Regular"], "citation": "demo"}, {"min_weekly_hours": 37.5, "min_weekly_wages": 600.0, "pt_band_hours": [20, 37.5], "pt_weight": 0.5}]


def role_scenarios(rec, rng):
    packs = [{"$pack_spec": s} for s in pack_specs()] + [{"$pack": {"key": k, "tax_year": 2025}} for k in STATES]
    hours = [None, 0, 0.0, 10, 20, 31.99, 32, 34.99, 35, 35.0, 35.01, 37.49, 37.5, 40, 80.5, -1.0, 1e-9, 1e6, 1234567.0, NAN, INF, -INF]
    rates = [None, 0, 0.0, 7.25, 12, 15.0, 18.17, 18.171, 18.1714, 20, 25.0, 100, 1e-9, -3.0, NAN, INF, 1e300]
    for pack in packs:
        for h in hours:
            for r in rates:
                if rng.random() < 0.18 or (h in (35, 35.0, 34.99, 35.01) and r in (None, 18.17, 18.171, 18.1714, 20)):
                    call(rec, "describe_role", {"weekly_hours": h, "hourly_rate": r, "pack": pack})
    for pack in packs[:4]:
        for h in (35.0, 34.99, 35.01):
            floor = 636.0 / h
            for r in (floor, floor * (1 - 1e-12), floor * (1 + 1e-12), 636 / 35.0, 18.17, 18.1714286):
                call(rec, "describe_role", {"weekly_hours": h, "hourly_rate": r, "pack": pack})


def snapshot_scenarios(rec, rng):
    call(rec, "onezero_snapshot", {"rows": [prow("E1", "2025-01-01", "2025-01-14", 80.0, 2000.0, site="GA_GA-016")], "tax_year": 2025, "state": "GA", "pack": {"$pack": {"key": "GA", "tax_year": 2025}}})
    for tr in (None, trail("Pending")):
        for prior in (None, 0.0, 10.0, 12.5, 7, 0.005, 29.995, NAN):
            kw = {} if prior is None else {"prior_average_headcount": prior}
            call(rec, "onezero_snapshot", {"rows": tn_greenfield(), "tax_year": 2025, "state": "TN", "pack": {"$pack": {"key": "TN", "tax_year": 2025}}, **kw, **({"trail": tr} if tr else {})})
    for key in STATES:
        for year, fy in ((2025, 2025), (2024, 2024), (2025, 2024), (2026, 2026)):
            for prior in (None, 40.0, 5):
                if key != "GA" or prior is not None or year == fy:
                    kw = {} if prior is None else {"prior_average_headcount": prior}
                    call(rec, "onezero_snapshot", {"rows": {"$payroll": {"prefix": key + "_", "fy": fy}}, "tax_year": year, "state": key, "pack": {"$pack": {"key": key, "tax_year": min(year, 2025)}}, **kw})
    for state in ("ga", "GA_JTC", "SC_JOBS", "TX", "ZZ"):
        call(rec, "onezero_snapshot", {"rows": {"$payroll": {"prefix": "SC_", "fy": 2025}}, "tax_year": 2025, "state": state, "pack": {"$pack": {"key": "SC", "tax_year": 2025}}, "prior_average_headcount": 8.0})
    for spec in pack_specs():
        call(rec, "onezero_snapshot", {"rows": {"$payroll": {"prefix": "GA_", "fy": 2025, "max_employees": 25}}, "tax_year": 2025, "state": "GA", "pack": {"$pack_spec": spec}, "prior_average_headcount": 3.0})
    for rows in [r for r in test_lever_rows() if not any(str(c.get("Hours_Worked")).lower() in ("nan", "inf", "-inf") for c in r)] + [random_rows(rng, 8) for _ in range(40)]:
        call(rec, "onezero_snapshot", {"rows": rows, "tax_year": rng.choice([2025, 2025, 2024]), "state": rng.choice(["GA", "TN"]), "pack": {"$pack_spec": rng.choice(pack_specs())}, "prior_average_headcount": rng.choice([0.0, 2.5, 4])})
    call(rec, "onezero_snapshot", {"rows": [], "tax_year": 2025, "state": "GA", "pack": {"$pack": {"key": "GA", "tax_year": 2025}}})
    call(rec, "onezero_snapshot", {"rows": [], "tax_year": 0, "state": "GA", "pack": {"$pack": {"key": "GA", "tax_year": 2025}}})


def lever_scenarios(rec, rng):
    ga = {"$pack": {"key": "GA", "tax_year": 2025}}
    packs = [ga] + [{"$pack_spec": s} for s in pack_specs()[:6]]
    actions = ["adjust_hours", "adjust_wages", "add_headcount", "remove_headcount", "bogus", ""]
    mags = [0, 1, 2, 3, 5, -1, -2, 2.5, 0.5, -0.5, 10, -10, 100, 1e3, 7.77, -7.77, 0.05]
    for rows in test_lever_rows():
        for action in actions:
            for mag in mags:
                if rng.random() < 0.3:
                    call(rec, "apply_onezero_lever", {"rows": rows, "action": action, "magnitude": mag, "pack": rng.choice(packs), "state": rng.choice(["GA", "ga", "TX"]),
                                                      **({"fein": "58-1111111"} if rng.random() < 0.3 else {})})
        for hours, rate in ((30, 20), (30, None), (None, 20), (40.0, 7.25), (35.0, 18.17), (34.99, 18.17), (35, 18.1714286), (0, 0), (20, 15), (12.5, None), (None, 0.0), (1e6, 1e6), (37.5, 16.0)):
            call(rec, "apply_onezero_lever", {"rows": rows, "action": "add_headcount", "magnitude": rng.choice([1, 2, 3]), "pack": rng.choice(packs), "state": "GA", "hire_weekly_hours": hours, "hire_hourly_rate": rate})
    for mag in (float("nan"), INF, -INF):
        for action in ("remove_headcount", "add_headcount", "adjust_hours", "adjust_wages"):
            call(rec, "apply_onezero_lever", {"rows": test_lever_rows()[3], "action": action, "magnitude": mag, "pack": ga, "state": "GA"})
    # test_simulate_unit: a part-time role is not refused, the engine just does not count it
    call(rec, "apply_onezero_lever", {"rows": test_lever_rows()[0], "action": "add_headcount", "magnitude": 1, "pack": ga, "state": "GA", "hire_weekly_hours": 30, "hire_hourly_rate": 20})
    for sel in ({"prefix": "GA_GA-016"}, {"prefix": "TN_", "fy": 2025}, {"prefix": "SC_", "fy": 2025, "max_employees": 20}, {"prefix": "GA_", "fy": 2025, "max_employees": 15}):
        full = {"$payroll": sel}
        for action, mag in (("adjust_hours", 2.0), ("adjust_hours", -3.5), ("adjust_wages", 10.0), ("adjust_wages", -12.5), ("remove_headcount", 3), ("remove_headcount", -2), ("add_headcount", 2), ("add_headcount", 4.9)):
            call(rec, "apply_onezero_lever", {"rows": full, "action": action, "magnitude": mag, "pack": ga, "state": "GA", "digest": True, "fein": "62-2222222"})
        for hours, rate in ((30, 20), (40, 12.5), (35, None), (None, 25.0)):
            call(rec, "apply_onezero_lever", {"rows": full, "action": "add_headcount", "magnitude": 2, "pack": ga, "state": "TN", "hire_weekly_hours": hours, "hire_hourly_rate": rate, "digest": True})
    call(rec, "apply_onezero_lever", {"rows": {"$payroll": {"prefix": "TN_", "fy": 2025, "max_employees": 6}}, "action": "add_headcount", "magnitude": 2, "pack": ga, "state": "TN"})
    call(rec, "apply_onezero_lever", {"rows": {"$payroll": {"prefix": "TN_", "fy": 2025, "max_employees": 6}}, "action": "remove_headcount", "magnitude": 2, "pack": ga, "state": "TN"})
    for _ in range(250):
        call(rec, "apply_onezero_lever", {"rows": random_rows(rng, rng.randint(1, 10)), "action": rng.choice(actions[:5]), "magnitude": rng.choice(mags), "pack": rng.choice(packs), "state": rng.choice(["GA", "TN"]),
                                          **({"hire_weekly_hours": rng.choice([None, 20, 30.5, 35.0, 40])} if rng.random() < 0.5 else {}),
                                          **({"hire_hourly_rate": rng.choice([None, 7.25, 15, 18.17, 25.5])} if rng.random() < 0.5 else {})})


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    rec = Rec()
    call(rec, "_payroll", {})
    months_scenarios(rec, rng)
    ytd_scenarios(rec, rng)
    project_scenarios(rec, rng)
    location_scenarios(rec, rng)
    hiring_scenarios(rec, rng)
    role_scenarios(rec, rng)
    snapshot_scenarios(rec, rng)
    lever_scenarios(rec, rng)
    return gr.serialise(rec, {"payroll_rows": len(PAYROLL), "states": STATES}, seed, oracle.stamp())


if __name__ == "__main__":
    raise SystemExit(gr.main("forecast", DEFAULT_OUT, SEED, build))
