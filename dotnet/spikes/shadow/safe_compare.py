"""Reuse public comparisons in memory; emit a new value-free schema, never filtered raw diffs."""
from __future__ import annotations

from collections import Counter
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
import hashlib
import io
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from contract import compare, jsontext, normalise  # noqa: E402
from catalogue import CASES, Refused  # noqa: E402

FIELDS = frozenset(("status", "headers", "body", "facts", "result", "structuredContent",
                    "items", "rows", "events", "data", "event", "money", "eligible", "total",
                    "kind", "value", "type", "detail", "code", "error", "sha256", "size",
                    "zip_entries", "trail_hash", "canonical_hash", "manifest", "blocks",
                    "content-type", "x-content-sha256", "content-length", "nullable"))
CATEGORIES = frozenset(("status", "header", "body-kind", "value", "type", "missing-field",
                        "extra-field", "array-length", "event", "zip-entry",
                        "key-order", "number-lexeme", "raw-bytes"))
MAX_INPUT = 4_194_304


def safe_path(path: str) -> str:
    # Bracket contents include archive filenames, and unknown keys may themselves be private.
    path = re.sub(r"\[[^\]]*\]", "[*]", path)
    tokens = re.findall(r"\[\*\]|[^.\[\]]+", path[:4096])
    return "$" + "".join("[*]" if token == "[*]" else "." + (token if token in FIELDS else "*")
                         for token in tokens[:30])


def _record(case: str, response: dict) -> dict:
    method, path = CASES[case].route.split(" ", 1)
    return {"scenario": "shadow", "id": "sample", "request": {"method": method, "path": path},
            "response": deepcopy(response)}


def compare_responses(case: str, expected: dict, actual: dict, ordinal: int = 1) -> dict:
    if case not in CASES or type(ordinal) is not int or not 1 <= ordinal <= 20:
        raise Refused("catalogue-or-ordinal")
    wire_equal = hashlib.sha256(jsontext.dumps(expected).encode()).digest() == hashlib.sha256(
        jsontext.dumps(actual).encode()).digest()
    before_body, after_body = expected["body"], actual["body"]
    body_equal = (_body_hash(before_body) == _body_hash(after_body))
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        left, right = normalise.apply(_record(case, expected)), normalise.apply(_record(case, actual))
        failures, tolerated = compare.split(compare.compare_record(left, right), "semantic")
    categories = Counter(f["category"] if f["category"] in CATEGORIES else "comparison-error" for f in failures)
    return {"route": CASES[case].route, "sample": ordinal, "wire_equal": wire_equal,
            "content_hash_equal": body_equal, "semantic_equal": not failures,
            "failure_count": len(failures), "categories": dict(categories),
            "paths": sorted({safe_path(f["path"]) for f in failures}),
            "semantic_tolerances": len(tolerated)}


def _body_hash(body: dict) -> str:
    return body.get("raw_sha256", body.get("sha256")) or hashlib.sha256(jsontext.dumps(body).encode()).hexdigest()


def compare_document(document: dict) -> dict:
    """Catch only at this privacy boundary; error text, repr, traceback and chained causes never escape."""
    try:
        return compare_responses(document["case"], document["expected"], document["actual"],
                                 document.get("sample", 1))
    except Exception:  # noqa: BLE001 - explicit, value-free boundary failure, not a parity success
        return {"verdict": "comparison-error", "semantic_equal": False}


def main() -> int:
    try:
        data = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(data) > MAX_INPUT:
            raise Refused("byte-bound")
        document = jsontext.loads(data)
        # Ordinals are control data, not response values.
        if isinstance(document.get("sample"), jsontext.Num):
            document["sample"] = int(document["sample"].text)
        result = compare_document(document)
    except Exception:  # noqa: BLE001 - never emit input/parser exception text
        result = {"verdict": "comparison-error", "semantic_equal": False}
    print(json.dumps(result, sort_keys=True))
    return int(result.get("verdict") == "comparison-error")


if __name__ == "__main__":
    raise SystemExit(main())
