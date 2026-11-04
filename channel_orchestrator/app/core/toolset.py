"""The tools a model may name, what it is shown of them, and the small types a turn's results travel in. [CH-08]

Split from `tools.py` (the turn) by size. Nothing here runs a tool: this is the catalog seen through
the orchestrator's rules, and the value types the turn, the composer and the pipeline share. Which tools
a model may name, and what of each it is shown, is the CATALOG's to say (`catalog.model_offered`,
`catalog.model_schema`); the functions here only index it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from app.core.placeholders import with_placeholders
from application.capabilities import catalog
from application.capabilities.catalog_types import OWNED_METHOD, OWNED_METHOD_BOTH
from application.capabilities.lanes import has_user_lane, is_user_block
from application.capabilities.lanes import model_facts as lane_model_facts

_YEAR = re.compile(r"\b(?:ty\s?)?((?:19|20)\d\d)\b", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\w.\-])\d+(?:\.\d+)?(?![\w])")
_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
          "eleven": 11, "twelve": 12}


def model_tools() -> dict[str, catalog.CapabilitySpec]:
    """The tools a model may name, by name."""
    return {spec.name: spec for spec in catalog.model_offered()}


def years_in(text: str) -> list[int]:
    """Every four-digit year in `text`, in order, without repeats."""
    found: list[int] = []
    for match in _YEAR.finditer(text or ""):
        year = int(match.group(1))
        if year not in found:
            found.append(year)
    return found


def numbers_in(text: str) -> set[float]:
    """The numbers the reader wrote, as digits or as the words one to twelve."""
    found = {float(m.group(0)) for m in _NUMBER.finditer(text or "")}
    found |= {float(n) for word, n in _WORDS.items() if re.search(rf"\b{word}\b", (text or "").lower())}
    return found


def offered_schema(spec: catalog.CapabilitySpec) -> dict[str, Any]:
    """The schema a model is shown, from the catalog (`catalog.model_schema`)."""
    return catalog.model_schema(spec)


def method_argument(spec: catalog.CapabilitySpec) -> str | None:
    """The name of the argument that carries the certified method, as the catalog marks it (None when there is none)."""
    return next((o.name for o in spec.owned(OWNED_METHOD, OWNED_METHOD_BOTH)), None)


def refusal(code: str, message: str) -> dict[str, Any]:
    """What a model is told when a call did not run: a stable code and one sentence, never a value."""
    return {"ok": False, "error": code, "message": message}


def needs_reader(clarify: Clarification | None) -> dict[str, Any]:
    """The model's answer when the reader must say something first (a client, a year, a size): stop and wait."""
    what = clarify.kind if clarify else "client"
    return refusal("needs_" + what, f"the reader must say which {what} (or how much); stop and wait")


def first_schema_problem(spec: catalog.CapabilitySpec, args: dict[str, Any]) -> str | None:
    """The first few schema problems as one sentence, or None when `args` fit the catalog's own schema."""
    errors = sorted(Draft202012Validator(spec.schema).iter_errors(args), key=lambda e: list(e.absolute_path))
    if not errors:
        return None
    return "; ".join(f"{'.'.join(str(p) for p in e.absolute_path) or 'arguments'}: {e.message}" for e in errors[:3])


@dataclass(frozen=True)
class ToolRun:
    """One tool that ran and answered: its name, the arguments used, the gateway's envelope and its label.

    The `label` namespaces the run's facts in the composed reply (`client_eligibility_min_max`),
    so the same tool run under two methods never collides on a path.
    """

    name: str
    args: dict[str, Any]
    envelope: dict[str, Any]
    label: str = ""

    @property
    def facts(self) -> dict[str, Any]:
        """The envelope's facts without the confirmation token, which only the owner's `confirm` may use."""
        return {k: v for k, v in (self.envelope.get("facts") or {}).items() if k != "confirmation"}

    @property
    def model_facts(self) -> dict[str, Any]:
        """What a MODEL may be shown of this run: `facts` less the person-only lane (employee-level rows).

        The reader's reply is composed from `facts` and the blocks; only this projection may reach a
        prompt, a tool result handed to a model, or anything else a model reads [ADR-009].
        """
        return {k: v for k, v in lane_model_facts(self.envelope).items() if k != "confirmation"}


def model_answer(spec: catalog.CapabilitySpec, run: ToolRun, brief: dict[str, Any]) -> dict[str, Any]:
    """The reply a model gets for one tool: the NAMES of the facts, never their values.

    One exception, by declaration: a `lookup` tool (`data_catalog`, `data_distinct_values`) describes the
    shape of the data, never its content, and the model cannot write a valid query without reading it, so it
    is handed the facts themselves (still through the lane projection) and only the numeric paths.
    """
    paths = with_placeholders(brief["fact_paths"])
    if catalog.LOOKUP not in spec.tags:
        return {"ok": True, "tool": spec.name, "fact_paths": paths, "notes": brief["notes"]}
    numeric = [p for p in paths if p.get("format") != "text"]
    return {"ok": True, "tool": spec.name, "fact_paths": numeric, "notes": brief["notes"], "result": run.model_facts}


def lane_diagnostic(run: ToolRun, answer: dict[str, Any]) -> str:
    """One log line about what a model was just handed for `run`: NAMES and COUNTS only, never a value.

    It exists so a live run can show, without reading a row, that a result carrying a person-only lane
    reached the model as column names and a count: how many blocks and fact keys were withheld, which
    keys the model's answer holds, and whether any `rows` list crossed.
    """
    envelope = run.envelope
    blocks = envelope.get("blocks") or ()
    hidden = [b for b in blocks if is_user_block(b)]
    facts = answer.get("result") if isinstance(answer.get("result"), dict) else {}
    return (
        f"tool={run.name} user_lane={'yes' if has_user_lane(envelope) else 'no'} "
        f"user_blocks_withheld={len(hidden)} user_only_fact_keys_withheld={len(envelope.get('user_only_facts') or ())} "
        f"answer_keys={','.join(sorted(answer))} fact_paths={len(answer.get('fact_paths') or ())} "
        f"rows_in_answer={'yes' if 'rows' in facts else 'no'}"
    )


@dataclass(frozen=True)
class Clarification:
    """What the reader must say before anything can run. `candidates` are numbered in the reply."""

    kind: str
    reason: str = ""
    candidates: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class Problem:
    """A tool that did not answer, in words that are safe to show."""

    tool: str
    code: str
    message: str
