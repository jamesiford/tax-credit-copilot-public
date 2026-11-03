"""Provider chain semantics and the Foundry catalog. [AI-02]

`foundry,gateway` and `gateway,foundry` are both configuration; the rules below
are what both orders rely on: a provider that is not ready is skipped, one that
fails before output hands over to the next, one that fails after output does
NOT (splicing two models' sentences shows a reader something neither said), and
the hop that answered is reported.
"""
from __future__ import annotations

import asyncio

import pytest

from application.ai.chain import ProviderChain
from domain.ai import AgentSpec, ModelUnavailable, NarrationUnavailable, StreamEnd, TextDelta
from tests.ai_fakes import ScriptedRuntime

SPEC = AgentSpec(name="ReportingAgent", instructions="x")


def run(chain):
    async def go():
        return [e async for e in chain.stream(SPEC, "p")]

    return asyncio.run(go())


def text(events):
    return "".join(e.text for e in events if isinstance(e, TextDelta))


def test_the_first_ready_provider_answers_and_the_hop_is_recorded():
    a, b = ScriptedRuntime("a", ["A"]), ScriptedRuntime("b", ["B"])
    events = run(ProviderChain([a, b]))
    assert text(events) == "A" and b.calls == 0
    assert events[-1] == StreamEnd(provider="a", model="m-a", agent_version="v-a", hops=("a",), finish_reason=None)


def test_a_provider_that_fails_before_output_hands_over_and_both_hops_are_listed():
    a = ScriptedRuntime("a", error=ModelUnavailable("down"))
    b = ScriptedRuntime("b", ["B"])
    events = run(ProviderChain([a, b]))
    assert text(events) == "B"
    assert events[-1].hops == ("a", "b") and events[-1].fallback_used


def test_the_reverse_order_prefers_the_other_provider():
    a, b = ScriptedRuntime("a", ["A"]), ScriptedRuntime("b", ["B"])
    assert text(run(ProviderChain([b, a]))) == "B"


def test_a_provider_not_ready_for_the_agent_is_skipped_without_a_call():
    a, b = ScriptedRuntime("a", ["A"], ready=False), ScriptedRuntime("b", ["B"])
    events = run(ProviderChain([a, b]))
    assert text(events) == "B" and a.calls == 0 and events[-1].hops == ("b",)


def test_a_failure_after_output_is_not_papered_over_by_the_next_provider():
    a = ScriptedRuntime("a", ["Half a sen"], error=ModelUnavailable("cut"), error_after_output=True)
    b = ScriptedRuntime("b", ["B"])

    async def go():
        seen = []
        with pytest.raises(ModelUnavailable):
            async for event in ProviderChain([a, b]).stream(SPEC, "p"):
                seen.append(event)
        return seen

    seen = asyncio.run(go())
    assert text(seen) == "Half a sen" and b.calls == 0


def test_every_provider_failing_is_one_typed_error_naming_the_hops():
    chain = ProviderChain([
        ScriptedRuntime("a", error=ModelUnavailable("x")), ScriptedRuntime("b", error=RuntimeError("y")),
    ])
    with pytest.raises(NarrationUnavailable) as caught:
        run(chain)
    assert caught.value.hops == ("a", "b")


def test_an_empty_chain_or_none_ready_is_unavailable_not_empty():
    with pytest.raises(NarrationUnavailable):
        run(ProviderChain([]))
    with pytest.raises(NarrationUnavailable):
        run(ProviderChain([ScriptedRuntime("a", ready=False)]))


def test_the_chain_is_ready_when_any_provider_is_and_reports_each_state():
    chain = ProviderChain([ScriptedRuntime("a", ready=False), ScriptedRuntime("b")])
    assert chain.ready_for("ReportingAgent")
    status = chain.status()
    assert status.state == "ready" and "a=unavailable" in status.detail and "b=ready" in status.detail
    assert not ProviderChain([ScriptedRuntime("a", ready=False)]).ready_for("x")


# ------------------------------------------------------------- the Foundry catalog


def _catalog(**kw):
    from application.ai.settings import AiSettings
    from infrastructure.ai.foundry_prompt_agents import FoundryAgentCatalog

    class Versions:
        def __init__(self):
            self.created: list[tuple[str, str]] = []
            self.store: dict[str, list] = {}

        def list_versions(self, name):
            return self.store.get(name, [])

        def get_version(self, name, version):
            return next(v for v in self.store[name] if str(v.version) == str(version))

        def create_version(self, name, definition):
            n = len(self.store.get(name, [])) + 1
            info = type("V", (), {"version": str(n), "id": f"{name}:{n}", "definition": definition})()
            self.store.setdefault(name, []).append(info)
            self.created.append((name, str(n)))
            return info

    versions = Versions()
    client = type("C", (), {"agents": versions})()
    specs = [AgentSpec(name="ReportingAgent", instructions="v1"), AgentSpec(name="HeadcountAgent", instructions="h")]
    settings = AiSettings(foundry_endpoint="https://acct.services.ai.azure.com/api/projects/proj", **kw.pop("settings", {}))
    return FoundryAgentCatalog(settings, specs, client_factory=lambda: client, sleep=lambda s: None, **kw), versions, specs


def test_publishing_is_idempotent_an_identical_definition_is_reused():
    catalog, versions, _ = _catalog()
    catalog.publish_all()
    catalog.publish_all()
    assert len(versions.created) == 2  # one per agent, not four
    assert catalog.status().state == "ready" and catalog.version_of("ReportingAgent") == "1"


def test_a_changed_prompt_publishes_a_new_version():
    catalog, versions, specs = _catalog()
    catalog.publish_all()
    changed = AgentSpec(name="ReportingAgent", instructions="v2")
    catalog._specs = (changed, specs[1])
    catalog.publish_all()
    assert catalog.version_of("ReportingAgent") == "2" and catalog.version_of("HeadcountAgent") == "1"


def test_a_pinned_version_is_fetched_not_created():
    from application.ai.settings import AiSettings

    catalog, versions, _ = _catalog()
    catalog.publish_all()
    changed = AgentSpec(name="ReportingAgent", instructions="v2")
    catalog._specs = (changed,)
    catalog._settings = AiSettings(foundry_endpoint=catalog.endpoint, version_pins={"ReportingAgent": "1"})
    created_before = len(versions.created)
    catalog.publish_all()
    assert catalog.version_of("ReportingAgent") == "1" and len(versions.created) == created_before


def test_without_an_endpoint_the_catalog_is_disabled_and_publishes_nothing():
    from application.ai.settings import AiSettings
    from infrastructure.ai.foundry_prompt_agents import FoundryAgentCatalog

    catalog = FoundryAgentCatalog(AiSettings(), [SPEC], client_factory=lambda: pytest.fail("must not connect"))
    catalog.warm(background=False)
    assert catalog.status().state == "disabled" and not catalog.has("ReportingAgent")


def test_an_unreachable_project_retries_with_backoff_then_reports_unavailable():
    sleeps: list[float] = []
    from application.ai.settings import AiSettings
    from infrastructure.ai.foundry_prompt_agents import FoundryAgentCatalog

    def down():
        raise ConnectionError("no route")

    catalog = FoundryAgentCatalog(
        AiSettings(foundry_endpoint="https://x.services.ai.azure.com/api/projects/p"), [SPEC],
        client_factory=down, sleep=sleeps.append, attempts=4,
    )
    catalog.warm(background=False)
    assert catalog.status().state == "unavailable" and sleeps == [2.0, 4.0, 8.0]
    assert not catalog.has("ReportingAgent")


def test_one_agent_failing_to_publish_degrades_rather_than_fails():
    catalog, versions, _ = _catalog()
    original = versions.create_version

    def flaky(name, definition):
        if name == "HeadcountAgent":
            raise RuntimeError("quota")
        return original(name, definition)

    versions.create_version = flaky
    catalog.publish_all()
    status = catalog.status()
    assert status.state == "degraded" and "HeadcountAgent" in status.detail
    assert catalog.has("ReportingAgent") and not catalog.has("HeadcountAgent")


def test_the_connection_provider_publishes_under_a_distinct_name_with_the_connection_model():
    from application.ai.settings import AiSettings
    from infrastructure.ai.foundry_model_connection import build_connection_runtime

    _, versions, specs = _catalog()
    client = type("C", (), {"agents": versions})()
    settings = AiSettings(
        foundry_endpoint="https://a.services.ai.azure.com/api/projects/p", connection_name="corp-gw",
        models={"narrator__foundry_connection": "big-model"},
    )
    runtime = build_connection_runtime(settings, specs, client_factory=lambda: client, sleep=lambda s: None)
    runtime.catalog.publish_all()
    entry = runtime.catalog.entry("ReportingAgent")
    assert runtime.name == "foundry_connection" and entry.published_name == "ReportingAgent-byom"
    assert entry.model == "corp-gw/big-model"
    assert ("ReportingAgent-byom", "1") in versions.created
