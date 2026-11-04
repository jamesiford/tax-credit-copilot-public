"""The backend README's folder map names every folder and every architecture test. [RM-25]

A map that omits a new folder, or points at a test that was renamed, sends a reader to the wrong place
with confidence. The map is short, so keeping it complete is cheap; this makes it a failure to forget.
"""
from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
README = (BACKEND / "README.md").read_text(encoding="utf-8")
SKIPPED = {"__pycache__", ".pytest_cache", ".venv", "node_modules", "vendor"}


def test_every_backend_folder_has_a_row_in_the_map():
    folders = [p.name for p in BACKEND.iterdir() if p.is_dir() and p.name not in SKIPPED and not p.name.startswith(".")]
    missing = [f for f in folders if f"| `{f}/` |" not in README]
    assert not missing, f"add these folders to backend/README.md: {missing}"


def test_the_map_names_no_folder_that_does_not_exist():
    rows = re.findall(r"^\| `([a-z_]+)/` \|", README, re.M)
    assert rows, "the folder table is missing"
    gone = [r for r in rows if not (BACKEND / r).is_dir()]
    assert not gone, f"backend/README.md maps folders that do not exist: {gone}"


def test_every_test_the_readme_cites_exists():
    cited = set(re.findall(r"`(tests/[A-Za-z0-9_./]+\.py)`", README))
    assert cited, "the README should point at the tests that enforce the rules"
    gone = sorted(c for c in cited if not (BACKEND / c).is_file())
    assert not gone, f"backend/README.md cites tests that do not exist: {gone}"


def test_the_readme_states_the_dependency_direction():
    assert re.search(r"presentation.*->\s+application/\s+->\s+domain/", README)
    assert "implements the ports" in README
    assert "bootstrap/" in README and "composes" in README
