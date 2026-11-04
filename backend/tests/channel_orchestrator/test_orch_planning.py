"""What the model is told about the tools, because that is its only guide to choosing one. [CH-15c]

Live, a one-client question was occasionally planned with the whole-book tool. The routing itself
is code (the runner resolves the client and writes it over whatever the model passed), so the
repair for the CHOICE is in the words the model reads: each tool's description and the planner's
instructions. These tests hold those words to the distinction, so a later edit cannot blur it.
"""
from __future__ import annotations

import pytest

from app.core import prompts
from app.core.maf_agent import function_tools
from app.core.tools import model_tools
from application.capabilities import catalog


def client_tools() -> list[str]:
    """The read tools a question about one client is answered with (those with a chat intent)."""
    return sorted(n for n, spec in model_tools().items() if "client_id" in spec.schema["properties"] and spec.chat_intent)


def test_book_rank_says_it_is_for_the_whole_book_only():
    text = model_tools()["book_rank"].description
    assert "WHOLE BOOK" in text and "Never use it for a question about one client" in text


def test_the_client_tools_are_found_and_every_one_says_it_needs_a_client():
    names = client_tools()
    assert {"client_situation", "client_eligibility", "client_trend", "client_at_risk", "client_discovery", "simulate"} <= set(names)
    for name in names:
        assert model_tools()[name].description.startswith("ONE client (needs a client)"), name


def test_a_tool_that_needs_no_client_does_not_claim_to():
    assert "needs a client" not in model_tools()["book_rank"].description.replace("Needs no client", "")


def test_the_maf_tools_and_the_json_catalogue_carry_the_same_words():
    by_name = {t.name: t.description for t in function_tools(_Runner())}
    catalogue = prompts.tool_catalogue()
    for name, spec in model_tools().items():
        assert by_name[name] == spec.description
        assert f"- {name}: {spec.description}" in catalogue


@pytest.mark.parametrize("instruction", [prompts.PLANNER, prompts.PLAN_JSON])
def test_the_planner_instructions_send_one_client_questions_to_client_tools(instruction):
    flat = " ".join(instruction.split())
    assert "never `book_rank`" in flat
    assert "client" in flat


def test_the_planner_says_how_to_tell_the_two_apart_and_who_resolves_the_client():
    flat = " ".join(prompts.PLANNER.split())
    for must in ("WHOLE BOOK", "ONE client", '"them", "their" or "this client"', "never pass one", "the platform resolves which client"):
        assert must.lower() in flat.lower(), must


class _Runner:
    """Just enough of a runner to build the tool list; nothing here is called."""

    async def run(self, name, proposed):  # pragma: no cover - never invoked
        raise AssertionError("not called")
