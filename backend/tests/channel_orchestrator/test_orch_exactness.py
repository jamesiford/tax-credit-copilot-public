"""The exactness property: whatever the narrator does, no figure the engine did not produce reaches the reader. [CH-08]

Four narrator behaviours, played through the real pipeline many times with random figures:

1. **well-behaved**: placeholders and digit-free connective words. The narration survives.
2. **types a digit**: a figure written out by the model, in any common form, even one that happens to
   EQUAL a fact. The narration is dropped whole.
3. **rewrites a figure**: a real figure with a digit changed. Dropped whole.
4. **invents a figure**: a number unrelated to anything the engine said. Dropped whole.

Dropped means the reply is the platform's blocks and the disclaimer, the guard status is `rejected`,
and the audit report says so. In EVERY case the finished reply, footer aside, passes the numeric
guard on its own against the engine's facts and what the reader said: the invariant does not depend
on which behaviour the model chose.
"""
from __future__ import annotations

import asyncio
import random
import re

import pytest

from app.core.compose import allowed_for, facts_of
from application.numeric_guard import FactIndex, check
from orch_harness import build_rig

QUESTION = "What is Cascade's credit for 2023 under Min-Max?"
PATHS = {
    "annual_credit_usd": "money", "lifetime_credit_usd": "money", "average_headcount": "headcount",
    "qualifying_jobs": "headcount",
}
FIGURES = ("227605", "227,605", "$227,605", "$227.6k", "1138025", "$1,138,025", "375.53", "65.03")
MARKER = "Narrator says"


def placeholder(path: str) -> str:
    return "{{facts.client_eligibility_min_max.credit.%s|%s}}" % (path, PATHS[path])


def well_behaved(rng: random.Random) -> str:
    paths = rng.sample(sorted(PATHS), rng.randint(1, len(PATHS)))
    return f"{MARKER}: " + " and ".join(f"the figure is {placeholder(p)}" for p in paths) + "."


def types_a_digit(rng: random.Random) -> str:
    return f"{MARKER}: the credit is {rng.choice(FIGURES)} as the table shows."


def rewrites_a_figure(rng: random.Random) -> str:
    figure = rng.choice(("227605", "1138025", "37553", "6503"))
    at = rng.randrange(len(figure))
    changed = figure[:at] + str((int(figure[at]) + rng.randint(1, 8)) % 10) + figure[at + 1:]
    return f"{MARKER}: {placeholder('annual_credit_usd')}, about ${int(changed):,}."


def invents_a_figure(rng: random.Random) -> str:
    return f"{MARKER}: this reflects {rng.randint(11, 9999)} locations and {rng.randint(3, 90)} new hires."


BEHAVIOURS = {
    "well_behaved": (well_behaved, True),
    "types_a_digit": (types_a_digit, False),
    "rewrites_a_figure": (rewrites_a_figure, False),
    "invents_a_figure": (invents_a_figure, False),
}


def play(narration: str):
    rig = build_rig([
        {"tools": [{"tool": "client_eligibility", "args": {"tax_year": 2023, "method": "min_max"}}]}, {"text": narration},
    ])
    return rig, asyncio.run(rig.say(QUESTION))


def body_without_footer(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith("_Source:"))


@pytest.mark.parametrize("behaviour", sorted(BEHAVIOURS))
def test_each_narrator_behaviour_gets_exactly_its_outcome(behaviour):
    make, survives = BEHAVIOURS[behaviour]
    rng = random.Random(20240625)
    for _ in range(60):
        narration = make(rng)
        rig, reply = play(narration)
        assert reply.kind == "answer"
        assert (MARKER in reply.text) is survives, narration
        assert reply.narration_used is survives and reply.guard_status == ("pass" if survives else "rejected")
        assert "Annual credit" in reply.text and "Not tax advice" in reply.text, "the platform's own blocks always remain"
        (filed,) = rig.gateway.narrations
        assert filed["guard_status"] == reply.guard_status
        assert (filed["violations_count"] == 0) is survives


@pytest.mark.parametrize("behaviour", sorted(BEHAVIOURS))
def test_whatever_the_model_did_the_finished_reply_passes_the_guard_on_its_own(behaviour):
    make, _ = BEHAVIOURS[behaviour]
    rng = random.Random(7)
    from app.core.tools import ToolRun
    from orch_harness import FakeGateway

    args = {"client_id": 2001, "tax_year": 2023, "method": "min_max"}
    runs = [ToolRun("client_eligibility", args, FakeGateway()._read("client_eligibility", args), "client_eligibility_min_max")]
    for _ in range(40):
        _, reply = play(make(rng))
        verdict = check(
            re.sub(r"\*\*|\|", " ", body_without_footer(reply.text)), facts=FactIndex.coerce(facts_of(runs)),
            allowed_context=allowed_for(QUESTION, runs),
        )
        assert verdict.passed, (behaviour, [v.numeral.text for v in verdict.violations], reply.text)


def test_a_figure_the_model_types_is_rejected_even_when_it_equals_a_fact():
    _, reply = play(f"{MARKER}: the credit is $227,605.")
    assert reply.guard_status == "rejected" and MARKER not in reply.text and "$227,605" in reply.text
