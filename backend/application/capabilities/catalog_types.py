"""The shape of a capability: its spec, its kinds and the schema helpers. [CH-02]

Pure data and constructors, standard library only. Split out of `catalog`, which
re-exports every name here so `from application.capabilities.catalog import
CapabilitySpec` keeps working. Vendored into the orchestrator container.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

READ = "read"
WRITE_PREPARE = "write_prepare"
WRITE_COMMIT = "write_commit"
KINDS = (READ, WRITE_PREPARE, WRITE_COMMIT)

#: Tags that say who may name a tool. `GATEWAY_LOCAL`: the gateway answers it itself and the API never
#: does. `INTERNAL`: plumbing, offered to nobody. `CODE_ONLY`: the orchestrator's own code runs it (the
#: client resolver, a drill by opaque token); a model is never offered it. `DEBUG`: offered only while
#: the gateway's diagnostic switch is on.
GATEWAY_LOCAL = "gateway-local"
INTERNAL = "internal"
CODE_ONLY = "code-only"
DEBUG = "debug"

#: The two readings of the statute that are certified. `both` asks for each in turn: the statute has not chosen.
CERTIFIED_METHODS = ("min_max", "pay_period")
METHODS = (*CERTIFIED_METHODS, "both")
ACTIONS = ("add_headcount", "remove_headcount", "adjust_hours", "adjust_wages")

# What an argument the READER owns is, so an adapter knows how to settle it without knowing the tool.
OWNED_CLIENT = "client"  # chosen by code from the reader's words; never shown to a model
OWNED_YEAR = "year"  # the reader's year, or the conversation's current one
OWNED_EXPLICIT_YEAR = "explicit_year"  # only a year the reader wrote (a write's year, a base year)
OWNED_YEARS = "years"  # a list or range of years, the reader's
OWNED_METHOD = "method"  # a method string the model may propose and nobody else decides
OWNED_METHOD_BOTH = "method_both"  # the reader's method; unnamed means every certified method
OWNED_SIZE = "size"  # a what-if's size: asked for when the reader gave none
OWNED_SCENARIO = "scenario"  # an optional what-if input: the reader's, never the model's
#: The argument that names the conversation's tax year: a tool that ran with one moves the conversation onto it.
TAX_YEAR = "tax_year"
#: Argument name to what it is when a tool takes it. The one place these names are written down.
_OWNED_BY_NAME = {
    "client_id": OWNED_CLIENT, TAX_YEAR: OWNED_YEAR, "year": OWNED_YEAR, "base_year": OWNED_EXPLICIT_YEAR,
    "tax_years": OWNED_YEARS, "method": OWNED_METHOD, "magnitude": OWNED_SIZE,
    "hire_weekly_hours": OWNED_SCENARIO, "hire_hourly_rate": OWNED_SCENARIO,
}


@dataclass(frozen=True)
class ReaderOwned:
    """An argument of a tool whose value the reader's words (or code) decide, never a model's guess."""

    name: str
    kind: str


def owned_arguments(schema: dict[str, Any], kind: str, *, both_methods: bool = False) -> tuple[ReaderOwned, ...]:
    """The reader-owned arguments a schema carries, in schema order.

    A write's year is the reader's alone (`OWNED_EXPLICIT_YEAR`): the conversation's current year must
    never choose the year of a change. `both_methods` marks a tool whose unnamed method means every
    certified method.
    """
    found = []
    for name in schema.get("properties", {}):
        owned = _OWNED_BY_NAME.get(name)
        if owned == OWNED_YEAR and kind == WRITE_PREPARE:
            owned = OWNED_EXPLICIT_YEAR
        if owned == OWNED_METHOD and both_methods:
            owned = OWNED_METHOD_BOTH
        if owned:
            found.append(ReaderOwned(name, owned))
    return tuple(found)


@dataclass(frozen=True)
class CapabilitySpec:
    """One tool the platform offers.

    `implemented=False` declares a tool that a later work package builds. It is
    listed so the orchestrator and the audit schema already know the name, and
    the tests refuse to let an unimplemented tool be called.

    `reader_owned` says which arguments are not the model's to supply (the client, the years, the
    method, a what-if's size). It is derived from the schema when not given, so every adapter reads
    the same answer from the catalog instead of keeping its own list of argument names.
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
    reader_owned: tuple[ReaderOwned, ...] | None = None

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind must be one of {KINDS}, got {self.kind!r}")
        if self.schema.get("type") != "object":
            raise ValueError(f"{self.name}: schema must be a JSON-Schema object")
        if self.reader_owned is None:
            object.__setattr__(self, "reader_owned", owned_arguments(self.schema, self.kind))

    def owned(self, *kinds: str) -> tuple[ReaderOwned, ...]:
        """The reader-owned arguments of the given kinds (all of them when none are named)."""
        return tuple(o for o in self.reader_owned or () if not kinds or o.kind in kinds)

    def to_dict(self) -> dict[str, Any]:
        """What a caller is told about the tool: the contract, not the code behind it."""
        return {
            "name": self.name, "description": self.description, "kind": self.kind,
            "needs_client": self.needs_client, "needs_year": self.needs_year, "sensitive": self.sensitive,
            "implemented": self.implemented, "schema": self.schema, "tags": list(self.tags),
        }


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


def _marked(spec: CapabilitySpec, *tags: str, both_methods: bool = False) -> CapabilitySpec:
    """`spec` with `tags` added; `both_methods` makes an unnamed method mean every certified method."""
    owned = owned_arguments(spec.schema, spec.kind, both_methods=True) if both_methods else spec.reader_owned
    return replace(spec, tags=(*spec.tags, *tags), reader_owned=owned)


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
