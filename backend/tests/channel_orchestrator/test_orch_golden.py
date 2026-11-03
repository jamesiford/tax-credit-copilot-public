"""Golden prompts: what the orchestrator does with real-looking questions, end to end. [CH-08]

Each case in `golden/*.json` is a short conversation: what the person says, what the scripted model
does in reply (tool calls, then a sentence), and what must be true afterwards. The pipeline, the MAF
agent, the tool runner, the composer and the numeric guard are the shipped code; only the model and
the gateway are fakes. A case states the gateway calls it expects, so "the model asked for a client
id and we ignored it" and "no model was called for a confirmation" are assertions, not hopes.

Case shape:
    {"name": ..., "supports_tools": true, "configured": true, "writers": ["user"], "env": {...},
     "overrides": {"<tool>": {"status": 422, "error": {...}}}, "narration_status": 200,
     "turns": [{"who": "user|other|none", "say": "...", "advance": 0, "model": [<scripted turns>],
                "expect": {kind, mode, guard, narration_used, audit, gateway, args, contains, absent,
                           model_calls, narrations, refused}}]}
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from orch_harness import OTHER_OID, USER_OID, FakeGateway, build_rig, identity

GOLDEN = Path(__file__).parent / "golden"
WHO = {"user": identity(), "other": identity(OTHER_OID, name="Sam Reader"), "none": None}
WRITERS = {"user": USER_OID, "other": OTHER_OID}


def load_cases() -> list[dict]:
    return [case for path in sorted(GOLDEN.glob("*.json")) for case in json.loads(path.read_text(encoding="utf-8"))]


CASES = load_cases()


def test_there_are_enough_golden_prompts_and_every_read_tool_is_asked_for():
    assert len(CASES) >= 25
    asked = {call["tool"] for case in CASES for turn in case["turns"] for step in turn.get("model", []) for call in step.get("tools", [])}
    from application.capabilities import catalog

    reads = {s.name for s in catalog.offered() if s.kind == catalog.READ and not s.tags and s.name not in ("client_resolve", "employee_drill")}
    assert reads <= asked, f"no golden case exercises: {sorted(reads - asked)}"


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden(case):
    asyncio.run(play(case))


async def play(case: dict) -> None:
    gateway = FakeGateway(writers={WRITERS[w] for w in case.get("writers", ["user"])})
    for tool, reply in case.get("overrides", {}).items():
        gateway.overrides[tool] = lambda _args, r=reply: (r["status"], {"error": r["error"]} if "error" in r else r["body"])
    gateway.narration_status = case.get("narration_status", 200)
    rig = build_rig([], supports_tools=case.get("supports_tools", True), gateway=gateway,
                    env=case.get("env"), configured=case.get("configured", True))
    for number, turn in enumerate(case["turns"], 1):
        rig.chat.script.extend(turn.get("model", []))
        rig.clock.now += turn.get("advance", 0)
        calls, narrations, model_turns = len(gateway.calls), len(gateway.narrations), len(rig.chat.seen)
        reply = await rig.say(turn["say"], WHO[turn.get("who", "user")])
        where = f"{case['name']} turn {number}: {turn['say']!r}\n{reply.text}\n"
        expect = turn["expect"]
        for field in ("kind", "mode", "audit"):
            if field in expect:
                assert getattr(reply, field) == expect[field], f"{field} — {where}"
        if "guard" in expect:
            assert reply.guard_status == expect["guard"], where
        if "narration_used" in expect:
            assert reply.narration_used is expect["narration_used"], where
        if "gateway" in expect:
            assert [c.tool for c in gateway.calls[calls:]] == expect["gateway"], where
        if "model_calls" in expect:
            assert len(rig.chat.seen) - model_turns == expect["model_calls"], where
        if "narrations" in expect:
            assert len(gateway.narrations) - narrations == expect["narrations"], where
        if "refused" in expect:
            assert list(reply.refused) == expect["refused"], where
        for tool, wanted in expect.get("args", {}).items():
            sent = [c.args for c in gateway.calls[calls:] if c.tool == tool][-1]
            assert {k: sent.get(k) for k in wanted} == wanted, f"{tool} args {sent} — {where}"
        for text in expect.get("contains", []):
            assert text in reply.text, f"missing {text!r} — {where}"
        for text in expect.get("absent", []):
            assert text not in reply.text, f"unexpected {text!r} — {where}"
