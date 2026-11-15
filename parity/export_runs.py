"""Golden vectors for ``domain/runs.py`` (stage DS6): the run-batch model, its two state machines, the unchanged rule and the backoff.

Everything is a call of the PRODUCTION function (or a construction of the production dataclass), recorded with its arguments,
its output tree or the exception type and message. Scenarios are every input ``test_run_orchestration.py`` and
``test_run_batch_store.py`` use, the full cross product of the item state machine (every state to every state), every
``batch_status`` count table built from the eight statuses at 0/1/2 (both cancel flags), the fingerprint matrix of
``unchanged_decision`` (each of the seven fields known, unknown, empty and different on either side) and a grid of
``backoff_seconds`` around both ends of the cap and the ``2 ** k`` float overflow, plus seeded random batches.

``backoff_seconds`` defaults ``jitter`` to the global ``random.random``. A golden cannot depend on the Mersenne Twister state, so every
call supplies the jitter it uses and the golden records it, with the number of times it was called.

Usage: python parity/export_runs.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import dataclasses
import itertools
import math
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import golden_rec as gr  # noqa: E402
from domain import runs as rn  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "runs.jsonl.gz"
SEED = 20261118
INF = float("inf")
NAN = float("nan")
NOW = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)
ENUMS = {"BatchKind": rn.BatchKind, "ScopeKind": rn.ScopeKind, "BatchStatus": rn.BatchStatus, "ItemStatus": rn.ItemStatus}
IS = rn.ItemStatus


def tagged(x):
    """Inverse of ``golden_rec.enc`` for the dates in an argument."""
    if isinstance(x, dict):
        if set(x) == {"$dt"}:
            return datetime.fromisoformat(x["$dt"])
        return {k: tagged(v) for k, v in x.items()}
    if isinstance(x, list):
        return [tagged(v) for v in x]
    return x


def mk_batch(kw: dict) -> rn.RunBatch:
    kw = tagged(kw)
    for key, cls in (("kind", rn.BatchKind), ("scope_kind", rn.ScopeKind), ("status", rn.BatchStatus)):
        if key in kw:
            kw[key] = cls(kw[key])
    if "tax_years" in kw:
        kw["tax_years"] = tuple(kw["tax_years"])
    return rn.RunBatch(**kw)


def mk_item(kw: dict) -> rn.RunBatchItem:
    kw = tagged(kw)
    if "status" in kw:
        kw["status"] = IS(kw["status"])
    return rn.RunBatchItem(**kw)


def mk_result(kw: dict) -> rn.ItemResult:
    kw = dict(kw)
    kw["status"] = IS(kw["status"])
    return rn.ItemResult(**kw)


def mk_fp(kw: dict | None) -> rn.Fingerprint | None:
    return None if kw is None else rn.Fingerprint(**kw)


def out_of(obj) -> dict:
    return {"fields": gr.enc(obj), "order": [f.name for f in dataclasses.fields(obj)]}


def edit(obj, changes: dict):
    changes = tagged(changes)
    if "status" in changes:
        changes["status"] = type(obj.status)(changes["status"])
    if "kind" in changes:
        changes["kind"] = rn.BatchKind(changes["kind"])
    if "scope_kind" in changes:
        changes["scope_kind"] = rn.ScopeKind(changes["scope_kind"])
    if "tax_years" in changes:
        changes["tax_years"] = tuple(changes["tax_years"])
    return dataclasses.replace(obj, **changes)


def hash_pair(a, b) -> dict:
    ha = hash(a)
    return {"hashable": True, "equal_objects_equal_hash": (a != b) or ha == hash(b)}


BATCH = dict(batch_id="b-0001", kind="calculate", scope_kind="list", scope_spec={"client_ids": [1, 2, 3]}, requested_by="tester",
             requested_at={"$dt": "2026-03-01T09:00:00+00:00"})
ITEM = dict(item_id="b-0001-0000", batch_id="b-0001", client_id=1, seq=0)


def batch_specs() -> list[dict]:
    at = {"$dt": "2026-03-01T09:00:00+00:00"}
    specs = [BATCH, {**BATCH, "kind": "assess", "scope_kind": "one"}, {**BATCH, "kind": "assess_and_calculate", "scope_kind": "filter"},
             {**BATCH, "scope_kind": "all", "scope_spec": {}}, {**BATCH, "program_code": "GA_JTC", "tax_years": [2023, 2024]},
             {**BATCH, "tax_years": []}, {**BATCH, "force": True, "include_code_commit": True, "refresh_once": False, "skip_unchanged": True},
             {**BATCH, "status": "running", "started_at": at}, {**BATCH, "status": "partial", "started_at": at, "finished_at": {"$dt": "2026-03-01T10:30:15.250000+00:00"}},
             {**BATCH, "status": "cancelled", "cancel_requested": True, "idempotency_key": "k-1"},
             {**BATCH, "dry_run_summary": {"clients": 3, "skipped": [], "note": "a\u00e9"}, "counts": {"queued": 3, "succeeded": 0}},
             {**BATCH, "requested_at": {"$dt": "2026-03-01T09:00:00"}}, {**BATCH, "requested_at": {"$dt": "2026-03-01T09:00:00+05:30"}},
             {**BATCH, "scope_spec": {"b": 1, "a": 1.0, "c": [1, 2.5, None, True], "d": {"x": "\U00010000"}}},
             {**BATCH, "requested_by": "", "batch_id": ""}, {**BATCH, "program_code": "Stra\u00dfe"}]
    return specs


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
    for a, b in itertools.product(specs[:8], repeat=2):
        rec.call("equals_" + name, {"a": a, "b": b}, lambda a=a, b=b: make(a) == make(b))
        rec.call("hash_" + name, {"a": a, "b": b}, lambda a=a, b=b: hash_pair(make(a), make(b)))
    for f in dataclasses.fields(make(specs[0])):
        rec.call("frozen_assign_" + name, {"kw": specs[0], "field": f.name}, lambda f=f: setattr(make(specs[0]), f.name, 1))


def batch_models(rec: gr.Recorder) -> None:
    changes = [{}, {"status": "succeeded"}, {"force": True}, {"counts": {"succeeded": 2}}, {"scope_spec": {"x": 1}}, {"tax_years": [2020]},
               {"cancel_requested": True, "finished_at": {"$dt": "2026-03-02T00:00:00+00:00"}}, {"program_code": None}, {"batch_id": "z"}, {"kind": "assess"}, {"scope_kind": "all"},
               {"requested_by": "z"}, {"requested_at": {"$dt": "2026-03-02T00:00:00+00:00"}}, {"program_code": "GA_JTC"}, {"include_code_commit": True}, {"refresh_once": False}, {"skip_unchanged": True},
               {"idempotency_key": "k"}, {"dry_run_summary": {"a": 1}}, {"started_at": {"$dt": "2026-03-02T00:00:00+00:00"}}, {"finished_at": {"$dt": "2026-03-02T00:00:00+00:00"}},
               {"counts": {"queued": 1.0}}, {"scope_spec": {"client_ids": [3, 2, 1]}}]
    model_calls(rec, "run_batch", mk_batch, batch_specs(), changes)
    # a dict-valued default is a fresh dict per instance, never shared
    rec.call("batch_defaults_not_shared", {}, lambda: {"same_object": mk_batch(BATCH).counts is mk_batch(BATCH).counts,
                                                         "same_object_summary": mk_batch(BATCH).dry_run_summary is mk_batch(BATCH).dry_run_summary})
    items = [ITEM, {**ITEM, "status": "leased", "attempts": 1, "lease_owner": "w1", "lease_expires_at": {"$dt": "2026-03-01T09:05:00+00:00"},
                    "heartbeat_at": {"$dt": "2026-03-01T09:00:30+00:00"}},
             {**ITEM, "program_code": "GA_JTC", "tax_year": 2023}, {**ITEM, "status": "failed", "error_dependency": "validation", "error_message": "no"},
             {**ITEM, "status": "succeeded", "run_id": "r1", "started_at": {"$dt": "2026-03-01T09:00:00+00:00"}, "finished_at": {"$dt": "2026-03-01T09:01:00+00:00"}},
             {**ITEM, "status": "skipped_unchanged", "skip_reason": "unchanged"}, {**ITEM, "not_before": {"$dt": "2026-03-01T09:00:05+00:00"}, "seq": 7},
             {**ITEM, "status": "running", "attempts": 3}, {**ITEM, "client_id": 2, "item_id": "x"}, {**ITEM, "heartbeat_at": {"$dt": "2026-03-01T09:00:00"}}]
    model_calls(rec, "run_batch_item", mk_item, items, [{}, {"attempts": 2}, {"lease_owner": None}, {"seq": 9, "tax_year": 2024}, {"status": "failed"}, {"item_id": "z"}, {"batch_id": "z"}, {"client_id": 9},
                                                                       {"seq": 1}, {"program_code": "X"}, {"tax_year": 1999}, {"lease_owner": "w9"}, {"lease_expires_at": {"$dt": "2026-03-02T00:00:00+00:00"}},
                                                                       {"heartbeat_at": {"$dt": "2026-03-02T00:00:00+00:00"}}, {"not_before": {"$dt": "2026-03-02T00:00:00+00:00"}}, {"run_id": "r"},
                                                                       {"skip_reason": "s"}, {"error_dependency": "d"}, {"error_message": "m"}, {"started_at": {"$dt": "2026-03-02T00:00:00+00:00"}},
                                                                       {"finished_at": {"$dt": "2026-03-02T00:00:00+00:00"}}])
    results = [{"status": s.value} for s in IS] + [
        {"status": "failed", "error_dependency": "operational_store", "error_message": "the server could not be reached."},
        {"status": "succeeded", "run_id": "r1", "tax_year": 2025}, {"status": "skipped_unchanged", "skip_reason": "same"}]
    model_calls(rec, "item_result", mk_result, results, [{}, {"run_id": "r2"}, {"tax_year": None}, {"tax_year": 1}, {"status": "failed"}, {"skip_reason": "s"}, {"error_dependency": "d"}, {"error_message": "m"}])
    fps = [{}, FULL, {**FULL, "tax_year": None}, {**FULL, "calculation_id": ""}, {"tax_year": 2025}, {**FULL, "code_commit": "def"}]
    model_calls(rec, "fingerprint", lambda kw: rn.Fingerprint(**kw), fps, [{}, {"calculation_id": "other"}, {"tax_year": 2024}, {"source_snapshot_id": None}, {"step1_assumption_sha256": "x"}, {"onezero_assumption_sha256": "x"},
                                                                                                    {"rule_pack_version": "x"}, {"code_commit": "x"}, {"source_snapshot_id": "x"}, {"calculation_id": None}])
    for n, kw in enumerate(items):
        rec.call("item_status_default", {"kw": kw}, lambda kw=kw: mk_item(kw).status)


FULL = dict(calculation_id="calc", step1_assumption_sha256="s1", onezero_assumption_sha256="oz", rule_pack_version="rules/x/2025.json",
            code_commit="abc", tax_year=2025, source_snapshot_id="snap")


def enum_calls(rec: gr.Recorder) -> None:
    rec.call("enum_tables", {}, lambda: {
        "members": {n: [[m.name, m.value] for m in cls] for n, cls in ENUMS.items()},
        "terminal": sorted(s.value for s in rn.TERMINAL_ITEMS), "skipped": sorted(s.value for s in rn.SKIPPED_ITEMS),
        "active": sorted(s.value for s in rn.ACTIVE_ITEMS),
        "moves": {s.value: sorted(t.value for t in ts) for s, ts in rn._ITEM_MOVES.items()},
        "set_types": [type(rn.TERMINAL_ITEMS).__name__, type(rn.SKIPPED_ITEMS).__name__, type(rn.ACTIVE_ITEMS).__name__],
        "str_subclass": all(issubclass(c, str) for c in ENUMS.values())})
    bogus = ["", "Queued", "QUEUED", " queued", "queued\n", "queued ", "\u00fcn\u00ef", "\U00010000", "assess ", "None", "0", "a'b", 'a"b', "line\nbreak", "tab\t", "\u00a0",
             "all", "ALL", "one_", "partial ", "skipped", "skipped_unchanged\n"]
    for n, cls in ENUMS.items():
        for v in [m.value for m in cls] + bogus:
            rec.call("enum_from_value", {"enum": n, "value": v}, lambda cls=cls, v=v: cls(v))


def move_calls(rec: gr.Recorder) -> None:
    for cur, tgt in itertools.product(IS, IS):
        rec.call("check_item_move", {"current": cur.value, "target": tgt.value}, lambda cur=cur, tgt=tgt: rn.check_item_move(cur, tgt))
    bases = [ITEM, {**ITEM, "attempts": 2, "lease_owner": "w", "program_code": "GA_JTC", "tax_year": 2023}]
    changes = [{}, {"attempts": 1}, {"lease_owner": "w1", "lease_expires_at": {"$dt": "2026-03-01T09:05:00+00:00"}}, {"run_id": "r", "tax_year": 2024},
               {"error_dependency": "validation", "error_message": "m\u00e9"}, {"skip_reason": "x", "finished_at": {"$dt": "2026-03-01T09:05:00+00:00"}}]
    for base, cur, tgt, ch in itertools.product(bases, IS, IS, changes):
        kw = {**base, "status": cur.value}
        rec.call("item_moved", {"kw": kw, "target": tgt.value, "changes": ch},
                 lambda kw=kw, tgt=tgt, ch=ch: out_of(mk_item(kw).moved(tgt, **tagged(ch))))
    # a chain: every legal walk of length three from queued, to prove `moved` applies the check at each step
    legal = {s: sorted(rn._ITEM_MOVES.get(s, ()), key=lambda m: m.value) for s in IS}
    for a in legal[IS.QUEUED]:
        for b in legal[a]:
            for c in legal[b]:
                rec.call("item_walk", {"steps": [a.value, b.value, c.value]}, lambda a=a, b=b, c=c: out_of(mk_item(ITEM).moved(a).moved(b).moved(c)))


def count_tables(rng: random.Random) -> list[dict]:
    names = [s.value for s in IS]
    tables: list[dict] = [{}, {"queued": 3}, {"queued": 1, "succeeded": 2}, {"running": 1}, {"succeeded": 2, "skipped_unchanged": 1},
                          {"skipped_unchanged": 3}, {"succeeded": 2, "failed": 1}, {"failed": 2}, {"cancelled": 2}, {"succeeded": 1, "cancelled": 1}]
    tables += [{"bogus": 2}, {"bogus": 2, "queued": 1}, {"bogus": 1, "succeeded": 1}, {"queued": 0}, {"succeeded": 0, "failed": 0}, {"failed": 0, "cancelled": 0},
               {"queued": -1, "running": 1}, {"queued": 1, "succeeded": -1}, {"failed": -1}, {"failed": -1, "succeeded": 1}, {"succeeded": 1, "failed": 1, "queued": -1},
               {"running": 2 ** 40, "failed": 2 ** 40}, {"succeeded": 2 ** 50}, {"leased": 1}, {"leased": 1, "failed": 3}, {"failed": 1, "cancelled": -1},
               {"failed": 1, "cancelled": -1, "succeeded": 1}, {"cancelled": -3, "succeeded": 3}, {"queued": 2, "bogus": -2}]
    for values in itertools.product((0, 1, 2), repeat=len(names)):
        tables.append({n: v for n, v in zip(names, values) if v or (v == 0 and rng.random() < 0.1)})
    for _ in range(1500):
        k = rng.randint(0, 6)
        tables.append({rng.choice(names + ["bogus"]): rng.choice([-2, -1, 0, 1, 2, 3, 100]) for _ in range(k)})
    return tables


def status_calls(rec: gr.Recorder, rng: random.Random) -> None:
    for counts in count_tables(rng):
        for cancel in (False, True):
            args = {"counts": counts, "cancel_requested": cancel}
            if not cancel and rng.random() < 0.5:
                args = {"counts": counts}
                rec.call("batch_status", args, lambda c=counts: rn.batch_status(c))
            else:
                rec.call("batch_status", args, lambda c=counts, x=cancel: rn.batch_status(c, cancel_requested=x))


def fingerprint_cases(rng: random.Random) -> list[tuple]:
    cases: list[tuple] = []
    full = FULL
    fields = [f for f in full]
    variants = lambda v: [v, None, "", " ", "other", "\u00e9", "e\u0301"]  # noqa: E731
    cases.append((None, full, False))
    cases.append((None, full, True))
    cases.append((full, full, False))
    cases.append((full, full, True))
    cases.append(({}, full, False))
    cases.append((full, {}, False))
    cases.append(({}, {}, False))
    for f in fields:
        if f == "tax_year":
            continue
        for a, b in itertools.product(variants(full[f]), repeat=2):
            for commit in (False, True):
                cases.append(({**full, f: a}, {**full, f: b}, commit))
    for a, b in itertools.product([None, 2025, 2024, 0, -1, 2 ** 40], repeat=2):
        for commit in (False, True):
            cases.append(({**full, "tax_year": a}, {**full, "tax_year": b}, commit))
    for _ in range(1200):
        side = lambda: {k: rng.choice([full[k], full[k], None, "", "z"]) if k != "tax_year" else rng.choice([2025, 2025, 2024, None]) for k in fields}  # noqa: E731
        a, b = side(), side()
        if rng.random() < 0.5:
            b = {**a, **{k: v for k, v in b.items() if rng.random() < 0.3}}
        cases.append((None if rng.random() < 0.05 else a, b, rng.random() < 0.5))
    return cases


def fingerprint_calls(rec: gr.Recorder, rng: random.Random) -> None:
    for last, current, commit in fingerprint_cases(rng):
        args = {"last": last, "current": current, "include_code_commit": commit}
        if not commit and rng.random() < 0.5:
            args = {"last": last, "current": current}
            rec.call("unchanged_decision", args, lambda l=last, c=current: list(rn.unchanged_decision(mk_fp(l), mk_fp(c))))
        else:
            rec.call("unchanged_decision", args, lambda l=last, c=current, k=commit: list(rn.unchanged_decision(mk_fp(l), mk_fp(c), include_code_commit=k)))


def backoff(attempt, base, cap, jitter_value) -> dict:
    calls = []

    def jitter():
        calls.append(1)
        return jitter_value

    kwargs = {"jitter": jitter}
    if base is not NOTHING:
        kwargs["base"] = base
    if cap is not NOTHING:
        kwargs["cap"] = cap
    value = rn.backoff_seconds(attempt, **kwargs)
    return {"value": value, "type": type(value).__name__, "jitter_calls": len(calls)}


NOTHING = object()


def backoff_calls(rec: gr.Recorder, rng: random.Random) -> None:
    def call(attempt, base, cap, jv):
        args = {"attempt": attempt, "jitter": jv}
        if base is not NOTHING:
            args["base"] = base
        if cap is not NOTHING:
            args["cap"] = cap
        rec.call("backoff_seconds", args, lambda: backoff(attempt, base, cap, jv))

    # the four assertions of test_run_orchestration.py
    call(1, 5, NOTHING, 0)
    call(3, 5, NOTHING, 0)
    call(30, 5, 120, 0)
    call(1, 5, NOTHING, 1)
    attempts = [-5, -1, 0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 20, 24, 25, 26, 30, 40, 53, 54, 55, 62, 63, 64, 100, 1000, 1022, 1023, 1024, 1025, 1100, 2000, 3000]
    bases = [NOTHING, 0, 1, 5, 7, -3, 2 ** 53 + 1, 2 ** 62, 0.0, -0.0, 5.0, 0.1, 1.5, 1e-320, 1e300, 1.7976931348623157e308, NAN, INF, -INF, -5.0]
    caps = [NOTHING, 120.0, 120, 0, 0.0, -1, 1e308, INF, -INF, NAN, 3.5, 7.0, 2.5e-320, 1e15]
    jitters = [0, 0.0, 1, 0.5, 0.123456789, 0.9999999999999999, 4, -1, -4.0, NAN, INF]
    for attempt in attempts:
        for base in bases:
            for cap in caps:
                for jv in (0.0, 0.37, 1):
                    call(attempt, base, cap, jv)
    for jv in jitters:
        for base, cap in itertools.product([NOTHING, 5, 5.0, 3, 0.5], [NOTHING, 120, 30.0, INF]):
            for attempt in (1, 2, 5, 30):
                call(attempt, base, cap, jv)
    # the exact boundary where doubling reaches the cap, one step either side of it, for several bases
    for base in (1, 2, 3, 5, 7, 10, 1.0, 5.0, 0.25):
        for cap in (120.0, 100.0, 40.0, 41.0, 39.0):
            for attempt in range(1, 12):
                call(attempt, base, cap, 0.0)
                call(attempt, base, cap, rng.random())
    for _ in range(3000):
        base = rng.choice([NOTHING, rng.randint(0, 20), rng.uniform(0, 20), rng.choice([0.5, 1, 2, 5])])
        cap = rng.choice([NOTHING, rng.randint(1, 400), rng.uniform(1, 400), 120.0])
        call(rng.randint(-2, 60), base, cap, rng.random())


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    rec = gr.Recorder()
    enum_calls(rec)
    move_calls(rec)
    batch_models(rec)
    status_calls(rec, rng)
    fingerprint_calls(rec, rng)
    backoff_calls(rec, rng)
    rec.call("module_constants", {}, lambda: {"module_has_random_default": rn.backoff_seconds.__kwdefaults__["jitter"] is __import__("random").random,
                                               "kwdefaults": {k: v for k, v in rn.backoff_seconds.__kwdefaults__.items() if k != "jitter"}})
    return gr.serialise(rec, {"python_module": "domain/runs.py"}, seed, oracle.stamp())


if __name__ == "__main__":
    raise SystemExit(gr.main("runs", DEFAULT_OUT, SEED, build))
