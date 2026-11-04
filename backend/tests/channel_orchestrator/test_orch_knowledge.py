"""The knowledge tier inside the orchestrator: off by default, context only, cited, and never a figure. [RM-15, ADR-010]

The tier reaches the orchestrator through one framework context provider and one line of the reply. These tests play a
whole turn through the real pipeline (real `ModelChain`, `PortChatClient` and MAF `Agent`, a scripted model, a fake
gateway) with the fake knowledge source and pin:

- with the tier off (the default) a turn is exactly what it was: the model is told no reference text and the reply
  carries none;
- with it on, the model is told the passages as fenced reference text with no citation to copy, the reader gets the
  quoted passages WITH their citations beside a narration that survived, and the engine's figures are still verbatim;
- a narration that repeats a figure read only in a passage is dropped whole, and then no reference block is shown;
- a knowledge source that fails costs the reader nothing;
- the provider adds instructions and nothing else, and the settings are read at start.
"""
from __future__ import annotations

import asyncio

import pytest
from agent_framework import SessionContext

from app.core.compose import facts_of
from app.core.maf_knowledge import SOURCE_ID, KnowledgeContextProvider
from app.core.models import ModelChain, Provider
from app.core.planned import Planned
from app.core.planner import Planner
from app.core.settings import OrchestratorConfigError, load_settings
from app.core.state import StateStore
from app.core.turn import TurnPipeline
from app.wiring import build_orchestrator
from application import knowledge as k
from application.ai.safety.injection import PromptInjectionGuard
from application.knowledge.fake import FakeKnowledge
from orch_harness import ENV, FakeClock, FakeGateway, Rig, ScriptedChat, identity

QUESTION = "What is Cascade's credit for 2023 under Min-Max, and what is a credit per job for a designation?"
CALL = {"tool": "client_eligibility", "args": {"tax_year": 2023, "method": "min_max"}}
PLAIN = "Here is the position, and the cited source explains the rule behind it."
FIGURE = "The cited source says the credit is $1,234 per job."
ANNUAL = "{{facts.client_eligibility_min_max.credit.annual_credit_usd|money}}"


class Broken:
    def search(self, query, *, top):
        raise RuntimeError("the search service is down")


def rig(script, knowledge=None, *, top=3) -> Rig:
    settings = load_settings(dict(ENV))
    gateway, clock, chat = FakeGateway(), FakeClock(), ScriptedChat(script)
    chain = ModelChain([Provider("gateway", chat, "test-model", True)], egress_policy=settings.ai.egress_policy, timeout_seconds=5.0,
                       injection=PromptInjectionGuard())
    planner = Planner(chain, knowledge=knowledge, knowledge_top=top)
    return Rig(TurnPipeline(settings, gateway.client(), planner, StateStore(settings.state_ttl_seconds, clock), clock), gateway, chat, clock, settings)


def play(narration, knowledge=None, **kw):
    rig_ = rig([{"tools": [CALL]}, {"text": narration}], knowledge, **kw)
    return rig_, asyncio.run(rig_.say(QUESTION))


def told(chat: ScriptedChat) -> str:
    return "\n".join(str(getattr(m, "content", m)) for turn in chat.seen for m in turn["messages"])


# ------------------------------------------------------------------ off by default


def test_with_the_tier_off_the_model_is_told_no_reference_text_and_the_reply_carries_none():
    rig_, reply = play(f"{PLAIN} {ANNUAL}")
    assert reply.narration_used is True
    assert "REFERENCE TEXT" not in told(rig_.chat) and "Reference text" not in reply.text


def test_the_planner_and_the_agent_builder_default_to_no_knowledge():
    import inspect

    from app.core.maf_agent import build_agent

    assert inspect.signature(Planner.__init__).parameters["knowledge"].default is None
    assert inspect.signature(build_agent).parameters["context_providers"].default == ()


def test_the_default_wiring_builds_no_knowledge_source():
    built = build_orchestrator(dict(ENV), gateway=FakeGateway().client(), chain=ModelChain([], egress_policy="allow_all", timeout_seconds=5.0))
    assert built.pipeline._planner._knowledge is None


def test_switching_it_on_in_the_environment_builds_the_fake_and_a_bad_setting_stops_the_start():
    chain = ModelChain([], egress_policy="allow_all", timeout_seconds=5.0)
    on = {**ENV, "KNOWLEDGE_ENABLED": "true", "KNOWLEDGE_PROVIDER": "fake", "KNOWLEDGE_TOP": "2"}
    built = build_orchestrator(on, gateway=FakeGateway().client(), chain=chain)
    assert isinstance(built.pipeline._planner._knowledge, FakeKnowledge) and built.pipeline._planner._knowledge_top == 2
    for bad, expected in (({"KNOWLEDGE_ENABLED": "true"}, "nothing to consult"),
                          ({"KNOWLEDGE_ENABLED": "true", "KNOWLEDGE_PROVIDER": "foundry-iq"}, "not implemented")):
        with pytest.raises(OrchestratorConfigError, match=expected):
            build_orchestrator({**ENV, **bad}, gateway=FakeGateway().client(), chain=chain)


# ------------------------------------------------------------------ on: context for the model, citations for the reader


def test_the_model_is_told_the_passages_as_fenced_reference_text_without_their_citations():
    rig_, _ = play(f"{PLAIN} {ANNUAL}", FakeKnowledge())
    seen = told(rig_.chat)
    assert k.MODEL_HEADER in seen and "<<<UNTRUSTED source=reference 1>>>" in seen and "Synthetic example, not statute" in seen
    assert "synthetic:" not in seen, "the platform prints the citation; the model has none to copy"


def test_the_reader_gets_the_quoted_passages_with_their_citations_beside_a_surviving_narration():
    rig_, reply = play(f"{PLAIN} {ANNUAL}", FakeKnowledge())
    assert reply.narration_used is True and reply.guard_status == "pass"
    assert k.READER_HEADER in reply.text and "synthetic:example-credit" in reply.text and "retrieved 2026-01-01" in reply.text
    assert "227,605" in reply.text or "$227,605" in reply.text, "the engine's figure, verbatim, from the platform's own blocks and placeholder"
    footer = reply.text.rindex("_Source:")
    assert reply.text.index(k.READER_HEADER) < footer, "the provenance footer stays last"


def test_only_as_many_passages_as_the_setting_allows_are_retrieved_and_shown():
    _, reply = play(f"{PLAIN} {ANNUAL}", FakeKnowledge(), top=1)
    assert reply.text.count("synthetic:") == 1


# ------------------------------------------------------------------ a passage is never a figure


def test_a_narration_that_repeats_a_figure_read_only_in_a_passage_is_dropped_and_no_reference_block_is_shown():
    corpus = [k.Passage("Synthetic example, not statute. The credit per job is $1,234 for a designation.", "Synthetic corpus", "synthetic:figure", FakeKnowledge().search("credit", top=1)[0].retrieved_at)]
    rig_, reply = play(FIGURE, FakeKnowledge(corpus))
    assert reply.narration_used is False and reply.guard_status == "rejected"
    assert "1,234" not in reply.text and "cited source says" not in reply.text
    assert "Reference text" not in reply.text, "reference text is shown only beside the narration it may have informed"
    assert "Annual credit" in reply.text, "the platform's own blocks always remain"
    (filed,) = rig_.gateway.narrations
    assert filed["guard_status"] == "rejected" and "1,234" not in str(filed)


def test_the_turns_facts_are_the_tools_facts_and_hold_nothing_from_a_passage():
    _, reply = play(f"{PLAIN} {ANNUAL}", FakeKnowledge())
    facts = facts_of(reply.runs)
    assert list(facts) == ["client_eligibility_min_max"]
    assert "Synthetic example" not in str(facts)


def test_a_placeholder_into_reference_text_drops_the_narration():
    _, reply = play("The rule is {{facts.reference.0.text}}.", FakeKnowledge())
    assert reply.narration_used is False and reply.guard_status == "rejected"


# ------------------------------------------------------------------ a source that fails costs nothing


def test_a_knowledge_source_that_fails_leaves_the_turn_exactly_as_it_was():
    rig_, reply = play(f"{PLAIN} {ANNUAL}", Broken())
    assert reply.kind == "answer" and reply.narration_used is True
    assert "Reference text" not in reply.text and "REFERENCE TEXT" not in told(rig_.chat)


def test_a_turn_with_no_matching_passage_shows_no_reference_block():
    rig_ = rig([{"tools": [CALL]}, {"text": f"{PLAIN} {ANNUAL}"}], FakeKnowledge([]))
    reply = asyncio.run(rig_.say(QUESTION))
    assert reply.narration_used is True and "Reference text" not in reply.text


def test_falling_back_to_the_platforms_own_answer_forgets_the_reference():
    planned = Planned("tools", reference=tuple(FakeKnowledge().search("credit", top=2)))
    planned.fall_back()
    assert planned.reference == () and planned.degraded is True


# ------------------------------------------------------------------ the provider adds instructions and nothing else


def run_provider(port, question="hypothetical credit"):
    provider = KnowledgeContextProvider(port, question, top=2)
    context = SessionContext(input_messages=[])
    asyncio.run(provider.before_run(agent=None, session=None, context=context, state={}))
    return provider, context


def test_the_provider_adds_instructions_only_and_keeps_what_it_found():
    provider, context = run_provider(FakeKnowledge())
    assert provider.source_id == SOURCE_ID and len(provider.passages) == 2
    assert context.instructions and k.MODEL_HEADER in context.instructions[0]
    assert not context.tools and not context.context_messages and not context.middleware


def test_the_provider_with_nothing_found_or_a_failing_source_adds_nothing():
    for port in (FakeKnowledge([]), Broken()):
        provider, context = run_provider(port)
        assert provider.passages == () and not context.instructions
