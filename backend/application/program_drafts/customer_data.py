"""A conservative detector for customer data pasted into a program draft. [F07.3]

Why: a draft's notes are free text, drafts are visible to every writer, and an export bundle carries them into git. A program
draft holds statute, never a client's records, so anything that looks like a person's or an employer's identifier is a BLOCKING
finding on validate and on export, addressed to the field and saying what kind of thing matched. The matched text is never
repeated in a finding, a log line or an event: a detector that echoes the value spreads it further.

Deliberately simple pattern checks, not a classifier. It will miss things (a name it has no list for, a number written in
words); it exists to catch the common accident, and the reviewer's checklist still says to read the notes. Only STRINGS are
scanned: numbers in a pack are statute values (caps, rates, thresholds), and years, dollar amounts with separators, section
numbers and citations are shaped differently from every pattern below (see the false-positive tests).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable, Iterator

from domain.program_drafts import ProgramDraft

log = logging.getLogger(__name__)

#: Client or employer names shorter than this are ignored: a short name matches ordinary words in a citation.
MIN_NAME_LENGTH = 4
MAX_FINDINGS = 20

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("a social security number", re.compile(r"(?<![\d-])\d{3}-\d{2}-\d{4}(?![\d-])")),
    ("an employer identification number", re.compile(r"(?<![\d-])\d{2}-\d{7}(?![\d-])")),
    ("an email address", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    ("a phone number", re.compile(r"(?<![\d-])(?:\+?1[ .-])?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?![\d-])")),
    ("a long digit string (an identifier or account number)", re.compile(r"(?<![\w.,-])\d{9,}(?![\w.,-])")),
)


def _strings(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """`(path, text)` for every string in a JSON document, in the same path format the placeholder check uses."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _strings(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _strings(value, f"{path}/{i}")
    elif isinstance(node, str):
        yield path, node


def book_names() -> list[str]:
    """Every client and employer name in the book, or none (logged) when the book cannot be read here.

    The pattern checks do not need the book, so a draft is still scanned when it is unavailable; only the name match is lost.
    """
    try:
        from application.client_book import clients

        return [str(c.get("name") or "").strip() for c in clients()]
    except Exception as exc:  # noqa: BLE001 - the scan must never fail a validation because the book is unreachable
        log.warning("customer-data scan: client names unavailable (%s); pattern checks still ran", type(exc).__name__)
        return []


def _name_matcher(names: Iterable[str]) -> re.Pattern[str] | None:
    usable = sorted({n for n in names if len(n) >= MIN_NAME_LENGTH}, key=len, reverse=True)
    if not usable:
        return None
    return re.compile(r"(?<!\w)(?:" + "|".join(re.escape(n) for n in usable) + r")(?!\w)", re.IGNORECASE)


def _finding(where: str, path: str, what: str) -> dict[str, str]:
    return {
        "file": where, "severity": "error", "code": "customer_data", "path": path or "/",
        "message": f"looks like {what} (not shown here). A program draft holds statute, not customer data: remove it.",
    }


def _scan_text(where: str, path: str, text: str, names: re.Pattern[str] | None) -> Iterator[dict[str, str]]:
    for what, pattern in _PATTERNS:
        if pattern.search(text):
            yield _finding(where, path, what)
    if names is not None and names.search(text):
        yield _finding(where, path, "the name of a client or employer in the book")


def scan_documents(draft: ProgramDraft, names: Iterable[str] | None = None) -> list[dict[str, str]]:
    """Blocking findings for every string field that looks like customer data. `names` defaults to the book's."""
    matcher = _name_matcher(book_names() if names is None else names)
    documents = [("draft", {"name": draft.name}), ("pack", draft.pack), *((f"year {k}", d) for k, d in sorted(draft.years.items()))]
    found: list[dict[str, str]] = []
    for where, doc in documents:
        for path, text in _strings(doc):
            found += _scan_text(where, path, text, matcher)
            if len(found) >= MAX_FINDINGS:
                return found[:MAX_FINDINGS]
    return found
