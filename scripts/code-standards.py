"""Report on, or re-baseline, the coding-standards ratchet. [AI-08]

    python scripts/code-standards.py            # counts per rule, worst offenders, and the verdict
    python scripts/code-standards.py --update   # accept the current state as the new baseline

`--update` refuses to LOOSEN the baseline (a new violation, or a worse one): that is
the point of a ratchet. Fix the code. It only tightens: after a refactor, run it and
commit the smaller file. See `backend/tools/code_standards/baseline.py`.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from tools.code_standards import baseline as ratchet  # noqa: E402


def report(current: dict[str, int], saved: dict[str, int]) -> int:
    print("rule                 baseline  now")
    now, before = ratchet.summary(current), ratchet.summary(saved)
    for rule in sorted(set(now) | set(before)):
        print(f"{rule:<20}{before.get(rule, 0):>8}{now.get(rule, 0):>6}")
    worst = sorted(current.items(), key=lambda kv: -kv[1])[:10]
    print("\nlargest offenders:", *(f"  {v:>6}  {k}" for k, v in worst), sep="\n")
    verdict = ratchet.compare(current, saved)
    for label, rows in (("NEW", verdict.new), ("WORSE", verdict.worse), ("IMPROVED (run --update)", verdict.improved)):
        for row in rows:
            print(f"{label}: {row}")
    return 0 if verdict.ok else 1


def main(argv: list[str]) -> int:
    current, saved = ratchet.current_findings(), ratchet.load_baseline()
    if "--update" not in argv:
        return report(current, saved)
    verdict = ratchet.compare(current, saved)
    if saved and (verdict.new or verdict.worse):
        print("refused: the baseline may only tighten.", *verdict.new, *verdict.worse, sep="\n  ")
        return 1
    ratchet.save_baseline(current)
    print(f"baseline written: {len(current)} violations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
