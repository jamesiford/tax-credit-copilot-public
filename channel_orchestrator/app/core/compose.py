"""Turning tool results and a model's sentence into the reply, and nothing else. [CH-08]

Everything a reader sees that carries a figure is the platform's own rendering of the engine's
facts. This module gathers the pieces; `composer.compose` (vendored from the platform,
unchanged) decides what survives:

- the model's narration may hold only `{{facts.path|format}}` placeholders; a digit it typed,
  a figure it rewrote, a path that does not exist or a link it invented drops the narration
  and the reader gets the platform's blocks and the disclaimer;
- the finished reply is checked a second time against the facts.

The provenance footer is appended AFTER the composer, from the envelopes' own provenance
fields, verbatim: a run id, a rule-pack path and a trail hash are identifiers, not figures,
and no model touches them.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.core.tools import ToolRun
from application.capabilities.envelope import Block
from application.composer import Composed, compose
from application.numeric_guard import AllowedContext

METHOD_LABEL = {"min_max": "Min-Max method", "pay_period": "Pay Period method"}
_YEAR_KEYS = ("tax_year", "year")


def facts_of(runs: Sequence[ToolRun]) -> dict[str, Any]:
    """Every run's facts under its own label, so the same tool under two methods never shares a path."""
    return {run.label: run.facts for run in runs}


def blocks_of(runs: Sequence[ToolRun]) -> list[Block]:
    """The platform's blocks in call order, each run led by its method when it has one."""
    blocks: list[Block] = []
    for run in runs:
        method = run.args.get("method")
        if method in METHOD_LABEL:
            blocks.append(Block("heading", text=METHOD_LABEL[method]))
        for raw in run.envelope.get("blocks") or []:
            blocks.append(Block(raw["kind"], raw.get("text", ""), tuple(tuple(row) for row in raw.get("rows") or ())))
    return blocks


def allowed_for(question: str, runs: Sequence[ToolRun]) -> AllowedContext:
    """What the reader supplied: their own words, plus the tax years and client the answer is scoped to."""
    years = {run.args[k] for run in runs for k in _YEAR_KEYS if isinstance(run.args.get(k), int)}
    clients = {run.args["client_id"] for run in runs if isinstance(run.args.get("client_id"), int)}
    return AllowedContext.build(question, years=sorted(years), numbers=sorted(clients))


def compose_reply(question: str, runs: Sequence[ToolRun], narration: str | None, allowed_hosts: Sequence[str] = ()) -> Composed:
    """The composed reply for these results; `narration` None gives the platform's blocks alone."""
    return compose(
        blocks_of(runs), narration, facts_of(runs), allowed_for(question, runs), allowed_hosts=tuple(allowed_hosts),
    )


def provenance_footer(runs: Sequence[ToolRun]) -> str:
    """One line per distinct source: run, rules and trail hash as the envelope states them."""
    seen: list[str] = []
    for run in runs:
        prov = run.envelope.get("provenance") or {}
        parts = [f"run {prov['run_id']}" if prov.get("run_id") else None,
                 f"rules {prov['rule_pack_version']}" if prov.get("rule_pack_version") else None,
                 f"trail {str(prov['trail_sha256'])[:12]}" if prov.get("trail_sha256") else None,
                 str(prov["source"]) if prov.get("source") and not prov.get("run_id") else None]
        line = " · ".join(p for p in parts if p)
        if line and line not in seen:
            seen.append(line)
    return "\n".join(f"_Source: {line}_" for line in seen)
