"""Golden vectors for ``tools/canonical.py`` (stage DS7, ingestion family).

Every function of the module is called over a scenario matrix: every input ``tests/test_canonical.py`` and ``tests/test_fabric_source.py`` use, plus
the frequency boundaries (7/14/15/16/17/30/31 day spans, leap days, a period that ends before it starts), pay-code include and exclude sets (whitespace-only,
empty, unicode, ``None``, missing; every shape of ingested config including ones that make the classifier fall back), every date spelling
``date.fromisoformat`` accepts or refuses, every cell type ``float()`` accepts or refuses, duplicate pay lines, the worksite registry in each shape
(production's ``Site`` objects, dict-shaped entries, a mix), ``csv.DictReader`` texts for the infrastructure adapter, the committed synthetic payroll
``backend/data/payroll_pay_periods.csv`` through the default adapter, and seeded random batches.

The two hooks the module imports at call time are PATCHED from the call's arguments, so the golden records its own inputs: ``rules_ingestion.load_ingested_config``
(a dict program to config, ``{"$raise": ...}`` to raise, absent program gives ``None`` = the 'none' port) and ``data.sites.SITES`` (``"$object"`` is a real ``Site``).

Line format (JSONL, gzip, mtime 0), as ``golden_rec``: ``{"k":"call","id":n,"fn":name,"out":tree,"args":{...}}`` or ``{"k":"call",...,"err":"TypeName","msg":...}``.
Dates are ``{"$date": iso}`` and a ``CanonicalRecord`` is its dataclass dict. A large result is ``{"$digest": sha256 of the compact ASCII JSON, "n": count, "head": first two}``.

Usage: python parity/export_canonical.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import contextlib
import hashlib
import os
import random
import sys
import tempfile
from datetime import date, timedelta
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
from data import sites as sites_mod  # noqa: E402
from tools import canonical as C  # noqa: E402
from tools import rules_ingestion as ri  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "canonical.jsonl.gz"
SEED = 20261121
CSV_PATH = BACKEND / "data" / "payroll_pay_periods.csv"
REAL_GA = ri.load_ingested_config("GA_JTC")
INF, NAN = float("inf"), float("nan")
GA_BASIS = {"parameters": {"wage_basis": REAL_GA["parameters"]["wage_basis"]}}


class Adapter:
    def __init__(self, rows):
        self._rows = rows

    def rows(self):
        return self._rows


def raw(emp="E1", unit="GA_ATL_HQ", pay_date="2025-02-02", code="Regular", wages=2000, hours=80, start="2025-01-15", end="2025-01-28", fein="58-1234567"):
    """``test_canonical._raw`` exactly (numbers arrive as strings from a CSV)."""
    return {"Tax_Year": "2025", "Employee_ID": emp, "Job_Title": "Analyst", "Worksite_ID": unit, "Pay_Period_Start": start, "Pay_Period_End": end,
            "Pay_Date": pay_date, "Entity_FEIN": fein, "Hours_Worked": str(hours), "Gross_Wages": str(wages), "Pay_Code": code}


@contextlib.contextmanager
def hooks(args: dict):
    """Patch the two call-time imports of ``canonical`` from the call's own arguments."""
    ingested = args.get("ingested", {})
    original_load, original_sites = ri.load_ingested_config, sites_mod.SITES

    def fake(program):
        value = ingested.get(program)
        if isinstance(value, dict) and "$raise" in value:
            raise RuntimeError("ingestion source down")
        return value

    ri.load_ingested_config = fake
    if "sites" in args:
        sites_mod.SITES = [original_sites[0] if s == "$object" else s for s in args["sites"]]
    try:
        yield
    finally:
        ri.load_ingested_config = original_load
        sites_mod.SITES = original_sites


def digest(records) -> dict:
    encoded = [gr.enc(r) for r in records]
    return {"$digest": hashlib.sha256(gr.dumps(encoded).encode("ascii")).hexdigest(), "n": len(records), "head": encoded[:2]}


class Rec(gr.Recorder):
    def call(self, fn: str, args: dict, run=None) -> None:
        super().call(fn, args, lambda: run_fn(fn, args))


def run_fn(fn: str, a: dict):
    with hooks(a):
        if fn == "to_canonical":
            kw = {k: a[k] for k in ("tax_year", "program") if k in a}
            return C.to_canonical(Adapter(a["rows"]), **kw)
        if fn == "to_canonical_csv":
            kw = {k: a[k] for k in ("tax_year", "program") if k in a}
            recs = C.to_canonical(**kw)
            return digest(recs)
        if fn == "collapse_to_employee_period":
            return C.collapse_to_employee_period(a["records"])
        if fn == "_infer_frequency":
            return C._infer_frequency(a["start"], a["end"])
        if fn == "_pay_code_classifier":
            inc, exc = C._pay_code_classifier(a["program"])
            # only text can equal a pay code, so only text members are reported (a number in the list is a member that matches nothing)
            return [sorted(s for s in inc if isinstance(s, str)) if inc is not None else None, sorted(s for s in exc if isinstance(s, str))]
        if fn == "_is_includable":
            inc = set(a["included"]) if a["included"] is not None else None
            return C._is_includable(a["pay_code"], inc, set(a["excluded"]))
        if fn == "_worksite_join":
            return C._worksite_join(a["worksite_id"])
        if fn == "csv_rows":
            return csv_rows(a)
    raise KeyError(fn)


def csv_rows(a: dict):
    """The production adapter over a file holding ``text`` (UTF-8, written byte for byte) or over a path that does not exist."""
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as scratch:
        path = Path(scratch) / "pay.csv"
        if not a.get("missing"):
            path.write_bytes(a["text"].encode("utf-8"))
        rows = C.PayPeriodCsvAdapter(path=path).rows()
        return [{k: v for k, v in r.items() if k is not None} for r in rows]


def call(rec, fn, args):
    rec.call(fn, args)


# ------------------------------------------------------------------------------------------------ scenarios

def test_inputs(rec):
    call(rec, "to_canonical", {"rows": [raw()], "tax_year": 2025})
    call(rec, "to_canonical", {"rows": [raw(start="2025-01-01", end="2025-01-07")]})
    call(rec, "to_canonical", {"rows": [raw(start="2025-01-01", end="2025-01-14")]})
    call(rec, "to_canonical", {"rows": [raw(pay_date="2025-01-05"), raw(pay_date="2024-12-28"), raw(pay_date="2026-01-03")], "tax_year": 2025})
    for ingested in ({}, {"GA_JTC": GA_BASIS}):
        call(rec, "to_canonical", {"rows": [raw(code="Regular"), raw(code="Mileage", wages=25, hours=0)], "tax_year": 2025, "program": "GA_JTC", "ingested": ingested})
        call(rec, "collapse_to_employee_period", {"records": C.to_canonical(Adapter([raw(code="Regular", wages=2000, hours=80), raw(code="Mileage", wages=50, hours=0)]), tax_year=2025)})
    # test_fabric_source: a mapped Fabric row (floats arrive as floats)
    fabric = {"Tax_Year": 2026, "Employee_ID": "E100001", "Worksite_ID": "NC_WS069", "Entity_FEIN": "56-0000001", "Pay_Period_Start": "2026-01-05", "Pay_Period_End": "2026-01-18",
              "Pay_Date": "2026-01-23", "Hours_Worked": 37.55, "Gross_Wages": 1306.74, "Pay_Code": "Regular", "Job_Title": "Recruiter"}
    call(rec, "to_canonical", {"rows": [fabric], "tax_year": 2026})
    call(rec, "to_canonical", {"rows": [], "tax_year": 2025})
    call(rec, "to_canonical", {"rows": []})
    for ty in (None, 2024, 2025, 2026):
        for prog in ("GA_JTC", "TN_JTC", "FED_WOTC"):
            for ing in ({}, {"GA_JTC": GA_BASIS}):
                args = {"program": prog, "ingested": ing}
                if ty is not None:
                    args["tax_year"] = ty
                call(rec, "to_canonical_csv", args)


def frequency_scenarios(rec):
    base = date(2025, 1, 1)
    for span in list(range(-3, 41)) + [59, 60, 90, 365]:
        call(rec, "_infer_frequency", {"start": base, "end": base + timedelta(days=span - 1)})
    for start, end in ((date(2024, 2, 28), date(2024, 3, 1)), (date(2023, 2, 28), date(2023, 3, 1)), (date(2024, 2, 1), date(2024, 2, 29)), (date(2024, 2, 15), date(2024, 3, 1)),
                       (date(2024, 2, 15), date(2024, 2, 29)), (date(2024, 12, 31), date(2025, 1, 14)), (date(2025, 1, 1), date(2025, 1, 1)), (date(2025, 1, 5), date(2025, 1, 1)),
                       (date(1, 1, 1), date(1, 1, 7)), (date(9999, 12, 25), date(9999, 12, 31))):
        call(rec, "_infer_frequency", {"start": start, "end": end})
        call(rec, "to_canonical", {"rows": [raw(start=start.isoformat(), end=end.isoformat())]})
    for span in (7, 8, 14, 15, 16, 17, 30, 31):
        end = date(2025, 3, 1) + timedelta(days=span - 1)
        call(rec, "to_canonical", {"rows": [raw(start="2025-03-01", end=end.isoformat())]})


def pay_code_scenarios(rec):
    codes = ["Regular", "Overtime", "Mileage", "Expense_Reimbursement", "Relocation", "", " ", "\t", "regular", "REGULAR", "Bonus", "Commission", "Holiday", "Incentive",
             "Régulier", "\u00a0", "\u3000", "Regular ", "Bonus\u0301", "日本語", None, "None", 0, 5, 1.5, True]
    configs = {
        "none": {}, "real-ga": {"GA_JTC": GA_BASIS}, "full-ga": {"GA_JTC": REAL_GA}, "empty-cfg": {"GA_JTC": {}}, "params-none": {"GA_JTC": {"parameters": None}},
        "basis-missing": {"GA_JTC": {"parameters": {}}}, "included-empty": {"GA_JTC": {"parameters": {"wage_basis": {"included_pay_codes": [], "excluded_pay_codes": ["X"]}}}},
        "excluded-none": {"GA_JTC": {"parameters": {"wage_basis": {"included_pay_codes": ["Regular"], "excluded_pay_codes": None}}}},
        "included-str": {"GA_JTC": {"parameters": {"wage_basis": {"included_pay_codes": "Regular"}}}},
        "excluded-str": {"GA_JTC": {"parameters": {"wage_basis": {"excluded_pay_codes": "Mileage"}}}},
        "included-dict": {"GA_JTC": {"parameters": {"wage_basis": {"included_pay_codes": {"Regular": 1, "Bonus": 2}}}}},
        "included-mixed": {"GA_JTC": {"parameters": {"wage_basis": {"included_pay_codes": ["Regular", 5, None, 1.5, "Bonus"]}}}},
        "included-nested": {"GA_JTC": {"parameters": {"wage_basis": {"included_pay_codes": ["Regular", ["x"]]}}}},
        "included-int": {"GA_JTC": {"parameters": {"wage_basis": {"included_pay_codes": 5}}}},
        "excluded-int": {"GA_JTC": {"parameters": {"wage_basis": {"excluded_pay_codes": 7}}}},
        "cfg-list": {"GA_JTC": [1]}, "cfg-str": {"GA_JTC": "x"}, "params-list": {"GA_JTC": {"parameters": [1]}}, "basis-str": {"GA_JTC": {"parameters": {"wage_basis": "abc"}}},
        "wins": {"GA_JTC": {"parameters": {"wage_basis": {"included_pay_codes": ["Regular", "Mileage"], "excluded_pay_codes": ["Mileage"]}}}},
        "only-excl": {"GA_JTC": {"parameters": {"wage_basis": {"excluded_pay_codes": ["Regular", " "]}}}},
        "raises": {"GA_JTC": {"$raise": 1}}, "other-program": {"TN_JTC": GA_BASIS}, "unicode": {"GA_JTC": {"parameters": {"wage_basis": {"included_pay_codes": ["Régulier", "日本語", "\u00a0"]}}}},
    }
    for name, ing in configs.items():
        for prog in ("GA_JTC", "TN_JTC"):
            call(rec, "_pay_code_classifier", {"program": prog, "ingested": ing, "case": name})
        rows = [{**raw(emp=f"E{i}"), "Pay_Code": c} for i, c in enumerate(codes)]
        call(rec, "to_canonical", {"rows": rows, "program": "GA_JTC", "ingested": ing})
        call(rec, "collapse_to_employee_period", {"records": C.to_canonical(Adapter(rows))})
    missing = raw()
    del missing["Pay_Code"]
    call(rec, "to_canonical", {"rows": [missing]})
    inc_sets = (None, [], ["Regular"], ["Regular", "Overtime"], [""], [" "])
    exc_sets = ([], ["Mileage"], ["Regular"], ["Regular", "Mileage"], [" "])
    for inc in inc_sets:
        for exc in exc_sets:
            for code in ("Regular", "Mileage", "", " ", "Other"):
                call(rec, "_is_includable", {"pay_code": code, "included": inc, "excluded": exc})


def date_and_cell_scenarios(rec):
    dates = ["2025-01-15", "2025-01-15T10:00:00", "2025-01-15 10:00", "20250115", "2025-W03-3", "2025W033", "2025-13-01", "2025-02-30", "2024-02-29", "2023-02-29", "", " ", "None",
             " 2025-01-15", "2025-1-15", "2025/01/15", "２０２５-01-15", "0000-01-01", "9999-12-31", "2025-01-15abc", "2025-W53-1", "2025-W00-1", "2025-01", "25-01-15", None, 20250115, 20250115.0,
             "2025-01-15\u0000", "2025-01-15\n", "2025-01-1"]
    for field in ("Pay_Period_Start", "Pay_Period_End", "Pay_Date"):
        for value in dates:
            row = raw()
            row[field] = value
            call(rec, "to_canonical", {"rows": [row], "tax_year": 2025})
            call(rec, "to_canonical", {"rows": [row]})
        row = raw()
        del row[field]
        call(rec, "to_canonical", {"rows": [row]})
    cells = ["40", 40, 40.5, "", None, "0", "abc", " 12 ", "1e3", "nan", "-nan", "inf", "-inf", "Infinity", "1_0", "1__0", "_1", True, False, [], [1], {}, {"a": 1}, "٣٤", "1,000", "0x10", ".5", "5.", "+7", "-0",
             -0.0, 0, 0.0, 1e308, 1e-320, "1e999", "\u00a012\u00a0", 10**18, 2**70, "٣.٥"]
    for field in ("Hours_Worked", "Gross_Wages"):
        for value in cells:
            row = raw()
            row[field] = value
            call(rec, "to_canonical", {"rows": [row]})
        row = raw()
        del row[field]
        call(rec, "to_canonical", {"rows": [row]})
    for field in ("Employee_ID", "Worksite_ID", "Entity_FEIN", "Job_Title"):
        for value in ("", " ", "E1", "é", "日本語", None, 7, 7.5, True, 0, "\ud83d\ude00".encode("utf-16", "surrogatepass").decode("utf-16"), "a|b", "x" * 300):
            row = raw()
            row[field] = value
            call(rec, "to_canonical", {"rows": [row]})
        row = raw()
        del row[field]
        call(rec, "to_canonical", {"rows": [row]})
    call(rec, "to_canonical", {"rows": [raw(emp="E1"), raw(emp="E1"), raw(emp="E1", code="Overtime"), raw(emp="E1", unit="GA_B")]})
    call(rec, "to_canonical", {"rows": [{}, {"Pay_Date": "2025-01-01"}, raw()]})


def site_scenarios(rec):
    registry = [{"worksite_id": "GA_X", "address": "1 Main St", "city": "Atlanta", "state": "GA"}, {"id": "TN_Y", "city": "Nashville", "state": "TN"},
                {"worksite_id": "ZZ", "address": "", "city": None, "state": "ZZ"}, {"worksite_id": "W", "city": " , ", "state": ""}, {"worksite_id": "S", "state": "SC"},
                {"worksite_id": "Q", "city": "Q", "state": "QQ", "address": 0}, {"worksite_id": "A", "id": "B", "address": "dual"}, {"id": "A", "address": "second"}]
    mixed = ["$object", *registry]
    late = [*registry[:2], "$object", *registry[2:]]
    for name, sites in (("real", None), ("object", ["$object"]), ("dict", registry), ("mixed", mixed), ("late-object", late), ("empty", [])):
        for wid in ("GA_X", "TN_Y", "ZZ", "W", "S", "Q", "A", "B", "NOPE", "", "GA_ATL_HQ"):
            args = {"worksite_id": wid}
            if sites is not None:
                args["sites"] = sites
            if name == "dict" and wid == "Q":
                continue  # a non-string address is not modelled
            call(rec, "_worksite_join", args)
            if wid in ("GA_X", "TN_Y", "A", "B", "NOPE"):
                call(rec, "to_canonical", {"rows": [raw(unit=wid)], **({"sites": sites} if sites is not None else {})})


def random_row(rng):
    def pick(*xs):
        return rng.choice(xs)

    start = date(2024, 11, 1) + timedelta(days=rng.randint(0, 400))
    end = start + timedelta(days=pick(0, 3, 6, 7, 13, 14, 15, 29, 30))
    pay = end + timedelta(days=rng.randint(-2, 12))
    row = {"Tax_Year": pick("2024", "2025", 2025, ""), "Employee_ID": pick("E1", "E2", "E3", "E4", 5, "é"), "Job_Title": pick("A", "", None, "Lead"),
           "Worksite_ID": pick("GA_A", "GA_B", "TN_C", "NC_D", ""), "Pay_Period_Start": start.isoformat(), "Pay_Period_End": end.isoformat(), "Pay_Date": pay.isoformat(),
           "Entity_FEIN": pick("58-1", "62-2", "", None), "Hours_Worked": pick(rng.choice([0, 4, 40, 72.82]), str(round(rng.uniform(0, 90), 2)), "", None, "0"),
           "Gross_Wages": pick(round(rng.uniform(-5, 4000), 2), str(round(rng.uniform(0, 3000), 2)), 0, "", None),
           "Pay_Code": pick("Regular", "Regular", "Overtime", "Mileage", "Bonus", " ", "Relocation")}
    if rng.random() < 0.1:
        row["Pay_Date"] = pick("bad", None, "2025-02-30")
    if rng.random() < 0.05:
        del row[pick("Employee_ID", "Pay_Code", "Hours_Worked", "Worksite_ID")]
    return row


def records_for_collapse(rng, n):
    out = []
    for _ in range(n):
        start = date(2025, 1, 1) + timedelta(days=rng.randint(0, 30))
        end = start + timedelta(days=rng.choice([6, 13]))
        out.append(C.CanonicalRecord(tax_year=2025, employee_id=rng.choice("ABC"), worksite_id=rng.choice(["GA_1", "GA_2"]), legal_entity_fein=rng.choice(["F1", "F2"]),
                                     pay_frequency=rng.choice(["weekly", "biweekly"]), pay_period_start=start, pay_period_end=end, pay_date=end + timedelta(days=rng.randint(0, 9)),
                                     hours_worked=rng.choice([0.1, 0.2, 0.3, 7.77, 40.0, 1e-9, -3.5, 0.005, 2.675, 1e15]), gross_wages=rng.choice([0.1, 0.7, 19.999, 2000.0, 1234.565, -0.24, 0.0]),
                                     includable=rng.random() < 0.8, pay_code=rng.choice(["Regular", "Mileage"])))
    return out


def collapse_scenarios(rec, rng):
    call(rec, "collapse_to_employee_period", {"records": []})
    t = date(2025, 1, 14)
    base = dict(tax_year=2025, employee_id="E1", worksite_id="GA_A", legal_entity_fein="F", pay_frequency="biweekly", pay_period_start=date(2025, 1, 1), pay_period_end=t, pay_date=date(2025, 1, 20))
    inc = lambda **kw: C.CanonicalRecord(**{**base, **kw})  # noqa: E731
    call(rec, "collapse_to_employee_period", {"records": [inc(hours_worked=0.1, gross_wages=0.1), inc(hours_worked=0.2, gross_wages=0.2), inc(hours_worked=0.3, gross_wages=0.7)]})
    call(rec, "collapse_to_employee_period", {"records": [inc(hours_worked=1.005, gross_wages=2.675), inc(hours_worked=0.0, gross_wages=0.0, includable=False)]})
    call(rec, "collapse_to_employee_period", {"records": [inc(hours_worked=NAN, gross_wages=1.0), inc(hours_worked=1.0, gross_wages=INF), inc(hours_worked=-INF, gross_wages=-INF)]})
    call(rec, "collapse_to_employee_period", {"records": [inc(hours_worked=1.0, gross_wages=1.0, pay_date=date(2025, 2, 1)), inc(hours_worked=2.0, gross_wages=2.0, pay_date=date(2025, 3, 1), pay_frequency="weekly")]})
    call(rec, "collapse_to_employee_period", {"records": [inc(hours_worked=1.0, gross_wages=1.0, worksite_id="GA_B"), inc(hours_worked=1.0, gross_wages=1.0, employee_id="E2"), inc(hours_worked=1.0, gross_wages=1.0)]})
    call(rec, "collapse_to_employee_period", {"records": [inc(hours_worked=1e308, gross_wages=1e308), inc(hours_worked=1e308, gross_wages=1e308)]})
    for _ in range(150):
        call(rec, "collapse_to_employee_period", {"records": records_for_collapse(rng, rng.randint(1, 14))})
    for _ in range(300):
        rows = [random_row(rng) for _ in range(rng.randint(1, 8))]
        args = {"rows": rows}
        if rng.random() < 0.5:
            args["tax_year"] = rng.choice([2024, 2025, 2026])
        if rng.random() < 0.3:
            args["ingested"] = {"GA_JTC": GA_BASIS}
        try:
            C.to_canonical(Adapter(rows))
        except Exception:  # noqa: BLE001 - the recorded call carries the exception
            pass
        call(rec, "to_canonical", args)
        recs = []
        try:
            recs = C.to_canonical(Adapter(rows))
        except Exception:  # noqa: BLE001
            continue
        call(rec, "collapse_to_employee_period", {"records": recs})


CSV_TEXTS = [
    "", "\n", "a,b\n", "a,b\n1,2\n", "a,b\r\n1,2\r\n3,4\r\n", "a,b\r1,2\r3,4", "a,b\n1,2", "a,b\n\n\n1,2\n\n", "a,b\n1\n", "a,b\n1,2,3,4\n", "a,b\n,\n", "a,b\n\"\",\"\"\n",
    "a,b\n\"x,y\",2\n", "a,b\n\"x\"\"y\",2\n", "a,b\n\"x\ny\",2\n", "a,b\n\"x\r\ny\",2\r\n", "a,b\n\"x\ry\",2\n", "a,b\nx\"y,2\n", "a,b\n\"x\"y,2\n", "a,b\n\"x\" ,2\n",
    "a,b\n\"unterminated,2\n", "a,b\n\"unterminated\n", "a,b\n1,\"\n", "\ufeffa,b\n1,2\n", "a,a\n1,2\n", "a,a\n1\n", "a,b,c\n1\n", " a , b \n 1 , 2 \n", "a,b\n\u00e9,\u65e5\u672c\n",
    "a,b\n\"\"\"\",2\n", "a,b\n1,2\n\r\n3,4\r\n", "a,b\r\n\r\n1,2\r\n", ",\n,\n", "a\n1\n2\n", "a,b\n1,2\n3", "a,b\n\"1\n\"\n", "a,b\n\"x\"\n", "a,b\n1;2,3\n", "a,b\n'x,y',2\n",
    "a,b\n1,2\n\"3\n", "Tax_Year,Employee_ID\n2025,E1\n", "a,b\n\"\n\",2\n", "a,b\n1,2\r", "a,b\n1,2\n\r", "a,b\n\r\r1,2\n",
]


def csv_scenarios(rec):
    call(rec, "csv_rows", {"missing": True})
    for text in CSV_TEXTS:
        call(rec, "csv_rows", {"text": text})
    call(rec, "csv_rows", {"text": CSV_PATH.read_text(encoding="utf-8")[:600]})


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    rec = Rec()
    test_inputs(rec)
    frequency_scenarios(rec)
    pay_code_scenarios(rec)
    date_and_cell_scenarios(rec)
    site_scenarios(rec)
    collapse_scenarios(rec, rng)
    csv_scenarios(rec)
    return gr.serialise(rec, {"csv_rows": sum(1 for _ in CSV_PATH.open(encoding="utf-8")) - 1}, seed, oracle.stamp())


if __name__ == "__main__":
    raise SystemExit(gr.main("canonical", DEFAULT_OUT, SEED, build))
