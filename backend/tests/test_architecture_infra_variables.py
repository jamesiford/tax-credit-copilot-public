"""infra/variables.tf stays grouped by numbered section. [RM-25]

The file holds about eighty inputs. Terraform does not care about their order, a reader does, and an
ungrouped file is where a duplicate or a misplaced setting hides. Every variable must sit under a numbered
`# ==== N. title` banner, the numbers must run 1..N without a gap, and the contents list at the top must name
each section, so a new section cannot be added without the index being updated.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "infra" / "variables.tf").read_text(encoding="utf-8")
LINES = TEXT.splitlines()
BANNER = re.compile(r"^# ==== (\d+)\. (.+?) =*$")


def _banners() -> list[tuple[int, int, str]]:
    return [(i, int(m.group(1)), m.group(2).strip()) for i, line in enumerate(LINES) if (m := BANNER.match(line))]


def test_section_numbers_run_from_one_without_a_gap():
    numbers = [n for _, n, _ in _banners()]
    assert numbers and numbers == list(range(1, len(numbers) + 1)), numbers


def test_every_variable_sits_under_a_section():
    first = _banners()[0][0]
    stray = [line for i, line in enumerate(LINES) if line.startswith("variable ") and i < first]
    assert not stray, f"variables before the first section banner: {stray}"


def test_the_contents_list_names_every_section():
    head = "\n".join(LINES[: _banners()[0][0]])
    for _, number, title in _banners():
        word = re.split(r"[ (]", title)[0].lower()
        assert re.search(rf"\b{number}\.\s+\S*{re.escape(word)}", head.lower()) or word in head.lower(), (number, title)
        assert re.search(rf"\b{number}\. ", head), f"section {number} is missing from the contents list"


def test_no_variable_is_declared_twice():
    names = re.findall(r'^variable "([a-z0-9_]+)"', TEXT, re.M)
    assert len(names) == len(set(names)) and len(names) >= 70
