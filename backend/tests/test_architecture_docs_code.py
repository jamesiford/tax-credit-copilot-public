"""Code lives in code folders, not in docs/. [RM-23]

`docs/` is read, not run. Two scripts once lived there (the portable rules and the schema variant
generator), which put executable code where no test, linter or code-standards scan looks. They now live
under `scripts/`. This pins that, and proves the two moved tools still work from their new home.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
ROOT = BACKEND.parent
PORTABLE = ROOT / "scripts" / "portable-rules"
CODE_SUFFIXES = {".py", ".ps1", ".sh", ".js", ".mjs", ".ts"}


def test_no_executable_code_lives_under_docs():
    found = sorted(
        str(p.relative_to(ROOT)) for p in (ROOT / "docs").rglob("*")
        if p.is_file() and p.suffix in CODE_SUFFIXES and "__pycache__" not in p.parts
    )
    assert not found, f"code belongs in scripts/ or backend/, not docs/: {found}"


def _run(script: Path, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script)], cwd=cwd, capture_output=True, text=True, timeout=180,
        encoding="utf-8", errors="replace",
    )


def test_the_portable_rules_self_check_passes_from_scripts():
    result = _run(PORTABLE / "flex_rules.py", ROOT)
    assert result.returncode == 0, result.stdout[-800:] + result.stderr[-800:]
    assert "16/16 passed" in result.stdout


def test_the_portable_rules_agree_with_the_engine():
    result = _run(PORTABLE / "crosscheck.py", BACKEND)
    assert result.returncode == 0, result.stdout[-800:] + result.stderr[-800:]
    assert "AGREES" in result.stdout


def test_the_schema_generator_reads_and_writes_the_docs_schema_folder():
    spec_source = (ROOT / "scripts" / "generate-schema-variants.py").read_text(encoding="utf-8")
    assert '"docs" / "data" / "schema"' in spec_source
    assert (ROOT / "docs" / "data" / "schema" / "tcc-schema.fabric.sql").exists()
    generated = (ROOT / "docs" / "data" / "schema" / "tcc-schema.sqlserver.sql").read_text(encoding="utf-8")
    assert "scripts/generate-schema-variants.py" in generated


def test_the_old_locations_are_gone():
    assert not (ROOT / "docs" / "data" / "portable-rules" / "flex_rules.py").exists()
    assert not (ROOT / "docs" / "data" / "schema" / "generate_variants.py").exists()
