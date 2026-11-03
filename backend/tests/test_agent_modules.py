"""Every agent module must export what the roster reads.

`all_specs` reads every module with no per-module guard, so one malformed module
does not degrade one capability — it takes the whole roster down, and `chat()`
then falls through to the scripted stub for every question. That failure only
shows at startup, against live Foundry, which is the slowest possible place to
find a typo.
"""
from __future__ import annotations

import pytest

from agents.factory import all_specs, list_agent_modules

MODULES = list_agent_modules()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_an_agent_module_exports_what_the_factory_reads(module):
    assert isinstance(module.NAME, str) and module.NAME.endswith("Agent")
    assert module.INSTRUCTIONS.strip(), f"{module.NAME} has no instructions"
    assert isinstance(module.AGENT_PROFILE, dict)
    for key in ("tab_label", "summary", "responsibility", "inputs", "outputs"):
        assert key in module.AGENT_PROFILE, f"{module.NAME} profile lacks {key}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_an_agent_module_exports_a_spec_that_matches_its_constants(module):
    """The spec is what the catalog publishes, so it must say what the module says.

    Replaces the old `build()` signature check: modules no longer build anything
    (AI-02), they declare an `AgentSpec`, and a spec that drifted from NAME or
    INSTRUCTIONS would publish a different agent than the one the page describes.
    """
    from domain.ai import AgentSpec

    assert isinstance(module.SPEC, AgentSpec)
    assert module.SPEC.name == module.NAME
    assert module.SPEC.instructions == module.INSTRUCTIONS
    assert module.SPEC.profile == module.AGENT_PROFILE
    assert not hasattr(module, "build"), "agents declare a spec; publishing is the provider's job"


def test_agent_names_are_unique():
    """The registry is keyed by name, so a duplicate silently replaces another."""
    names = [m.NAME for m in MODULES]
    assert len(names) == len(set(names)), f"duplicate agent name in {names}"


def test_the_roster_as_data_is_the_module_roster():
    assert [s.name for s in all_specs()] == [m.NAME for m in MODULES]


def test_the_agents_package_imports_no_sdk():
    """The roster is data; the SDKs live under infrastructure/ai only."""
    import pathlib

    for path in pathlib.Path(__file__).resolve().parents[1].joinpath("agents").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "agent_framework" not in text and "azure.ai" not in text, path.name
