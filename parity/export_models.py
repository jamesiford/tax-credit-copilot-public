"""Golden vectors for the pure data models (stage DS5): ``domain/programs.py``, ``domain/findings.py``,
``domain/warehouse.py`` and ``application/open_year.py``.

For a data model the scenarios are construction (with every default), validation errors (message included), equality,
hashability, ``dataclasses.replace`` (which re-runs ``__post_init__``), the frozen-assignment error, and every method
or property output: ``ProgramEntry.status``, ``FindingResolution.to_dict``, ``base_year_key``, ``is_open`` and
``open_year_reading``. The two repository ``Protocol`` classes have no behaviour to record; the constants are recorded once.

``open_year.today`` is pinned by assignment (as the Python tests do with ``monkeypatch``) and the pinned date is part of the
arguments, so no output depends on the day the golden was made.

Usage: python parity/export_models.py [--check] [--out FILE] [--seed N]
"""
from __future__ import annotations

import dataclasses
import math
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle  # noqa: E402

OVERRIDE = oracle.require()
ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import golden_rec as gr  # noqa: E402
from application import open_year as oy  # noqa: E402
from domain import findings as fnd  # noqa: E402
from domain import programs as prg  # noqa: E402
from domain import warehouse as wh  # noqa: E402

DEFAULT_OUT = Path(__file__).resolve().parent / "goldens" / "models.jsonl.gz"
SEED = 20261117
INF = float("inf")
NAN = float("nan")


def tagged(x):
    """Decode the exporter's argument tags back to Python values (the inverse of ``golden_rec.enc`` for dates)."""
    if isinstance(x, dict):
        if set(x) == {"$date"}:
            return date.fromisoformat(x["$date"])
        if set(x) == {"$dt"}:
            return datetime.fromisoformat(x["$dt"])
        return {k: tagged(v) for k, v in x.items()}
    if isinstance(x, list):
        return [tagged(v) for v in x]
    return x


def out_of(obj) -> dict:
    return {"fields": gr.enc(obj), "order": [f.name for f in dataclasses.fields(obj)]}


MODELS = {"engine_profile": prg.EngineProfile, "program_entry": prg.ProgramEntry, "finding_resolution": fnd.FindingResolution,
          "run_manifest": wh.RunManifest, "manual_override": wh.ManualOverride}


def model_calls(rec: gr.Recorder, name: str, specs: list[dict], changes: list[dict], pairs: list[tuple[dict, dict]]) -> None:
    cls = MODELS[name]
    for kw in specs:
        rec.call("construct_" + name, {"kw": kw}, lambda kw=kw: out_of(cls(**tagged(kw))))
    for kw in specs[: len(changes) * 3]:
        for ch in changes:
            rec.call("replace_" + name, {"kw": kw, "changes": ch}, lambda kw=kw, ch=ch: out_of(dataclasses.replace(cls(**tagged(kw)), **tagged(ch))))
    for a, b in pairs:
        rec.call("equals_" + name, {"a": a, "b": b}, lambda a=a, b=b: cls(**tagged(a)) == cls(**tagged(b)))
        rec.call("hash_" + name, {"a": a, "b": b}, lambda a=a, b=b: _hash_pair(cls(**tagged(a)), cls(**tagged(b))))
    if specs:
        for f in dataclasses.fields(cls):
            rec.call("frozen_assign_" + name, {"kw": specs[0], "field": f.name}, lambda f=f: setattr(cls(**tagged(specs[0])), f.name, 1))


def _hash_pair(a, b):
    ha = hash(a)
    return {"hashable": True, "equal_objects_equal_hash": (a != b) or ha == hash(b)}


# --------------------------------------------------------------------------- programs


def programs_cases(rec: gr.Recorder, rng: random.Random) -> None:
    rec.call("constants_programs", {}, lambda: {
        "credit": list(prg.SUPPORTED_CREDIT_MODELS), "headcount": list(prg.SUPPORTED_HEADCOUNT_MODELS),
        "lifecycles": list(prg.STORED_LIFECYCLES), "levels": list(prg.JURISDICTION_LEVELS)})
    for msg in ("", "x", "manifest 'programs.json': entry 'GA_JTC': lifecycle must be one of ['draft']", "ünï \u2014 §", "line1\nline2"):
        rec.call("registry_error", {"message": msg}, lambda msg=msg: {"str": str(prg.RegistryError(msg)), "args": [msg],
                                                                           "is_value_error": issubclass(prg.RegistryError, ValueError)})
    profiles = [{}, {"credit_model": "per_net_new_job"}, {"credit_model": "pct_of_wages"}, {"headcount_model": "fte"},
                {"credit_model": "", "headcount_model": ""}, {"credit_model": "ünï", "headcount_model": "one_zero"}]
    model_calls(rec, "engine_profile", profiles, [{}, {"credit_model": "x"}, {"headcount_model": "y"}],
                [(a, b) for a in profiles for b in profiles])
    entry = {"code": "GA_JTC", "name": "Georgia Job Tax Credit", "level": "state", "jurisdiction_code": "GA", "pack_file": "ga_jtc.json"}
    lifecycles = ["described", "draft", "retired", "calculable", "", "Retired", "DRAFT", "weird", "ünï"]
    entries = [entry, {**entry, "state": "GA"}, {**entry, "state": None, "level": "federal", "jurisdiction_code": "US", "code": "FED_WOTC"},
               {**entry, "notes": "n", "state": "GA", "engine_profile": {"credit_model": "per_net_new_job", "headcount_model": "one_zero"}}]
    entries += [{**entry, "lifecycle": lc} for lc in lifecycles]
    entries += [{**entry, "code": c} for c in ("", "ga_jtc", "Straße", "\U00010000")]
    # an engine_profile is an object, so it is built in the lambda; the argument records its two fields
    def mk(e: dict) -> prg.ProgramEntry:
        e = dict(e)
        if isinstance(e.get("engine_profile"), dict):
            e["engine_profile"] = prg.EngineProfile(**e["engine_profile"])
        return prg.ProgramEntry(**e)

    for e in entries:
        rec.call("construct_program_entry", {"kw": e}, lambda e=e: out_of(mk(e)))
        for years in ([], [2023], [2019, 2020, 2021, 2022, 2023, 2024, 2025, 2026], None, [0], [-1]):
            rec.call("program_entry_status", {"kw": e, "authored_years": years}, lambda e=e, years=years: mk(e).status(years))
    for a in entries[:8]:
        for b in entries[:8]:
            rec.call("equals_program_entry", {"a": a, "b": b}, lambda a=a, b=b: mk(a) == mk(b))
            rec.call("hash_program_entry", {"a": a, "b": b}, lambda a=a, b=b: _hash_pair(mk(a), mk(b)))
    for ch in ({"lifecycle": "retired"}, {"state": "NC"}, {"state": None}, {"name": "x", "notes": "y"}, {}):
        rec.call("replace_program_entry", {"kw": entry, "changes": ch}, lambda ch=ch: out_of(dataclasses.replace(mk(entry), **ch)))
    rec.call("replace_program_entry", {"kw": entry, "changes": {"engine_profile": {"credit_model": "z"}}},
             lambda: out_of(dataclasses.replace(mk(entry), engine_profile=prg.EngineProfile(credit_model="z"))))
    for f in dataclasses.fields(prg.ProgramEntry):
        rec.call("frozen_assign_program_entry", {"kw": entry, "field": f.name}, lambda f=f: setattr(mk(entry), f.name, 1))


# --------------------------------------------------------------------------- findings


def findings_cases(rec: gr.Recorder, rng: random.Random) -> None:
    base = {"finding_id": "f-1", "client_id": 1001, "tax_year": 2023, "resolution": "accept", "decided_by": "analyst@example.test", "decided_at": "2026-09-01T10:00:00Z"}
    details = [None, {}, {"keep_worksite": "GA_GA-010"}, {"a": 1, "b": 2}, {"b": 2, "a": 1}, {"a": 1.0, "b": 2}, {"a": True, "b": 2}, {"n": {"x": [1, 2, {"y": None}]}},
               {"a": 1, "b": 2, "c": [1.5, "é"]}, {"k": 10 ** 20}, {"k": 1e20}, {"k": 2 ** 53 + 1}, {"k": float(2 ** 53)}, {"k": [True]}, {"k": [1]}, {"k": 0}, {"k": False},
               {"k": 0.0}, {"k": -0.0}, {"k": None}, {"k": ""}]
    notes = [None, "", "n", "ünï \u2014 \U00010000", "x" * 3]
    specs = [base]
    specs += [{**base, "resolution": r} for r in ("accept", "assign", "drop", "flag", "other", "", "ACCEPT")]
    specs += [{**base, "detail": d} for d in details]
    specs += [{**base, "note": n, "superseded_at": s} for n in notes for s in (None, "2026-10-01T00:00:00Z", "")]
    specs += [{**base, "client_id": c, "tax_year": y} for c in (0, -1, 2 ** 40) for y in (0, 2019, 2026, -5)]
    specs += [{"finding_id": "f", "client_id": 1, "tax_year": 2, "resolution": "drop", "decided_by": "d", "decided_at": "t", "detail": {"a": 1}, "note": "n", "superseded_at": "s"}]
    for kw in specs:
        rec.call("construct_finding_resolution", {"kw": kw}, lambda kw=kw: out_of(fnd.FindingResolution(**kw)))
        rec.call("finding_to_dict", {"kw": kw}, lambda kw=kw: fnd.FindingResolution(**kw).to_dict())
    pairs = [(a, b) for a in specs[:6] + specs[8:30] for b in (specs[0], specs[10], specs[12], specs[13]) ]
    pairs += [({**base, "detail": a}, {**base, "detail": b}) for a in details for b in details]
    pairs += [({**base, "note": a}, {**base, "note": b}) for a in notes for b in notes]
    for a, b in pairs:
        rec.call("equals_finding_resolution", {"a": a, "b": b}, lambda a=a, b=b: fnd.FindingResolution(**a) == fnd.FindingResolution(**b))
    for kw in (base, {**base, "detail": None}, {**base, "detail": {"a": 1}}, {**base, "detail": {}}, {**base, "note": "n"}):
        rec.call("hash_finding_resolution", {"a": kw, "b": kw}, lambda kw=kw: _hash_pair(fnd.FindingResolution(**kw), fnd.FindingResolution(**kw)))
    for ch in ({"resolution": "drop"}, {"detail": {"a": 1}}, {"detail": None}, {"superseded_at": "2027-01-01"}, {"note": None}, {}):
        rec.call("replace_finding_resolution", {"kw": {**base, "detail": {"keep": 1}}, "changes": ch},
                 lambda ch=ch: out_of(dataclasses.replace(fnd.FindingResolution(**{**base, "detail": {"keep": 1}}), **ch)))
    for f in dataclasses.fields(fnd.FindingResolution):
        rec.call("frozen_assign_finding_resolution", {"kw": base, "field": f.name}, lambda f=f: setattr(fnd.FindingResolution(**base), f.name, 1))
    # to_dict hands back the very dict it was given (no copy); recorded so the C# side keeps the reference
    d = {"keep": 1}
    rec.call("finding_detail_identity", {"detail": d}, lambda: fnd.FindingResolution(**{**base, "detail": d}).to_dict()["detail"] is d)


# --------------------------------------------------------------------------- warehouse

UTC = timezone.utc
T0 = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def d(y, m, dd):
    return {"$date": date(y, m, dd).isoformat()}


def dt(x: datetime):
    return {"$dt": x.isoformat()}


def manifest_base(**kw) -> dict:
    b = {"run_id": "run-0001", "client_id": 1001, "program_code": "GA_JTC", "tax_year": 2023, "fiscal_year_begin": d(2023, 7, 28),
         "fiscal_year_end": d(2024, 8, 2), "run_started_at": dt(T0), "run_status": "success"}
    b.update(kw)
    return b


def warehouse_cases(rec: gr.Recorder, rng: random.Random) -> None:
    rec.call("constants_warehouse", {}, lambda: {"run_statuses": sorted(wh.RUN_STATUSES), "columns": list(wh.RUN_MANIFEST_COLUMNS),
                                                  "override_scopes": sorted(wh.OVERRIDE_SCOPES), "run_statuses_type": type(wh.RUN_STATUSES).__name__})
    full = manifest_base(entity_id=7, source_snapshot_id="snap", step1_assumption_set_id="GDS-STEP1-2026-08-25-v8", step1_assumption_sha256="ab" * 32,
                         onezero_assumption_set_id="GDS-ONEZERO-2026-08-24-v7", onezero_assumption_sha256="cd" * 32, rule_pack_version="2023.json",
                         code_commit="deadbeef", calculation_id="calc", run_completed_at=dt(T0 + timedelta(minutes=3, microseconds=7)),
                         superseded_by_run_id="run-0002", triggered_by="user@example.test")
    statuses = ["running", "success", "failed", "superseded", "", "Success", "SUCCESS", "done", "run", " success", "success ", "it's", 'say "hi"', "both ' and \"",
                "back\\slash", "tab\there", "new\nline", "cr\rx", "é", "\u2014", "\U00010000", "\x00", "\x7f", "\xa0", "\u200b", "\u2028", "\x80", "\ud800", "\ufeff",
                "\u0378", "\u00ad", "\ue000", "\U000e0001"]
    specs = [manifest_base(), full]
    specs += [manifest_base(run_status=s) for s in statuses]
    windows = [((2023, 1, 1), (2023, 12, 31)), ((2023, 1, 1), (2023, 1, 2)), ((2023, 1, 1), (2023, 1, 1)), ((2023, 1, 2), (2023, 1, 1)), ((2024, 2, 28), (2024, 2, 29)),
               ((2024, 2, 29), (2025, 2, 28)), ((2023, 7, 28), (2024, 8, 2)), ((1, 1, 1), (1, 1, 2)), ((999, 12, 31), (1000, 1, 1)), ((9999, 12, 30), (9999, 12, 31)),
               ((9999, 12, 31), (9999, 12, 31)), ((2024, 12, 31), (2023, 1, 1)), ((100, 1, 1), (100, 1, 1)), ((2100, 2, 28), (2100, 3, 1))]
    specs += [manifest_base(fiscal_year_begin=d(*a), fiscal_year_end=d(*b)) for a, b in windows]
    specs += [manifest_base(run_status="bogus", fiscal_year_begin=d(2023, 1, 2), fiscal_year_end=d(2023, 1, 1)),
              manifest_base(run_status="running", run_completed_at=None, calculation_id=None)]
    starts = [T0, datetime(2026, 1, 2, 3, 4, 5), datetime(2026, 1, 2, 3, 4, 5, 123456), datetime(2026, 1, 2, 3, 4, 5, 100000, tzinfo=timezone(timedelta(hours=5, minutes=30))),
              datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=-8))), datetime(1, 1, 1), datetime(9999, 12, 31, 23, 59, 59, 999999)]
    specs += [manifest_base(run_started_at=dt(s)) for s in starts]
    specs += [manifest_base(client_id=c, tax_year=y) for c in (0, -1, 2 ** 40) for y in (0, 2019, 2026, -5)]
    changes = [{}, {"run_status": "failed"}, {"run_status": "bogus"}, {"fiscal_year_end": d(2020, 1, 1)}, {"fiscal_year_begin": d(2030, 1, 1)},
               {"run_completed_at": dt(T0 + timedelta(hours=1))}, {"entity_id": None}, {"superseded_by_run_id": "r2", "run_status": "superseded"},
               {"run_status": "bogus", "fiscal_year_end": d(2020, 1, 1)}, {"tax_year": 2024}, {"program_code": "ga_jtc"}]
    pairs = [(a, b) for a in specs[:6] for b in specs[:6]]
    pairs += [(manifest_base(), manifest_base(run_status=s)) for s in ("failed", "success")]
    pairs += [(manifest_base(), manifest_base(**{k: v})) for k, v in (("client_id", 1002), ("run_id", "x"), ("tax_year", 2024), ("entity_id", 1), ("code_commit", "c"),
                                                                      ("fiscal_year_end", d(2024, 8, 3)), ("run_started_at", dt(T0 + timedelta(microseconds=1))))]
    model_calls(rec, "run_manifest", specs, changes, pairs)
    # the keyword-dict construction used by the warehouse adapters and tests: unknown keys are filtered by the caller
    for kw in (full, manifest_base()):
        rec.call("manifest_columns_vs_fields", {"kw": kw}, lambda kw=kw: {
            "fields": [f.name for f in dataclasses.fields(wh.RunManifest)],
            "columns": list(wh.RUN_MANIFEST_COLUMNS),
            "same_set": set(f.name for f in dataclasses.fields(wh.RunManifest)) == set(wh.RUN_MANIFEST_COLUMNS)})
    ov = {"override_id": "o1", "run_id": "run-0001", "client_id": 1001, "scope": "unit", "target_key": "GA_JTC:GA_GA-010", "field_changed": "base_year",
          "value_before": "2023", "value_after": "2022", "reason_code": "partner", "justification_text": "why", "created_by": "u", "created_at": dt(T0)}
    ov_specs = [ov, {**ov, "approved_by": "boss", "approved_at": dt(T0 + timedelta(days=1))}, {**ov, "value_before": None, "value_after": None, "reason_code": None, "justification_text": None}]
    ov_specs += [{**ov, "scope": s} for s in ("employee", "record", "unit", "client", "", "Unit", "EMPLOYEE", "it's", 'a"b', "x\ny", "é", "\U00010000", "\xa0", "all")]
    ov_specs += [{**ov, "created_at": dt(s)} for s in starts]
    ov_changes = [{}, {"scope": "employee"}, {"scope": "client"}, {"value_after": None}, {"approved_by": "x"}, {"created_by": "y", "scope": "record"}]
    ov_pairs = [(a, b) for a in ov_specs[:5] for b in ov_specs[:5]] + [(ov, {**ov, "justification_text": "other"}), (ov, {**ov, "created_at": dt(T0 + timedelta(microseconds=1))})]
    model_calls(rec, "manual_override", ov_specs, ov_changes, ov_pairs)
    for p, w in (("GA_JTC", "GA_GA-010"), ("", ""), ("a:b", "c:d"), ("ünï", "\U00010000"), ("GA_JTC", ""), ("ga_jtc", "ga_ga-010"), (" ", " "), ("x\n", "\t")):
        rec.call("base_year_key", {"program_code": p, "worksite_id": w}, lambda p=p, w=w: wh.base_year_key(p, w))


# --------------------------------------------------------------------------- open year


def pinned(today: date, fn):
    real = oy.today
    oy.today = lambda: today
    try:
        return fn()
    finally:
        oy.today = real


def is_open_case(rec: gr.Recorder, window_end, on=None, today=None) -> None:
    args = {"window_end": window_end}
    if on is not None:
        args["on"] = on
    if today is not None:
        args["today"] = today

    def run():
        w = tagged(window_end)
        kw = {} if on is None else {"on": tagged(on)}
        if today is None:
            return oy.is_open(w, **kw)
        return pinned(tagged(today), lambda: oy.is_open(w, **kw))

    rec.call("is_open", args, run)


def open_year_cases(rec: gr.Recorder, rng: random.Random) -> None:
    rec.call("constants_open_year", {}, lambda: {"min_open_months": oy.MIN_OPEN_MONTHS, "today_is_date": type(oy.today()).__name__})
    is_open_case(rec, d(2026, 12, 31), on=d(2026, 9, 24))
    is_open_case(rec, "2025-12-31", on=d(2026, 9, 24))
    for today in (date(2026, 9, 24), date(2027, 2, 1), date(2024, 2, 29), date(2023, 12, 31), date(1, 1, 2), date(9999, 12, 30)):
        for off in (-1, 0, 1, 366):
            try:
                end = today + timedelta(days=off)
            except OverflowError:
                continue
            is_open_case(rec, {"$date": end.isoformat()}, on={"$date": today.isoformat()})
            is_open_case(rec, end.isoformat(), on={"$date": today.isoformat()})
            is_open_case(rec, end.isoformat() + "T23:59:59", on={"$date": today.isoformat()})
            is_open_case(rec, end.isoformat() + " trailing text", today={"$date": today.isoformat()})
            is_open_case(rec, {"$date": end.isoformat()}, today={"$date": today.isoformat()})
    for end in ("", "None", "2026", "2026-12", "2026-13-01", "2026-02-30", "0000-01-01", "20261231", "2026-W52-1", "26-12-31", "abcdefghij", " 2026-12-31", "2026-12-31 ",
                "\u0662\u0660\u0662\u0666-12-31", "2026/12/31", "2026-1-31", "２０２６-１２-３１", "2026-12-3", "2026-12-31\u2014", "é026-12-31"):
        is_open_case(rec, end, on=d(2026, 9, 24))
    for end in (None, 20261231, 5, 2026.5, True, False, 0):
        is_open_case(rec, end, on=d(2026, 9, 24))
    is_open_case(rec, d(2026, 12, 31), today=d(2026, 12, 31))
    is_open_case(rec, d(2026, 12, 31), on=d(2026, 12, 31), today=d(2020, 1, 1))
    for _ in range(300):
        y = rng.randint(1, 9998)
        today = date(2000, 1, 1) + timedelta(days=rng.randint(0, 20000))
        end = today + timedelta(days=rng.randint(-3, 3))
        is_open_case(rec, end.isoformat() if rng.random() < 0.5 else {"$date": end.isoformat()}, today={"$date": today.isoformat()})
    ocases = []
    trends = [{"base_average_headcount": 10.0, "final_high_water_mark": 14.0, "per_job_usd": 3500.0}]
    trends += [{"base_average_headcount": b, "final_high_water_mark": h, "per_job_usd": p}
               for b in (0.0, 10.0, 10.5, -3.0, 1e308, 5e-324, NAN, INF, -0.0, 7, "10", "10.25", " 1_0 ", "abc", "", None, True, 10 ** 20, 10 ** 400, [1], {"a": 1})
               for h in (14.0,) for p in (3500.0,)]
    trends += [{"base_average_headcount": 10.0, "final_high_water_mark": h, "per_job_usd": p}
               for h in (0.0, 9.0, 13.0, 14.0, 20.0, NAN, INF, -0.0, 12, "15", "x", None, 10 ** 400, [1], False)
               for p in (3500.0, 0.0, 0, 0.5, -1.0, NAN, INF, "2500", "z", None, False, True, 10 ** 400, [], {})]
    for tr in trends:
        for avg in (13.0, 11.0, 12.0, 10.0, 0.0, 0, None, "", "13.5", "abc", False, True, NAN, INF, -0.0, 10 ** 20, 10 ** 400, [], {}, 5e-324, 12.000000000000002, 11.999999999999998):
            ocases.append((avg, tr, {"threshold": 2.0, "per_job_usd": 3500.0}, 2.0))
    base_tr = trends[0]
    statutes = [{}, {"threshold": 2.0}, {"threshold": 2}, {"threshold": 0}, {"threshold": -1.0}, {"threshold": None}, {"threshold": "2"}, {"threshold": "x"}, {"threshold": NAN},
                {"threshold": INF}, {"threshold": 3.0000000000000004}, {"threshold": 3.0}, {"threshold": 2.9999999999999996}, {"per_job_usd": 0}, {"per_job_usd": None},
                {"per_job_usd": ""}, {"per_job_usd": 0.0}, {"per_job_usd": 1234.5}, {"per_job_usd": "77"}, {"per_job_usd": "x"}, {"per_job_usd": [1]}, {"per_job_usd": [], "threshold": 1},
                {"per_job_usd": 10 ** 400}, {"other": 1}, {"threshold": True}, {"threshold": [1]}, {"threshold": 10 ** 400}]
    for st in statutes:
        for thr in (2.0, 2, 0.0, -1.0, None, "5", "bad", NAN, INF, 10 ** 400, [1]):
            for avg in (13.0, 10.0, 10.0000000000000002, 12.0, 11.999999999999998):
                ocases.append((avg, base_tr, st, thr))
    # the tie edge: net_new exactly at, one ulp either side of, the threshold
    for thr in (2.0, 0.0, 1e-9, 0.1, 5.5):
        for delta in (math.nextafter(thr, -INF), thr, math.nextafter(thr, INF)):
            ocases.append((10.0 + delta, base_tr, {"threshold": thr}, thr))
            ocases.append((10.0 + delta, {**base_tr, "base_average_headcount": 0.0}, {}, thr))
    for avg, tr, st, thr in ocases:
        def run(avg=avg, tr=tr, st=st, thr=thr):
            r = oy.open_year_reading(avg, SimpleNamespace(**tr), st, thr)
            return dict(vars(r))

        rec.call("open_year_reading", {"average_headcount": avg, "trend": tr, "statute": st, "threshold": thr}, run)
    for _ in range(600):
        tr = {"base_average_headcount": round(rng.uniform(0, 100), 2), "final_high_water_mark": round(rng.uniform(0, 120), 2), "per_job_usd": rng.choice([3500.0, 0.0, 1200.5, 0])}
        st = rng.choice([{}, {"threshold": rng.choice([0.0, 1.0, 2.0, 5.5, 13.0, 0.01])}, {"per_job_usd": rng.choice([0, 3500.0, 12.25])}])
        avg = round(tr["base_average_headcount"] + rng.choice([-5.0, -0.01, 0.0, 0.01, 1.0, 2.0, 2.01, 13.0]), 2)
        thr = rng.choice([0.0, 1.0, 2.0, 5.5])

        def run(avg=avg, tr=tr, st=st, thr=thr):
            return dict(vars(oy.open_year_reading(avg, SimpleNamespace(**tr), st, thr)))

        rec.call("open_year_reading", {"average_headcount": avg, "trend": tr, "statute": st, "threshold": thr}, run)


def build(seed: int) -> bytes:
    rng = random.Random(seed)
    rec = gr.Recorder()
    programs_cases(rec, rng)
    findings_cases(rec, rng)
    warehouse_cases(rec, rng)
    open_year_cases(rec, rng)
    return gr.serialise(rec, {}, seed, oracle.stamp())


if __name__ == "__main__":
    raise SystemExit(gr.main("models", DEFAULT_OUT, SEED, build))
