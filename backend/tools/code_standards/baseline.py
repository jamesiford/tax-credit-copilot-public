"""The ratchet: what is already wrong may not get worse, and may only get better. [AI-08]

A standard applied retroactively to a large codebase fails on day one and is then
ignored. The baseline is the honest alternative: it records every existing
violation with how bad it is, and the build fails when

- a violation appears that is not in the baseline (new code broke a standard),
- a baseline violation got WORSE (a long function grew), or
- a baseline violation got better or went away and the baseline was not tightened
  (so a fixed problem cannot quietly come back).

Refactoring is therefore rewarded and never blocked: fix something, run
`python scripts/code-standards.py --update`, and the bar has moved for everyone.
"""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from tools.code_standards.duplicates import duplicate_findings
from tools.code_standards.metrics import LIMITS, Finding, measure

BACKEND = Path(__file__).resolve().parents[2]
BASELINE_PATH = BACKEND / "tests" / "code_standards_baseline.json"
_SKIP_DIRS = {"tests", "__pycache__", ".venv", "venv", "node_modules", "data"}


def source_files(root: Path = BACKEND) -> dict[str, str]:
    """Production Python under `root`, keyed by forward-slash relative path.

    Tests are exempt (a long parametrised table is not a design smell) and so is
    `data/`, the synthetic-data generators, which are scripts rather than product code.
    """
    found: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        if _SKIP_DIRS.isdisjoint(relative.parts):
            found[relative.as_posix()] = path.read_text(encoding="utf-8")
    return found


def current_findings(sources: dict[str, str] | None = None) -> dict[str, int]:
    sources = source_files() if sources is None else sources
    findings = [f for path, text in sources.items() for f in measure(path, text)]
    findings += duplicate_findings(sources)
    return {f.key: f.value for f in findings}


def load_baseline(path: Path = BASELINE_PATH) -> dict[str, int]:
    return json.loads(path.read_text(encoding="utf-8"))["violations"] if path.is_file() else {}


def save_baseline(violations: dict[str, int], path: Path = BASELINE_PATH) -> None:
    payload = {"limits": LIMITS, "violations": dict(sorted(violations.items()))}
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8", newline="\n")


@dataclass(frozen=True)
class Comparison:
    """How the code differs from the baseline: new violations, worse ones, and ones to tighten."""

    new: tuple[str, ...] = field(default_factory=tuple)
    worse: tuple[str, ...] = field(default_factory=tuple)
    improved: tuple[str, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not (self.new or self.worse or self.improved)


def _qualname(key: str) -> str | None:
    """`Class.method` of a function- or class-level key; None for a module-level one."""
    where = key.split("|", 1)[1]
    return where.split("::", 1)[1] if "::" in where else None


def _moves(new: dict[str, int], gone: dict[str, int]) -> set[tuple[str, str]]:
    """(new key, old key) pairs where a violation merely moved file: same rule, same name, no worse.

    A split moves code without changing it. Counting that as a new violation would
    make the ratchet punish the refactor it exists to encourage, so a function that
    keeps its name and does not get worse is carried across.
    """
    pairs: set[tuple[str, str]] = set()
    unused = dict(gone)
    for key, value in sorted(new.items()):
        name, rule = _qualname(key), key.split("|", 1)[0]
        match = next((k for k, v in unused.items()
                      if name and k.split("|", 1)[0] == rule and _qualname(k) == name and value <= v), None)
        if match:
            pairs.add((key, match))
            unused.pop(match)
    return pairs


def compare(current: dict[str, int], baseline: dict[str, int]) -> Comparison:
    """How `current` differs from `baseline`: new, worse, or (so the bar tightens) improved."""
    appeared = {k: v for k, v in current.items() if k not in baseline}
    gone = {k: v for k, v in baseline.items() if k not in current}
    moved = _moves(appeared, gone)
    moved_new, moved_old = {n for n, _ in moved}, {o for _, o in moved}
    return Comparison(
        new=tuple(f"{k} = {v}" for k, v in sorted(appeared.items()) if k not in moved_new),
        worse=_changes(current, baseline, lambda now, was: now > was),
        improved=tuple(c for c in _changes(current, baseline, lambda now, was: now < was, moved_old)),
    )


def _changes(current: dict[str, int], baseline: dict[str, int], differs, skip: set[str] = frozenset()) -> tuple[str, ...]:
    """`key: was -> now` for each baseline key whose value `differs` from today's (absent counts as 0)."""
    return tuple(
        f"{key}: {was} -> {current.get(key, 'fixed')}"
        for key, was in sorted(baseline.items())
        if key not in skip and differs(current.get(key, 0), was)
    )


def summary(violations: Iterable[str]) -> dict[str, int]:
    """Violation count per rule, for the report."""
    counts: dict[str, int] = {}
    for key in violations:
        counts[key.split("|", 1)[0]] = counts.get(key.split("|", 1)[0], 0) + 1
    return dict(sorted(counts.items()))
