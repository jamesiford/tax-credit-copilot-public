"""The docs index is complete, the archive holds only what it says, and the hand-rolled inventory is finished. [RM-22]

`scripts/check-links.py` proves a link resolves; it cannot prove a document is linked at all. These rules keep
`docs/README.md` the one door into `docs/`: every folder and every ADR is indexed, a superseded ADR says what
superseded it, the archive is indexed with a pointer to what replaced each file, and every row of the
hand-rolled inventory ends in REPLACED, WRAPPED or KEPT, never `pending`.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = ROOT / "docs"
INDEX = (DOCS / "README.md").read_text(encoding="utf-8")
ARCH = DOCS / "architecture"
ALIGNMENT = DOCS / "m365-channel" / "MAF-ALIGNMENT.md"
OUTCOME = re.compile(r"^\*\*(REPLACED|WRAPPED|KEPT)\b")
ROW = re.compile(r"^\| (?:H|T|R|P|G)\d+ \|")


def test_every_docs_folder_is_in_the_index():
    folders = sorted(p.name for p in DOCS.iterdir() if p.is_dir())
    missing = [name for name in folders if f"`{name}/`" not in INDEX]
    assert not missing, f"docs/README.md has no row in 'Every docs folder' for: {missing}"


def test_every_adr_is_in_the_index():
    adrs = sorted(p.name for p in ARCH.glob("ADR-*.md"))
    missing = [name for name in adrs if f"architecture/{name}" not in INDEX]
    assert not missing, f"docs/README.md does not index: {missing}"
    assert len(adrs) >= 10, "the ADR set shrank: an ADR was removed, which this repository does not do"


def test_a_superseded_adr_says_what_superseded_it():
    """An ADR whose status says Superseded must name the ADR that replaced it, in its first lines."""
    for path in sorted(ARCH.glob("ADR-*.md")):
        head = "\n".join(path.read_text(encoding="utf-8").splitlines()[:6])
        if "Superseded" in head:
            successors = set(re.findall(r"\[ADR-(\d{3})\]", head)) - {path.name[4:7]}
            assert successors, f"{path.name} says Superseded but names no successor ADR in its status"


def test_adr_001_is_marked_superseded_by_its_successors():
    head = "\n".join((ARCH / "ADR-001-persistence.md").read_text(encoding="utf-8").splitlines()[:8])
    assert "ADR-002" in head and "ADR-007" in head and "Superseded" in head


def test_every_archived_file_is_in_the_archive_index():
    archive = DOCS / "archive"
    listing = (archive / "README.md").read_text(encoding="utf-8")
    archived = sorted(p.relative_to(archive).as_posix() for p in archive.rglob("*.md") if p.name != "README.md")
    assert archived, "the archive is empty: the index describes files that are not there"
    missing = [name for name in archived if f"]({name})" not in listing]
    assert not missing, f"docs/archive/README.md does not list: {missing}"


def test_the_build_log_is_named_as_one_and_indexes_its_durable_decisions():
    log = (DOCS / "m365-channel" / "DECISIONS.md").read_text(encoding="utf-8")
    assert log.startswith("# Microsoft 365 channel — build log")
    assert "Durable decisions have a home elsewhere" in log


def test_every_inventory_row_ends_in_a_final_outcome():
    text = ALIGNMENT.read_text(encoding="utf-8").splitlines()
    start = text.index("## Hand-rolled inventory")
    end = next(i for i, line in enumerate(text) if line.startswith("## Where each guarantee lives"))
    rows = [line for line in text[start:end] if ROW.match(line)]
    assert len(rows) >= 47, f"the inventory lost rows: {len(rows)}"
    unfinished = [row[:8] for row in rows if not OUTCOME.match(re.split(r"\s\|\s", row.rstrip("| ").strip())[-1].strip())]
    assert not unfinished, f"inventory rows without a REPLACED, WRAPPED or KEPT outcome: {unfinished}"


def test_the_one_answer_document_carries_the_same_inventory():
    """Its condensed copy has a row for every id in the full table, so the two cannot drift apart silently."""
    full = ALIGNMENT.read_text(encoding="utf-8")
    ids = set(re.findall(r"^\| ((?:H|T|R|P|G)\d+) \|", full, re.MULTILINE))
    copy = (ARCH / "ONE-ANSWER-EVERYWHERE.md").read_text(encoding="utf-8")
    copied = set(re.findall(r"^\| ((?:H|T|R|P|G)\d+) \|", copy, re.MULTILINE))
    assert ids and ids == copied, f"differs: only in the full table {sorted(ids - copied)}, only in the copy {sorted(copied - ids)}"
    assert "```mermaid" in copy, "the document's diagram is gone"
