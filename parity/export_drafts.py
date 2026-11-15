"""Golden vectors for ``domain/program_drafts.py`` (stage DS6): the draft statuses, the ``DraftError`` hierarchy, ``CODE_PATTERN``,
the canonical JSON and the document hash, and the two dataclasses.

Every call is the PRODUCTION function (or a construction of the production dataclass) with its arguments, its output tree or its
exception type and message. The module holds no function that enforces ``MAX_DOCUMENT_CHARS``, ``MAX_YEAR_DOCUMENTS`` or
``MAX_DOCUMENT_DEPTH`` (``application/program_drafts`` does); the goldens record the constants and put documents on both sides of
each limit through ``canonical_json`` and ``documents_hash`` so the hashed bytes at those sizes are pinned.

Scenarios: the fictional pack of ``tests/draft_world.py`` (what the Python tests hash), every ASCII character in the first and
the later positions of ``CODE_PATTERN`` and the ``$``-before-newline cases, documents with non-ASCII text, non-BMP characters, lone
surrogates (``UnicodeEncodeError``), ints versus floats, NaN/Infinity, key orders, deep nesting, and seeded random documents.

Usage: python parity/export_drafts.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import dataclasses
import itertools
import random
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import golden_rec as gr  # noqa: E402
from domain import program_drafts as pd  # noqa: E402
from tests import draft_world as dw  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "drafts.jsonl.gz"
SEED = 20261119
INF = float("inf")
NAN = float("nan")
ERRORS = [pd.DraftError, pd.DraftNotFound, pd.DraftConflict, pd.DraftInvalid, pd.InvalidTransition, pd.ReviewRefused,
          pd.CustomerDataInDraft, pd.PreviewRefused, pd.CustomerDataRefused]
BY_NAME = {c.__name__: c for c in ERRORS}
NOW = {"$dt": "2026-01-01T12:00:00+00:00"}


def tagged(x):
    if isinstance(x, dict):
        if set(x) == {"$dt"}:
            return datetime.fromisoformat(x["$dt"])
        return {k: tagged(v) for k, v in x.items()}
    if isinstance(x, list):
        return [tagged(v) for v in x]
    return x


def mk_draft(kw: dict) -> pd.ProgramDraft:
    kw = tagged(kw)
    kw["status"] = pd.DraftStatus(kw["status"])
    return pd.ProgramDraft(**kw)


def mk_event(kw: dict) -> pd.DraftEvent:
    return pd.DraftEvent(**tagged(kw))


def out_of(obj) -> dict:
    return {"fields": gr.enc(obj), "order": [f.name for f in dataclasses.fields(obj)]}


def edit(obj, changes: dict):
    changes = tagged(changes)
    if "status" in changes:
        changes["status"] = pd.DraftStatus(changes["status"])
    return dataclasses.replace(obj, **changes)


def hash_pair(a, b) -> dict:
    ha = hash(a)
    return {"hashable": True, "equal_objects_equal_hash": (a != b) or ha == hash(b)}


def deep(n: int, leaf=None) -> dict:
    root: dict = {}
    node = root
    for _ in range(n):
        node["n"] = {}
        node = node["n"]
    node["leaf"] = leaf
    return root


def sized(chars: int) -> dict:
    """A document whose canonical JSON is exactly ``chars`` characters long (``{"k":"xxx"}`` is 8 plus the filler)."""
    return {"k": "x" * max(0, chars - 8)}


DOC = dw.documents()
PACK, YEARS = DOC["pack"], DOC["years"]


def documents() -> list[tuple]:
    """``(pack, years)`` pairs: the Python tests' fixtures first, then the edges."""
    out: list[tuple] = [(None, {}), ({}, {}), (PACK, YEARS), (PACK, {}), (None, YEARS), (dw.documents((2025,))["pack"], dw.documents((2025,))["years"]),
                        (dw.broken(DOC)["pack"], dw.broken(DOC)["years"])]
    flipped = {"years": dict(reversed(list(YEARS.items()))), "pack": dict(reversed(list(PACK.items())))}
    out.append((flipped["pack"], flipped["years"]))
    out.append(({**PACK, "_note": "x" * 9000}, YEARS))
    for n in (0, 1, 5, 11, 12, 13, 20, 40, 150, 300):
        out.append((deep(n), {}))
        out.append((None, {"2024": deep(n, [1, 2.5, "s"])}))
    for chars in (0, 7, 8, 9, 7999, 8000, 8001, 8002):
        out.append((sized(chars), {}))
        out.append((None, {"2024": sized(chars)}))
    for n in (0, 1, 29, 30, 31, 32):
        out.append((PACK, {str(2000 + i): YEARS["2024"] for i in range(n)}))
    out += [({"a": 1, "b": 1.0, "c": True, "d": None, "e": [], "f": {}}, {}), ({"b": 1, "a": 2, "B": 3, "\u00e9": 4, "e": 5, "\U00010000": 6, "\uffff": 7}, {}),
            ({"s": "caf\u00e9 \u2014 \u00a7 \U0001f600 \u0000 \u001f \u007f \u2028 \u2029 \\ \" / \n\r\t\b\f"}, {"2024": {"\u00e9": "e\u0301"}}),
            ({"f": [0.1, 1e22, 1e-7, 123456789.123456789, -0.0, 5e-324, 1.7976931348623157e308, 1e16, 12345678901234567890.0]}, {}),
            ({"i": [0, -1, 2 ** 53, 2 ** 63, 2 ** 64, -(2 ** 70), 10 ** 30]}, {}), ({"x": NAN, "y": INF, "z": -INF}, {}),
            ({"k": "\ud800"}, {}), ({"k": "a\udc00b"}, {}), ({"k": "\ud800\ud800"}, {}), 
            ({"k": "\ude00\ud83d"}, {}), ({"\ud800": 1}, {}), ({"k": "\U00010000\ud800\U00010001"}, {}),
            ({"k": ["\ud800", "x", "\udfff\udfff\udfff"]}, {}), ({"": ""}, {"": {}}), ({"a": {"b": {"c": [[], [[]], {}]}}}, {"2024": {}}),
            ({"1": 1, "10": 1, "2": 1, "-1": 1, "": 1, " ": 1}, {})]
    return out


def rand_value(rng: random.Random, depth: int):
    kinds = ["int", "float", "str", "bool", "none"] + (["list", "dict"] * 2 if depth < 4 else [])
    kind = rng.choice(kinds)
    if kind == "int":
        return rng.choice([0, 1, -1, rng.randint(-10 ** 6, 10 ** 6), 2 ** 53, 10 ** 25])
    if kind == "float":
        return rng.choice([0.0, -0.0, 0.5, 1e-9, 1e21, rng.uniform(-1e6, 1e6), rng.random(), float(rng.randint(0, 100))])
    if kind == "str":
        return rng.choice(["", "a", "GA_JTC", "caf\u00e9", "\U0001f600", "q\"b\\s", "n\nl", "\u0001", "\u007f", "\u2028", "x" * rng.randint(0, 40)])
    if kind == "bool":
        return rng.random() < 0.5
    if kind == "none":
        return None
    if kind == "list":
        return [rand_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {rng.choice(["a", "b", "B", "\u00e9", "c1", "c10", "c2", "", "\U00010000", "\uffff", "k" + str(rng.randint(0, 9))]): rand_value(rng, depth + 1)
            for _ in range(rng.randint(0, 5))}


CODES = ["GA_JTC", "ZZ_DEMO_JTC", "ZY_DRAFT_JTC", "ABC", "A_1", "A__", "A12", "AB", "A", "", "ga_jtc", "Ga_Jtc", "1AB", "_AB", "A B", "A-B", "A.B", " ABC", "ABC ", "ABC\n",
         "ABC\n\n", "ABC\r\n", "ABC\r", "\nABC", "A\nBC", "AB\nC", "ABC\x00", "\x00ABC", "ABC\u00e9", "\u00c9BC", "ABC\u212a", "\u212aBC", "\uff21\uff22\uff23", "ABC\u0661",
         "A\u0661C", "ABC\U00010000", "\U00010000ABC", "A" + "B" * 63, "A" + "B" * 62, "A" + "B" * 64, "A" + "B" * 65, "A" + "B" * 63 + "\n", "A" + "B" * 64 + "\n",
         "A" + "0" * 63, "A" + "_" * 63, "Z" * 64, "ABC\t", "ABC\x0b", "ABC\x0c", "ABC\x85", "ABC\u2028", "ABC\u2029", "ABC\u0000\n", "ABC\n\u0000", "AB_C_D_E_F"]


def code_calls(rec: gr.Recorder, rng: random.Random) -> None:
    def match(text):
        m = pd.CODE_PATTERN.match(text)
        return {"matched": m is not None, "end": None if m is None else m.end(), "group": None if m is None else m.group(0)}

    rec.call("code_pattern_meta", {}, lambda: {"pattern": pd.CODE_PATTERN.pattern})
    texts = list(CODES)
    for i in range(128):
        ch = chr(i)
        texts += ["A" + ch + "C", ch + "BC", "ABC" + ch, "AB" + ch, ch]
    for ch in ("\u00e9", "\u0130", "\u0131", "\u017f", "\u212a", "\ufb01", "\uff3f", "\u2160", "\u00b2", "\u0660", "\u200b", "\ufeff", "\U0001d400", "\U0001f600"):
        texts += ["A" + ch + "C", ch + "BC", "ABC" + ch]
    alphabet = "AZaz09_- \n\u00e9"
    for _ in range(3000):
        texts.append("".join(rng.choice(alphabet) for _ in range(rng.randint(0, 8))))
    for text in texts:
        rec.call("code_pattern", {"text": text}, lambda t=text: match(t))


def error_calls(rec: gr.Recorder) -> None:
    rec.call("error_info", {}, lambda: {c.__name__: {"code": c.code, "bases": [b.__name__ for b in c.__mro__[1:-2]],
                                                       "is_exception": issubclass(c, Exception)} for c in ERRORS})
    messages = ["", "x", "no such draft", "caf\u00e9 \u2014 \u00a7", "line1\nline2", "\U0001f600", "a" * 300, "'quoted' \"double\""]
    for c in ERRORS:
        for m in messages:
            rec.call("raise_error", {"cls": c.__name__, "message": m}, lambda c=c, m=m: (_ for _ in ()).throw(c(m)))
        rec.call("raise_error_empty", {"cls": c.__name__}, lambda c=c: (_ for _ in ()).throw(c()))
        rec.call("error_code", {"cls": c.__name__}, lambda c=c: c(" m").code)
    rec.call("error_is_a", {}, lambda: [[a.__name__, b.__name__, issubclass(a, b)] for a in ERRORS for b in ERRORS])


def enum_calls(rec: gr.Recorder) -> None:
    rec.call("status_tables", {}, lambda: {"members": [[m.name, m.value] for m in pd.DraftStatus], "editable": sorted(s.value for s in pd.EDITABLE),
                                           "closed": sorted(s.value for s in pd.CLOSED), "types": [type(pd.EDITABLE).__name__, type(pd.CLOSED).__name__],
                                           "limits": [pd.MAX_DOCUMENT_CHARS, pd.MAX_YEAR_DOCUMENTS, pd.MAX_DOCUMENT_DEPTH]})
    bogus = ["", "Draft", "DRAFT", "draft ", " draft", "draft\n", "needs-changes", "ready", "exported ", "\u00e9", "\U00010000", "withdrawn\n", "a'b", "None"]
    for v in [m.value for m in pd.DraftStatus] + bogus:
        rec.call("status_from_value", {"value": v}, lambda v=v: pd.DraftStatus(v))
    for s in pd.DraftStatus:
        rec.call("status_flags", {"status": s.value}, lambda s=s: {"editable": s in pd.EDITABLE, "closed": s in pd.CLOSED})


def doc_calls(rec: gr.Recorder, rng: random.Random) -> None:
    docs = documents()
    for _ in range(1500):
        pack = None if rng.random() < 0.15 else {f"k{rng.randint(0, 9)}": rand_value(rng, 0) for _ in range(rng.randint(0, 5))}
        years = {str(rng.randint(2018, 2030)): {f"k{rng.randint(0, 9)}": rand_value(rng, 1) for _ in range(rng.randint(0, 4))} for _ in range(rng.randint(0, 4))}
        docs.append((pack, years))
    for pack, years in docs:
        rec.call("documents_hash", {"pack": pack, "years": years}, lambda p=pack, y=years: pd.documents_hash(p, y))
        rec.call("canonical_documents", {"pack": pack, "years": years},
                 lambda p=pack, y=years: _canonical(p, y))
    singles = [None, True, False, 0, 1, -1, 1.0, 0.5, "s", "", "\u00e9", "\U0001f600", [], {}, [1, [2, [3]]], {"b": 1, "a": 2}, 2 ** 80, NAN, INF, "\ud800", [None, "\ud800"],
               {"k": "\u007f"}, "\u2028"]
    for v in singles:
        rec.call("canonical_json", {"document": v}, lambda v=v: pd.canonical_json(v))
    for _ in range(600):
        v = rand_value(rng, 0)
        rec.call("canonical_json", {"document": v}, lambda v=v: pd.canonical_json(v))


def _canonical(pack, years):
    text = pd.canonical_json({"pack": pack, "years": years})
    return {"text": text, "length": len(text)}


def draft_specs() -> list[dict]:
    base = dict(draft_id="d1", proposed_code=dw.CODE, name="Fictional", jurisdiction_level="state", state=dw.STATE, status="draft", version=1,
                created_by="ann", created_at=NOW, updated_by="ann", updated_at=NOW)
    ts = {"$dt": "2026-01-02T08:30:00.500000+00:00"}
    return [{**base}, {**base, "pack": PACK, "years": YEARS}, {**base, "years": {}}, {**base, "pack": {}, "years": {"2024": {}}},
            {**base, "state": None, "jurisdiction_level": "federal"}, {**base, "status": "needs_changes", "validation": {"valid": False, "errors": 3, "findings": [{"code": "schema"}]}},
            {**base, "status": "ready_for_review", "review_requested_by": "ann", "validation": {"valid": True}},
            {**base, "status": "approved_for_export", "reviewer": "bob", "decision": "approve", "decision_comment": "ok", "decided_at": ts, "approved_sha256": "ab" * 32},
            {**base, "status": "exported", "exported_at": ts, "export_sha256": "cd" * 32}, {**base, "status": "withdrawn", "version": 9},
            {**base, "status": "validating"}, {**base, "created_at": {"$dt": "2026-01-01T12:00:00"}}, {**base, "name": "caf\u00e9 \U0001f600", "draft_id": ""},
            {**base, "pack": {"b": 1, "a": 2}, "years": {"2025": {"x": 1.0}, "2024": {"x": 1}}}, {**base, "pack": {"a": 2, "b": 1}, "years": {"2024": {"x": 1}, "2025": {"x": 1.0}}}]


def event_specs() -> list[dict]:
    base = dict(draft_id="d1", seq=0, event_type="created", actor="ann", at=NOW)
    return [base, {**base, "seq": 2, "event_type": "edited", "from_status": "draft", "to_status": "draft", "detail": {"years": [2024, 2025]}},
            {**base, "event_type": "validated", "from_status": "draft", "to_status": "needs_changes", "detail": {"errors": 1, "actor_oid": "o", "ratio": 0.5}},
            {**base, "detail": {}}, {**base, "actor": "", "event_type": ""}, {**base, "detail": {"a": 1, "b": 2}}, {**base, "detail": {"b": 2, "a": 1}},
            {**base, "detail": {"a": 1.0, "b": 2}}, {**base, "at": {"$dt": "2026-01-01T12:00:00"}}]


def model_calls(rec: gr.Recorder, name: str, make, specs: list[dict], changes: list[dict]) -> None:
    for kw in specs:
        rec.call("construct_" + name, {"kw": kw}, lambda kw=kw: out_of(make(kw)))
    for kw in specs[:6]:
        for ch in changes:
            rec.call("replace_" + name, {"kw": kw, "changes": ch}, lambda kw=kw, ch=ch: out_of(edit(make(kw), ch)))
    # one field changed at a time: each field of the dataclass must take part in `==` on its own
    for kw in specs[:6]:
        for ch in changes:
            b = {**kw, **ch}
            rec.call("equals_" + name, {"a": kw, "b": b}, lambda a=kw, b=b: make(a) == make(b))
    for a, b in itertools.product(specs, repeat=2):
        rec.call("equals_" + name, {"a": a, "b": b}, lambda a=a, b=b: make(a) == make(b))
        rec.call("hash_" + name, {"a": a, "b": b}, lambda a=a, b=b: hash_pair(make(a), make(b)))
    for f in dataclasses.fields(make(specs[0])):
        rec.call("frozen_assign_" + name, {"kw": specs[0], "field": f.name}, lambda f=f: setattr(make(specs[0]), f.name, 1))


def model_all(rec: gr.Recorder) -> None:
    specs = draft_specs()
    model_calls(rec, "program_draft", mk_draft, specs,
                [{}, {"status": "ready_for_review"}, {"version": 2, "updated_by": "bob"}, {"pack": {"x": 1}}, {"years": {}}, {"validation": None}, {"state": None, "name": ""},
                 {"draft_id": "z"}, {"proposed_code": "ZZ_OTHER"}, {"name": "z"}, {"jurisdiction_level": "federal"}, {"state": "TX"}, {"version": 5}, {"created_by": "z"}, {"created_at": {"$dt": "2026-02-02T00:00:00+00:00"}},
                 {"updated_by": "z"}, {"updated_at": {"$dt": "2026-02-02T00:00:00+00:00"}}, {"validation": {"valid": True}}, {"review_requested_by": "z"}, {"reviewer": "z"}, {"decision": "approve"},
                 {"decision_comment": "c"}, {"decided_at": {"$dt": "2026-02-02T00:00:00+00:00"}}, {"approved_sha256": "z"}, {"exported_at": {"$dt": "2026-02-02T00:00:00+00:00"}}, {"export_sha256": "z"},
                 {"years": {"2024": {"a": 1}}}])
    model_calls(rec, "draft_event", mk_event, event_specs(), [{}, {"seq": 5}, {"detail": {"k": 1}}, {"to_status": "exported"}, {"draft_id": "z"}, {"event_type": "z"}, {"actor": "z"}, {"at": {"$dt": "2026-02-02T00:00:00+00:00"}}, {"from_status": "draft"}])
    for kw in specs:
        rec.call("content_sha256", {"kw": kw}, lambda kw=kw: mk_draft(kw).content_sha256)
        for ch in ({}, {"status": "ready_for_review"}, {"pack": {"x": 1}}, {"years": {"2024": {"y": 2}}}, {"name": "other", "version": 7}):
            rec.call("with_changes", {"kw": kw, "changes": ch}, lambda kw=kw, ch=ch: out_of(mk_draft(kw).with_changes(**tagged({k: pd.DraftStatus(v) if k == "status" else v for k, v in ch.items()}))))
    rec.call("defaults_not_shared", {}, lambda: {"years": mk_draft(draft_specs()[0]).years is mk_draft(draft_specs()[0]).years,
                                                 "detail": mk_event(event_specs()[0]).detail is mk_event(event_specs()[0]).detail})


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    rec = gr.Recorder()
    error_calls(rec)
    enum_calls(rec)
    code_calls(rec, rng)
    doc_calls(rec, rng)
    model_all(rec)
    return gr.serialise(rec, {"python_module": "domain/program_drafts.py"}, seed, oracle.stamp())


if __name__ == "__main__":
    raise SystemExit(gr.main("drafts", DEFAULT_OUT, SEED, build))
