"""The tools a model may name, what it is shown of them, and the small types a turn's results travel in. [CH-08]

Split from `tools.py` (the runner) by size. Nothing here runs a tool: this is the catalog seen through
the orchestrator's rules, and the value types the runner, the composer and the pipeline share.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator

from application.capabilities import catalog

_YEAR = re.compile(r"\b(?:ty\s?)?((?:19|20)\d\d)\b", re.IGNORECASE)
_NOT_FOR_MODELS = frozenset({"client_resolve", "employee_drill"})
CLIENT_PLACEHOLDER = "client_id"


def model_tools() -> dict[str, catalog.CapabilitySpec]:
    """The tools a model may name: built reads and previews, never a commit, never plumbing."""
    return {
        spec.name: spec for spec in catalog.offered()
        if spec.kind != catalog.WRITE_COMMIT and not {catalog.GATEWAY_LOCAL, catalog.INTERNAL} & set(spec.tags)
        and spec.name not in _NOT_FOR_MODELS
    }


def years_in(text: str) -> list[int]:
    """Every four-digit year in `text`, in order, without repeats."""
    found: list[int] = []
    for match in _YEAR.finditer(text or ""):
        year = int(match.group(1))
        if year not in found:
            found.append(year)
    return found


def offered_schema(spec: catalog.CapabilitySpec) -> dict[str, Any]:
    """The schema a model is shown: the client and the year are not the model's to supply.

    The client is written in by the runner; a year is used only if the reader said it. Neither is
    `required` here, so a call that omits them reaches the runner, which asks the reader, rather
    than being bounced back to the model to guess. Extra properties are tolerated at this door and
    judged by the runner against the catalog's own strict schema, so a client id the model invents
    reaches the one place that overwrites it.
    """
    schema = {**spec.schema, "properties": {k: v for k, v in spec.schema["properties"].items() if k != CLIENT_PLACEHOLDER}}
    schema["required"] = [name for name in spec.schema.get("required", []) if name not in (CLIENT_PLACEHOLDER, "tax_year", "year")]
    schema["additionalProperties"] = True
    return schema


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
