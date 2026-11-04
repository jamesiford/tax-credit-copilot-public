"""The channel narrator: registered, profiled, and unable to carry a figure.

Three claims are checked. It is part of the decided roster and has the profile the
Agent Workbench reads. Its instructions never contain a digit and say what the
composer relies on. And the brief it is handed names the facts without their
values — so the guarantee does not rest on the model obeying an instruction.
"""
from __future__ import annotations

import json
import re

import pytest

from agents import channel_narrator
from agents.factory import list_agent_modules
from application import composer


def test_it_is_registered_once_in_the_decided_roster():
    names = [m.NAME for m in list_agent_modules()]
    assert names.count("ChannelNarratorAgent") == 1
    assert channel_narrator in list_agent_modules()
    assert len(names) == 12


def test_it_follows_the_agent_module_contract():
    assert channel_narrator.NAME == "ChannelNarratorAgent"
    assert channel_narrator.INSTRUCTIONS.strip()
    profile = channel_narrator.AGENT_PROFILE
    for key in ("tab_label", "summary", "responsibility", "inputs", "outputs", "tools", "determinism"):
        assert profile[key], key
    assert channel_narrator.SPEC.name == channel_narrator.NAME and channel_narrator.SPEC.role.value == "narrator"


def test_its_profile_is_json_for_the_workbench_to_serve():
    """The Workbench lists every registered profile; it must serialise cleanly."""
    body = json.dumps({m.NAME: m.AGENT_PROFILE for m in list_agent_modules()})
    assert "ChannelNarratorAgent" in body


def test_its_instructions_carry_no_digit_to_copy():
    # A list index inside a fact path (clients.0.name) is addressing, not a figure; CH-15c's worked examples need one.
    assert not re.search(r"\d", re.sub(r"(?<=\.)\d+(?=\.)", "", channel_narrator.INSTRUCTIONS))


@pytest.mark.parametrize("must_say", [
    "{{facts.", "Never write a digit", "placeholder", "declined", "no authored rule",
    "one to four", "not a zero", "Never state tax law",
])
def test_its_instructions_state_what_the_composer_relies_on(must_say):
    flattened = " ".join(channel_narrator.INSTRUCTIONS.split())
    assert must_say.lower() in flattened.lower()


def test_it_is_never_shown_a_value():
    facts = {
        "credit": {"annual_credit_usd": 3500, "average_headcount": 12.67, "citation": "O.C.G.A. 48-7-40.26"},
        "snapshot": {"selected_tax_year": 2023, "begin": "2023-07-28", "calculated": True, "missing": None},
    }
    brief = composer.narrator_brief("what is the credit?", ["client_eligibility"], facts, notes=["Nothing hidden."])
    text = json.dumps(brief)

    for value in ("3500", "3,500", "12.67", "O.C.G.A.", "2023", "2023-07-28"):
        assert value not in text.replace("selected_tax_year", ""), value
    paths = {entry["path"]: entry["format"] for entry in brief["fact_paths"]}
    assert paths["credit.annual_credit_usd"] == "money"
    assert paths["credit.average_headcount"] == "headcount"
    assert paths["snapshot.selected_tax_year"] == "year"
    assert paths["snapshot.begin"] == "date"
    assert "snapshot.calculated" not in paths and "snapshot.missing" not in paths
    assert brief["question"] == "what is the credit?" and brief["declined"] is None


def test_a_narration_written_from_that_brief_composes():
    """The loop the channel runs: brief out, placeholders back, figures in code."""
    from application.capabilities.envelope import Block

    facts = {"credit": {"annual_credit_usd": 3500}}
    brief = composer.narrator_brief("credit?", ["client_eligibility"], facts)
    path = brief["fact_paths"][0]
    narration = f"The credit is {{{{facts.{path['path']}|{path['format']}}}}}."

    composed = composer.compose([Block("paragraph", text="Annual credit: $3,500")], narration, facts)
    assert composed.narration_used and composed.text.startswith("The credit is $3,500.")
