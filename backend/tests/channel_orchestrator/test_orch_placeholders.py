"""The placeholder a model is handed is the placeholder the composer resolves. [CH-14]

Live, a model wrote `{{book_rank.clients.0.identified_usd|money}}` (no `facts.`) because the brief listed the bare
path; the composer rightly refused it and the narration was withheld. Every `fact_paths` entry the model sees now
carries the exact placeholder.
"""
from __future__ import annotations

import pytest

from app.core.placeholders import placeholder_for, with_placeholders
from application.composer import narrator_brief
from application.composer_placeholders import substitute

FACTS = {"clients": [{"client_name": "Example Co", "identified_usd": "40495", "jobs_margin": 11.57, "tax_year": 2025}], "assessed_clients": 5}


def test_a_placeholder_names_the_path_and_the_format_hint():
    assert placeholder_for("book_rank.clients.0.identified_usd", "money") == "{{facts.book_rank.clients.0.identified_usd|money}}"
    assert placeholder_for("a.b", None) == "{{facts.a.b}}"


def test_entries_keep_their_own_keys_and_gain_a_placeholder():
    [entry] = with_placeholders([{"path": "x.y", "format": "count"}])
    assert entry == {"path": "x.y", "format": "count", "placeholder": "{{facts.x.y|count}}"}


@pytest.mark.parametrize("leaf", ["identified_usd", "jobs_margin", "tax_year", "client_name"])
def test_every_placeholder_the_model_is_given_resolves_to_the_engines_figure(leaf):
    brief = narrator_brief("q", ["book_rank"], {"book_rank": FACTS}, notes=[])
    entry = next(e for e in with_placeholders(brief["fact_paths"]) if e["path"] == f"book_rank.clients.0.{leaf}")
    text, _ = substitute(f"Say {entry['placeholder']} here.", {"book_rank": FACTS})
    assert "{{" not in text
    expected = {"identified_usd": "$40,495", "jobs_margin": "11.57", "tax_year": "2025", "client_name": "Example Co"}[leaf]
    assert expected in text


def test_the_path_without_the_facts_prefix_is_still_refused_not_loosened():
    with pytest.raises(Exception):
        substitute("{{book_rank.clients.0.identified_usd|money}}", {"book_rank": FACTS})
