"""The AI evals, as a test. [AI-06]

`ai_eval` is on by default: the offline evals are deterministic and fast, and a
regression in routing, the numeric guard or scope refusal should fail the build.
`TCC_AI_EVALS_LIVE=1` adds the live evals (needs configured providers); they are
opt-in for the same reason the live-Fabric tests are — CI has no model.

Run them with a table instead: `python scripts/ai-eval.py [--live]`.
"""
from __future__ import annotations

import asyncio
import os

import pytest

from tests.ai_evals import harness

pytestmark = pytest.mark.ai_eval


def _report(results):
    return "\n".join(f"{r.suite}: {r.passed}/{r.total}" + "".join(f"\n    {f}" for f in r.failures) for r in results)


def test_the_offline_evals_meet_their_thresholds():
    results = harness.run_offline()
    verdicts = harness.verdicts(results, "offline")
    assert all(verdicts.values()), "\n" + _report(results)


@pytest.mark.parametrize("suite", harness.SUITES)
def test_every_suite_has_rows_and_a_threshold(suite):
    assert len(harness.load_rows(suite, live=False)) >= 5
    assert 0 < harness.thresholds("offline")[suite] <= 1 and 0 < harness.thresholds("live")[suite] <= 1


def test_the_narration_suite_covers_both_verdicts():
    expectations = {r["expect"] for r in harness.load_rows("narration", live=False)}
    assert expectations == {"pass", "reject"}, "an eval that can only pass proves nothing"


def test_the_scorer_fails_when_the_subject_regresses():
    always_eligibility = harness.score_routing(harness.load_rows("routing", live=False), lambda q: ["eligibility"], "offline")
    assert always_eligibility.score < 0.5 and always_eligibility.failures


@pytest.mark.skipif(os.environ.get("TCC_AI_EVALS_LIVE") != "1", reason="set TCC_AI_EVALS_LIVE=1 to run the evals against live providers")
def test_the_live_evals_meet_their_thresholds():
    results = asyncio.run(harness.run_live())
    assert all(harness.verdicts(results, "live").values()), "\n" + _report(results)
