"""Golden vectors for ``tools/grid_filter.py`` (stage DS7, ingestion family).

``compile_filters`` and its four private builders (``_number``, ``_numeric_predicate``, ``_text_predicate``, ``_enum_predicate``) are called over
every input ``tests/test_grid_filter.py`` uses, the two production whitelists (``EMPLOYEE_FILTERS``, ``NEAR_FILTERS`` of ``gold_reader``), and a matrix
of expressions of every grammar type: comparators and their prefixes, ranges (inverted, open, doubled, NaN or infinite bounds, ``-0``), bare numbers, numbers
``float()`` reads in unusual spellings (underscores, full-width and Arabic-Indic digits, huge and tiny exponents), text needles with LIKE wildcards, brackets,
regex metacharacters, SQL fragments, case-folding oddities and whitespace, enums with empty members, duplicates and padding, malformed terms (no colon,
empty name or value, extra colons, repeated names, unknown columns, an unknown grammar type), plus seeded random wires.

Line format (JSONL, gzip, mtime 0), as ``golden_rec``. ``compile_filters`` records ``[sql, values, applied]``; a float keeps its ``repr`` (non-finite as
``NaN``/``Infinity``). Usage: python parity/export_grid_filter.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import os
import random
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
from infrastructure.persistence.gold_reader.stmt_unit_people import EMPLOYEE_FILTERS, NEAR_FILTERS  # noqa: E402
from tools import grid_filter as gf  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "grid_filter.jsonl.gz"
SEED = 20261122

NUMERIC = [">=35", "<=35", ">35", "<35", "=35", "35", "10..52", "52..10", "10..", "..52", "..", "1..2..3", "...", "1...5", "nan", ">=nan", "<=nan", "inf", "-inf", ">=inf", "<-inf", "1e999", "-1e999",
           "1e-999", "10..nan", "nan..10", "nan..nan", "inf..-inf", "-inf..inf", "-0..0", "0..-0", "0..0", "-0", "+0", ">= 35", " >=35", "> =35", ">=  35  ", "\u2265 35", "\u0661\u0662", "\u0663\u0664.\u0665",
           "1_000", "1__0", "_1", "1_", ">=1_0", ">=", "<=", ">", "<", "=", ">>5", "=>5", "<>5", "==5", "3.14159265358979323846", "1e308", ">=1e309", "0x10", "12abc", "+5", "-5", ".5", "5.", "1.5.5",
           "12345678901234567890123456789", "- 5", "\uff15", "\uff15\uff10..\uff11\uff10\uff10", "5\u00a0", "\u00a05", "5\u2003..\u20039", "1e5", "1E5", "1e+5", "1e", "e5", "Infinity", "-Infinity", "NaN", "+nan",
           "-nan", "1..2", "-5..-1", "-1..-5", "0.5..0.25", "1e308..1e309", "..nan", "nan..", "1.0..2.0", " 1 .. 2 ", "1 ..2", ".. 2", "\u0000", "5\u0000", "5\n", "\t5", ">=\u00a035", "<=-0", ">=-0.0"]
TEXT = ["~abc", "abc", "~", "~ ", "~  abc  ", "~%", "~_", "~[", "~]", "~[]", "~%_[", "~100%", "~a_b", "~\u00c4\u00d6", "~\u0130", "~\u00df", "~\u0391\u03a3", "~\u03a3", "~\u65e5\u672c", "~\u00a0x", "~\t",
        "~~x", "~~", "~'; DROP TABLE x;--", "~\\", "~a%b_c[d]", "~.*", "~^$", "~(a|b)", "~E001", "~e001", "~E 001", "\u00a0~x", "~ x", "~\u212a", "~\u1e9e", "~\ufb01", "~\u01c5", "~\u0345", "~ABC DEF",
        "~\u3000x\u3000", "~%%", "~__", "~[[", "~%[_]%", "~x" * 40, "~\ud83d\ude00".encode("utf-16", "surrogatepass").decode("utf-16"), "~i\u0307", "~\u03a3\u03a3", "~A\u03a3", "~A\u03a3 B"]
ENUM = ["a|b", "a", "|", "||", "a||b", " a | b ", "a|a", "|a", "a|", "A|a", "\u00e9|\u00fc", "a|b|c|d|e|f|g|h|i|j", "\u00a0|x", "a b|c d", "a\t|\tb", "x|\u3000|y", "%|_", "a;b|c", "a:b|c", "'a'|\"b\"",
        "\u65e5\u672c|\u8a9e", "qualified|declined", "a|b|", "|||a|||", "  |  "]
COLUMNS = {
    "employee": EMPLOYEE_FILTERS, "near": NEAR_FILTERS, "none": {}, "enum": {"employee_id": ("e.x", "enum"), "status": ("s.status", "enum")},
    "mixed": {"n": ("t.n", "numeric"), "t": ("t.t", "text"), "e": ("t.e", "enum"), "weird": ("[a b]", "numeric"), "empty-sql": ("", "text"), "unicode\u00e9": ("u.x", "enum")},
    "bogus-kind": {"x": ("e.x", "bogus"), "n": ("e.n", "numeric")},
}
WIRES = [
    "avg_weekly_hours:>=35", "weeks_worked:10..52", "weeks_worked:52..10", "weeks_worked:10", "employee_id:~E001", "weeks_worked:>=10;avg_weekly_hours:<40", "salary:>=100", "1=1 OR x:>=1;DROP TABLE t:~a",
    "weeks_worked:banana", "employee_id:~%_", "", None, "  ", "nocolon", ":", ";", ";;", ";;;", "a", "a:", ":b", "avg_weekly_hours:", " avg_weekly_hours : >=35 ", "avg_weekly_hours:>=35;", ";avg_weekly_hours:>=35",
    "avg_weekly_hours:>=35;;weeks_worked:5", "avg_weekly_hours:>=35;avg_weekly_hours:<40", "avg_weekly_hours:>=35;avg_weekly_hours:banana", "avg_weekly_hours:banana;avg_weekly_hours:>=35",
    "AVG_WEEKLY_HOURS:>=35", "avg weekly hours:>=35", "avg_weekly_hours:a:b", "employee_id:~a:b", "employee_id:~a;b", "employee_id:~a\u037eb", "weight:0.5", "weight:..", "total_hours:1e9..1",
    "avg_weekly_hours:>=35;weeks_worked:1..52;total_hours:<=2000;weight:>0;employee_id:~x", "employee_id:~x;employee_id:~y", "\u00a0weeks_worked\u00a0:\u00a05\u00a0", "weeks_worked:5\u2028", "weeks_worked\n:\n5",
    "x:1;;y:2", "x:1", "x:~a", "n:1;x:2", "x:", "constructor:1", "__proto__:1", "weeks_worked:>=10 ;; avg_weekly_hours : < 40 ;", "weeks_worked:5;weeks_worked:5", "a:b;c:d;e:f", "employee_id:A|B", "status:qualified|declined", "n:5;t:~x;e:a|b",
]


def run_fn(fn: str, a: dict):
    cols = COLUMNS[a["columns"]] if "columns" in a else None
    if fn == "compile_filters":
        return list(gf.compile_filters(a["wire"], cols))
    if fn == "_number":
        return gf._number(a["text"])
    if fn == "_numeric_predicate":
        return gf._numeric_predicate(a["column"], a["expr"])
    if fn == "_text_predicate":
        return gf._text_predicate(a["column"], a["expr"])
    if fn == "_enum_predicate":
        return gf._enum_predicate(a["column"], a["expr"])
    raise KeyError(fn)


class Rec(gr.Recorder):
    def call(self, fn: str, args: dict, run=None) -> None:
        # the whitelist travels IN the arguments, not by name, so the replay needs no knowledge of this module
        full = {**args, "columns_map": {k: list(v) for k, v in COLUMNS[args["columns"]].items()}} if "columns" in args else args
        super().call(fn, full, lambda: run_fn(fn, args))


def call(rec, fn, args):
    rec.call(fn, args)


def scenarios(rec, rng):
    for wire in WIRES:
        for cols in COLUMNS:
            call(rec, "compile_filters", {"wire": wire, "columns": cols})
    for expr in NUMERIC:
        for cols, column in (("mixed", "n"), ("employee", "weeks_worked")):
            call(rec, "compile_filters", {"wire": f"{column}:{expr}", "columns": cols})
        call(rec, "_numeric_predicate", {"column": "c.x", "expr": expr})
        call(rec, "_number", {"text": expr})
    for expr in TEXT:
        call(rec, "compile_filters", {"wire": f"t:{expr}", "columns": "mixed"})
        call(rec, "compile_filters", {"wire": f"employee_id:{expr}", "columns": "employee"})
        call(rec, "_text_predicate", {"column": "c.x", "expr": expr})
    for expr in ENUM:
        call(rec, "compile_filters", {"wire": f"e:{expr}", "columns": "mixed"})
        call(rec, "compile_filters", {"wire": f"status:{expr}", "columns": "enum"})
        call(rec, "_enum_predicate", {"column": "c.x", "expr": expr})
    for text in ("", " ", "5", "5.0", "1e3", "\u00a05\u00a0", "abc", "nan", "inf"):
        call(rec, "_number", {"text": text})
    for expr in ("", " ", "x"):
        call(rec, "_text_predicate", {"column": "c.x", "expr": expr})
        call(rec, "_enum_predicate", {"column": "c.x", "expr": expr})
        call(rec, "_numeric_predicate", {"column": "c.x", "expr": expr})
    pools = {"n": NUMERIC, "t": ["~" + e.lstrip("~") for e in TEXT] + TEXT, "e": ENUM}
    for _ in range(700):
        terms = []
        for _ in range(rng.randint(1, 5)):
            name = rng.choice(["n", "t", "e", "n", "t", "zzz", "weird", "empty-sql", "N", ""])
            expr = rng.choice(pools.get(name, rng.choice(list(pools.values()))))
            sep = rng.choice([":", ":", ":", " : ", ""])
            terms.append(f"{name}{sep}{expr}")
        wire = rng.choice([";", ";", "; ", ";;"]).join(terms)
        call(rec, "compile_filters", {"wire": wire, "columns": "mixed"})


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    rec = Rec()
    scenarios(rec, rng)
    return gr.serialise(rec, {"whitelists": {k: {n: list(v) for n, v in cols.items()} for k, cols in COLUMNS.items()}}, seed, oracle.stamp())


if __name__ == "__main__":
    raise SystemExit(gr.main("grid_filter", DEFAULT_OUT, SEED, build))
