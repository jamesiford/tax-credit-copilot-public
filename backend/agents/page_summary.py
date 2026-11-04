"""PageSummaryAgent — the headlines of one page, in the page's own figures.

29 Sep: the page-opening banners were replaced by a collapsed "Copilot summary"
that a reader opens when they want the story rather than the grid. This agent
writes it. The brief is built by `tools/page_brief.py` from the payload the page
itself was served, so the summary cannot describe a different answer from the
one on screen; it can only choose what to lead with and say it plainly.
"""
from __future__ import annotations

from .roster import build_spec

AGENT_PROFILE = {
    "tab_label": "Page Summary",
    "summary": "Writes the collapsed Copilot summary at the top of each page, from that page's own figures.",
    "responsibility": (
        "Read the JSON brief built by tools/page_brief.py for the page on screen and pick "
        "the two to four headlines that matter, quoting its figures exactly."
    ),
    "inputs": [
        "JSON brief: page, subject, facts[], caveats[], data",
    ],
    "outputs": [
        "Streamed 2-4 markdown bullets in the page's Copilot summary panel",
    ],
    "tools": [
        "tools/page_brief.py · portfolio_brief / client_brief / unit_brief / employee_brief — "
        "pure shaping of the payload the page was served",
        "tools/page_brief.py · unsupported_figures — every number in the summary is checked "
        "against the brief and flagged on screen if it is not there",
    ],
    "determinism": (
        "The brief is deterministic: it is the page's own payload, reformatted. Wording "
        "varies; figures are pinned by the brief and checked after the summary is written."
    ),
}


SPEC = build_spec("page_summary", AGENT_PROFILE)
NAME = SPEC.name
INSTRUCTIONS = SPEC.instructions
