"""The narrator's prompt, version 2: the voice it asks for and the examples it teaches by. [CH-15c]

A prompt cannot be unit-tested for how a model will read it, but its worked examples can be
held to the platform's own rules: every example reply must survive the composer — placeholders
that resolve, no typed digit, no hedged figure — or the prompt is teaching the model to be
withheld. And the rules the composer relies on must still be stated in words.
"""
from __future__ import annotations

import re

import pytest

from agents import channel_narrator
from application.capabilities.envelope import Block
from application.composer import compose
from infrastructure.ai.prompt_manifest import load_manifest
from infrastructure.ai.prompts_fs import FilePromptStore

TEXT = channel_narrator.INSTRUCTIONS
FLAT = " ".join(TEXT.split())
SAMPLE = {"money": 3500, "count": 12, "headcount": 12.67, "year": 2023, "text": "On the line"}
EXAMPLE = re.compile(r"^Example: (?P<title>.+?)\nFacts: (?P<facts>.+?)\nReply: (?P<reply>.+?)(?=\n\nExample:|\Z)", re.DOTALL | re.MULTILINE)
PLACEHOLDER = re.compile(r"\{\{(facts\.[^{}|]+)(?:\|[a-z_]+)?\}\}")


def examples() -> list[dict[str, str]]:
    return [m.groupdict() for m in EXAMPLE.finditer(TEXT)]


def facts_for(example: dict[str, str]) -> dict:
    """The sample facts an example's `Facts:` line describes, nested by path."""
    tree: dict = {}
    for path, kind in re.findall(r"([a-z_]+(?:\.[a-z0-9_]+)+) \((\w+)\)", example["facts"]):
        node = tree
        parts = path.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = SAMPLE[kind]
    return tree


def test_the_prompt_is_version_three_and_the_manifest_records_every_version():
    version = FilePromptStore().get("channel_narrator").version
    assert version == 3
    assert {"1", "2", "3"} <= set(load_manifest()["prompts"]["channel_narrator"]["versions"])


def test_it_teaches_by_worked_examples_and_keeps_them_few_enough_to_read():
    assert 4 <= len(examples()) <= 12


@pytest.mark.parametrize("topic", [
    "book", "brief", "both methods", "trend", "at-risk", "refusal",
    "descriptive aggregate", "comparison between the two methods", "capped result", "no column for",
    "individual employees", "why",
])
def test_the_examples_cover_the_answers_a_reader_asks_for(topic):
    assert any(topic in e["title"].lower() for e in examples()), topic


@pytest.mark.parametrize("example", [e for e in examples() if "Facts: none" not in e["title"]], ids=lambda e: e["title"][:40])
def test_every_example_reply_survives_the_composer(example):
    reply = compose([Block("paragraph", text="Table below.")], example["reply"].strip(), facts_for(example))
    assert reply.guard.passed and reply.narration_used, [v.reason for v in reply.guard.violations]


def test_every_placeholder_in_an_example_is_one_its_facts_line_lists():
    for example in examples():
        for path in PLACEHOLDER.findall(example["reply"]):
            assert path.removeprefix("facts.") in example["facts"], (example["title"], path)


def test_every_example_is_one_to_four_sentences():
    for example in examples():
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", example["reply"].strip()) if s]
        assert 1 <= len(sentences) <= 4, (example["title"], len(sentences))


@pytest.mark.parametrize("must_say", [
    "lead with the answer", "the engine's own labels", "never turn a rank into prose", "every figure is exact",
    "never say a figure is rounded", "approximately", "roughly", "character for character", "the `facts.` prefix",
    "no authored rule pack", "not a zero", "never state tax law",
    "exact rows and aggregates, not a conclusion", "capped", "has nothing for it", "have not been shown",
    "engine's figure is the authority",
])
def test_the_voice_and_the_composer_rules_are_stated(must_say):
    assert must_say.lower() in FLAT.lower() or must_say.lower() in " ".join(TEXT.lower().split())


def test_the_prompt_still_carries_no_digit_to_copy():
    assert not re.search(r"\d", re.sub(r"(?<=\.)\d+(?=\.)", "", TEXT))
