"""`verify_figures`: which numerals in a draft are not the engine's. [CH-06, ADR-008]

Cowork composes its own prose, so the platform cannot stop a figure being
misquoted on the way out. What it can do is let the author ask, before a document
is shared: this is the numeric guard (`numeric_guard.check`, zero tolerance) run
over the draft against the facts of the conversation.

The facts are NOT an argument a caller can supply — a caller that chose its own
facts would be marking its own homework. Only the channel gateway knows which
tool results this conversation actually received, so it passes them in; the API
has no such ledger and answers this tool with a refusal (`GATEWAY_LOCAL`). What a
caller MAY supply is `allowed_context`: the numerals the reader themselves typed,
which the guard has always let through.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from application.capabilities import _support as s
from application.capabilities.envelope import Provenance, ToolResult
from application.numeric_context import AllowedContext
from application.numeric_extract import extract_numerals
from application.numeric_guard import check

#: Numerals that need no fact: a list marker or a step number.
_FREE_KINDS = frozenset({"structural"})


def _violation_row(violation: Any) -> dict[str, Any]:
    numeral = violation.numeral
    return {"token": numeral.text, "position": numeral.start, "reason": violation.reason}


def verify_figures(
    draft_text: str,
    allowed_context: Sequence[str] = (),
    *,
    facts: Sequence[Mapping[str, Any]] = (),
) -> ToolResult:
    """Every numeral in `draft_text` must be a fact or something the reader supplied.

    `facts` is supplied by the gateway from its conversation ledger and is not part
    of the tool's schema. With no facts, every numeral that is not structural or
    reader-supplied is reported, which is the honest answer to "is this figure
    from the engine" when nothing has been fetched.
    """
    context = AllowedContext.build(*allowed_context)
    verdict = check(draft_text, facts=list(facts), allowed_context=context)
    checked = sum(1 for numeral in extract_numerals(draft_text) if numeral.kind not in _FREE_KINDS)
    rows = [_violation_row(v) for v in verdict.violations]
    blocks = [
        s.heading("Figure check"),
        s.paragraph(
            f"Every figure in the draft was found in this conversation's results ({checked} checked)."
            if verdict.passed else
            f"{len(rows)} of {checked} figures in the draft are not in this conversation's results."
        ),
    ]
    if rows:
        blocks.append(s.table(
            ("Figure", "Position", "Why"), [(r["token"], str(r["position"]), r["reason"]) for r in rows],
        ))
    return s.result(
        "verify_figures",
        {"status": verdict.status, "violations": rows, "violation_count": len(rows), "checked_numerals": checked},
        blocks,
        provenance=Provenance(source="numeric guard over this conversation's tool facts"),
    )
