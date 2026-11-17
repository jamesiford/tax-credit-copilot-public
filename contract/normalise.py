"""Normalisation of genuinely volatile fields. Every rule is justified in `contract/docs/normalisation.md`.

A rule exists only with proof that the field changed between two identical runs AND that freezing its source from the harness was
not possible. The default is no rules: the clock, ids and secrets are frozen at the source (`harness/freeze.py`).

A rule is `(scenario glob, exchange id glob, JSON path, placeholder)`; a record that had a rule applied lists it under
`normalised`, so the replay tool does not compare the raw-byte hash of a body it has rewritten.
"""
from __future__ import annotations

import fnmatch
import re
from typing import Any

from .jsontext import Num

#: (response body path from the document root, e.g. "source_schema.reads.tables.*.seconds", placeholder)
RULES: list[tuple[str, str, str, str]] = [
    # (scenario glob, step id glob, body path, placeholder)
]


def _walk(node: Any, parts: list[str], placeholder: Any, hits: list[str], trail: str = "") -> None:
    if not parts:
        return
    head, rest = parts[0], parts[1:]
    if isinstance(node, dict):
        for key in list(node):
            if fnmatch.fnmatch(key, head):
                path = f"{trail}.{key}" if trail else key
                if not rest:
                    node[key] = placeholder
                    hits.append(path)
                else:
                    _walk(node[key], rest, placeholder, hits, path)
    elif isinstance(node, list):
        for i, item in enumerate(node):
            if head in ("*", str(i)):
                path = f"{trail}.{i}" if trail else str(i)
                if not rest:
                    node[i] = placeholder
                    hits.append(path)
                else:
                    _walk(item, rest, placeholder, hits, path)


SIZE_PLACEHOLDER = "{container.size_bytes}"
SHA_PLACEHOLDER = "{container.sha256}"
_SIZE = re.compile(r"(0|[1-9][0-9]*)")
_SHA = re.compile(r"[0-9a-f]{64}")

#: (method, path regex, [(where, location, what)]). `where` is `body` (a dotted path into the JSON body, list indexes as numbers),
#: `header` (a response header) or `bytes` (a zip response body: its recorded `length` and `sha256`; its members stay compared).
#: `what` is `size` or `sha`. Evidence: every pair was observed to differ between CPython 3.14.2 and 3.12.13 (docs/normalisation.md).
CONTAINER_RULES: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    ("POST", r"/api/clients/[^/]+/packages", [("body", "size_bytes", "size"), ("body", "sha256", "sha")]),
    ("GET", r"/api/clients/[^/]+/artifacts/[^/]+", [("header", "x-content-sha256", "sha"), ("bytes", "", "zip")]),
    ("POST", r"/channel/v1/tools/claim_package_create_commit", [("body", "facts.result.size_bytes", "size"), ("body", "facts.result.sha256", "sha")]),
    ("POST", r"/channel/v1/tools/claim_package_link", [("body", "facts.size_bytes", "size"), ("body", "facts.sha256", "sha"), ("body", "blocks.1.rows.1.1", "sha")]),
    ("GET", r"/channel/v1/downloads/[^/]+", [("header", "x-content-sha256", "sha"), ("bytes", "", "zip")]),
    ("POST", r"/api/v2/program-drafts/[^/]+/export", [("header", "x-bundle-sha256", "sha"), ("bytes", "", "zip")]),
    ("GET", r"/api/v2/program-drafts/[^/]+/export/manifest", [("body", "bundle_sha256", "sha"), ("body", "bundle_bytes", "size")]),
]


def _shape_ok(value: Any, what: str) -> bool:
    if what == "size":
        return isinstance(value, Num) and bool(_SIZE.fullmatch(value.text))
    return isinstance(value, str) and bool(_SHA.fullmatch(value))


def _placeholder(what: str) -> str:
    return SIZE_PLACEHOLDER if what == "size" else SHA_PLACEHOLDER


def _step(node: Any, key: str) -> Any:
    """One step of a dotted path; a dict key or a list index. Anything else is absent (a sentinel), never an exception."""
    if isinstance(node, dict):
        return node[key] if key in node else _ABSENT
    if isinstance(node, list) and key.isdigit() and int(key) < len(node):
        return node[int(key)]
    return _ABSENT


_ABSENT = object()


def _replace_at(root: Any, path: str, what: str) -> bool:
    *parents, last = path.split(".")
    node = root
    for key in parents:
        node = _step(node, key)
        if node is _ABSENT:
            return False
    if _step(node, last) is _ABSENT or not _shape_ok(_step(node, last), what):
        return False
    if isinstance(node, dict):
        node[last] = _placeholder(what)
    else:
        node[int(last)] = _placeholder(what)
    return True


def _container(record: dict[str, Any]) -> None:
    request, response = record.get("request"), record.get("response")
    if not request or not response:
        return
    body = response.get("body") or {}
    notes: list[str] = []
    for method, pattern, fields in CONTAINER_RULES:
        if request["method"] != method or not re.fullmatch(pattern, request["path"]):
            continue
        for where, location, what in fields:
            if where == "header":
                value = response["headers"].get(location)
                declared_ok = body.get("kind") != "bytes" or "sha256" not in body or value == body["sha256"]
                if _shape_ok(value, what) and declared_ok:
                    response["headers"][location] = _placeholder(what)
                    notes.append(f"headers.{location}={_placeholder(what)}")
            elif where == "body" and body.get("kind") == "json":
                if _replace_at(body["value"], location, what):
                    notes.append(f"{location}={_placeholder(what)}")
                    body.pop("raw_sha256", None)
                    body.pop("raw_length", None)
            elif where == "bytes" and body.get("kind") == "bytes" and "zip_entries" in body:
                for key, kind in (("length", "size"), ("sha256", "sha")):
                    value = body.get(key)
                    if isinstance(value, int) and not isinstance(value, bool):
                        value = Num(str(value))
                    if _shape_ok(value, kind):
                        body[key] = _placeholder(kind)
                        notes.append(f"body.{key}={_placeholder(kind)}")
    if notes:
        record.setdefault("normalised", []).extend(notes)


def apply(record: dict[str, Any]) -> dict[str, Any]:
    response = record.get("response")
    if not response:
        return record
    location = response["headers"].get("location")
    if location and re.match(r"^https?://[^/]+", location):
        response["headers"]["location"] = re.sub(r"^https?://[^/]+", "{origin}", location)
        record.setdefault("normalised", []).append("headers.location origin={origin}")
    body = response.get("body") or {}
    for scenario, step, path, placeholder in RULES:
        if not (fnmatch.fnmatch(record["scenario"], scenario) and fnmatch.fnmatch(record["id"], step)):
            continue
        hits: list[str] = []
        if body.get("kind") == "json":
            _walk(body["value"], path.split("."), placeholder, hits)
        if hits:
            record.setdefault("normalised", []).extend(f"{h}={placeholder}" for h in hits)
            body.pop("raw_sha256", None)
    _container(record)
    return record


def apply_all(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [apply(r) for r in records]
