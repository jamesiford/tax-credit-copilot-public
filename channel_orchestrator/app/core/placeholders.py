"""Handing the model a placeholder it can copy, not a path it must dress. [CH-14]

The platform's narrator prompt says a figure is written `{{facts.<path>}}` or `{{facts.<path>|<format>}}` where the
path comes from `fact_paths`. `narrator_brief` lists the bare path (`book_rank.clients.0.identified_usd`), and
gpt-4.1-mini, live, wrote `{{book_rank.clients.0.identified_usd|money}}`: no `facts.`, so nothing resolved, the
digits of the unresolved path (`clients.0`) were counted as figures the model had typed, and the whole narration
was withheld. The composer is right to refuse it. The fix is on the sending side: every entry also carries the
exact placeholder, which the prompt's own rule already says to use. The composer, the guard and the platform's
prompt are untouched.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def placeholder_for(path: str, fmt: str | None) -> str:
    """The exact text the composer resolves for `path`, with the brief's own format hint when it gave one."""
    return "{{facts.%s|%s}}" % (path, fmt) if fmt else "{{facts.%s}}" % path


def with_placeholders(fact_paths: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Each fact path entry plus its `placeholder`; the entry's own keys are unchanged."""
    return [{**entry, "placeholder": placeholder_for(str(entry["path"]), entry.get("format"))} for entry in fact_paths]
