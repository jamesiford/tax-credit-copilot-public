"""Datasets and scorers for the AI evals. [AI-06]

An eval answers "is the AI behaving as well as it did?" with a NUMBER and a
threshold, so a regression is a failing build rather than somebody's impression.

Two modes share the datasets:

- OFFLINE (the default, runs in CI): the deterministic parts — keyword routing,
  the numeric guard over recorded good and bad replies, and per-capability scope
  refusal. No model, no network, exact.
- LIVE (`TCC_AI_EVALS_LIVE=1`): the same questions put to the configured
  providers — the router's JSON plan, and real narrations checked by the numeric
  guard — scored against the looser `live` thresholds, because a model varies.

A scorer returns an `EvalResult`; nothing here asserts. `thresholds.json` and the
test (or `scripts/ai-eval.py`) decide pass or fail.
"""
from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
SUITES = ("routing", "narration", "refusal")


@dataclass(frozen=True)
class EvalResult:
    suite: str
    mode: str
    passed: int
    total: int
    failures: tuple[str, ...] = field(default_factory=tuple)

    @property
    def score(self) -> float:
        return self.passed / self.total if self.total else 0.0


def load_rows(suite: str, *, live: bool) -> list[dict[str, Any]]:
    """The suite's rows for this mode. A row marked `"mode": "live"` is live-only."""
    lines = (HERE / "datasets" / f"{suite}.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    return [r for r in rows if live or r.get("mode", "offline") == "offline"]


def thresholds(mode: str) -> dict[str, float]:
    return json.loads((HERE / "thresholds.json").read_text(encoding="utf-8"))[mode]


def _tally(suite: str, mode: str, outcomes: Iterable[tuple[str, bool, str]]) -> EvalResult:
    outcomes = list(outcomes)
    failures = tuple(f"{rid}: {detail}" for rid, ok, detail in outcomes if not ok)
    return EvalResult(suite, mode, sum(1 for _, ok, _ in outcomes if ok), len(outcomes), failures)


def score_routing(rows: list[dict[str, Any]], route: Callable[[str], list[str]], mode: str) -> EvalResult:
    """Did the router name exactly the capabilities the question needs (order aside), and none it must not?

    `forbidden` names a capability that is wrong for the question even alongside the right one:
    a question about one client must never be answered by the whole-book ranking.
    """
    def judge(row):
        got = route(row["question"])
        banned = sorted(set(got) & set(row.get("forbidden", ())))
        ok = set(got) == set(row["expected"]) and not banned
        return row["id"], ok, f"expected {sorted(row['expected'])}, got {sorted(got)}" + (f", forbidden {banned}" if banned else "")

    return _tally("routing", mode, map(judge, rows))


#: Wording a narration must never contain, whatever the row says. Each is a failure seen live:
#: a hedge on an exact figure, and a rank restated as prose ("position 1", "ranked first because of").
FORBIDDEN_WORDING = (
    r"(?i)\b(about|roughly|approximately|approx\.?|around|nearly|almost|rounded|up to|close to|more or less|or so)\b",
    r"(?i)\bposition\s+(?:\d+|one)\b|\branked?\s+(?:number\s+)?(?:\d+|one|first)\b|\bnumber\s+one\b",
)


def composed_reply(row: dict[str, Any]) -> tuple[str, bool]:
    """A recorded narration (with placeholders) as the channel composer would show it, and whether it survived."""
    from application.capabilities.envelope import Block
    from application.composer import compose

    composed = compose([Block("paragraph", text="The table below is the platform's own.")], row["narration"], row["brief"])
    return composed.text, composed.narration_used


def _wording_problems(row: dict[str, Any], text: str) -> list[str]:
    """Missing must-contain patterns and present forbidden ones, for a narration that was kept."""
    missing = [p for p in row.get("must_contain", ()) if not re.search(p, text)]
    banned = [p for p in (*FORBIDDEN_WORDING, *row.get("forbidden", ())) if re.search(p, text)]
    return [*(f"missing /{p}/" for p in missing), *(f"forbidden /{p}/" for p in banned)]


def _judge_composed(row: dict[str, Any]) -> tuple[str, bool, str]:
    """A composed narration: kept or dropped as expected; if kept, in the wording the prompt asks for."""
    text, used = composed_reply(row)
    if row["expect"] == "reject":
        # `by: composer` demands the composer itself drops it; otherwise a wording flag also counts (rank prose has no guard).
        flagged = not used or (row.get("by") != "composer" and bool(_wording_problems(row, text)))
        leaked = [p for p in row.get("forbidden", ()) if not used and re.search(p, text)]
        return row["id"], flagged and not leaked, f"narration {'kept' if used else 'dropped'}, expected reject" + (f", leaked {leaked}" if leaked else "")
    problems = [] if used else ["narration was dropped"]
    problems += _wording_problems(row, text) if used else []
    return row["id"], not problems, "; ".join(problems) or "ok"

def score_narration(rows: list[dict[str, Any]], reply_for: Callable[[dict[str, Any]], str], mode: str) -> EvalResult:
    """Does the numeric guard (and, for a placeholder narration, the composer) agree with each row's expectation?"""
    from application.numeric_guard import check

    def judge(row):
        if "narration" in row:
            return _judge_composed(row)
        rejected = not check(reply_for(row), facts=row["brief"]).passed
        wanted_reject = row["expect"] == "reject"
        return row["id"], rejected == wanted_reject, f"guard {'rejected' if rejected else 'passed'}, expected {row['expect']}"

    return _tally("narration", mode, map(judge, rows))


def score_refusal(rows: list[dict[str, Any]], decide: Callable[[str, bool], str], mode: str) -> EvalResult:
    """Is a question that needs a client refused (or split) when none is selected?"""
    def judge(row):
        got = decide(row["question"], row["has_client"])
        return row["id"], got == row["expect"], f"expected {row['expect']}, got {got}"

    return _tally("refusal", mode, map(judge, rows))


# --- the offline subjects ---------------------------------------------------------

def keyword_route(question: str) -> list[str]:
    from api.chat.routing import _keyword_intents

    return _keyword_intents(question)


def recorded_reply(row: dict[str, Any]) -> str:
    return row["reply"]


def scope_decision(question: str, has_client: bool) -> str:
    """What the dispatcher does with this question's intents given whether a client is selected."""
    from application.capabilities.catalog import NEEDS_CLIENT
    from api.chat.routing import _keyword_intents

    intents = _keyword_intents(question)
    needing = [i for i in intents if i in NEEDS_CLIENT]
    if has_client or not needing:
        return "answer"
    return "ask_client" if len(needing) == len(intents) else "partial"


def run_offline() -> list[EvalResult]:
    from tests.ai_evals import data_routing

    return [
        score_routing(load_rows("routing", live=False), keyword_route, "offline"),
        score_narration(load_rows("narration", live=False), recorded_reply, "offline"),
        score_refusal(load_rows("refusal", live=False), scope_decision, "offline"),
        data_routing.score(data_routing.load_rows()),
    ]


# --- the live subjects ------------------------------------------------------------

async def _live_plan(question: str) -> list[str]:
    from api.chat.routing import _plan

    return await _plan(question, [], {"account_id": None, "tax_year": None, "state": None})


async def _live_narration(row: dict[str, Any]) -> str:
    from application.ai.requests import NarrateBriefQuery
    from application.wiring import get_mediator
    from domain.ai import TextDelta

    prompt = f"Summarise for a call.\n\nJSON:\n{json.dumps(row['brief'], indent=2)}"
    events = get_mediator().stream(NarrateBriefQuery(agent_name="ReportingAgent", prompt=prompt))
    return "".join([e.text async for e in events if isinstance(e, TextDelta)])


async def run_live() -> list[EvalResult]:
    """Routing and narration against the configured providers. Refusal stays deterministic."""
    routing_rows = load_rows("routing", live=True)
    plans = {r["id"]: await _live_plan(r["question"]) for r in routing_rows}
    by_question = {r["question"]: plans[r["id"]] for r in routing_rows}
    narration_rows = [r for r in load_rows("narration", live=True) if r["expect"] == "pass" and "narration" not in r]
    replies = {r["id"]: await _live_narration(r) for r in narration_rows}
    return [
        score_routing(routing_rows, lambda q: by_question[q], "live"),
        # In live mode every generated reply must pass the guard, whatever the recorded expectation was.
        score_narration([{**r, "expect": "pass"} for r in narration_rows], lambda r: replies[r["id"]], "live"),
        score_refusal(load_rows("refusal", live=True), scope_decision, "live"),
    ]


def verdicts(results: list[EvalResult], mode: str) -> dict[str, bool]:
    limits = thresholds(mode)
    return {r.suite: r.score >= limits[r.suite] for r in results}
