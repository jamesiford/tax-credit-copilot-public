"""Golden vectors for the rule-pack validator (stage DS8): ``tools/pack_validation.py``.

Three record kinds, all produced by the PRODUCTION functions on CPython 3.12 with ``jsonschema`` (Draft 2020-12):

``doc``  one ``validate_document(pack, name, kind, years_authored)`` call over a document held in memory, with the full ``Report`` (issues
         in order) AND the raw ``jsonschema`` errors (validator keyword, absolute path, message) stably sorted by path as the module sorts them
         (the unsorted ``iter_errors`` order depends on the string-hash seed). The corpus is: every real base, year and lookup/methodology file under ``backend/rules``; the draft skeletons of
         ``tools/program_scaffold.py`` (built in memory, nothing is written); the fictional programs of ``tests/two_program_world.py`` and the
         invented lab packs of ``credit_math_worlds.py``; and a seeded set of mutants (a SYSTEMATIC sweep that damages every node of four
         documents with each damage in a fixed menu, then a seeded RANDOM stack of one to three damages on any pool document).
``all``  one ``validate_all()`` over a rules-folder world (the shipped folder, and the credit-math overlays plus worlds of my own that hold
         a duplicate credit code, an unregistered pack, a registry mismatch, a year pack of another program, strays and unreadable files).
``pack`` one ``validate_pack(path, years_authored)`` over a file of the shipped folder or of an unreadable-file world.

Messages that carry a machine path say ``<RULES>``; separators are normalised to ``/``. Documents are written once per record (the C# replay
reads them back with the Python JSON reader, so int-versus-float and key order survive). No file under ``backend`` is read through anything
but the production code, and the scratch worlds under ``parity/.scratch-pack-validation`` are removed on exit.

Usage: python parity/export_pack_validation.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import argparse
import copy
import gzip
import io
import json
import os
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import credit_math_worlds as worlds_mod  # noqa: E402
import golden_rec as gr  # noqa: E402
import jsonschema  # noqa: E402
from domain.calculation.onezero import OneZeroMethodology  # noqa: E402

from tools import pack_validation as pv  # noqa: E402
from tools import program_scaffold as ps  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "pack_validation.jsonl.gz"
SCRATCH = Path(__file__).resolve().parent / ".scratch-pack-validation"
SEED = 20261119
RULES = worlds_mod.RULES
FLAG = {"_prototype_verify": True}


# --------------------------------------------------------------------------- encoding helpers


def norm(text: str, rules: Path | None) -> str:
    """Machine paths become ``<RULES>``; Windows separators become ``/``."""
    if rules is not None:
        text = text.replace(str(rules), "<RULES>")
    return text.replace("\\", "/")


def report_enc(report: pv.Report, rules: Path | None) -> dict:
    return {"file": norm(report.file, rules), "kind": report.kind, "ok": report.ok,
            "issues": [{"severity": i.severity, "code": i.code, "path": i.path, "message": norm(i.message, rules) if i.code == "unreadable" else i.message}
                       for i in report.issues]}


def schema_errors(doc, kind: str) -> list[dict]:
    """The raw errors of the production validator, in the order the module uses (stable sort by path).

    ``iter_errors`` itself is not recorded: ``additionalProperties`` walks a ``set`` of keys, so its order depends on the string-hash seed, and a golden must
    be byte-identical across seeds. The module sorts by path before it reports anything, so nothing it reports depends on the unsorted order.
    """
    validator = jsonschema.Draft202012Validator(pv._subschema(kind))
    errors = sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path))
    return [{"keyword": e.validator, "path": list(e.absolute_path), "message": e.message} for e in errors]


class Lines:
    def __init__(self) -> None:
        self.rows: list[str] = []
        self.counts: dict[str, int] = {}
        self.errors = 0
        self.invalid = 0
        self.skipped = 0

    def add(self, rec: dict) -> None:
        rec["id"] = len(self.rows)
        self.counts[rec["k"]] = self.counts.get(rec["k"], 0) + 1
        self.errors += 1 if "err" in rec else 0
        self.rows.append(gr.dumps(rec))


def unmodelled(doc) -> bool:
    """True when the document reaches a methodology value the C# record cannot hold (Python stores whatever type it is given; see `OneZeroMethodologyJson`)."""
    if not isinstance(doc, dict):
        return False
    oz = doc.get("one_zero") or {}
    if not isinstance(oz, dict):
        return False
    block = oz.get("methodology")
    if not block:
        return False
    if not isinstance(block, dict):
        return True
    try:
        OneZeroMethodology.from_pack_json(block)
    except ValueError:
        return False
    except Exception:
        return True
    kinds = {"minimum_pay_period_days": int, "average_decimals": int, "short_periods_excluded_from_numerator": bool, "count_zero_hour_periods": bool,
             "exclude_off_cycle_periods": bool, "pay_period_denominator_mode": str, "min_max_span_mode": str}
    if any(type(block[k]) is not t for k, t in kinds.items() if k in block):
        return True
    return type(block.get("maximum_weeks_without_review", 0)) not in (int, float)


def doc_record(out: Lines, label: str, doc, name: str, kind: str, years: bool) -> None:
    if unmodelled(doc):
        out.skipped += 1
        return
    rec = {"k": "doc", "label": label, "name": name, "kind": kind, "years": years, "doc": doc}
    try:
        rec["schema"] = schema_errors(doc, kind)
    except Exception as e:  # the exception type and message are part of the contract
        rec["schema_err"] = type(e).__name__
        rec["schema_msg"] = str(e)
    try:
        report = pv.validate_document(doc, name, kind, years)
        rec["report"] = report_enc(report, None)
        out.invalid += 0 if report.ok else 1
    except Exception as e:
        rec["err"] = type(e).__name__
        rec["msg"] = str(e)
    out.add(rec)


# --------------------------------------------------------------------------- the corpus


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def real_documents() -> list[tuple[str, object, str, str, bool]]:
    """Every JSON file under backend/rules as (label, doc, name, kind, years_authored)."""
    docs = []
    for path in sorted(RULES.rglob("*.json")):
        rel = path.relative_to(RULES).as_posix()
        doc = read(path)
        stem_year = path.stem.split(".")[0].isdigit()
        kind = "year" if stem_year else "base"
        if rel.count("/") == 0:
            docs.append((f"real:{rel}", doc, path.name, "base", False))
            docs.append((f"real:{rel}", doc, path.name, "base", True))
        elif stem_year:
            docs.append((f"real:{rel}", doc, path.name, "year", True))
        else:
            # lookups, methodology and the schema itself are not packs, but the validator judges whatever it is given
            docs.append((f"real:{rel}", doc, path.name, "base", False))
    return docs


def lab_documents() -> list[tuple[str, object, str, str, bool]]:
    """Every pack of the credit-math lab and ZZ worlds, parsed from the overlay text."""
    docs = []
    for world_name, spec in (("zz", worlds_mod.zz_world()), ("lab", worlds_mod.lab_world())):
        for rel, text in spec["files"].items():
            if text is None or rel == worlds_mod.MANIFEST or not rel.endswith(".json"):
                continue
            try:
                doc = json.loads(text)
            except ValueError:
                continue
            name = rel.rsplit("/", 1)[-1]
            year = name.split(".")[0].isdigit()
            docs.append((f"{world_name}:{rel}", doc, name, "year" if year else "base", year))
    return docs


def scaffold_documents() -> list[tuple[str, object, str, str, bool]]:
    base = ps.base_pack("ZZ_DEMO_JTC", "ZZ", "Zedland demo")
    docs = [("scaffold:base", base, "zz_demo.json", "base", False), ("scaffold:base-years", base, "zz_demo.json", "base", True)]
    for year in (2024, 2025):
        docs.append((f"scaffold:year{year}", ps.year_pack(base, year), f"{year}.draft.json", "year", False))
        docs.append((f"scaffold:year{year}-named", ps.year_pack(base, year), f"{year}.json", "year", True))
    federal = ps.base_pack("ZZ_FED", "US", "Federal demo")
    federal["jurisdiction"]["level"] = "federal"
    docs += [("scaffold:federal", federal, "federal_demo.json", "base", False), ("scaffold:federal-misnamed", federal, "zz_demo.json", "base", False)]
    registry = ps.registry_entry("ZZ_DEMO_JTC", "ZZ", "Zedland demo", "zz_demo.json")
    docs.append(("scaffold:registry-entry", registry, "zz_demo.json", "base", False))
    return docs


def fictional_documents() -> list[tuple[str, object, str, str, bool]]:
    from tests import two_program_world as w

    docs = []
    for code in (w.ALPHA, w.BETA):
        docs.append((f"zz:{code}", w.fictional_pack(code, None), f"{code.lower()}.json", "base", True))
        for year in w.YEARS:
            docs.append((f"zz:{code}:{year}", w.fictional_pack(code, year), f"{year}.json", "year", True))
    return docs


# --------------------------------------------------------------------------- damage menu

STRINGS = ["", " ", "x", "ab", "\u001c", "\u0085", "\u00a0", "\u200b", "\t", "\u000b", "\u001f", "\u1680", "\u2003", "\u2028", "\u2029", "\u202f", "\u205f", "\u3000", "\u180e", "\ufeff", "a b", "AB\n", "AB\n\n", "ab\u0301", "\u0301\u0301", "\u1100\u1161", "\U0001F468\u200d\U0001F469", "\U0001F1EC\U0001F1E7", "a\n", "é", "\U0001F600", "e\u0301", "\U0001F600\U0001F600", "v1.2.3", "1.2.3", "1.2.3+a.b", "1.2.3+",
           "1.2", "v1.2.3\n", "AB_1", "A-B", "ÄB", "ga", "GA", "2025", "2025\n", "２０２５", "annual", "quarterly", "pre-application", "per-hire", "monthly", "begins", "ends",
           "regular", "gross", "all_remuneration", "net", "statewide", "unit", "state", "county", "national", "permitted", "required", "prohibited", "federal", "local", "city"]
NUMBERS = [0, 1, -1, 2, 7, 35, 0.0, -0.0, 0.5, 1.5, 1.0000001, 2025.0, 2025.5, 1989, 1990, 2100, 2101, 1e300, 10 ** 30, 10 ** 400, -(10 ** 30), 5e-324]
OTHERS = [None, True, False, [], {}, [1], ["a"], {"a": 1}, [[]], [{}]]
KEYS_FALSE = ["extends", "inherits", "base", "base_year"]


def paths_of(doc, here=()):
    yield here
    if isinstance(doc, dict):
        for k, v in doc.items():
            yield from paths_of(v, here + (k,))
    elif isinstance(doc, list):
        for i, v in enumerate(doc):
            yield from paths_of(v, here + (i,))


def get_at(doc, path):
    for p in path:
        doc = doc[p]
    return doc


def put(doc, path, value):
    if not path:
        return value
    doc = copy.deepcopy(doc)
    parent = get_at(doc, path[:-1])
    parent[path[-1]] = value
    return doc


def delete(doc, path):
    doc = copy.deepcopy(doc)
    parent = get_at(doc, path[:-1])
    if isinstance(parent, dict):
        del parent[path[-1]]
    else:
        parent.pop(path[-1])
    return doc


def damages(value) -> list:
    """The replacement values tried at a node of this type (ints stay ints, floats floats; the menu is fixed)."""
    pool = list(OTHERS)
    if isinstance(value, bool):
        pool += [0, 1, "true"]
    elif isinstance(value, (int, float)):
        pool += NUMBERS + ["1", "x"]
    elif isinstance(value, str):
        pool += STRINGS + [1, 1.5]
    elif isinstance(value, dict):
        pool += ["x", 1]
    elif isinstance(value, list):
        pool += ["x", 1, {}]
    return pool


def systematic(label: str, doc, name: str, kind: str, years: bool, out: Lines, string_limit: int | None = None) -> None:
    """Damage every node of ``doc`` with every value of the menu, delete it, and add an extra key to every object."""
    for path in paths_of(doc):
        if not path:
            for value in OTHERS + ["x", 1, 1.5]:
                doc_record(out, f"{label}:root={value!r}", value, name, kind, years)
            continue
        text = "/".join(str(p) for p in path)
        doc_record(out, f"{label}:delete {text}", delete(doc, path), name, kind, years)
        value = get_at(doc, path)
        menu = damages(value)
        if string_limit is not None and isinstance(value, str):
            menu = menu[: len(OTHERS) + string_limit]
        for repl in menu:
            doc_record(out, f"{label}:set {text}={repl!r}"[:200], put(doc, path, repl), name, kind, years)
        if isinstance(value, dict):
            doc_record(out, f"{label}:extra {text}", put(doc, path, {**value, "zz_extra": [1]}), name, kind, years)
            doc_record(out, f"{label}:emptied {text}", put(doc, path, {}), name, kind, years)


def false_keys(label: str, doc, name: str, kind: str, years: bool, out: Lines) -> None:
    """The ``extends``/``inherits``/``base``/``base_year`` keys the year schema forbids, with every kind of value."""
    for key in KEYS_FALSE:
        for value in (None, False, 0, "", "a", [], {}, [1], {"a": 1}):
            doc_record(out, f"{label}:forbid {key}={value!r}", {**doc, key: value}, name, kind, years)


def semantic_cases(out: Lines) -> None:
    """Hand-built documents for every branch of the semantic checks (name, models, thresholds, verified claim, flags)."""
    ga = read(RULES / "ga_jtc.json")
    ga25 = read(RULES / "ga_jtc" / "2025.json")
    ny = read(RULES / "ny_excelsior.json")
    fed = read(RULES / "federal_wotc_lite.json")

    def add(label, doc, name="ga_jtc.json", kind="base", years=False):
        doc_record(out, "sem:" + label, doc, name, kind, years)

    stripped = json.loads(json.dumps(ga25))

    def strip_flags(node):
        if isinstance(node, dict):
            node.pop("_prototype_verify", None)
            for v in node.values():
                strip_flags(v)
        elif isinstance(node, list):
            for v in node:
                strip_flags(v)

    strip_flags(stripped)
    for years in (False, True):
        for kind, name, base in (("base", "ga_jtc.json", ga), ("year", "2025.json", ga25)):
            add(f"names:{kind}:{years}", base, name, kind, years)
        for name in ("GA_JTC.json", "ga_jtc", "sc_jtc.json", "ga.json", "", "2025.json", "x.json", "federal_x.json", "ga_.json", "gb_jtc.json"):
            add(f"base-name {name!r}", ga, name, "base", years)
            add(f"fed-name {name!r}", fed, name, "base", years)
        for name in ("2025.json", "2025.draft.json", "2024.json", "x.json", "2025", "", "2025.v2.json", "02025.json", "٢٠٢٥.json"):
            add(f"year-name {name!r}", ga25, name, "year", years)
    # the percentage-of-wages benefit: warning on a base pack with no years, error with years or on a year pack
    for years in (False, True):
        add(f"pct benefit base years={years}", ny, "ny_excelsior.json", "base", years)
        add(f"pct benefit year years={years}", {**ga25, "benefit": ny["benefit"]}, "2025.json", "year", years)
        add(f"both benefit years={years}", {**ga, "benefit": {**ga["benefit"], "amount_per_qualifying_job_pct_of_wages": 0.1}}, "ga_jtc.json", "base", years)
    for benefit in ("amount_per_qualifying_job_pct_of_wages", "xx amount_per_qualifying_job_pct_of_wages xx", "amount_per_qualifying_job_usd", "", "x", 5, 5.5, True, False, 0, None, [], ["a"],
                    ["amount_per_qualifying_job_pct_of_wages"], [1, "amount_per_qualifying_job_pct_of_wages"], {}, {"amount_per_qualifying_job_pct_of_wages": None}):
        add(f"benefit {benefit!r}", {**ga, "benefit": benefit})
        add(f"benefit {benefit!r} year", {**ga25, "benefit": benefit}, "2025.json", "year", True)
    # the methodology block: only the shapes the C# port models (a dict, or a falsy value that means "defaults")
    for methodology in (None, {}, False, 0, "", [], {"bogus": 1}, {"zzz": 1, "aaa": 2, "Mmm": 3}, {"pay_period_denominator_mode": "x"}, {"min_max_span_mode": "y"},
                        {"pay_period_denominator_mode": "frequency_code", "min_max_span_mode": "inclusive_days"}, {"minimum_pay_period_days": -1},
                        {"minimum_pay_period_days": 0}, 
                        {"minimum_pay_period_days": "x"}, {"pay_period_denominator_mode": 5, "min_max_span_mode": None},
                        {"average_decimals": 3, "count_zero_hour_periods": False, "maximum_weeks_without_review": 52, "short_periods_excluded_from_numerator": True,
                         "exclude_off_cycle_periods": True}):
        add(f"methodology {methodology!r}", {**ga, "one_zero": {**ga["one_zero"], "methodology": methodology}})
    # one_zero / thresholds_by_year / tax_year agreement
    oz = ga25["one_zero"]
    by_year = oz.get("thresholds_by_year", {})
    for tax_year in (2025, 2024, 2025.0, 2025.5, "2025", None, True, [2025], 1, 3000):
        add(f"tax_year {tax_year!r}", {**ga25, "tax_year": tax_year}, "2025.json", "year", True)
    for hours in (oz["min_weekly_hours"], 35, 35.0, 36, 34.99, True, 1, "35", None, [35], {"a": 1}, 1e300, 10 ** 30, 35.00000001):
        for wages in (oz["min_weekly_wages"], 0, 0.0, "x", None, 99999):
            block = {"min_weekly_hours": hours, "min_weekly_wages": wages}
            add(f"by_year hours={hours!r} wages={wages!r}", {**ga25, "one_zero": {**oz, "thresholds_by_year": {"2025": block}}}, "2025.json", "year", True)
    for block in ({}, {"min_weekly_hours": oz["min_weekly_hours"]}, {"min_weekly_wages": 0}, {"pt_weight": 0.5}, None, [], "", 0, False):
        add(f"by_year block {block!r}", {**ga25, "one_zero": {**oz, "thresholds_by_year": {"2025": block}}}, "2025.json", "year", True)
    for block in ("min_weekly_hours", "min_weekly_wages min_weekly_hours", ["min_weekly_hours"], 5, 5.5, True, [1]):
        add(f"by_year odd block {block!r}", {**ga25, "one_zero": {**oz, "thresholds_by_year": {"2025": block}}}, "2025.json", "year", True)
    for table in ({}, None, [], "", 0, "2025", ["2025"], 5, True, {"2025": {"min_weekly_hours": 1}, "2024": {"min_weekly_hours": 2}}):
        add(f"by_year table {table!r}", {**ga25, "one_zero": {**oz, "thresholds_by_year": table}}, "2025.json", "year", True)
    for one_zero in (None, {}, [], "", 0, False, "x", [1], 5, 5.5, True):
        add(f"one_zero {one_zero!r}", {**ga, "one_zero": one_zero})
    for other in (None, {}, "", 0, "x", [1], 5, True, [], False):
        add(f"jurisdiction {other!r}", {**ga, "jurisdiction": other})
        add(f"credit {other!r}", {**ga, "credit": other, "_verified": True})
        add(f"provenance {other!r}", {**ga25, "_year_provenance": other, "_verified": True}, "2025.json", "year", True)
        add(f"jurisdiction {other!r} year", {**ga25, "jurisdiction": other}, "2025.json", "year", True)
    for level in ("federal", "state", "local", None, "", 5, ["federal"], "FEDERAL", True):
        for code in ("US", "ga", "GA", None, "", 5, ["GA"], {"a": 1}, "Ünï", 1.5, True):
            add(f"base-jurisdiction {level!r}/{code!r}", {**ga, "jurisdiction": {"level": level, "code": code, "name": "N"}}, "ga_jtc.json" if code in ("ga", "GA") else "us_x.json")
    # the verified claim and the flags
    for verified in (True, False, None, 1, "true", [True], "x", 0):
        add(f"_verified {verified!r} flags", {**ga, "_verified": verified})
        add(f"_verified {verified!r} year flags", {**ga25, "_verified": verified}, "2025.json", "year", True)
        add(f"_verified {verified!r} clean", {**stripped, "_verified": verified}, "2025.json", "year", True)
    for citation in ("", None, "§ 1", 0, [], "x"):
        for source in ("", None, "src", 0, {}, "x"):
            add(f"_verified citation={citation!r} source={source!r}", {**stripped, "_verified": True, "credit": {**stripped["credit"], "statutory_citation": citation},
                                                                      "_year_provenance": {"source": source}}, "2025.json", "year", True)
    add("_verified no provenance key", {k: v for k, v in stripped.items() if k != "_year_provenance"} | {"_verified": True}, "2025.json", "year", True)
    add("_verified no credit key", {k: v for k, v in stripped.items() if k != "credit"} | {"_verified": True}, "2025.json", "year", True)
    for flagged in (True, False, 1, "true", None, [True], {}):
        add(f"flag {flagged!r}", {**ga, "x": {"_prototype_verify": flagged}, "y": [{"_prototype_verify": flagged}, [{"_prototype_verify": flagged}]], "_prototype_verify": flagged})
    add("flag in a flag", {"_prototype_verify": True, "a": {"_prototype_verify": {"_prototype_verify": True}}})
    add("flag keys order", {"b": {"_prototype_verify": True}, "a": {"_prototype_verify": True}, "_prototype_verify": True, "c": [{"_prototype_verify": True}]})
    add("flag unicode key", {"é": {"_prototype_verify": True}, "\U0001F600": [{"_prototype_verify": True}]})
    for value in (None, [], {}, 5, "x", True, 1.5, [1, 2], {"a": 1}):
        add(f"non-dict root {value!r}", value)
        add(f"non-dict root {value!r} year", value, "2025.json", "year", True)
    # a document that is not even an object, and kinds that do not fit the document
    for code in ("ΑΣ", "ΑΣΑ", "Σ", "İX", "ΑΣ.", "A\u0301Σ", "ß", "ǅ", "AB", "ab\U0001F600"):
        add(f"base-code lower {code!r}", {**ga, "jurisdiction": {"level": "state", "code": code, "name": "N"}}, "x.json")
    add("year doc as base", ga25, "2025.json", "base", True)
    add("base doc as year", ga, "ga_jtc.json", "year", False)
    add("kind other", ga, "ga_jtc.json", "bogus", False)


def random_cases(out: Lines, rng: random.Random, count: int) -> None:
    pool = real_documents() + scaffold_documents() + fictional_documents() + lab_documents()
    pool = [p for p in pool if isinstance(p[1], dict) and not p[0].startswith("real:schema/") and not p[0].startswith("scaffold:registry")]
    names_base = [None, "zz_demo.json", "federal_x.json", "ga_jtc.json", "GA_JTC.json", "x.json"]
    names_year = [None, "2025.json", "2024.json", "2025.draft.json", "x.json"]
    for n in range(count):
        label, doc, name, kind, years = rng.choice(pool)
        if kind == "year":
            name = rng.choice(names_year) or name
        else:
            name = rng.choice(names_base) or name
        years = rng.random() < 0.4 or years
        steps = []
        for _ in range(rng.randint(1, 3)):
            path = rng.choice([p for p in paths_of(doc)])
            if not path:
                continue
            action = rng.random()
            if action < 0.2:
                doc = delete(doc, path)
                steps.append(f"del {'/'.join(map(str, path))}")
            else:
                value = get_at(doc, path)
                repl = rng.choice(damages(value))
                doc = put(doc, path, repl)
                steps.append(f"set {'/'.join(map(str, path))}={repl!r}")
            if not isinstance(doc, dict):
                break
        doc_record(out, f"rand:{label}:{';'.join(steps)}"[:300], doc, name, kind, years)


# --------------------------------------------------------------------------- worlds


def own_worlds() -> dict[str, dict]:
    """Rules folders of my own for the registry and year-file consistency rules (overlay on the shipped folder)."""
    mk, entry, pack, dump = worlds_mod.MANIFEST, worlds_mod.entry, worlds_mod.pack, worlds_mod.dump
    ga = read(RULES / "ga_jtc.json")

    def registry(extra):
        data = worlds_mod.shipped_manifest()
        data["programs"].extend(extra)
        return json.dumps(data)

    worlds: dict[str, dict] = {}
    worlds["pv_dup_code"] = {"files": {"zz_dup.json": dump({**ga, "credit": {**ga["credit"]}}), mk: registry([entry("ZZ_DUP", "ZZ", "zz_dup.json")])}, "registry_file": None}
    worlds["pv_unregistered"] = {"files": {"zz_unreg.json": dump(pack("ZZ_UNREG", "ZZ")), "aa_unreg.json": dump(pack("AA_UNREG", "AA"))}, "registry_file": None}
    worlds["pv_mismatch"] = {"files": {"zz_one.json": dump(pack("ZZ_ONE", "ZZ")), mk: registry([entry("ZZ_OTHER", "ZZ", "zz_one.json")]),
                                       "zz_one/2025.json": dump(pack("ZZ_ONE", "ZZ", year=2025))}, "registry_file": None}
    worlds["pv_year_other_program"] = {"files": {"zz_two.json": dump(pack("ZZ_TWO", "ZZ")), mk: registry([entry("ZZ_TWO", "ZZ", "zz_two.json")]),
                                                 "zz_two/2024.json": dump(pack("ZZ_TWO", "ZZ", year=2024)), "zz_two/2025.json": dump(pack("ZZ_OTHER", "ZZ", year=2025)),
                                                 "zz_two/2026.json": dump({**pack("ZZ_TWO", "ZZ", year=2026), "jurisdiction": {"level": "state", "code": "QQ", "name": "N"}}),
                                                 "zz_two/2027.json": dump({**pack("ZZ_TWO", "ZZ", year=2027), "tax_year": 2028})}, "registry_file": None}
    worlds["pv_strays"] = {"files": {"zz_three.json": dump(pack("ZZ_THREE", "ZZ")), mk: registry([entry("ZZ_THREE", "ZZ", "zz_three.json")]),
                                     "zz_three/2025.json": dump(pack("ZZ_THREE", "ZZ", year=2025)), "zz_three/2025.draft.json": dump(pack("ZZ_THREE", "ZZ", year=2025)),
                                     "zz_three/notes.json": "{}", "zz_three/abc.json": "[]", "zz_three/2024.json": "not json", "zz_three/2023.json": "[]",
                                     "zz_three/2022.json": "", "zz_three/2021.json": "{\"tax_year\": 2021}", "zz_three/readme.txt": "x", "10000.json": "{}"}, "registry_file": None}
    worlds["pv_unreadable_base"] = {"files": {"zz_bad.json": "{\"a\": ", "zz_list.json": "[1, 2]", "zz_null.json": "null", "zz_empty.json": "", "zz_bom.json": "\ufeff{}",
                                              "zz_dups.json": "{\"credit\": {\"code\": \"A\"}, \"credit\": {\"code\": \"B\"}}",
                                              "zz_big.json": "{\"x\": " + "9" * 5000 + "}"}, "registry_file": None}
    worlds["pv_same_code_twice"] = {"files": {"zz_a.json": dump(pack("ZZ_SAME", "ZZ")), "zz_b.json": dump(pack("ZZ_SAME", "ZZ")),
                                              mk: registry([entry("ZZ_SAME", "ZZ", "zz_a.json"), entry("ZZ_SAME", "ZZ", "zz_b.json")])}, "registry_file": None}
    for label, credit in (("code_none", {"code": None}), ("code_empty", {"code": ""}), ("code_int", {"code": 5}), ("code_true", {"code": True}), ("code_missing", {}),
                          ("code_list", {"code": ["A"]}), ("code_dict", {"code": {"a": 1}}), ("credit_str", "x"), ("credit_list", [1]), ("credit_zero", 0), ("credit_empty", {})):
        doc = {**pack("ZZ_X", "ZZ"), "credit": credit}
        worlds[f"pv_credit_{label}"] = {"files": {"zz_x.json": dump(doc), mk: registry([entry("ZZ_X", "ZZ", "zz_x.json")])}, "registry_file": None}
    for label, value in (("year_credit_str", "x"), ("year_jur_list", [1]), ("year_credit_none", None), ("year_credit_dict_nocode", {"name": "n"})):
        worlds[f"pv_{label}"] = {"files": {"zz_y.json": dump(pack("ZZ_Y", "ZZ")), mk: registry([entry("ZZ_Y", "ZZ", "zz_y.json")]),
                                           "zz_y/2025.json": dump({**pack("ZZ_Y", "ZZ", year=2025), "credit": value})}, "registry_file": None}
        worlds[f"pv_{label}_jur"] = {"files": {"zz_y.json": dump(pack("ZZ_Y", "ZZ")), mk: registry([entry("ZZ_Y", "ZZ", "zz_y.json")]),
                                               "zz_y/2025.json": dump({**pack("ZZ_Y", "ZZ", year=2025), "jurisdiction": value})}, "registry_file": None}
    return worlds


class World:
    """One rules folder on disk (the shipped one, or a scratch copy with an overlay applied), entered through ``RULES_DIR``."""

    def __init__(self, name: str, spec: dict | None) -> None:
        self.name = name
        self.spec = spec or {"files": {}, "registry_file": None}
        self.rules = RULES.resolve()
        self.registry: Path | None = None
        if spec is not None:
            d = SCRATCH / name
            shutil.copytree(RULES, d)
            for rel, text in spec["files"].items():
                p = d / rel
                if text is None:
                    p.unlink(missing_ok=True)
                    continue
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(text.encode("utf-8"))
            self.rules = d.resolve()
            self.registry = (d / spec["registry_file"]).resolve() if spec.get("registry_file") else None

    def run(self, fn):
        saved = {k: os.environ.get(k) for k in ("RULES_DIR", "PROGRAM_REGISTRY_FILE")}
        for k in saved:
            os.environ.pop(k, None)
        if self.name != "shipped":
            os.environ["RULES_DIR"] = str(self.rules)
            if self.registry:
                os.environ["PROGRAM_REGISTRY_FILE"] = str(self.registry)
        try:
            return fn()
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


def world_records(out: Lines) -> dict:
    specs = {n: s for n, s in worlds_mod.all_worlds().items() if n != "shipped"}
    specs.update(own_worlds())
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir()
    try:
        for name, spec in {"shipped": None, **specs}.items():
            world = World(name, spec)
            rec = {"k": "all", "world": name}
            try:
                reports = world.run(lambda: pv.validate_all())
                rec["reports"] = [report_enc(r, world.rules) for r in reports]
                out.invalid += sum(0 if r.ok else 1 for r in reports)
            except Exception as e:
                rec["err"] = type(e).__name__
                rec["msg"] = norm(str(e), world.rules)
            out.add(rec)
            if name in ("shipped", "pv_strays", "pv_unreadable_base"):
                files = sorted(p for p in world.rules.rglob("*.json") if "schema" not in p.relative_to(world.rules).parts)
                for path in files:
                    for years in (False, True):
                        rel = path.relative_to(world.rules).as_posix()
                        prec = {"k": "pack", "world": name, "path": rel, "years": years}
                        try:
                            prec["report"] = report_enc(world.run(lambda p=path, y=years: pv.validate_pack(p, years_authored=y)), world.rules)
                        except Exception as e:
                            prec["err"] = type(e).__name__
                            prec["msg"] = norm(str(e), world.rules)
                        out.add(prec)
        return specs
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    out = Lines()
    for label, doc, name, kind, years in real_documents() + scaffold_documents() + fictional_documents() + lab_documents():
        doc_record(out, label, doc, name, kind, years)
    semantic_cases(out)
    ga = read(RULES / "ga_jtc.json")
    ga25 = read(RULES / "ga_jtc" / "2025.json")
    from tests import two_program_world as w

    systematic("sys:ga_jtc", ga, "ga_jtc.json", "base", True, out, string_limit=24)
    systematic("sys:ga_jtc/2025", ga25, "2025.json", "year", True, out, string_limit=24)
    systematic("sys:zz_alpha", w.fictional_pack(w.ALPHA, None), "zz_alpha_jtc.json", "base", False, out)
    systematic("sys:zz_alpha/2025", w.fictional_pack(w.ALPHA, 2025), "2025.json", "year", False, out)
    false_keys("sys:forbid", ga25, "2025.json", "year", True, out)
    false_keys("sys:forbid-base", ga, "ga_jtc.json", "base", True, out)
    random_cases(out, rng, 2500)
    docs = out.counts.get("doc", 0)
    specs = world_records(out)
    meta = {"k": "meta", "seed": seed, "docs": docs, "records": len(out.rows), "errors": out.errors, "invalid_reports": out.invalid, "skipped_unmodelled_methodology": out.skipped, "counts": out.counts,
            "schema_version": pv.schema_version(), "jsonschema": __import__("importlib.metadata").metadata.version("jsonschema"), "worlds": specs, **oracle.stamp()}
    lines = [gr.dumps(meta)] + out.rows
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
        print("pack_validation golden is current" if ok else "STALE pack_validation golden", file=sys.stderr)
        return 0 if ok else 1
    args.out.write_bytes(data)
    print(f"wrote {args.out} ({len(data)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
