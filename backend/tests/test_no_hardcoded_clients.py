"""No production module may know a specific client. [04]

The app loads whatever accounts the source holds. A client id or a demo client's name written into
production code is a client the code "knows" and the next customer's data does not contain, so it
quietly misbehaves (an invented designation, a claim attached to the wrong company, a tour that walks to
a page that does not exist).

Fixture builders and operator scripts that exist to produce or check the generated reference book are
named below, each with the reason it may. Everything else fails this test. Docstrings and comments are
free to name a client; code is not.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
DEMO_IDS = {1001, 2001, 2002, 2003, 2004, 2005}
DEMO_NAMES = re.compile(r"Candle Bottle|Cascade Retail|Northwind|Ironbridge|Halloway", re.I)

#: path (relative to backend/) -> why it may carry demo identities
ALLOWED = {
    "data/source/synth.py": "generator of the synthetic accounts",
    "data/source/from_reference.py": "builder of the reference conformance fixture",
    "data/source/__init__.py": "re-exports the reference fixture builder",
    "data/source/load_fabric.py": "operator loader of the synthetic accounts",
    "data/generate_pay_periods.py": "generator of the synthetic CSV",
    "data/seed_claims.py": "illustrative seed, guarded to synthetic environments and name-checked",
    "data/designations.py": "designation registry for the generated clients",
    "tools/verify_reference_independent.py": "independent check of the reference dataset",
    "data/rules/materialise_years.py": "rule-pack materialiser fixture",
}
SKIP_DIRS = {"tests", ".venv", "__pycache__", "vendor", "node_modules"}


def _production_files():
    for path in BACKEND.rglob("*.py"):
        rel = path.relative_to(BACKEND).as_posix()
        if SKIP_DIRS & set(path.relative_to(BACKEND).parts):
            continue
        yield rel, path


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def _offences(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = _docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in docs:
            continue
        if isinstance(node.value, bool):
            continue
        if isinstance(node.value, int) and node.value in DEMO_IDS:
            found.append(f"line {node.lineno}: client id {node.value}")
        elif isinstance(node.value, str) and DEMO_NAMES.search(node.value):
            found.append(f"line {node.lineno}: demo client name in {node.value[:40]!r}")
    return found


def test_no_production_module_knows_a_specific_client():
    breaches = {}
    for rel, path in _production_files():
        if rel in ALLOWED:
            continue
        found = _offences(path)
        if found:
            breaches[rel] = found
    assert not breaches, f"production code names a specific client: {breaches}"


def test_the_allow_list_has_no_stale_entries():
    present = {rel for rel, _ in _production_files()}
    assert not (set(ALLOWED) - present), f"allow-list names files that do not exist: {set(ALLOWED) - present}"


def test_no_module_tells_demo_from_real_accounts_by_an_id_threshold():
    """`account_id >= 2000` once labelled real customer accounts synthetic and invented their designations."""
    pattern = re.compile(r"(account_id|client_id|AccountId)\W{0,12}(>=|>|<=|<)\s*(1000|2000)\b")
    hits = {}
    for rel, path in _production_files():
        if rel == "tests/test_no_hardcoded_clients.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line) and not line.lstrip().startswith("#"):
                hits.setdefault(rel, []).append(number)
    assert not hits, f"an id threshold decides demo from real: {hits}"
