"""Run the AI evals and print a table. [AI-06]

    python scripts/ai-eval.py            # offline: deterministic, no model, no network
    python scripts/ai-eval.py --live     # the configured providers (needs AI_* / FOUNDRY_* settings)
    python scripts/ai-eval.py --json out.json

Exit code 1 if any suite is below its threshold in `backend/tests/ai_evals/thresholds.json`.
The same checks run in the test suite as the `ai_eval` marker.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from tests.ai_evals import harness  # noqa: E402


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--live", action="store_true", help="evaluate the configured providers")
    parser.add_argument("--json", metavar="PATH", help="also write the results as JSON")
    args = parser.parse_args(argv)
    mode = "live" if args.live else "offline"
    results = asyncio.run(harness.run_live()) if args.live else harness.run_offline()
    limits, verdicts = harness.thresholds(mode), harness.verdicts(results, mode)
    print(f"AI evals ({mode})\n{'suite':<12}{'passed':>8}{'total':>7}{'score':>8}{'min':>7}  result")
    for r in results:
        print(f"{r.suite:<12}{r.passed:>8}{r.total:>7}{r.score:>8.2f}{limits[r.suite]:>7.2f}  {'ok' if verdicts[r.suite] else 'FAIL'}")
        for failure in r.failures:
            print(f"    {failure}")
    if args.json:
        Path(args.json).write_text(json.dumps([{**vars(r), "score": r.score, "ok": verdicts[r.suite]} for r in results], indent=2))
    return 0 if all(verdicts.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
