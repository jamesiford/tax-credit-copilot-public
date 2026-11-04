"""Egress: the invariant that is not configurable, and the lever that is. [AI-03]

Employee identifiers and opaque record tokens never enter a prompt — for any
provider, under any policy. That was a repository rule; here it is a check that
fails closed, so a pipeline that starts leaking one gets the engine's own blocks
and a log line, not a model reading somebody's id.
"""
from __future__ import annotations

import asyncio
import json

import pytest

from application.ai.egress import (
    AggregatesOnly, AllowAll, BlockExternal, build_egress_policy, identifier_findings,
)
from application.ai.guarded import GuardedRuntime
from domain.ai import AgentSpec, EgressRefused, ModelRole, NarrationUnavailable, TextDelta
from tests.ai_fakes import ScriptedRuntime, install_providers

SPEC = AgentSpec(name="ReportingAgent", instructions="x")
TOKEN = "01234567" * 3  # 24 hex: the shape tools/tokens.record_token mints
TRAIL_HASH = "ab" * 32            # 64 hex: a trail hash, which is fine to send

LEAKS = [
    f"Employee {TOKEN} qualifies",
    'JSON:\n{"employee_id": "E123"}',
    'JSON:\n{"employee_ids": ["E1"]}',
    '{"record_token": "x"}',
    "SSN 123-45-6789 on file",
]
AGGREGATE = 'Summarise.\n\nJSON:\n{"average_headcount": 12.67, "annual_credit_usd": "3500"}'
ROW_GRAIN = 'Summarise.\n\nJSON:\n{"worksites": [{"worksite_id": "GA_GA-001", "jobs": 2}]}'


@pytest.mark.parametrize("policy", ["allow_all", "aggregates_only", "block"])
@pytest.mark.parametrize("provider", ["foundry", "foundry_connection", "gateway"])
@pytest.mark.parametrize("prompt", LEAKS)
def test_an_identifier_is_refused_under_every_policy_for_every_provider(policy, provider, prompt):
    decision = build_egress_policy(policy).prepare(prompt, role=ModelRole.NARRATOR, provider=provider)
    assert not decision.allowed and decision.reason.startswith("the prompt carries")


def test_the_refusal_never_echoes_the_identifier():
    decision = AllowAll().prepare(f"Employee {TOKEN}", role=ModelRole.NARRATOR, provider="gateway")
    assert TOKEN not in decision.reason and TOKEN not in str(identifier_findings(f"x {TOKEN}"))


def test_a_trail_hash_and_an_ordinary_brief_are_not_mistaken_for_identifiers():
    assert identifier_findings(f"evidence sha256:{TRAIL_HASH}") == []
    assert identifier_findings(AGGREGATE) == []
    assert identifier_findings("a 25-hex run id " + "0123456789abcdef012345678") == []


def test_allow_all_lets_a_clean_prompt_reach_any_provider():
    for provider in ("foundry", "gateway"):
        assert AllowAll().prepare(AGGREGATE, role=ModelRole.NARRATOR, provider=provider).allowed


def test_aggregates_only_refuses_row_grain_briefs_for_external_providers_only():
    policy = AggregatesOnly()
    assert not policy.prepare(ROW_GRAIN, role=ModelRole.NARRATOR, provider="gateway").allowed
    assert not policy.prepare(ROW_GRAIN, role=ModelRole.NARRATOR, provider="foundry_connection").allowed
    assert policy.prepare(ROW_GRAIN, role=ModelRole.NARRATOR, provider="foundry").allowed
    assert policy.prepare(AGGREGATE, role=ModelRole.NARRATOR, provider="gateway").allowed
    assert not policy.prepare("no json at all", role=ModelRole.NARRATOR, provider="gateway").allowed


def test_block_stops_everything_external_and_nothing_on_foundry():
    policy = BlockExternal()
    assert not policy.prepare(AGGREGATE, role=ModelRole.NARRATOR, provider="gateway").allowed
    assert policy.prepare(AGGREGATE, role=ModelRole.NARRATOR, provider="foundry").allowed


def _collect(runtime, prompt):
    async def go():
        return [e async for e in runtime.stream(SPEC, prompt)]

    return asyncio.run(go())


def test_the_guarded_runtime_refuses_before_the_provider_is_called():
    inner = ScriptedRuntime("gateway", ["hi"])
    guarded = GuardedRuntime(inner, BlockExternal())
    with pytest.raises(EgressRefused, match="nothing may leave"):
        _collect(guarded, AGGREGATE)
    assert inner.calls == 0
    assert guarded.name == "gateway" and guarded.ready_for("x") and guarded.version_of("x") == "v-gateway"


def test_a_policy_refusal_for_the_gateway_falls_through_to_foundry():
    install_providers(ScriptedRuntime("gateway", ["G"]), ScriptedRuntime("foundry", ["F"]), egress_policy="block")
    from bootstrap import wiring
    from application.ai.requests import NarrateBriefQuery

    async def go():
        return [e async for e in wiring.get_mediator().stream(NarrateBriefQuery(agent_name="ReportingAgent", prompt=AGGREGATE))]

    events = asyncio.run(go())
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "F" and events[-1].hops == ("gateway", "foundry")


def test_an_identifier_refuses_every_provider_so_nothing_is_narrated():
    gateway, foundry = ScriptedRuntime("gateway", ["G"]), ScriptedRuntime("foundry", ["F"])
    install_providers(gateway, foundry)
    from bootstrap import wiring
    from application.ai.requests import NarrateBriefQuery

    async def go():
        return [e async for e in wiring.get_mediator().stream(
            NarrateBriefQuery(agent_name="ReportingAgent", prompt=f"JSON:\n{json.dumps({'employee_id': 'E9'})}"))]

    with pytest.raises(NarrationUnavailable):
        asyncio.run(go())
    assert gateway.calls == 0 and foundry.calls == 0


def test_every_chat_brief_the_pipelines_build_passes_the_invariant():
    """The briefs are built from capability facts; none may carry an identifier."""
    from api.chat.narration import _brief
    from application.capabilities.client import client_discovery

    facts = client_discovery(exclude_codes=[]).facts
    assert identifier_findings(_brief("List every hit.", facts)) == []
