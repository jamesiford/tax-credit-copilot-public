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

from contract import exchange, replay  # noqa: E402
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenario", default="p1_query_edges")
    args = parser.parse_args()
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
    (ROOT / "contract" / "docs" / "mutation-selftest.json").write_text(json.dumps(results, indent=1), encoding="utf-8", newline="\n")
    missed = [r for r in results if not r["caught"]]
    print(f"{len(results) - len(missed)}/{len(results)} mutations caught")
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
