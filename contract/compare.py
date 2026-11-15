"""Compare a recorded exchange with what a server answered now.

Categories (each diff carries one):

  status, header, body-kind, value, type, missing-field, extra-field, array-length, event, zip-entry   always a failure
  key-order, number-lexeme, raw-bytes                                                                  a failure in `strict`; in
                                                                                                       `semantic` reported
                                                                                                       separately as `tolerated`

`number-lexeme`: the numbers are equal as numbers but written differently (`1.0` / `1`, `1e3` / `1000`). `key-order`: the same keys in
a different order. `raw-bytes`: every decoded value equal but the response bytes differ (whitespace, escaping).
A port may choose to tolerate those three, and must do so knowingly.
"""
from __future__ import annotations

from typing import Any

from .jsontext import Num

TOLERABLE = ("key-order", "number-lexeme", "raw-bytes")


def _d(category: str, path: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {"category": category, "path": path, "expected": _show(expected), "actual": _show(actual)}


def _show(value: Any) -> Any:
    from . import jsontext

    text = jsontext.dumps(value) if not isinstance(value, str) else value
    return text if len(text) <= 300 else text[:300] + f"...({len(text)} chars)"


def compare_tree(e: Any, a: Any, path: str, out: list[dict[str, Any]]) -> None:
    if isinstance(e, dict) and isinstance(a, dict):
        for key in e:
            if key not in a:
                out.append(_d("missing-field", f"{path}.{key}" if path else key, e[key], "<absent>"))
        for key in a:
            if key not in e:
                out.append(_d("extra-field", f"{path}.{key}" if path else key, "<absent>", a[key]))
        common_e = [k for k in e if k in a]
        common_a = [k for k in a if k in e]
        if common_e != common_a:
            out.append(_d("key-order", path or "$", common_e, common_a))
        for key in common_e:
            compare_tree(e[key], a[key], f"{path}.{key}" if path else key, out)
    elif isinstance(e, list) and isinstance(a, list):
        if len(e) != len(a):
            out.append(_d("array-length", path or "$", len(e), len(a)))
        for i, (x, y) in enumerate(zip(e, a)):
            compare_tree(x, y, f"{path}[{i}]", out)
    elif isinstance(e, Num) and isinstance(a, Num):
        if e.text != a.text:
            equal = False
            try:
                equal = e.value == a.value
            except Exception:  # noqa: BLE001
                pass
            out.append(_d("number-lexeme" if equal else "value", path or "$", e.text, a.text))
    elif type(e) is not type(a) or e != a:
        kind = "type" if type(e) is not type(a) else "value"
        out.append(_d(kind, path or "$", e, a))


def compare_body(e: dict[str, Any], a: dict[str, Any], out: list[dict[str, Any]], normalised: bool) -> None:
    if e["kind"] != a["kind"]:
        out.append(_d("body-kind", "body", e["kind"], a["kind"]))
        return
    kind = e["kind"]
    if kind == "json":
        before = len(out)
        compare_tree(e["value"], a["value"], "", out)
        if len(out) == before and not normalised and e.get("raw_sha256") != a.get("raw_sha256"):
            out.append(_d("raw-bytes", "body", e.get("raw_sha256"), a.get("raw_sha256")))
    elif kind == "text":
        if e.get("text") is not None and e.get("text") != a.get("text"):
            out.append(_d("value", "body.text", e.get("text"), a.get("text")))
        elif e.get("raw_sha256") != a.get("raw_sha256"):
            out.append(_d("value", "body.sha256", e.get("raw_sha256"), a.get("raw_sha256")))
    elif kind == "sse":
        ee, aa = e["events"], a["events"]
        if len(ee) != len(aa):
            out.append(_d("event", "events.length", len(ee), len(aa)))
        for i, (x, y) in enumerate(zip(ee, aa)):
            before = len(out)
            compare_tree({k: v for k, v in x.items()}, {k: v for k, v in y.items()}, f"events[{i}]", out)
            for diff in out[before:]:
                diff["category"] = diff["category"] if diff["category"] in TOLERABLE else "event"
    elif kind == "bytes":
        if "zip_entries" in e:
            if e.get("zip_entries") != a.get("zip_entries"):
                out.append(_d("zip-entry", "body.zip_entries", e.get("zip_entries"), a.get("zip_entries")))
        elif e.get("sha256") != a.get("sha256"):
            out.append(_d("value", "body.sha256", e.get("sha256"), a.get("sha256")))


def compare_record(e: dict[str, Any], a: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if "control" in e:
        if e["control"].get("status") != a.get("control", {}).get("status"):
            out.append(_d("status", "control", e["control"].get("status"), a.get("control", {}).get("status")))
        return out
    er, ar = e["response"], a["response"]
    if er["status"] != ar["status"]:
        out.append(_d("status", "status", er["status"], ar["status"]))
    for name in sorted(set(er["headers"]) | set(ar["headers"])):
        if er["headers"].get(name) != ar["headers"].get(name):
            out.append(_d("header", f"headers.{name}", er["headers"].get(name, "<absent>"), ar["headers"].get(name, "<absent>")))
    compare_body(er["body"], ar["body"], out, bool(e.get("normalised")))
    return out


def split(diffs: list[dict[str, Any]], mode: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(failures, tolerated) for the mode."""
    if mode == "strict":
        return diffs, []
    return [d for d in diffs if d["category"] not in TOLERABLE], [d for d in diffs if d["category"] in TOLERABLE]
