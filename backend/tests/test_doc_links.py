"""Every relative Markdown link in the repository resolves. [A14]"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check-links.py"
_spec = importlib.util.spec_from_file_location("check_links", _SCRIPT)
check_links = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_links)


def test_inline_reference_and_image_links_are_found():
    text = "\n".join([
        "See [the spec](docs/a.md#part) and ![diagram](img/d.svg).",
        "[ref]: ../b.md",
        "A [site](https://example.com) and an [anchor](#top).",
    ])

    found = [target for _, target in check_links.links(text)]

    assert found == ["docs/a.md#part", "img/d.svg", "../b.md", "https://example.com", "#top"]


def test_code_is_not_a_link():
    text = "\n".join([
        "Run `[x](missing.md)` inline.",
        "```md",
        "[y](also-missing.md)",
        "```",
    ])

    assert check_links.links(text) == []


def test_a_missing_target_is_reported_and_urls_are_not(tmp_path):
    (tmp_path / "there.md").write_text("ok", encoding="utf-8")
    doc = tmp_path / "doc.md"
    doc.write_text(
        "[a](there.md#h) [b](gone.md) [c](https://x.test) [d](#local) [e](mailto:x@y.test)",
        encoding="utf-8",
    )
    check_links.ROOT = tmp_path

    assert check_links.broken(doc) == ["doc.md:1: gone.md"]


def test_every_tracked_markdown_link_resolves():
    check_links.ROOT = _SCRIPT.parent.parent
    problems = [p for path in check_links.tracked_markdown() for p in check_links.broken(path)]

    assert problems == [], "\n".join(problems)
