"""Fixture code stays out of the runtime path. [RM-21]

`data/source/synth.py` invents clients (names, payrolls, fiscal windows) for tests and for the public
profile's synthetic load. It lives in the `data.source` package because the loader that ships with the
backend (`load_fabric --synthetic-only`, run by postprovision) needs it, so it cannot move under a
test-support folder without breaking that deployment step. What can be guaranteed instead, and is
guaranteed here: nothing the product serves a request with imports it, and importing the package
that holds it does not load it.
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
SYNTH_NAMES = {"SYNTHETIC_CLIENTS", "build_all_synthetic", "build_synthetic_dataset", "SyntheticClientSpec"}

#: Who may import the fixture, and why. Everything else under backend/ and the orchestrator may not.
ALLOWED = {
    "data/source/load_fabric.py": "the synthetic loader postprovision runs on the public profile",
    "data/source/__init__.py": "resolves the fixture names lazily, on first use",
}


def _runtime_sources() -> list[Path]:
    skipped = {"tests", "__pycache__", ".venv", "node_modules", "vendor"}
    bases = (BACKEND, ROOT / "channel_orchestrator" / "app")
    return [p for base in bases for p in base.rglob("*.py") if not skipped & set(p.relative_to(base).parts)]


def _reaches_synth(path: Path) -> list[str]:
    found = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            found += [a.name for a in node.names if a.name.endswith("source.synth")]
        elif isinstance(node, ast.ImportFrom):
            module = ("." * node.level) + (node.module or "")
            if module.endswith("synth") and "source" in module or (node.level and module == ".synth"):
                found.append(module)
            elif module in {"data.source", "data", "."} and any(a.name in SYNTH_NAMES | {"synth"} for a in node.names):
                found.append(f"{module} import {[a.name for a in node.names]}")
    return found


def test_no_runtime_module_imports_the_synthetic_fixture_beyond_the_named_loader():
    offenders = {}
    for path in _runtime_sources():
        relative = path.relative_to(BACKEND).as_posix() if BACKEND in path.parents else path.relative_to(ROOT).as_posix()
        if relative == "data/source/synth.py" or relative in ALLOWED:
            continue
        if reached := _reaches_synth(path):
            offenders[relative] = reached
    assert offenders == {}, f"only {sorted(ALLOWED)} may import data.source.synth: {offenders}"


def test_the_allowed_importers_are_still_importers_so_the_list_cannot_go_stale():
    for relative in ALLOWED:
        text = (BACKEND / relative).read_text(encoding="utf-8")
        assert "synth" in text, f"{relative} no longer touches the fixture; remove it from ALLOWED"


def test_importing_the_source_package_does_not_load_the_fixture_but_using_a_fixture_name_does():
    code = (
        "import sys, data.source\n"
        "assert 'data.source.synth' not in sys.modules, 'importing data.source loaded the fixture'\n"
        "assert data.source.SYNTHETIC_CLIENTS and 'data.source.synth' in sys.modules\n"
        "assert callable(data.source.build_synthetic_dataset) and callable(data.source.build_all_synthetic)\n"
        "try:\n"
        "    data.source.not_a_name\n"
        "except AttributeError:\n"
        "    print('lazy ok')\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=BACKEND, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0 and "lazy ok" in result.stdout, result.stderr[-1500:]


def test_the_scanner_finds_each_way_to_reach_the_fixture(tmp_path):
    for source in (
        "from data.source.synth import build_all_synthetic\n",
        "import data.source.synth\n",
        "from data.source import SYNTHETIC_CLIENTS\n",
        "from data.source import synth\n",
        "from .synth import SYNTHETIC_CLIENTS\n",
    ):
        path = tmp_path / "m.py"
        path.write_text(source, encoding="utf-8")
        assert _reaches_synth(path), source
    path.write_text("from data.source import FabricLakehouseReader\n", encoding="utf-8")
    assert _reaches_synth(path) == []
