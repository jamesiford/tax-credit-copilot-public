"""Mutation self-test for the replay tool: a checker that cannot fail does not count.

Each mutation perturbs ONE thing in a copy of a read-only recording; the replay of that copy against a real Python server must fail,
and the failure must name the route, the case, the category and the field. In `semantic` mode the lexeme / key-order / raw-bytes
mutations must instead be reported as tolerated, and every other mutation must still fail.

    .\\contract\\py.ps1 -m contract.selftest [--scenario p1_query_edges]
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contract import exchange, oracle, replay  # noqa: E402
from contract.jsontext import Num  # noqa: E402


def _first(records: list[dict], pred: Callable[[dict], bool]) -> dict:
    return next(r for r in records if "response" in r and pred(r))


def _walk(node: Any, pred: Callable[[Any], bool], path: str = ""):
    if pred(node):
        yield node, path
    if isinstance(node, dict):
        for k, v in node.items():
            yield from _walk(v, pred, f"{path}.{k}" if path else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, pred, f"{path}[{i}]")


def is_json(r: dict) -> bool:
    return r["response"]["body"].get("kind") == "json"


def mutations(records: list[dict]) -> list[tuple[str, str, str, Callable[[], None]]]:
    """(name, expected category in strict mode, expected category in semantic mode, apply).\n\n    The categories are from the replay\x27s point of view: a field deleted from the RECORDING is an extra field in what the server answered."""
    out = []

    def status():
        r = _first(records, lambda r: r["response"]["status"].text == "200")
        r["response"]["status"] = Num("201")
        out_ids["status"] = r["id"]

    def lexeme():
        r = _first(records, lambda r: is_json(r) and any(isinstance(n, Num) and n.is_integral_text() for n, _ in _walk(r["response"]["body"]["value"], lambda x: isinstance(x, Num))))
        node, path = next((n, p) for n, p in _walk(r["response"]["body"]["value"], lambda x: isinstance(x, Num) and x.is_integral_text()))
        node.text = node.text + ".0"
        out_ids["lexeme"] = r["id"]

    def value():
        r = _first(records, lambda r: is_json(r) and any(isinstance(n, Num) for n, _ in _walk(r["response"]["body"]["value"], lambda x: isinstance(x, Num))))
        node, _ = next((n, p) for n, p in _walk(r["response"]["body"]["value"], lambda x: isinstance(x, Num)))
        node.text = "987654321"
        out_ids["value"] = r["id"]

    def key_order():
        r = _first(records, lambda r: is_json(r) and isinstance(r["response"]["body"]["value"], dict) and len(r["response"]["body"]["value"]) > 2)
        d = r["response"]["body"]["value"]
        items = list(d.items())
        d.clear()
        d.update(dict(reversed(items)))
        out_ids["key_order"] = r["id"]

    def header():
        r = _first(records, lambda r: "content-type" in r["response"]["headers"])
        r["response"]["headers"]["content-type"] = "text/plain"
        out_ids["header"] = r["id"]

    def missing():
        r = _first(records, lambda r: is_json(r) and isinstance(r["response"]["body"]["value"], dict) and len(r["response"]["body"]["value"]) > 1)
        d = r["response"]["body"]["value"]
        del d[list(d)[-1]]
        out_ids["missing"] = r["id"]

    def extra():
        r = _first(records, lambda r: is_json(r) and isinstance(r["response"]["body"]["value"], dict))
        r["response"]["body"]["value"]["zz_extra_field"] = True
        out_ids["extra"] = r["id"]

    def message():
        r = _first(records, lambda r: is_json(r) and isinstance(r["response"]["body"]["value"], dict) and isinstance(r["response"]["body"]["value"].get("detail"), str))
        r["response"]["body"]["value"]["detail"] += " (changed)"
        out_ids["message"] = r["id"]

    def array_length():
        r = _first(records, lambda r: is_json(r) and any(isinstance(n, list) and len(n) > 0 for n, _ in _walk(r["response"]["body"]["value"], lambda x: isinstance(x, list))))
        node, _ = next((n, p) for n, p in _walk(r["response"]["body"]["value"], lambda x: isinstance(x, list) and len(x) > 0))
        node.pop()
        out_ids["array_length"] = r["id"]

    def null_for_value():
        r = _first(records, lambda r: is_json(r) and any(isinstance(v, str) for d, _ in _walk(r["response"]["body"]["value"], lambda x: isinstance(x, dict)) for v in d.values()))
        d, _ = next((d, p) for d, p in _walk(r["response"]["body"]["value"], lambda x: isinstance(x, dict) and any(isinstance(v, str) for v in x.values())))
        k = next(k for k, v in d.items() if isinstance(v, str))
        d[k] = None
        out_ids["null_for_value"] = r["id"]

    for name, strict, semantic, fn in [
        ("status", "status", "status", status), ("lexeme", "number-lexeme", "tolerated", lexeme), ("value", "value", "value", value),
        ("key_order", "key-order", "tolerated", key_order), ("header", "header", "header", header), ("missing", "extra-field", "extra-field", missing),
        ("extra", "missing-field", "missing-field", extra), ("message", "value", "value", message), ("array_length", "array-length", "array-length", array_length),
        ("null_for_value", "type", "type", null_for_value),
    ]:
        out.append((name, strict, semantic, fn))
    return out


out_ids: dict[str, str] = {}


def _entry(record: dict, index: int = 0) -> dict:
    return record["response"]["body"]["zip_entries"][index]


def _flip(sha: str) -> str:
    return ("0" if sha[0] != "0" else "1") + sha[1:]


def container_mutations() -> list[tuple[str, str, str, Callable[[dict], None], str | None, str | None]]:
    """(name, scenario, case, mutate(raw ACTUAL record), expected category, expected path fragment).

    These mutate what the SERVER answered, before normalisation, because the question is whether the container rule masks a real
    change: a change the rule must not hide is caught, a change in the container's bytes alone (tier D) must not be reported.
    A `None` category means "must be tolerated: no difference at all".
    """
    def val(r: dict) -> dict:
        return r["response"]["body"]["value"]

    def hdr(name: str) -> Callable[[dict, str], None]:
        return lambda r, v: r["response"]["headers"].__setitem__(name, v)

    pkg, art, drafts, chan = ("p1_artifacts_ai", "package.create"), ("p1_artifacts_ai", "artifact.download"), ("p1_program_drafts", "second-export"), ("g1_rest", "download.owner")
    link, commit, manifest = ("g1_rest", "write.claim-package-link"), ("g1_rest", "write.claim-package-commit"), ("p1_program_drafts", "second-manifest")
    return [
        ("size_is_a_string", *pkg, lambda r: val(r).__setitem__("size_bytes", "10011"), "value", "size_bytes"),
        ("size_is_negative", *pkg, lambda r: val(r).__setitem__("size_bytes", Num("-5")), "type", "size_bytes"),
        ("size_is_a_float", *pkg, lambda r: val(r).__setitem__("size_bytes", Num("10011.0")), "type", "size_bytes"),
        ("hash_is_null", *pkg, lambda r: val(r).__setitem__("sha256", None), "type", "sha256"),
        ("hash_wrong_length", *pkg, lambda r: val(r).__setitem__("sha256", val(r)["sha256"][:63]), "value", "sha256"),
        ("hash_uppercase", *pkg, lambda r: val(r).__setitem__("sha256", val(r)["sha256"].upper()), "value", "sha256"),
        ("hash_field_missing", *pkg, lambda r: val(r).pop("sha256"), "missing-field", "sha256"),
        ("hash_is_a_number", *commit, lambda r: val(r)["facts"]["result"].__setitem__("sha256", Num("7")), "type", "facts.result.sha256"),
        ("displayed_hash_malformed", *link, lambda r: val(r)["blocks"][1]["rows"][1].__setitem__(1, "not-a-hash"), "value", "blocks[1].rows[1][1]"),
        ("neighbour_field_changed", *link, lambda r: val(r)["facts"].__setitem__("file_name", "other.xlsx"), "value", "facts.file_name"),
        ("manifest_bytes_is_null", *manifest, lambda r: val(r).__setitem__("bundle_bytes", None), "type", "bundle_bytes"),
        ("manifest_hash_wrong_type", *manifest, lambda r: val(r).__setitem__("bundle_sha256", True), "type", "bundle_sha256"),
        ("header_hash_not_the_bytes", *art, lambda r: hdr("x-content-sha256")(r, _flip(r["response"]["headers"]["x-content-sha256"])), "header", "x-content-sha256"),
        ("header_hash_malformed", *drafts, lambda r: hdr("x-bundle-sha256")(r, "zz"), "header", "x-bundle-sha256"),
        ("zip_member_renamed", *art, lambda r: _entry(r).__setitem__("name", _entry(r)["name"] + "-renamed"), "zip-entry", "body.zip_entries["),
        ("zip_member_content_changed", *art, lambda r: _entry(r, 1).__setitem__("sha256", _flip(_entry(r, 1)["sha256"])), "zip-entry", ".sha256"),
        ("zip_member_size_changed", *art, lambda r: _entry(r, 1).__setitem__("size", Num(str(int(_entry(r, 1)["size"].text) + 1))), "zip-entry", ".size"),
        ("zip_member_missing", *art, lambda r: r["response"]["body"]["zip_entries"].pop(), "zip-entry", "body.zip_entries["),
        ("zip_member_extra", *art, lambda r: r["response"]["body"]["zip_entries"].append({"name": "extra.txt", "size": Num("1"), "sha256": "0" * 64}), "zip-entry", "extra.txt"),
        ("zip_members_reordered", *art, lambda r: r["response"]["body"]["zip_entries"].reverse(), "zip-entry", "$order"),
        ("export_member_content_changed", *drafts, lambda r: _entry(r, 2).__setitem__("sha256", _flip(_entry(r, 2)["sha256"])), "zip-entry", ".sha256"),
        ("download_member_missing", *chan, lambda r: r["response"]["body"]["zip_entries"].pop(0), "zip-entry", "body.zip_entries["),
        ("response_not_a_zip", *art, lambda r: r["response"]["body"].pop("zip_entries"), "zip-entry", "body.zip_entries"),
        # Tier D: only the container's own bytes change (a different zlib, a .NET writer). Members are identical: nothing may be reported.
        ("container_bytes_differ_artifact", *art, lambda r: (r["response"]["body"].update(sha256="1" * 64, length=Num("1")), hdr("x-content-sha256")(r, "1" * 64)), None, None),
        ("container_hash_and_size_differ_package", *pkg, lambda r: (val(r).__setitem__("sha256", "2" * 64), val(r).__setitem__("size_bytes", Num("1"))), None, None),
        ("container_bytes_differ_export", *drafts, lambda r: (r["response"]["body"].update(sha256="3" * 64, length=Num("9")), hdr("x-bundle-sha256")(r, "3" * 64)), None, None),
    ]


def run_container_mutations() -> list[dict[str, Any]]:
    """Replay the scenarios once, keep the raw answers, mutate copies of them, normalise, compare with the recording."""
    import asyncio

    from contract import compare, normalise

    muts = container_mutations()
    results: list[dict[str, Any]] = []
    for scenario_name in sorted({m[1] for m in muts}):
        scenario = json.loads((ROOT / "contract" / "scenarios" / f"{scenario_name}.json").read_text(encoding="utf-8"))
        proc, url = replay.spawn_server(scenario["profile"], replay.auth_limit(scenario_name))
        try:
            raw = asyncio.run(replay.run_against(url, scenario))
        finally:
            proc.kill()
        expected = {r["id"]: r for r in exchange.load_records((ROOT / "contract" / "recordings" / f"{scenario_name}.jsonl").read_text(encoding="utf-8"))}
        by_id = {r["id"]: r for r in raw}
        for name, scenario_of, case, mutate, category, fragment in (m for m in muts if m[1] == scenario_name):
            for mode in ("strict", "semantic"):
                actual = copy.deepcopy(by_id[case])
                actual["response"]["body"] = _numify(actual["response"]["body"])
                mutate(actual)
                shown = exchange.roundtrip([normalise.apply(actual)])[0]
                failures, tolerated = compare.split(compare.compare_record(expected[case], shown), mode)
                hit = next((d for d in failures if d["category"] == category and fragment in d["path"]), None) if category else None
                ok = (not failures and not tolerated) if category is None else hit is not None
                route = f"{expected[case]['request']['method']} {expected[case]['request']['path']}"
                detail = hit or (failures[0] if failures else None)
                results.append({"group": "container", "mode": mode, "mutation": name, "scenario": scenario_name, "case": case, "route": route, "caught": ok,
                                "reported": detail if category else "no difference (tier D)" if ok else failures[:1]})
                print(f"{'CAUGHT' if ok else 'MISSED'} [{mode}] {name} @ {scenario_name}/{case}: {json.dumps(results[-1]['reported'])[:240]}", flush=True)
    return results


def _numify(body: dict) -> dict:
    """The recorder's raw record carries Python ints for the zip sizes; a recording read back carries `Num`. Mutations assume the latter."""
    for entry in body.get("zip_entries") or []:
        if isinstance(entry.get("size"), int):
            entry["size"] = Num(str(entry["size"]))
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="p1_query_edges")
    parser.add_argument("--allow-other-python", action="store_true", help="cross-check only")
    args = parser.parse_args()
    oracle.require(args.allow_other_python)
    src = ROOT / "contract" / "recordings" / f"{args.scenario}.jsonl"
    original = exchange.load_records(src.read_text(encoding="utf-8"))
    proc, url = replay.spawn_server("P1")
    results = []
    try:
        for mode in ("strict", "semantic"):
            for name, strict_cat, semantic_cat, _fn in mutations(original):
                records = copy.deepcopy(original)
                dict(((n, f) for n, _s, _m, f in mutations(records)))[name]()
                tmp = Path(tempfile.mkdtemp(prefix="tcc-mutation-"))
                (tmp / f"{args.scenario}.jsonl").write_text("".join(exchange.dump_record(r) + "\n" for r in records), encoding="utf-8", newline="\n")
                os.environ["CONTRACT_RECORDINGS"] = str(tmp)
                report = replay.replay_one(args.scenario, url, mode)
                shutil.rmtree(tmp, ignore_errors=True)
                hit = out_ids[name]
                named = [d for d in report["failures"] if d["case"] == hit]
                tolerated = [d for d in report["tolerated"] if d["case"] == hit]
                if mode == "strict":
                    ok = bool(named) and any(d["category"] == strict_cat for d in named)
                    detail = named[0] if named else None
                elif semantic_cat == "tolerated":
                    ok = not named and bool(tolerated)
                    detail = tolerated[0] if tolerated else None
                else:
                    ok = bool(named) and any(d["category"] == semantic_cat for d in named)
                    detail = named[0] if named else None
                results.append({"mode": mode, "mutation": name, "case": hit, "caught": ok, "reported": detail})
                print(f"{'CAUGHT' if ok else 'MISSED'} [{mode}] {name} @ {hit}: {json.dumps(detail)[:260]}", flush=True)
    finally:
        proc.kill()
    results += run_container_mutations()
    stamp = oracle.describe()
    (ROOT / "contract" / "docs" / "mutation-selftest.json").write_text(json.dumps({"interpreter": stamp, "results": results}, indent=1), encoding="utf-8", newline="\n")
    missed = [r for r in results if not r["caught"]]
    print(f"{len(results) - len(missed)}/{len(results)} mutations caught")
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
