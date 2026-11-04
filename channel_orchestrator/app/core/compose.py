"""Turning tool results and a model's sentence into the reply, and nothing else. [CH-08]

Everything a reader sees that carries a figure is the platform's own rendering of the engine's
facts. This module gathers the pieces; `composer.compose` (vendored from the platform,
unchanged) decides what survives:

- the model's narration may hold only `{{facts.path|format}}` placeholders; a digit it typed,
  a figure it rewrote, a path that does not exist, a path the model was never shown (the person's
  lane, or rows past the model's cut) or a link it invented drops the narration
  and the reader gets the platform's blocks and the disclaimer;
- the finished reply is checked a second time against the facts.

The provenance footer is appended AFTER the composer, from the envelopes' own provenance
fields, verbatim: a run id, a rule-pack path and a trail hash are identifiers, not figures,
and no model touches them.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from app.core.tools import ToolRun
from application.capabilities import catalog
from application.capabilities.envelope import AUDIENCE_USER, AUDIENCES, Block
from application.composer import Composed, compose, placeholders
from application.numeric_guard import REJECTED, AllowedContext, FactIndex, GuardResult, Numeral, Violation

METHOD_LABEL = {"min_max": "Min-Max method", "pay_period": "Pay Period method"}
#: What the audit records, as a code: never the path, which names the person's lane.
OUTSIDE_VIEW = "narration named a fact outside the model's view"
LOOKUP_TOOLS = frozenset(spec.name for spec in catalog.CATALOG if catalog.LOOKUP in spec.tags)
_YEAR_KEYS = ("tax_year", "year")


def facts_of(runs: Sequence[ToolRun]) -> dict[str, Any]:
    """Every run's facts under its own label, so the same tool under two methods never shares a path.

    These are the reader's: the composer checks the finished reply against them. A model is never
    handed this; it gets `model_facts_of`.
    """
    return {run.label: run.facts for run in runs}


def model_facts_of(runs: Sequence[ToolRun]) -> dict[str, Any]:
    """The same, as a model may see them: the person-only lane (employee-level rows) removed [ADR-009]."""
    return {run.label: run.model_facts for run in runs}


def blocks_of(runs: Sequence[ToolRun]) -> list[Block]:
    """The platform's blocks in call order, each run led by its method when it has one.

    A `lookup` run (the catalog, a list of distinct values) is plumbing for the model's next call; its
    blocks are left out of the reply when something else answered, and shown when it IS the answer.
    """
    answering = [run for run in runs if run.name not in LOOKUP_TOOLS] or list(runs)
    blocks: list[Block] = []
    for run in answering:
        method = run.args.get("method")
        if method in METHOD_LABEL:
            blocks.append(Block("heading", text=METHOD_LABEL[method]))
        for raw in run.envelope.get("blocks") or []:
            audience = raw.get("audience", "both")
            blocks.append(Block(
                raw["kind"], raw.get("text", ""), tuple(tuple(row) for row in raw.get("rows") or ()),
                audience if audience in AUDIENCES else AUDIENCE_USER,
            ))
    return blocks


def allowed_for(question: str, runs: Sequence[ToolRun]) -> AllowedContext:
    """What the reader supplied: their own words, plus the tax years and client the answer is scoped to."""
    years = {run.args[k] for run in runs for k in _YEAR_KEYS if isinstance(run.args.get(k), int)}
    clients = {run.args["client_id"] for run in runs if isinstance(run.args.get("client_id"), int)}
    return AllowedContext.build(question, years=sorted(years), numbers=sorted(clients))


def paths_outside_model_view(narration: str | None, runs: Sequence[ToolRun]) -> list[str]:
    """Placeholder paths in `narration` that are the reader's facts but not what a model may see.

    A narrator is only ever told the NAMES of `model_facts_of`; the person's lane (employee-level rows)
    and the rows past `MODEL_ROW_LIMIT` are not among them. A placeholder pointing there is a path the
    model guessed, so it is not a figure the engine vouched for to the narrator, whatever it would render.
    """
    found = placeholders(narration) if narration else []
    if not found:
        return []
    shown = FactIndex.coerce(model_facts_of(runs)).leaves
    held = FactIndex.coerce(facts_of(runs)).leaves
    return [m.group(1) for m in found if m.group(1) in held and m.group(1) not in shown]


def compose_reply(question: str, runs: Sequence[ToolRun], narration: str | None, allowed_hosts: Sequence[str] = ()) -> Composed:
    """The composed reply for these results; `narration` None gives the platform's blocks alone.

    The narration is dropped whole, and the guard says so, if it names a fact outside the model's view.
    """
    outside = paths_outside_model_view(narration, runs)
    composed = compose(
        blocks_of(runs), None if outside else narration, facts_of(runs), allowed_for(question, runs),
        allowed_hosts=tuple(allowed_hosts),
    )
    if not outside:
        return composed
    violation = Violation(Numeral(OUTSIDE_VIEW, 0, 0, "placeholder"), OUTSIDE_VIEW, stage="narration")
    return replace(composed, guard=GuardResult(REJECTED, (violation, *composed.guard.violations)))


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
