"""The capability catalog: every tool name, what it does, and its argument schema.

Pure data, standard library only. The portal chat, the channel gateway, the
orchestrator and the tests all read this one list, so a tool cannot be renamed
in one place and still be offered under its old name in another. This file is
vendored into the orchestrator container unchanged, which is why it imports
nothing — not even a sibling module.

Two vocabularies live here and they are deliberately different:

* **Tools** (`CATALOG`) — the contract the channel exposes: `book_rank`,
  `client_situation`, … Each is a function in this package.
* **Chat intents** (`CAPABILITIES`) — what the portal's router may choose
  between: `book`, `situation`, … Each intent runs one tool (`CHAT_INTENT_TOOL`).

The router is a language model and will invent names, so an intent it names that
is not in `CAPABILITIES` is dropped, never dispatched.
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


# ------------------------------------------------------------ the portal's intents

#: Everything the chat can actually answer, and what each one costs.
#:
#: A plan is validated against these names. The router is a language model and
#: will happily invent `trend_analysis` or `client_deep_dive`; an unrecognised
#: intent is DROPPED rather than dispatched, because a made-up intent that
#: silently runs the default pipeline answers a question nobody asked.
CAPABILITIES: dict[str, str] = {
    "book": (
        "who to call ACROSS EVERY CLIENT, ranked by why — the portfolio question. "
        "Needs no client selected; naming one would be the opposite of what was asked."
    ),
    "situation": "why this client is worth calling — bands, programmes, years. Claims only.",
    "eligibility": "the credit figure and headcount for the selected client-year.",
    "at_risk": (
        "which employees ALREADY counted toward the credit sit close enough to a "
        "statutory floor that they could fall out of it — jobs the client could lose."
    ),
    "trend": "how a client has moved across years, and whether they have been eligible since their base year.",
    "multi_state": (
        "which PROGRAMMES across every state one client may qualify for — a rule-pack "
        "scan for the selected client, NOT a view across clients."
    ),
    "discovery": "other programmes the client may qualify for, excluding the one in scope.",
    "simulate": "what-if: hiring, losing, hours or wages against the statutory engine.",
    "explain": "re-narrate the cached calculation trail, step by step.",
}

#: Which intents are about ONE client, and therefore cannot be answered without
#: one selected.
#:
#: The chat used to refuse every question without a client, which made the
#: portfolio question — "who should we reach out to?" — unanswerable from the
#: title bar, where no client is selected BY DESIGN. The refusal itself is
#: right and stays: it exists so nothing silently answers against the default
#: tenant. It just belongs per capability rather than across the whole door.
NEEDS_CLIENT: frozenset[str] = frozenset({
    "situation", "eligibility", "at_risk", "trend", "multi_state",
    "discovery", "simulate", "explain",
})

#: The tool each intent runs. `multi_state` and `discovery` are one scan with
#: different exclusions, so they share a tool.
CHAT_INTENT_TOOL: dict[str, str] = {
    "book": "book_rank",
    "situation": "client_situation",
    "eligibility": "client_eligibility",
    "at_risk": "client_at_risk",
    "trend": "client_trend",
    "multi_state": "client_discovery",
    "discovery": "client_discovery",
    "simulate": "simulate",
    "explain": "calc_walkthrough",
}


# -------------------------------------------------------------------- schemas


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
    *, needs_year: bool = False,
) -> tuple[CapabilitySpec, CapabilitySpec]:
    """A write is two steps: a preview bound to the caller, then a commit.

    Declared now so the audit schema and the orchestrator know the names; built
    in a later work package, behind the mediator and a signed confirmation.
    """
    prepare = CapabilitySpec(
        name=f"{name}_prepare",
        description=f"Preview: {description} Changes nothing; returns a confirmation token.",
        kind=WRITE_PREPARE, needs_client=True, needs_year=needs_year,
        schema=_object(properties, required), implemented=False,
    )
    commit = CapabilitySpec(
        name=f"{name}_commit",
        description=f"Commit: {description} Requires the token from the preview.",
        kind=WRITE_COMMIT, needs_client=True, needs_year=needs_year,
        schema=_object(
            {"confirmation_token": {"type": "string"}, "idempotency_key": {"type": "string"}},
            ("confirmation_token", "idempotency_key"),
        ),
        implemented=False,
    )
    return prepare, commit


_WRITES: tuple[CapabilitySpec, ...] = (
    *_write_pair(
        "finding_resolve", "Record a human decision about a finding.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "finding_id": {"type": "string"},
         "resolution": {"type": "string", "enum": ["accept", "assign", "drop", "flag"]},
         "keep_worksite": {"type": "string"}, "note": {"type": "string"}},
        ("client_id", "tax_year", "finding_id", "resolution"), needs_year=True,
    ),
    *_write_pair(
        "finding_reopen", "Withdraw a decision, leaving the finding open.",
        {"client_id": _CLIENT_ID, "finding_id": {"type": "string"}},
        ("client_id", "finding_id"),
    ),
    *_write_pair(
        "claim_transition", "Move a claim cell along its lifecycle.",
        {"client_id": _CLIENT_ID, "program_code": _PROGRAM, "tax_year": _TAX_YEAR,
         "status": {"type": "string"}, "decline_reason": {"type": "string"}},
        ("client_id", "program_code", "tax_year", "status"), needs_year=True,
    ),
    *_write_pair(
        "claim_record", "Record a claim the platform did not compute.",
        {"client_id": _CLIENT_ID, "program_code": _PROGRAM, "tax_year": _TAX_YEAR,
         "status": {"type": "string"}},
        ("client_id", "program_code", "tax_year", "status"), needs_year=True,
    ),
    *_write_pair(
        "engagement_set", "Declare whether a programme is our mandate for a client.",
        {"client_id": _CLIENT_ID, "program_code": _PROGRAM,
         "scope": {"type": "string"}, "note": {"type": "string"}},
        ("client_id", "program_code", "scope"),
    ),
    *_write_pair(
        "base_year_set", "Set a location's base year.",
        {"client_id": _CLIENT_ID, "unit_id": {"type": "string"}, "base_year": _TAX_YEAR},
        ("client_id", "unit_id", "base_year"),
    ),
    *_write_pair(
        "claim_package_create", "Build the claim package for a client-year.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR},
        ("client_id", "tax_year"), needs_year=True,
    ),
)


#: Every tool, reads first. Names are the contract the orchestrator, the Cowork
#: connector and the tests share.
CATALOG: tuple[CapabilitySpec, ...] = (
    _read(
        "book_rank", "Who to call across every client, ranked by why, in the page's own order.",
        {"limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 8}},
        needs_client=False, chat_intent="book",
    ),
    _read(
        "client_resolve", "Resolve a name or a pronoun to one client, or return candidates to ask about.",
        {"name_or_text": {"type": "string"},
         "history": {"type": "array", "items": _object({"role": {"type": "string"}, "text": {"type": "string"}}, ("role", "text"))},
         "current_client_id": {"type": ["integer", "null"]}},
        ("name_or_text",), needs_client=False,
    ),
    _read(
        "client_situation", "Why this client is worth calling: bands, programmes and years, from recorded claims.",
        {"client_id": _CLIENT_ID, "year": _TAX_YEAR}, ("client_id",), chat_intent="situation",
    ),
    _read(
        "client_eligibility", "The credit figure and headcount for one client-year.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE, "method": _METHOD},
        ("client_id", "tax_year"), needs_year=True, chat_intent="eligibility",
    ),
    _read(
        "client_trend", "How a client has moved across years, and whether it has been eligible since its base year.",
        {"client_id": _CLIENT_ID}, ("client_id",), chat_intent="trend",
    ),
    _read(
        "client_at_risk", "Counted jobs close enough to a statutory floor that they could fall out of the credit.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE, "method": _METHOD},
        ("client_id", "tax_year"), needs_year=True, sensitive=True, chat_intent="at_risk",
    ),
    _read(
        "client_discovery", "Other programmes the client may qualify for, from the rule-pack library.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE},
        ("client_id",), chat_intent="discovery",
    ),
    _read(
        "simulate", "What-if at one location: add or remove headcount, or change hours or wages.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "worksite_id": {"type": "string"},
         "action": {"type": "string", "enum": list(ACTIONS), "default": "add_headcount"},
         "magnitude": {"type": "number", "default": 1}, "state": _STATE,
         "method": {"type": "string", "enum": ["min_max", "pay_period"], "default": "min_max"},
         "hire_weekly_hours": {"type": "number", "exclusiveMinimum": 0, "maximum": 80},
         "hire_hourly_rate": {"type": "number", "exclusiveMinimum": 0, "maximum": 500}},
        ("client_id", "tax_year", "worksite_id"), needs_year=True, chat_intent="simulate",
    ),
    _read(
        "calc_walkthrough", "The calculation trail for a client-year: step, inputs, formula, output, citation, SHA-256.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE, "method": _METHOD},
        ("client_id", "tax_year"), needs_year=True, chat_intent="explain",
    ),
    _read(
        "employee_drill", "One employee's derivation for a client-year, by opaque record token.",
        {"client_id": _CLIENT_ID, "record_token": _TOKEN, "tax_year": _TAX_YEAR, "state": _STATE},
        ("client_id", "record_token", "tax_year"), needs_year=True, sensitive=True,
    ),
    _read(
        "findings_list", "Open findings for a client-year that need a human decision.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE},
        ("client_id", "tax_year"), needs_year=True, sensitive=True,
    ),
    _read(
        "claim_cell_history", "One claim cell and everything that ever happened to it.",
        {"client_id": _CLIENT_ID, "program_code": _PROGRAM, "tax_year": _TAX_YEAR},
        ("client_id", "program_code", "tax_year"), needs_year=True,
    ),
    CapabilitySpec(
        name="verify_figures",
        description="Check draft text: which numerals are not in the session's tool facts.",
        kind=READ, needs_client=False, needs_year=False,
        schema=_object({"draft_text": {"type": "string"}}, ("draft_text",)),
        implemented=False,
    ),
    *_WRITES,
)

BY_NAME: dict[str, CapabilitySpec] = {spec.name: spec for spec in CATALOG}

if len(BY_NAME) != len(CATALOG):
    raise ValueError("duplicate capability name in CATALOG")


def get(name: str) -> CapabilitySpec:
    try:
        return BY_NAME[name]
    except KeyError:
        raise KeyError(f"unknown capability {name!r}") from None


def implemented() -> tuple[CapabilitySpec, ...]:
    return tuple(spec for spec in CATALOG if spec.implemented)
