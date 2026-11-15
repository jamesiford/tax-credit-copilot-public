"""Golden vectors for the rule-pack tools (stage DS7): ``tools/credit_math.py``, ``tools/program_credit.py``,
``tools/program_registry.py``, ``tools/pack_lookup.py`` and ``tools/one_zero_pack.py`` (plus the two pure helpers they
lean on: ``OneZeroMethodology.from_pack_json`` and the offline half of ``rules_ingestion.ingested_one_zero``).

Every call goes to the PRODUCTION function with the rules folder pointed (``RULES_DIR`` / ``PROGRAM_REGISTRY_FILE``) at a
*world*: the shipped ``backend/rules`` plus an overlay built in ``credit_math_worlds.py`` (the two-program ZZ world of
``tests/two_program_world.py``, a retired program, reversed registry order, a moved manifest, broken manifests, and a lab
of invented programs, one per shape the shipped packs lack). The overlay files are written to the golden's meta line so
the C# replay rebuilds the identical folder in memory; no rule file is ever copied. The scratch folders live under
``parity/.scratch-credit-math`` and are removed on exit.

Recorded per call: the arguments, the result tree (floats keep their ``repr``, ints stay ints, so int-versus-float
shows at every step), the exception type and message, and, for the credit functions, the calculation trail the call
recorded (with its SHA-256) plus every payroll-wage lookup it made (``avg_program_wage`` reads a CSV, which is I/O and
not ported; the replay serves the recorded wage back). Messages that carry a path say ``<RULES>`` / ``<REGISTRY>``.

Usage: python parity/export_credit_math.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import contextlib
import copy
import json
import math
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
from domain.calculation.onezero import OneZeroMethodology  # noqa: E402
from domain.calculation.trail import TrailRecorder, reset_recorder, set_recorder  # noqa: E402
from tools import credit_math as cm  # noqa: E402
from tools import one_zero_pack as ozp  # noqa: E402
from tools import pack_lookup as pl  # noqa: E402
from tools import program_credit as pc  # noqa: E402
from tools import program_registry as pr  # noqa: E402
from tools import rules_ingestion as ri  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "credit_math.jsonl.gz"
SCRATCH = Path(__file__).resolve().parent / ".scratch-credit-math"
SEED = 20261118
INF = float("inf")
NAN = float("nan")
YEARS = [None, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026, 2027, 2030, 0, -1]
LAB_YEARS = [None, 2024, 2025, 2026, 2027, 2028, 2029, 2030, 2031, 2032, 2033, 2034, 2035, 42, 0, 2036]
HEAD = {"k": "head"}


# --------------------------------------------------------------------------- worlds


class Worlds:
    """Materialises each world once and enters it (environment variables) for the duration of a call."""

    def __init__(self, specs: dict[str, dict]) -> None:
        self.specs = specs
        self.dirs: dict[str, Path] = {"shipped": worlds_mod.RULES.resolve()}
        self.registry: dict[str, Path | None] = {"shipped": None}

    def build(self, name: str, spec: dict) -> None:
        d = SCRATCH / name
        shutil.copytree(worlds_mod.RULES, d)
        for rel, text in spec["files"].items():
            p = d / rel
            if text is None:
                p.unlink(missing_ok=True)
                continue
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(text.encode("utf-8"))
        self.dirs[name] = d.resolve()
        self.registry[name] = (d / spec["registry_file"]).resolve() if spec.get("registry_file") else None

    @contextlib.contextmanager
    def enter(self, name: str):
        rules = self.dirs.get(name)
        saved = {k: os.environ.get(k) for k in ("RULES_DIR", "PROGRAM_REGISTRY_FILE")}
        for k in saved:
            os.environ.pop(k, None)
        if name != "shipped":
            os.environ["RULES_DIR"] = str(rules)
            if self.registry[name]:
                os.environ["PROGRAM_REGISTRY_FILE"] = str(self.registry[name])
        try:
            yield rules, self.registry[name]
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None)
                if v is not None:
                    os.environ[k] = v


def norm(text: str, rules: Path | None, registry: Path | None) -> str:
    """Replace machine paths in a message by placeholders (the registry file first: it sits inside the rules folder)."""
    for path, mark in ((registry, "<REGISTRY>"), (rules, "<RULES>")):
        if path is not None:
            text = text.replace(str(path), mark)
    return text


class Rec(gr.Recorder):
    """``golden_rec.Recorder`` whose arguments are encoded AFTER the run (the run may add what it observed, e.g. wages)."""

    def __init__(self, worlds: Worlds) -> None:
        super().__init__()
        self.worlds = worlds

    def call(self, fn: str, args: dict, run) -> None:
        with self.worlds.enter(args["world"]) as (rules, registry):
            try:
                rec = {"k": "call", "id": len(self.lines), "fn": fn, "out": gr.enc(run())}
            except Exception as e:  # the exception type and message are part of the contract
                self.errors += 1
                rec = {"k": "call", "id": len(self.lines), "fn": fn, "err": type(e).__name__, "msg": norm(str(e), rules, registry)}
        self.counts[fn] = self.counts.get(fn, 0) + 1
        self.lines.append((gr.dumps(gr.enc(args)), rec))


# --------------------------------------------------------------------------- observation helpers


def registry_summary(reg: pr.Registry, rules: Path | None) -> dict:
    return {
        "entries": [gr.enc(e) for e in reg.entries], "active": [e.code for e in reg.active()],
        "code_to_pack": [[k, v] for k, v in reg.code_to_pack().items()], "state_to_pack": [[k, v] for k, v in reg.state_to_pack().items()],
        "federal": [e.code for e in reg.federal()], "rules_dir": "<RULES>", "source": reg.source.name,
    }


@contextlib.contextmanager
def ingestion(spec):
    """``None`` keeps the real captured configs; otherwise ``{"none":1}``, ``{"raises":1}`` or ``{"value": dict}`` replace the hook."""
    if spec is None:
        yield []
        return
    calls: list = []
    original = ri.ingested_one_zero

    def fake(key, tax_year=None):
        calls.append([key, tax_year])
        if spec.get("raises"):
            raise RuntimeError("ingestion is down")
        return copy.deepcopy(spec.get("value"))

    ri.ingested_one_zero = fake
    try:
        yield calls
    finally:
        ri.ingested_one_zero = original


@contextlib.contextmanager
def wages(args: dict, override):
    """Records every ``avg_program_wage`` lookup into ``args['wage_calls']``; an override replaces the CSV value."""
    seen: list = []
    original = pc.avg_program_wage

    def spy(key):
        value = original(key) if override is None else override
        seen.append([key, value])
        return value

    pc.avg_program_wage = spy
    try:
        yield
    finally:
        pc.avg_program_wage = original
        args["wage_calls"] = seen


def traced(args: dict, body):
    """Runs ``body`` inside the trail recorder and wage spy the arguments ask for; returns ``{"result", "trail"?}``."""
    spec = args.get("trail")
    recorder = TrailRecorder(title=spec["title"], citation=spec["citation"]) if spec is not None else None
    token = set_recorder(recorder) if recorder is not None else None
    try:
        with wages(args, args.get("wage_override")):
            result = body()
    finally:
        if token is not None:
            reset_recorder(token)
    out = {"result": result}
    if recorder is not None:
        out["trail"] = recorder.to_dict()
    return out


# --------------------------------------------------------------------------- registry and lookups


PARSE_BASE = {"code": "XX_TEST", "name": "Test", "jurisdiction": {"level": "state", "code": "XX"}, "state": "XX",
              "pack_file": "ga_jtc.json", "lifecycle": "described"}


def entry_variants() -> list[dict]:
    b = PARSE_BASE
    out = [b]
    for k in ("code", "name", "jurisdiction", "pack_file"):
        for v in (None, "", 0, False, [], {}):
            out.append({**b, k: v})
        out.append({kk: vv for kk, vv in b.items() if kk != k})
    out += [{**b, "code": 123}, {**b, "code": "ga_jtc"}, {**b, "code": "Straße"}, {**b, "name": 5}, {**b, "pack_file": 5}, {**b, "pack_file": "nope.json"},
            {**b, "pack_file": "registry"}, {**b, "pack_file": "registry/../ga_jtc.json"}, {**b, "pack_file": "ga_jtc"}, {**b, "pack_file": "lookups/industry_type.v1.json"}]
    for jur in ("state", ["a"], 5, None, {"level": "galaxy", "code": "XX"}, {"level": None, "code": "XX"}, {"level": "state"}, {"level": "state", "code": ""},
                {"level": "state", "code": 5}, {"level": "local", "code": "XX"}, {"level": "federal", "code": "US"}, {"code": "XX"}, {"level": "State", "code": "XX"}):
        out.append({**b, "jurisdiction": jur})
    for st in (None, "", " xx ", "xx", "x\u00df", "Straße", 5, False, "ǆ", "\U00010000"):
        out.append({**b, "state": st})
        out.append({**b, "state": st, "jurisdiction": {"level": "federal", "code": "US"}})
        out.append({**b, "state": st, "jurisdiction": {"level": "local", "code": "XX"}})
    for lc in ("described", "draft", "retired", "calculable", "", "Retired", None, 5, False, "live", " draft"):
        out.append({**b, "lifecycle": lc})
        out.append({**b, "lifecycle": lc, "pack_file": "nope.json"})
    out.append({k: v for k, v in b.items() if k != "lifecycle"})
    for prof in (None, {}, [], "x", 5, {"credit_model": "per_net_new_job"}, {"credit_model": "pct_of_wages"}, {"headcount_model": "fte"}, {"credit_model": 5},
                 {"credit_model": None}, {"headcount_model": ""}, {"credit_model": "per_net_new_job", "headcount_model": "one_zero", "extra": 1},
                 {"headcount_model": "one_zero", "credit_model": "x"}):
        out.append({**b, "engine_profile": prof})
    for notes in ("n", None, 5, "", ["x"]):
        out.append({**b, "notes": notes})
    return out


def parse_texts() -> list[str]:
    def doc(programs, version=1):
        return json.dumps({"schema_version": version, "programs": programs})

    texts = [doc([e]) for e in entry_variants()]
    texts += [doc([]), doc([PARSE_BASE, PARSE_BASE]), doc([PARSE_BASE, {**PARSE_BASE, "code": "XX_TEST2"}, {**PARSE_BASE, "code": "xx_test"}]),
              doc([{**PARSE_BASE, "code": "A"}, {**PARSE_BASE, "code": "B", "pack_file": "sc_jtc.json"}, {**PARSE_BASE, "code": "C", "state": "YY"}]),
              doc([PARSE_BASE], 2), doc([PARSE_BASE], "1"), doc([PARSE_BASE], 1.0), doc([PARSE_BASE], True), doc([PARSE_BASE], None), doc([PARSE_BASE], 0),
              doc({}), doc(None), doc("x"), doc(5), doc([5]), doc([None]), doc(["x"]), doc([[1]]),
              "", "{", "}", "nul", "[1,", '{"a":}', '{"schema_version": 1, "programs": [}', "[]", "[1]", "null", "1", '"x"', "{}", '{"programs": []}',
              '{"schema_version": 1}', '{"schema_version": 1, "programs": null}', '{"schema_version": NaN, "programs": []}', '{"schema_version": 1, "schema_version": 2, "programs": []}',
              '{"schema_version": 1, "programs": [], "programs": [1]}', "\ufeff{}", '{"schema_version": 1, "programs": []} x', '{"schema_version": 1e0, "programs": []}',
              '{"schema_version": 1, "programs": [{"code": "A\u00e9", "name": "n", "jurisdiction": {"level": "state", "code": "XX"}, "state": "xx", "pack_file": "ga_jtc.json"}]}',
              '{"a": ' + "9" * 5000 + "}", "\t\n {}", '{"schema_version": 1, "programs": []}\n']
    return texts


def registry_cases(rec: Rec, world_names: list[str]) -> None:
    rules_src = {"shipped", "zz", "lab"}
    for text in parse_texts():
        for w in sorted(rules_src & set(world_names)) if len(text) < 2000 else ["shipped"]:
            def run(text=text):
                rules = rec.worlds.dirs.get(w)
                reg = pr.parse_registry(text, Path("programs.json"), rules or worlds_mod.RULES)
                return registry_summary(reg, rules)

            rec.call("parse_registry", {"world": w, "text": text}, run)
    for w in world_names:
        rec.call("load_registry", {"world": w}, lambda w=w: registry_summary(pr.load_registry(), None))
        rec.call("registry_views", {"world": w}, lambda: {"state": [[k, v] for k, v in cm.STATE_TO_PACK.items()], "code": [[k, v] for k, v in cm.PROGRAM_CODE_TO_PACK.items()],
                                                          "state_len": len(cm.STATE_TO_PACK), "code_len": len(cm.PROGRAM_CODE_TO_PACK),
                                                          "state_equals": cm.STATE_TO_PACK == dict(cm.STATE_TO_PACK.items())})
    keys = ["GA", "ga", "GA_JTC", "ga_jtc", "TX", "", "FED_WOTC", "VA", "VA_MBJF", "ZZ", "zz", "ZZ_ALPHA_JTC", "zz_beta_jtc", "ZL", "ZL_FLAT", "ZL_RETIRED", "ZM_DRAFT",
            "FED_LAB", "NY", " GA", "Ga_Jtc", "straße", "\U00010000", "ZN_YS", "XX"]
    for w in world_names:
        for key in keys:
            rec.call("registry_get", {"world": w, "code": key}, lambda key=key: gr.enc(pr.load_registry().get(key)))
            rec.call("registry_for_state", {"world": w, "state": key}, lambda key=key: [gr.enc(e) for e in pr.load_registry().for_state(key)])
            rec.call("programs_for_state", {"world": w, "state": key}, lambda key=key: [gr.enc(e) for e in pr.programs_for_state(key)])
            rec.call("program_for_code", {"world": w, "code": key}, lambda key=key: gr.enc(pr.program_for_code(key)))
            for view in ("state", "code"):
                v = lambda view=view: cm.STATE_TO_PACK if view == "state" else cm.PROGRAM_CODE_TO_PACK
                rec.call("view_lookup", {"world": w, "view": view, "key": key}, lambda v=v, key=key: {"contains": key in v(), "get": v().get(key), "item": v()[key]})
        for key in (None, 0):
            rec.call("registry_get", {"world": w, "code": key}, lambda key=key: gr.enc(pr.load_registry().get(key)))
            rec.call("registry_for_state", {"world": w, "state": key}, lambda key=key: [gr.enc(e) for e in pr.load_registry().for_state(key)])
    for w in world_names:
        for key in keys + [None]:
            rec.call("pack_file_for", {"world": w, "key": key}, lambda key=key: pl.pack_file_for(key))
            rec.call("state_of", {"world": w, "key": key}, lambda key=key: pc.state_of(key) if key is not None else pc.state_of(""))
    for a, b in ((None, "GA"), ("", "GA"), ("ZZ_ALPHA_JTC", "ZZ"), ("x", ""), (None, None)):
        rec.call("credit_key", {"world": "shipped", "program_code": a, "state": b}, lambda a=a, b=b: pc.credit_key(a, b))


def sequences(rec: Rec) -> None:
    """The registry cache is call-history: keyed by (file, folder), refreshed only when the manifest's mtime changes."""
    manifest = worlds_mod.MANIFEST
    shipped = json.dumps(worlds_mod.shipped_manifest())
    va = json.loads(shipped)
    for e in va["programs"]:
        if e["code"] == "VA_MBJF":
            e["lifecycle"] = "retired"
    retired = json.dumps(va)
    plans = {
        "hit": [("stamp", 100), ("load",), ("load",)],
        "refresh": [("stamp", 100), ("load",), ("set", retired, 101), ("load",), ("load",)],
        "same_stamp_is_stale": [("stamp", 100), ("load",), ("set", retired, 100), ("load",)],
        "back_in_time": [("stamp", 100), ("load",), ("set", retired, 50), ("load",), ("set", shipped, 51), ("load",)],
        "bad_then_good": [("stamp", 100), ("load",), ("set", "{", 101), ("load",), ("load",), ("set", shipped, 102), ("load",)],
        "bad_first_then_same_stamp": [("stamp", 100), ("set", "{", 101), ("load",), ("set", shipped, 101), ("load",)],
        "deleted": [("stamp", 100), ("load",), ("delete",), ("load",), ("set", retired, 7), ("load",)],
        "pack_added_later": [("stamp", 100), ("set", json.dumps({"schema_version": 1, "programs": [worlds_mod.entry("ZS_NEW", "ZS", "zs_new.json")]}), 101), ("load",),
                              ("file", "zs_new.json", json.dumps(worlds_mod.pack("ZS_NEW", "ZS"))), ("load",), ("set", json.dumps({"schema_version": 1, "programs": [worlds_mod.entry("ZS_NEW", "ZS", "zs_new.json")]}), 102), ("load",)],
    }
    for n, (name, raw_steps) in enumerate(plans.items()):
        # NTFS keeps modification times in 100 ns ticks, so stamps are whole milliseconds: 100 and 101 ns would be the same tick.
        steps = [(s[0], s[1] * 1_000_000) if s[0] == "stamp" else (s[0], s[1], s[2] * 1_000_000) if s[0] == "set" else s for s in raw_steps]
        world = f"seq{n}"
        d = SCRATCH / world
        shutil.copytree(worlds_mod.RULES, d)
        rec.worlds.dirs[world] = d.resolve()
        rec.worlds.registry[world] = None
        rec.worlds.specs[world] = {"files": {}, "registry_file": None}

        def run(steps=steps, d=d, world=world):
            out, previous = [], None
            path = d / manifest
            for step in steps:
                op = step[0]
                if op == "stamp":
                    os.utime(path, ns=(step[1], step[1]))
                    out.append({"op": "stamp"})
                elif op == "set":
                    path.write_bytes(step[1].encode("utf-8"))
                    os.utime(path, ns=(step[2], step[2]))
                    out.append({"op": "set"})
                elif op == "file":
                    (d / step[1]).write_bytes(step[2].encode("utf-8"))
                    out.append({"op": "file"})
                elif op == "delete":
                    path.unlink()
                    out.append({"op": "delete"})
                else:
                    try:
                        reg = pr.load_registry()
                        rec_out = {"op": "load", "registry": registry_summary(reg, d), "same_as_previous": reg is previous}
                        previous = reg
                    except Exception as e:
                        rec_out = {"op": "load", "err": type(e).__name__, "msg": norm(str(e), d.resolve(), None)}
                    out.append(rec_out)
            return out

        rec.call("registry_sequence", {"world": world, "name": name, "steps": [list(s) for s in steps]}, run)


# --------------------------------------------------------------------------- packs, floors, convention


PACK_FILES_ODD = ["", ".json", "registry.json", "lookups.json", "schema.json", "methodology.json", "nope.json", "ga_jtc", "ga_jtc.json.json", "x.y.json"]
# The other JSON files under rules/ are not rule packs (assumption sets, lookups, the schema, the manifest): they read as flat documents.
OTHER_RULE_FILES = sorted(p.relative_to(worlds_mod.RULES).as_posix() for sub in ("methodology", "lookups", "schema", "registry") for p in (worlds_mod.RULES / sub).glob("*.json"))


def packs_cases(rec: Rec, world_names: list[str]) -> None:
    shipped = [e["pack_file"] for e in worlds_mod.shipped_manifest()["programs"]]
    files = {"shipped": shipped + PACK_FILES_ODD + OTHER_RULE_FILES}
    files["zz"] = files["zz_one"] = files["zz_rev"] = files["shipped"] + ["zz_alpha_jtc.json", "zz_beta_jtc.json"]
    files["retired"] = files["shipped"]
    lab_programs = json.loads(worlds_mod.lab_world()["files"][worlds_mod.MANIFEST])["programs"]
    files["lab"] = files["shipped"] + [e["pack_file"] for e in lab_programs if e["code"].startswith(("Z", "FED_LAB"))]
    for w in world_names:
        pack_files = files.get(w, files["shipped"][:12])
        years = LAB_YEARS if w == "lab" else YEARS
        for f in dict.fromkeys(pack_files):
            rec.call("authored_years", {"world": w, "pack_file": f}, lambda f=f: cm.authored_years(f))
            rec.call("is_year_scoped", {"world": w, "pack_file": f}, lambda f=f: cm.is_year_scoped(f))
            if f.endswith(".json"):  # `_load_pack("ga_jtc")` reads a folder: a PermissionError whose message is a machine path
                rec.call("load_pack_flat", {"world": w, "pack_file": f}, lambda f=f: cm._load_pack(f))
            for y in ([None, 2023] if f in OTHER_RULE_FILES else years):
                if not f and y is None:
                    continue
                rec.call("load_year_pack", {"world": w, "pack_file": f, "tax_year": y},
                         lambda f=f, y=y: (lambda r: {"pack": r[0], "year_resolved": r[1]})(cm.load_year_pack(f, y)))
    for w in world_names:
        codes = registry_codes(rec, w) + ["NOPE", "", "ga_jtc", "GA", "XX", "ZZ_ALPHA_JTC", "ZZ_BETA_JTC"]
        years = LAB_YEARS if w == "lab" else YEARS + [2031, 2032, 2033, 2034, 2035, 42, 2 ** 31]
        for code in dict.fromkeys(codes):
            for y in years:
                rec.call("resolve_statutory_floors", {"world": w, "program_code": code, "tax_year": y},
                         lambda code=code, y=y: (lambda f: {"fields": gr.enc(f), "as_dict": f.as_dict(), "prototype_verify": f.prototype_verify})(cm.resolve_statutory_floors(code, y)))
                rec.call("resolve_tax_year_convention", {"world": w, "program_code": code, "tax_year": y},
                         lambda code=code, y=y: cm.resolve_tax_year_convention(code, y))
            rec.call("resolve_tax_year_convention", {"world": w, "program_code": code, "tax_year": None}, lambda code=code: cm.resolve_tax_year_convention(code))

def registry_codes(rec: Rec, world: str) -> list[str]:
    with rec.worlds.enter(world):
        try:
            return [e.code for e in pr.load_registry().entries]
        except Exception:
            return []


# --------------------------------------------------------------------------- One/Zero packs


def ingestion_specs() -> list[dict | None]:
    full = {"min_weekly_hours": 41.0, "min_weekly_wages": 999.5, "wage_basis": "all_remuneration", "measuring_date": "15",
            "included_pay_codes": ["Regular", "Tips"], "excluded_pay_codes": ["Mileage", "Relocation"], "source": "rules_ingested", "provenance": []}
    return [None, {"none": 1}, {"raises": 1}, {"value": {}}, {"value": full}, {"value": {**full, "included_pay_codes": []}},
            {"value": {**full, "included_pay_codes": None, "excluded_pay_codes": None}},
            {"value": {"wage_basis": "x"}}, {"value": {"min_weekly_hours": 41.0}}, {"value": {"min_weekly_hours": 41.0, "min_weekly_wages": 5.0}},
            {"value": {"min_weekly_hours": 41.0, "min_weekly_wages": 5.0, "wage_basis": None, "measuring_date": None}},
            {"value": {"min_weekly_hours": "x", "min_weekly_wages": 5.0}}]


def one_zero_cases(rec: Rec, world_names: list[str], rng: random.Random) -> None:
    for w in world_names:
        if w in ("nomanifest", "badjson", "badschema", "badprograms", "emptyprograms", "bom"):
            continue
        keys = registry_codes(rec, w)
        states = sorted({k[:2] for k in keys} | {"TX", "ZZ"})
        years = LAB_YEARS if w == "lab" else YEARS + [2031, 42]
        for key in dict.fromkeys(keys + states + [k.lower() for k in keys[:3]] + ["", "NOPE", "BOGUS_CODE", "ga", " GA", "Straße"]):
            for y in years:
                for spec in ([None, {"none": 1}] if w != "shipped" or key.upper() not in ("GA", "GA_JTC", "TN", "TN_JTC") else ingestion_specs()[:3]):
                    def run(key=key, y=y, spec=spec):
                        with ingestion(spec) as calls:
                            pack = cm.load_pack_one_zero(key, y)
                        return {"pack": gr.enc(pack), "ingestion_calls": calls}

                    rec.call("load_pack_one_zero", {"world": w, "key": key, "tax_year": y, "ingestion": spec}, run)
    for w, keys, years in (("shipped", ["GA", "GA_JTC", "TN", "SC"], [None, 2023, 2024, 2025]), ("lab", ["ZL_FLAT", "ZN_YS", "ZL_PCT", "FED_LAB", "ZP_BANDMIN"], [None, 2024, 2025, 2026]),
                           ("zz", ["ZZ_ALPHA_JTC", "ZZ"], [None, 2025])):
        for key in keys:
            for y in years:
                for spec in ingestion_specs()[3:]:
                    def run(key=key, y=y, spec=spec):
                        with ingestion(spec) as calls:
                            pack = cm.load_pack_one_zero(key, y)
                        return {"pack": gr.enc(pack), "ingestion_calls": calls}

                    rec.call("load_pack_one_zero", {"world": w, "key": key, "tax_year": y, "ingestion": spec}, run)
    for key in ("GA", "ga", "GA_JTC", "TN", "TN_JTC", "tn", "SC", "", "NY", "FED_WOTC"):
        for y in (None, 2018, 2019, 2023, 2024, 2025, 2026, 2030, 0, -1):
            def run(key=key, y=y):
                out = ri.ingested_one_zero(key, tax_year=y)
                if out is not None:
                    out.pop("provenance", None)
                return out

            rec.call("ingested_one_zero", {"world": "shipped", "key": key, "tax_year": y}, run)
    build_cases(rec, rng)


def doc_pool() -> list[tuple[str, dict]]:
    pool: list = []
    for p in sorted(worlds_mod.RULES.glob("*.json")):
        pool.append((p.name, json.loads(p.read_text("utf-8"))))
    for p in sorted(worlds_mod.RULES.glob("ga_jtc/*.json")):
        pool.append((f"ga_jtc/{p.name}", json.loads(p.read_text("utf-8"))))
    for rel in OTHER_RULE_FILES:
        pool.append((rel, json.loads((worlds_mod.RULES / rel).read_text("utf-8"))))
    from tests import draft_world as dw, two_program_world as tw

    docs = dw.documents()
    pool += [("draft/pack", docs["pack"]), ("draft/2024", docs["years"]["2024"]), ("draft/broken", dw.broken(docs)["pack"]),
             ("zz/alpha", tw.fictional_pack(tw.ALPHA, None)), ("zz/beta2025", tw.fictional_pack(tw.BETA, 2025))]
    lab = worlds_mod.lab_world()
    for rel, text in sorted(lab["files"].items()):
        if rel.endswith(".json") and rel != worlds_mod.MANIFEST:
            pool.append((f"lab/{rel}", json.loads(text)))
    return pool


def one_zero_variants(rng: random.Random) -> list[dict]:
    base = {"min_weekly_hours": 35.0, "min_weekly_wages": 680.0, "wage_basis": "all_remuneration", "geographic_granularity": "unit", "pt_aggregation": False,
            "headcount_unit_field": "Worksite_ID", "measuring_date": "last_day", "entity_combination": "permitted"}
    out = [base, {}, {"min_weekly_hours": 35}, {"min_weekly_hours": 35, "min_weekly_wages": 680}, {"min_weekly_hours": "35", "min_weekly_wages": "680.5"},
           {"min_weekly_hours": True, "min_weekly_wages": False}, {"min_weekly_hours": None, "min_weekly_wages": 1.0}, {"min_weekly_hours": 1.0, "min_weekly_wages": None},
           {"min_weekly_hours": 1.0, "min_weekly_wages": [1]}, {"min_weekly_hours": [1]}, {"min_weekly_hours": "x"}, {"min_weekly_hours": 10 ** 30, "min_weekly_wages": 1e300},
           {"min_weekly_hours": 10 ** 400}, {"min_weekly_hours": NAN, "min_weekly_wages": INF}, {"min_weekly_hours": 1}, {"min_weekly_hours": -0.0, "min_weekly_wages": -5}]
    for k, vals in (("wage_basis", ("regular", None, 5, True, "")), ("geographic_granularity", ("county", None, 0)), ("pt_aggregation", (True, 1, 0, None, "x", "", [], [1], {})),
                    ("headcount_unit_field", ("Site", None, 3.5)), ("measuring_date", ("15", None, 15, 15.0, "", False)),
                    ("entity_combination", ("required", "prohibited", None, 7)), ("pt_band_hours", ([20, 32], [20.5, 31.5], [], [20], [20, 32, 40], [0, 0], None, [None, 1], ["20", "32"], [True, False], [1e300, 1e-300], [NAN, 1])),
                    ("pt_weight", (0.5, 0, 0.0, 1, None, "0.5", "", "x", [1], True, NAN, 10 ** 30)), ("tax_year", (2024, "x"))):
        for v in vals:
            out.append({**base, k: v})
    for m in (None, {}, [], {"minimum_pay_period_days": 3}, {"minimum_pay_period_days": 0}, {"minimum_pay_period_days": -1}, {"unknown": 1}, {"b": 1, "a": 2, "minimum_pay_period_days": 7},
              {"pay_period_denominator_mode": "frequency_code"}, {"pay_period_denominator_mode": "weird"}, {"pay_period_denominator_mode": 5}, {"min_max_span_mode": "inclusive_days"},
              {"min_max_span_mode": "x"}, {"minimum_pay_period_days": "x"}, {"minimum_pay_period_days": None}, {"minimum_pay_period_days": [1]},
              {"count_zero_hour_periods": False}, {"short_periods_excluded_from_numerator": True}, {"average_decimals": 3}, {"average_decimals": 0}, {"maximum_weeks_without_review": 52},
              {"maximum_weeks_without_review": 52.5}, {"exclude_off_cycle_periods": True},
              {"minimum_pay_period_days": 5, "average_decimals": 3, "count_zero_hour_periods": False, "maximum_weeks_without_review": 52,
               "pay_period_denominator_mode": "frequency_code", "min_max_span_mode": "inclusive_days", "exclude_off_cycle_periods": True,
               "short_periods_excluded_from_numerator": True},
              {"Minimum_Pay_Period_Days": 1}, {"zz": 1, "yy": 2, "aa": 3}, {"min_max_span_mode": "inclusive_days", "pay_period_denominator_mode": "q", "minimum_pay_period_days": -3}):
        out.append({**base, "methodology": m})
    for _ in range(300):
        v = dict(base)
        v["min_weekly_hours"] = rng.choice([35, 35.0, 37.5, 40, 0, 12.25, 1e-9])
        v["min_weekly_wages"] = rng.choice([680, 680.0, 686.25, 0, 0.0, 1e6, 12.5])
        if rng.random() < 0.4:
            v["pt_band_hours"] = rng.choice([[20, 32], [20.0, 32.0], [19.5, 34.25]])
            v["pt_weight"] = rng.choice([0.5, 0.25, 0.75, 1, 0])
        if rng.random() < 0.3:
            v["pay_code_policy"] = {"included_pay_codes": rng.choice([["Regular"], [], None, ["Regular", "Bonus"]]), "excluded_pay_codes": rng.choice([["Mileage"], [], None])}
        if rng.random() < 0.3:
            v["methodology"] = rng.choice([{"minimum_pay_period_days": rng.randint(-2, 20)}, {"average_decimals": rng.randint(0, 5)}, {"count_zero_hour_periods": rng.random() < 0.5}])
        out.append(v)
    return out


def build_cases(rec: Rec, rng: random.Random) -> None:
    pool = doc_pool()
    for name, doc in pool:
        for y in (None, 2023, 2025):
            rec.call("pack_from_document", {"world": "shipped", "doc": doc, "tax_year": y, "label": name}, lambda doc=doc, y=y: gr.enc(ozp.pack_from_document(doc, y)))
    base = next(d for n, d in pool if n == "ga_jtc.json")
    for oz in one_zero_variants(rng):
        doc = {**base, "one_zero": oz}
        for y in (None, 2024):
            rec.call("pack_from_document", {"world": "shipped", "doc": doc, "tax_year": y, "label": "variant"}, lambda doc=doc, y=y: gr.enc(ozp.pack_from_document(doc, y)))
        for pay in ((None, None), (["A", "B"], None), (None, ["C"]), ([], []), (["A"], ["B"]), (("A",), ("B",)), (["only"], [])):
            rec.call("build_one_zero_pack", {"world": "shipped", "pack": doc, "resolved": oz, "pay_codes": [pay[0], pay[1]], "tax_year": 2023},
                     lambda doc=doc, oz=oz, pay=pay: gr.enc(ozp.build_one_zero_pack(doc, dict(oz), (pay[0], pay[1]), 2023)))
        rec.call("from_pack_json", {"world": "shipped", "block": oz.get("methodology")}, lambda oz=oz: gr.enc(OneZeroMethodology.from_pack_json(oz.get("methodology"))))
    for name, doc in pool:
        oz = doc.get("one_zero") or {}
        rec.call("build_one_zero_pack", {"world": "shipped", "pack": doc, "resolved": oz, "pay_codes": [None, None], "tax_year": None, "label": name},
                 lambda doc=doc, oz=oz: gr.enc(ozp.build_one_zero_pack(doc, dict(oz), (None, None), None)))
    for doc in ({}, {"one_zero": None}, {"one_zero": {}}, {"one_zero": {"min_weekly_hours": 1}}, {"credit": None, "one_zero": {"min_weekly_hours": 1}},
                {"credit": {}, "one_zero": {"min_weekly_hours": 1}}, {"credit": {"statutory_citation": None}, "one_zero": {"min_weekly_hours": 1}},
                {"credit": {"statutory_citation": 5}, "one_zero": {"min_weekly_hours": 1}}):
        rec.call("pack_from_document", {"world": "shipped", "doc": doc, "tax_year": None, "label": "shape"}, lambda doc=doc: gr.enc(ozp.pack_from_document(doc, None)))
    for blk in (None, {}, [], "", 0, {"minimum_pay_period_days": 3}):
        rec.call("from_pack_json", {"world": "shipped", "block": blk}, lambda blk=blk: gr.enc(OneZeroMethodology.from_pack_json(blk)))


# --------------------------------------------------------------------------- credit


AVGS = [0.0, -0.0, 0, 1.0, 1.5, 2.0, 2.0000000000000004, 2.9999999999999996, 3.0, 4.999999999999999, 5.0, 5.000000000000001, 5.5, 10.0, 10.125, 12.0, 14.0, 14.135, 14.145,
        25.0, 50.0, 112.0, 120.5, 200.0, 1e6, 123456789.12345, 1e15, 1e300, 1.7976931348623157e308, 5e-324, NAN, INF, -INF, -3.5, 14, 10 ** 20, 10 ** 400, True,
        "14.5", "bad", None, "", [1]]
PRIORS = [0.0, 0, 1.0, 3.5, 40.0, 100.0, NAN, INF, -2.0, "7", None]
OVERRIDES = [None, 0, 0.0, 2.5, 3, 10.0, -1.0, NAN, INF, 1e308, "2.5", "", [1]]
WAGES = [None, 0.0, 52000.0, 51234.5678, 0.5, 1e12, -100.0, NAN, INF, 1e-300]
TRAILS = [None, {"title": "", "citation": ""}, {"title": "Pending", "citation": "c"}, {"title": "Custom", "citation": "x"}]


def edges(t: float) -> list[float]:
    out = []
    for d in (0.0, 0.005, 0.015, 0.025, 0.125, 0.5, 1.0, 1.5, 12.0):
        base = t + d
        out += [base, math.nextafter(base, -INF), math.nextafter(base, INF)]
    return out


def credit_calls(rec: Rec, rng: random.Random, world_names: list[str]) -> None:
    keys_by_world = {w: registry_codes(rec, w) for w in world_names}
    for w in ("shipped", "zz", "zz_one", "zz_rev", "retired", "lab", "custom"):
        states = sorted({k[:2] for k in keys_by_world[w] if len(k) > 2} | {"TX", "XX"})
        extra = ["GA", "ga", "Ga_Jtc", "ga_jtc", "", " GA", "NOPE", "Straße", "\u01c6", "\u0149", "\ufb01", "\u0131", "FED_WOTC", "fed_wotc", "ZZ", "zz"]
        keys = list(dict.fromkeys(keys_by_world[w] + states + extra))
        if w != "shipped" and w != "lab":
            keys = keys[:0] + [k for k in keys if k.startswith(("ZZ", "GA", "VA", "zz", "ga", "NOPE", "TX", "XX", "NY", "SC", "NC")) or k in ("", " GA")]
        real_keys = set(keys_by_world["shipped"]) | {k[:2] for k in keys_by_world["shipped"] if len(k) > 2} | {"ga", "Ga_Jtc", "ga_jtc", "TX", "XX", ""}
        thresholds = {}
        with rec.worlds.enter(w):
            for k in keys:
                try:
                    pf = pl.pack_file_for(k)
                    thresholds[k] = float(cm._load_pack(pf)["thresholds"]["minimum_new_jobs"]) if pf else 2.0
                except Exception:
                    thresholds[k] = 2.0
        for k in keys:
            program_grid(rec, w, k, thresholds[k], rng, wide=(w == "shipped" and k in real_keys))
        for k in keys[:: max(1, len(keys) // 12)]:
            for wage in WAGES:
                apply(rec, "apply_one_zero_program_credit", w, k, 80.0, 30.0, None, None, wage)
    fein_cases(rec, rng)
    random_cases(rec, rng, keys_by_world)


def make_run(args: dict):
    """The closure for one apply call; ``args`` carries every input, including the trail and wage options."""
    fn = {"apply_one_zero_program_credit": pc.apply_one_zero_program_credit, "apply_one_zero_state_credit": cm.apply_one_zero_state_credit}[args["fn"]]

    def run():
        return traced(args, lambda: fn(args["key"], args["average_headcount"], prior_period_average_headcount=args["prior"], threshold_override=args["threshold_override"]))

    return run


def apply(rec: Rec, fn: str, w: str, key, avg, prior, override, trail=None, wage=None) -> None:
    args = {"world": w, "key": key, "average_headcount": avg, "prior": prior, "threshold_override": override, "wage_override": wage, "trail": trail, "fn": fn}
    rec.call(fn, args, make_run(args))


def program_grid(rec: Rec, w: str, key: str, t: float, rng: random.Random, *, wide: bool) -> None:
    for avg in AVGS:
        apply(rec, "apply_one_zero_program_credit", w, key, avg, 0.0, None)
    for avg in edges(t):
        for prior in (0.0, 10.0):
            apply(rec, "apply_one_zero_program_credit", w, key, avg + prior if prior else avg, prior, None)
    if not wide:
        for avg in (0.0, 14.0, 112.0):
            apply(rec, "apply_one_zero_state_credit", w, key, avg, 100.0, None)
        for avg in (t + 0.5, 80.0, NAN):
            for prior in (0.0, 3.5, "7"):
                for override in (None, 2.5, NAN):
                    apply(rec, "apply_one_zero_program_credit", w, key, avg, prior, override)
        for trail in TRAILS[1:3]:
            for avg in (0.0, t + 1.0, 1e300):
                apply(rec, "apply_one_zero_program_credit", w, key, avg, 5.0, None, trail)
        rec.call("program_per_job_usd", {"world": w, "key": key}, lambda key=key: pc.program_per_job_usd(key))
        rec.call("state_per_job_usd", {"world": w, "key": key}, lambda key=key: cm.state_per_job_usd(key))
        return
    for avg in (0.0, t + 0.5, t + 14.0, 112.0, 1e6, NAN):
        for prior in PRIORS:
            for override in OVERRIDES:
                apply(rec, "apply_one_zero_program_credit", w, key, avg, prior, override)
    for avg in AVGS[:: 3]:
        apply(rec, "apply_one_zero_state_credit", w, key, avg, 0.0, None)
        apply(rec, "apply_one_zero_state_credit", w, key, avg, 20.0, 2.5)
    for trail in TRAILS[1:]:
        for avg in (0.0, t, t + 1.0, 80.5, NAN, 1e300):
            apply(rec, "apply_one_zero_program_credit", w, key, avg, 5.0, None, trail)
            apply(rec, "apply_one_zero_state_credit", w, key, avg, 5.0, 0.5, trail)
    for wage in WAGES[1:]:
        apply(rec, "apply_one_zero_program_credit", w, key, t + 10.0, 1.0, None, None, wage)
    rec.call("program_per_job_usd", {"world": w, "key": key}, lambda key=key: pc.program_per_job_usd(key))
    rec.call("state_per_job_usd", {"world": w, "key": key}, lambda key=key: cm.state_per_job_usd(key))


FEINS = [{}, {"E1": {"average_headcount": 4.0}, "E2": {"average_headcount": 3.0}}, {"E1": {"average_headcount": 0.0}}, {"E1": {"average_headcount": 112.0}, "E2": {"average_headcount": 12.5}, "E3": {"average_headcount": 1.0}},
         {"E1": {"average_headcount": 1e300}, "E2": {"average_headcount": 1e300}}, {"E1": {"average_headcount": 1.7976931348623157e308}}, {"E1": {"average_headcount": NAN}},
         {"E1": {"average_headcount": INF}}, {"E1": {"average_headcount": 14}, "E2": {"average_headcount": "15"}}, {"E1": {}}, {"E1": {"average_headcount": None}},
         {"E1": {"average_headcount": 5.5, "other": 1}}, {"b": {"average_headcount": 20.0}, "a": {"average_headcount": 30.0}, "": {"average_headcount": 40.0}},
         {"E1": {"average_headcount": 10 ** 20}, "E2": {"average_headcount": 3.0}}, {"E\u00e9": {"average_headcount": 3.25}, "\U00010000": {"average_headcount": 7.75}},
         {"E1": {"average_headcount": 2.125}, "E2": {"average_headcount": 2.135}, "E3": {"average_headcount": 2.145}}, {"E1": 5}]


def fein_cases(rec: Rec, rng: random.Random) -> None:
    for w, keys in (("shipped", ["GA", "GA_JTC", "FED_WOTC", "SC", "NY", "TX", "ga", "NC_JTEC", "VA"]), ("zz", ["ZZ", "ZZ_ALPHA_JTC", "ZZ_BETA_JTC", "zz_beta_jtc"]),
                    ("lab", ["ZL_FLAT", "ZP_BIGFLOAT", "ZP_BIGINT", "ZP_FRAC", "ZP_TIE", "ZL_PCT", "ZM_NOSHAPE", "ZM_DRAFT"])):
        for key in keys:
            for fe in FEINS:
                for fn, call in (("combine_program_entity_credits", pc.combine_program_entity_credits), ("combine_entity_credits", cm.combine_entity_credits)):
                    for trail in (None, TRAILS[1]) if fe in FEINS[:4] else (None,):
                        args = {"world": w, "key": key, "fein_breakdown": fe, "trail": trail, "wage_override": None}
                        rec.call(fn, args, lambda args=args, call=call: traced(args, lambda: call(args["key"], args["fein_breakdown"])))
    for wage in WAGES[1:]:
        args = {"world": "shipped", "key": "NY", "fein_breakdown": FEINS[3], "trail": None, "wage_override": wage}
        rec.call("combine_program_entity_credits", args, lambda args=args: traced(args, lambda: pc.combine_program_entity_credits(args["key"], args["fein_breakdown"])))


def random_cases(rec: Rec, rng: random.Random, keys_by_world: dict[str, list[str]]) -> None:
    for _ in range(4000):
        w = rng.choice(["shipped", "shipped", "lab", "zz", "zz_rev"])
        keys = keys_by_world[w] + ["GA", "TX", "ZZ", "ga_jtc", "SC", "NY"]
        key = rng.choice(keys)
        avg = round(rng.uniform(-5, 300), rng.choice([0, 1, 2, 3, 10]))
        prior = rng.choice([0.0, round(rng.uniform(0, 250), rng.choice([0, 2, 5])), 0, 5.5])
        override = rng.choice([None, None, None, round(rng.uniform(-1, 20), rng.choice([0, 1, 2])), 0, 3])
        trail = rng.choice([None, None, None, TRAILS[1], TRAILS[3]])
        wage = rng.choice([None, None, None, round(rng.uniform(1000, 99999), 2), 52000.0])
        apply(rec, rng.choice(["apply_one_zero_program_credit", "apply_one_zero_state_credit"]), w, key, avg, prior, override, trail, wage)
    for _ in range(600):
        w = rng.choice(["shipped", "lab"])
        key = rng.choice(keys_by_world[w] + ["GA", "TX"])
        fe = {f"F{i}": {"average_headcount": round(rng.uniform(0, 80), rng.choice([0, 1, 2, 4]))} for i in range(rng.randint(0, 5))}
        args = {"world": w, "key": key, "fein_breakdown": fe, "trail": None, "wage_override": None}
        rec.call("combine_program_entity_credits", args, lambda args=args: traced(args, lambda: pc.combine_program_entity_credits(args["key"], args["fein_breakdown"])))


def credit_from_pack_cases(rec: Rec, rng: random.Random) -> None:
    pool = doc_pool()
    names_variants = [("GA_JTC", "GA", "ga_jtc.json"), ("zy_draft_jtc", "ZY", "x.json"), ("", "", ""), ("NOPE", "", "p.json"), ("ZL_PCT", "ZL", "zl_pct.json")]
    for label, doc in pool:
        if not isinstance(doc.get("benefit"), dict) or "credit" not in doc:
            continue
        for names in names_variants[:2] + names_variants[4:]:
            for avg, prior, override in ((14.0, 0.0, None), (112.0, 100.0, None), (0.0, 0.0, None), (3.5, 1.5, 0.5), (1e6, 5.0, 2.5), (NAN, 0.0, None), (80, 30, 3)):
                for trail in (None, TRAILS[2]):
                    args = {"world": "shipped", "label": label, "doc": doc, "names": list(names), "average_headcount": avg, "prior": prior, "threshold_override": override,
                            "trail": trail, "wage_override": 51234.5678}
                    rec.call("credit_from_pack", args, lambda args=args: traced(args, lambda: pc.credit_from_pack(
                        args["doc"], tuple(args["names"]), args["average_headcount"], args["prior"], args["threshold_override"])))
    for doc in ({}, {"thresholds": {}}, {"thresholds": {"minimum_new_jobs": 1}}, {"thresholds": {"minimum_new_jobs": 1}, "benefit": {}},
                {"thresholds": {"minimum_new_jobs": 1}, "benefit": {"benefit_period_years": 2}}, {"thresholds": {"minimum_new_jobs": 1}, "benefit": {"benefit_period_years": 2, "amount_per_qualifying_job_usd": 5}},
                {"thresholds": {"minimum_new_jobs": 1}, "benefit": {"benefit_period_years": 2, "amount_per_qualifying_job_usd": 5}, "credit": {}},
                {"thresholds": {"minimum_new_jobs": 1}, "benefit": {"benefit_period_years": 2, "amount_per_qualifying_job_usd": 5}, "credit": {"code": "C", "name": "N", "statutory_citation": "S"}},
                {"thresholds": {"minimum_new_jobs": 1}, "benefit": {"benefit_period_years": 2, "amount_per_qualifying_job_usd": 5}, "credit": {"code": "C", "name": "N", "statutory_citation": "S"}, "jurisdiction": {}},
                {"thresholds": {"minimum_new_jobs": 1}, "benefit": {"benefit_period_years": 2, "amount_per_qualifying_job_usd": 5}, "credit": {"code": "C", "name": "N", "statutory_citation": "S"}, "jurisdiction": {"code": "Q"}}):
        for trail in (None, TRAILS[1]):
            args = {"world": "shipped", "label": "shape", "doc": doc, "names": ["K", "Q", "f.json"], "average_headcount": 10.0, "prior": 1.0, "threshold_override": None, "trail": trail, "wage_override": None}
            rec.call("credit_from_pack", args, lambda args=args: traced(args, lambda: pc.credit_from_pack(args["doc"], tuple(args["names"]), args["average_headcount"], args["prior"], args["threshold_override"])))


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    specs = worlds_mod.all_worlds()
    if SCRATCH.exists():
        shutil.rmtree(SCRATCH)
    SCRATCH.mkdir()
    try:
        worlds = Worlds(specs)
        for name, spec in specs.items():
            if name != "shipped":
                worlds.build(name, spec)
        world_names = list(specs)
        rec = Rec(worlds)
        import time

        t0 = time.time()

        def stage(name):
            print(f"{name}: {len(rec.lines)} calls, {time.time() - t0:.0f}s", file=sys.stderr, flush=True)

        registry_cases(rec, world_names)
        stage("registry")
        sequences(rec)
        stage("sequences")
        packs_cases(rec, world_names)
        stage("packs")
        one_zero_cases(rec, world_names, rng)
        stage("one_zero")
        credit_calls(rec, rng, world_names)
        stage("credit")
        credit_from_pack_cases(rec, rng)
        stage("credit_from_pack")
        meta = {"worlds": {n: s for n, s in worlds.specs.items()}, "ingested_dir": "backend/data/rules_ingested"}
        return gr.serialise(rec, meta, seed, oracle.stamp())
    finally:
        shutil.rmtree(SCRATCH, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(gr.main("credit_math", DEFAULT_OUT, SEED, build))
