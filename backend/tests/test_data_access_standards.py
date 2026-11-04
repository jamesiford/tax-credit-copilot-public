"""The data-access package meets the coding standards outright. [CH-16]

The code-standards ratchet skips any path containing a `data/` directory (it exists to
skip the synthetic-data generators), which would silently exempt `application/data/`.
This applies the same measurement to it directly, with no baseline: new code does not
get a vote on its own limits.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.code_standards.metrics import measure

PACKAGE = Path(__file__).resolve().parents[1] / "application" / "data"
FILES = sorted(p for p in PACKAGE.glob("*.py"))


def test_the_package_exists_and_is_not_empty():
    assert len(FILES) >= 6


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_a_module_meets_every_standard(path):
    findings = measure(f"application/data/{path.name}", path.read_text(encoding="utf-8"))
    assert not findings, [f"{f.key}={f.value}" for f in findings]
