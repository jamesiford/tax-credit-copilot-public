"""The shape of a capability: its spec, its kinds and the schema helpers. [CH-02]

Pure data and constructors, standard library only. Split out of `catalog`, which
re-exports every name here so `from application.capabilities.catalog import
CapabilitySpec` keeps working. Vendored into the orchestrator container.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

READ = "read"
WRITE_PREPARE = "write_prepare"
WRITE_COMMIT = "write_commit"
KINDS = (READ, WRITE_PREPARE, WRITE_COMMIT)

METHODS = ("min_max", "pay_period", "both")
ACTIONS = ("add_headcount", "remove_headcount", "adjust_hours", "adjust_wages")


@dataclass(frozen=True)
class CapabilitySpec:
    """One tool the platform offers.

    `implemented=False` declares a tool that a later work package builds. It is
    listed so the orchestrator and the audit schema already know the name, and
    the tests refuse to let an unimplemented tool be called.
    """

    name: str
    description: str
    kind: str
    needs_client: bool
    needs_year: bool
    schema: dict[str, Any]
    sensitive: bool = False
    implemented: bool = True
    chat_intent: str | None = None
    tags: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind must be one of {KINDS}, got {self.kind!r}")
        if self.schema.get("type") != "object":
            raise ValueError(f"{self.name}: schema must be a JSON-Schema object")


def _object(properties: dict[str, Any], required: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


_CLIENT_ID = {"type": "integer", "description": "The client's account id."}
_TAX_YEAR = {"type": "integer", "minimum": 1900, "maximum": 2100, "description": "Tax year, labelled per the programme's statute."}
_STATE = {"type": "string", "minLength": 2, "maxLength": 2, "default": "GA", "description": "Two-letter work state; selects the programme."}
_METHOD = {"type": "string", "enum": list(METHODS), "default": "min_max", "description": "Certified headcount method."}
_PROGRAM = {"type": "string", "description": "Programme code, e.g. GA_JTC."}
_TOKEN = {"type": "string", "minLength": 8, "maxLength": 128, "description": "Opaque employee handle. Never an employee id."}
_CLAIM_STATUSES = ["not_assessed", "assessed", "proposed", "declined", "claimed", "certified", "amended"]


def _read(
    name: str, description: str, properties: dict[str, Any], required: tuple[str, ...] = (), *,
    needs_client: bool = True, needs_year: bool = False, sensitive: bool = False,
    chat_intent: str | None = None,
) -> CapabilitySpec:
    return CapabilitySpec(
        name=name, description=description, kind=READ,
        needs_client=needs_client, needs_year=needs_year,
        schema=_object(properties, required), sensitive=sensitive, chat_intent=chat_intent,
    )


def _write_pair(
    name: str, description: str, properties: dict[str, Any], required: tuple[str, ...],
    *, needs_year: bool = False, implemented: bool = True,
) -> tuple[CapabilitySpec, CapabilitySpec]:
    """A write is two steps: a preview bound to the caller, then a commit.

    `prepare` changes nothing and returns a single-use confirmation token. `commit`
    takes that token, the SAME `arguments` and an idempotency key; the change goes
    through the mediator, behind the writer policy (`capabilities/writes.py`).
    """
    prepare = CapabilitySpec(
        name=f"{name}_prepare",
        description=f"Preview: {description} Changes nothing; returns a confirmation token.",
        kind=WRITE_PREPARE, needs_client=True, needs_year=needs_year,
        schema=_object(properties, required), implemented=implemented,
    )
    commit = CapabilitySpec(
        name=f"{name}_commit",
        description=(
            f"Commit: {description} Requires the token from the preview and the same arguments."
        ),
        kind=WRITE_COMMIT, needs_client=True, needs_year=needs_year,
        schema=_object(
            {"confirmation_token": {"type": "string"}, "idempotency_key": {"type": "string"},
             "arguments": _object(properties, required)},
            ("confirmation_token", "idempotency_key", "arguments"),
        ),
        implemented=implemented,
    )
    return prepare, commit
