"""The semantic-model page is generated; it must equal what the model renders. [CH-16a]"""
from __future__ import annotations

from pathlib import Path

from application.data.model_doc import render_markdown
from application.data.semantic_model import default_model

PAGE = Path(__file__).resolve().parents[2] / "docs" / "data" / "SEMANTIC-MODEL.md"


def test_the_committed_page_is_what_the_model_renders():
    assert PAGE.read_text(encoding="utf-8") == render_markdown(default_model()), (
        "docs/data/SEMANTIC-MODEL.md is stale: run python scripts/generate-semantic-model-doc.py"
    )


def test_the_page_lists_every_dataset_and_every_blocked_column():
    text = render_markdown(default_model())
    model = default_model()
    assert all(f"### `{d.name}`" in text for d in model.datasets)
    assert "Never queryable" in text and "`employee_id`" in text


def test_the_page_names_the_authoritative_tools_for_the_overlapping_measures():
    text = render_markdown(default_model())
    for tool in ("client_eligibility", "client_trend", "client_at_risk"):
        assert tool in text
