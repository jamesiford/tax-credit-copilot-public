"""Find function bodies that are the same code in two places. [AI-08]

Copy-paste is how one fix becomes three: somebody corrects the copy they were reading
and never learns there are others. This looks for the unambiguous case — two
functions whose bodies have an IDENTICAL syntax tree (names and all, docstrings
ignored) and are long enough that the match is not a coincidence of `return x`.

It does not look for near-duplicates: a detector that cries wolf gets its baseline
bulk-updated, which is the same as not having one. Exact and boring is the point.
"""
from __future__ import annotations

import ast
import hashlib
from collections import defaultdict

from tools.code_standards.metrics import Finding, _walk

MIN_BODY_LINES = 8


def _fingerprint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    body = node.body[1:] if ast.get_docstring(node) else node.body
    if not body or body[-1].end_lineno - body[0].lineno + 1 < MIN_BODY_LINES:
        return None
    dumped = "|".join(ast.dump(stmt, annotate_fields=False) for stmt in body)
    return hashlib.sha1(dumped.encode()).hexdigest()[:12]


def duplicate_locations(sources: dict[str, str]) -> dict[str, list[str]]:
    """Where each duplicated body lives, keyed `duplicate|<hash>`."""
    seen: dict[str, list[str]] = defaultdict(list)
    for path, source in sources.items():
        for name, node in _walk(ast.parse(source).body):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (digest := _fingerprint(node)):
                seen[digest].append(f"{path}::{name}")
    return {f"duplicate|{d}": places for d, places in sorted(seen.items()) if len(places) > 1}


def duplicate_findings(sources: dict[str, str]) -> list[Finding]:
    """One finding per duplicated body, valued at the number of copies."""
    return [Finding(key, len(places)) for key, places in duplicate_locations(sources).items()]
