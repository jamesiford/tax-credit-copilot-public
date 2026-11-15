"""Normalisation of genuinely volatile fields. Every rule is justified in `contract/docs/normalisation.md`.

A rule exists only with proof that the field changed between two identical runs AND that freezing its source from the harness was
not possible. The default is no rules: the clock, ids and secrets are frozen at the source (`harness/freeze.py`).

A rule is `(scenario glob, exchange id glob, JSON path, placeholder)`; a record that had a rule applied lists it under
`normalised`, so the replay tool does not compare the raw-byte hash of a body it has rewritten.
"""
from __future__ import annotations

import fnmatch
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


def apply(record: dict[str, Any]) -> dict[str, Any]:
    response = record.get("response")
    if not response:
        return record
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
    return record


def apply_all(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [apply(r) for r in records]
