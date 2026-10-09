"""Every agent module must be buildable before the app tries to build it.

`build_all` loops `list_agent_modules()` with no per-module guard, so one
malformed module does not degrade one capability — it takes the whole registry
down, and `chat()` then falls through to the scripted stub for every question.
That failure only shows at startup, against live Foundry, which is the slowest
possible place to find a typo in a keyword argument.
"""
from __future__ import annotations

import inspect

import pytest

from agents.factory import build_all, list_agent_modules

MODULES = list_agent_modules()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_an_agent_module_exports_what_the_factory_reads(module):
    assert isinstance(module.NAME, str) and module.NAME.endswith("Agent")
    assert module.INSTRUCTIONS.strip(), f"{module.NAME} has no instructions"
    assert isinstance(module.AGENT_PROFILE, dict)
    for key in ("tab_label", "summary", "responsibility", "inputs", "outputs"):
        assert key in module.AGENT_PROFILE, f"{module.NAME} profile lacks {key}"


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_build_takes_exactly_what_build_all_passes(module):
    """A signature mismatch is a TypeError at startup, not an import error.

    Tests import these modules freely, so nothing else catches it.
    """
    expected = {"project_client", "project_endpoint", "credential", "model"}
    params = inspect.signature(module.build).parameters
    assert set(params) == expected, f"{module.NAME}.build takes {set(params)}"
    assert all(p.kind is inspect.Parameter.KEYWORD_ONLY for p in params.values()), (
        f"{module.NAME}.build must take keyword-only arguments; build_all passes them by name"
    )


def test_agent_names_are_unique():
    """The registry is keyed by name, so a duplicate silently replaces another."""
    names = [m.NAME for m in MODULES]
    assert len(names) == len(set(names)), f"duplicate agent name in {names}"


def test_build_all_declines_without_a_project_rather_than_half_registering(monkeypatch):
    """A partial registry is worse than none: `chat()` checks for a set of
    agents and would stub out anyway, but a half-built one hides which.

    `KeyError` rather than a tidier error on purpose — it names the variable
    that is missing, which is the whole content of the message.
    """
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    with pytest.raises(KeyError, match="FOUNDRY_PROJECT_ENDPOINT"):
        build_all()
