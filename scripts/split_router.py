"""Split a FastAPI router module into concern-shaped files, safely.

Written after doing this by hand four times and getting it wrong twice. The
mistakes were not careless — they are the ones this problem invites:

**Copy from the decorator, not the `def`.** Starting at `node.lineno` moves the
function and leaves `@router.get(...)` behind. The module still imports, unit
tests that call handlers directly still pass, and the endpoint is simply gone.
Nine disappeared that way.

**Carry the module-level names.** Constants like `_BUILD_IN_HOUSE_BENCHMARK`
are not functions, so a def-only extraction silently orphans them.

**Imports do not follow.** The moved code needs whatever it referenced, and
Python only complains when the line executes — which for a router is when a
client calls it.

This does the first two mechanically. For the third it reports what each new
module needs, and `tests/test_architecture.py` fails the build if anything is
missed. `tests/test_api_surface.py` proves no route was lost.

    python scripts/split_router.py api/onezero.py --plan
"""
from __future__ import annotations

import argparse
import ast
import builtins
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
_BUILTINS = set(dir(builtins)) | {"Any", "self", "cls"}


def _top_level_spans(tree: ast.Module) -> dict[str, tuple[int, int]]:
    """Name -> (first line, last line), **including decorators**.

    The decorator span is the whole point. Everything else here is bookkeeping.
    """
    spans: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min(
                [d.lineno for d in getattr(node, "decorator_list", [])] + [node.lineno]
            )
            spans[node.name] = (start, node.end_lineno or node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    spans[target.id] = (node.lineno, node.end_lineno or node.lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            spans[node.target.id] = (node.lineno, node.end_lineno or node.lineno)
    return spans


def _bound_names(tree: ast.Module) -> set[str]:
    """Everything a module defines or imports at any depth."""
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bound |= {a.asname or a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            bound |= {a.asname or a.name for a in node.names}
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
    return bound


def external_names(source: str) -> set[str]:
    """Names a fragment uses but does not itself define.

    Covers the five shapes that have each broken a split: calls, subscripts,
    attribute calls, attribute reads, and **type annotations** — the last
    because FastAPI reads annotations at import time and turns an unresolved
    one into a required query parameter rather than an error.
    """
    tree = ast.parse(source)
    bound = _bound_names(tree) | _BUILTINS
    used: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                used.add(node.func.id)
            elif isinstance(node.func, ast.Attribute) and isinstance(
                node.func.value, ast.Name
            ):
                used.add(node.func.value.id)
        elif isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            used.add(node.value.id)
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            used.add(node.value.id)

        annotations = []
        if isinstance(node, ast.arg) and node.annotation is not None:
            annotations.append(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns:
            annotations.append(node.returns)
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            annotations.append(node.annotation)
        for annotation in annotations:
            used |= {
                p.id for p in ast.walk(annotation) if isinstance(p, ast.Name)
            }

    return used - bound


def extract(source_path: Path, names: list[str]) -> tuple[str, set[str], int]:
    """Return (fragment, names it needs, route count) for the given members."""
    source = source_path.read_text(encoding="utf-8")
    lines = source.split("\n")
    spans = _top_level_spans(ast.parse(source))

    missing = [n for n in names if n not in spans]
    if missing:
        raise SystemExit(f"not found in {source_path}: {missing}")

    chunks = ["\n".join(lines[spans[n][0] - 1 : spans[n][1]]) for n in names]
    fragment = "\n\n\n".join(chunks)
    return fragment, external_names(fragment), fragment.count("@router.")


def remove(source_path: Path, names: list[str]) -> int:
    """Delete those members from the source module. Returns the new line count."""
    source = source_path.read_text(encoding="utf-8")
    lines = source.split("\n")
    spans = _top_level_spans(ast.parse(source))

    doomed: set[int] = set()
    for name in names:
        start, end = spans[name]
        doomed |= set(range(start, end + 1))

    kept = [ln for i, ln in enumerate(lines, start=1) if i not in doomed]
    source_path.write_text("\n".join(kept), encoding="utf-8")
    return len(kept)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", help="e.g. api/onezero.py")
    parser.add_argument("--members", nargs="+", required=True)
    parser.add_argument("--plan", action="store_true", help="report, change nothing")
    args = parser.parse_args()

    path = BACKEND / args.module
    fragment, needs, routes = extract(path, args.members)

    print(f"{len(fragment.splitlines())} lines, {routes} route decorator(s)")
    print(f"needs: {sorted(needs)}")
    if args.plan:
        return 0

    out = path.parent / "_fragment.py"
    out.write_text(fragment, encoding="utf-8")
    print(f"fragment written to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
