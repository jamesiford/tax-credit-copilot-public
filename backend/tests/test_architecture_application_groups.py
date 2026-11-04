"""`application/` is grouped by concern, and the renderer cannot forget a block kind. [RM-21]

The numeric guard, the composer and the knowledge port each grew into several sibling modules, so
they are packages (`application.numeric`, `application.composer`, `application.knowledge`); a loose
`numeric_*`, `composer_*` or `knowledge_*` module beside them is how the directory became a flat list
of fifty files. The renderer dispatches on block kind through tables, and a kind added to the envelope
without an entry would be silently dropped from a reply, so the tables are pinned to `BLOCK_KINDS`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from application.capabilities.envelope import BLOCK_KINDS, Block
from application.composer import render

APPLICATION = Path(__file__).resolve().parent.parent / "application"
GROUPS = {"numeric": "numeric_", "composer": "composer", "knowledge": "knowledge"}


@pytest.mark.parametrize("package, prefix", GROUPS.items())
def test_a_grouped_concern_has_a_package_and_no_loose_sibling_modules(package, prefix):
    assert (APPLICATION / package / "__init__.py").is_file()
    loose = sorted(p.name for p in APPLICATION.glob("*.py") if p.name.startswith(prefix))
    assert loose == [], f"{loose} belong inside application/{package}/"


def test_the_package_init_files_re_export_what_callers_import():
    from application.composer import Composed, PlaceholderError, cards_payload, compose, narrator_brief, placeholders, render_markdown, substitute  # noqa: F401
    from application.knowledge import KnowledgePort, Passage, model_context, render_reference  # noqa: F401
    from application.numeric import PASS, REJECTED, AllowedContext, FactIndex, GuardResult, check, check_raw  # noqa: F401


def test_the_renderer_has_an_entry_for_every_block_kind_and_nothing_else():
    assert set(render._MARKDOWN) == set(BLOCK_KINDS)
    assert set(render._CARD_ITEM) == set(BLOCK_KINDS)


def test_the_renderer_does_not_grow_an_if_chain_on_block_kind_again():
    source = (APPLICATION / "composer" / "render.py").read_text(encoding="utf-8")
    assert not re.search(r"\bblock\.kind\s*==\s*\"(paragraph|callout|bullets|table)\"", source)


def test_each_kind_renders_and_an_empty_table_renders_nothing():
    blocks = [
        Block("heading", text="Title"), Block("paragraph", text="Body"), Block("callout", text="a\nb"),
        Block("bullets", rows=(("one",), ("two",))), Block("table", rows=(("K", "V"), ("a", "1"))),
        Block("table", rows=()),
    ]
    assert render.render_markdown(blocks) == "### Title\n\nBody\n\n> a\n> b\n\n- one\n- two\n\n| K | V |\n| --- | --- |\n| a | 1 |"
    cards = render.cards_payload(blocks)
    assert cards["title"] == "Title"
    assert [item["type"] for item in cards["body"]] == ["paragraph", "callout", "bullets", "facts"]
    assert render.cards_payload([Block("paragraph", text="x"), Block("heading", text="late")])["body"][1] == {"type": "heading", "text": "late"}
