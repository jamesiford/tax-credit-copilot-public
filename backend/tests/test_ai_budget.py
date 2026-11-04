"""The token budget, and its place in front of a provider. [AI-04]"""
from __future__ import annotations

import asyncio

import pytest

from bootstrap import wiring
from application.ai.budget import InMemoryTokenBudget, estimate_tokens
from application.ai.guarded import GuardedRuntime
from domain.ai import AgentSpec, BudgetExceeded, ModelUsage, TextDelta
from tests.ai_fakes import ScriptedRuntime, install_providers

SPEC = AgentSpec(name="ReportingAgent", instructions="x")


class AllowAll:
    name = "allow_all"

    def prepare(self, prompt, *, role, provider):
        from domain.ai import EgressDecision

        return EgressDecision(True, prompt, "allow_all")


class Counting:
    def __init__(self):
        self.counts = []

    def count(self, metric, value=1, **attributes):
        self.counts.append((metric, attributes))


def run(runtime, prompt="a" * 40):
    async def go():
        return [e async for e in runtime.stream(SPEC, prompt)]

    return asyncio.run(go())


def test_a_call_that_would_cross_the_overall_ceiling_is_refused():
    budget = InMemoryTokenBudget(100, None)
    budget.record("u", ModelUsage(60, 30))
    with pytest.raises(BudgetExceeded) as refused:
        budget.check("u", 11)
    assert refused.value.scope == "overall"
    budget.check("u", 10)


def test_the_per_user_ceiling_is_independent_of_other_users():
    budget = InMemoryTokenBudget(None, 50)
    budget.record("alice", ModelUsage(40, 5))
    with pytest.raises(BudgetExceeded) as refused:
        budget.check("alice", 10)
    assert refused.value.scope == "per-user"
    budget.check("bob", 50)


def test_no_ceiling_means_no_refusal():
    budget = InMemoryTokenBudget(None, None)
    budget.record("u", ModelUsage(10**9, 10**9))
    budget.check("u", 10**9)


def test_a_new_utc_day_starts_a_fresh_allowance():
    day = ["2026-01-01"]
    budget = InMemoryTokenBudget(100, 100, today=lambda: day[0])
    budget.record("u", ModelUsage(100, 0))
    with pytest.raises(BudgetExceeded):
        budget.check("u", 1)
    day[0] = "2026-01-02"
    budget.check("u", 100)
    assert budget.used() == 0


def test_estimates_are_four_characters_to_a_token():
    assert estimate_tokens("") == 0 and estimate_tokens("abcd") == 1 and estimate_tokens("abcde") == 2


def test_a_refused_call_never_reaches_the_provider_and_is_counted():
    inner, telemetry = ScriptedRuntime("p", ["hi"]), Counting()
    guarded = GuardedRuntime(inner, AllowAll(), InMemoryTokenBudget(5, None), telemetry)
    with pytest.raises(BudgetExceeded):
        run(guarded)
    assert inner.calls == 0
    assert telemetry.counts == [("ai.budget_refusals", {"provider": "p", "scope": "overall"})]


def test_usage_is_estimated_when_the_provider_reports_none_and_charged_after_the_call():
    budget = InMemoryTokenBudget(1000, None)
    run(GuardedRuntime(ScriptedRuntime("p", ["b" * 8]), AllowAll(), budget))
    assert budget.used() == estimate_tokens("a" * 40) + 2  # 10 in, 8 chars out


def test_reported_usage_wins_over_the_estimate():
    class Reporting(ScriptedRuntime):
        async def stream(self, spec, prompt):
            yield TextDelta("x")
            yield ModelUsage(7, 3)

    budget = InMemoryTokenBudget(1000, None)
    run(GuardedRuntime(Reporting("p"), AllowAll(), budget))
    assert budget.used() == 10


def test_a_spent_budget_ends_in_narration_unavailable_through_the_whole_chain():
    from application.ai.requests import NarrateBriefQuery
    from domain.ai import NarrationUnavailable

    first, second = ScriptedRuntime("a", ["x"]), ScriptedRuntime("b", ["y"])
    install_providers(first, second, budget_global_daily=1)

    async def go():
        return [e async for e in wiring.get_mediator().stream(
            NarrateBriefQuery(agent_name="ReportingAgent", prompt="a" * 400))]

    with pytest.raises(NarrationUnavailable):
        asyncio.run(go())
    assert first.calls == 0 and second.calls == 0, "the one shared budget refuses before any provider is called"
