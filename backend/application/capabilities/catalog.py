"""The capability catalog: every tool name, what it does, and its argument schema.

Pure data, standard library only. The portal chat, the channel gateway, the
orchestrator and the tests all read this one list, so a tool cannot be renamed
in one place and still be offered under its old name in another. It is vendored
into the orchestrator container with its siblings.

Two vocabularies live here and they are deliberately different:

* **Tools** (`CATALOG`) — the contract the channel exposes: `book_rank`,
  `client_situation`, … Each is a function in this package.
* **Chat intents** (`CAPABILITIES`) — what the portal's router may choose
  between: `book`, `situation`, … Each intent runs one tool (`CHAT_INTENT_TOOL`).

The router is a language model and will invent names, so an intent it names that
is not in `CAPABILITIES` is dropped, never dispatched.

**Where the pieces live.** The list is here. The spec type and schema helpers are in
`catalog_types`, the chat intents in `catalog_intents`; both were split out by size
and are re-exported below, so every import of `application.capabilities.catalog` is
unchanged.
"""
from __future__ import annotations

from application.capabilities.catalog_data import DATA_TOOLS, LOOKUP  # noqa: F401 - re-exported
from application.capabilities.catalog_intents import CAPABILITIES, CHAT_INTENT_TOOL, NEEDS_CLIENT  # noqa: F401
from application.capabilities.catalog_types import (  # noqa: F401 - re-exported
    ACTIONS, KINDS, METHODS, READ, WRITE_COMMIT, WRITE_PREPARE, CapabilitySpec, _CLAIM_STATUSES,
    _CLIENT_ID, _METHOD, _PROGRAM, _STATE, _TAX_YEAR, _TOKEN, _object, _read, _write_pair,
)

_WRITES: tuple[CapabilitySpec, ...] = (
    *_write_pair(
        "finding_resolve", "Record a human decision about a finding.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "finding_id": {"type": "string"},
         "resolution": {"type": "string", "enum": ["accept", "assign", "drop", "flag"]},
         "keep_worksite": {"type": "string", "description": "Required for `assign`: the unit that keeps the employee."},
         "note": {"type": "string"}},
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
         "status": {"type": "string", "enum": _CLAIM_STATUSES}, "decline_reason": {"type": "string"}},
        ("client_id", "program_code", "tax_year", "status"), needs_year=True,
    ),
    *_write_pair(
        "claim_record", "Record a claim the platform did not compute (recorded as an unverified client assertion).",
        {"client_id": _CLIENT_ID, "program_code": _PROGRAM, "tax_year": _TAX_YEAR,
         "status": {"type": "string", "enum": _CLAIM_STATUSES}},
        ("client_id", "program_code", "tax_year", "status"), needs_year=True,
    ),
    *_write_pair(
        "engagement_set", "Declare whether a programme is our mandate for a client.",
        {"client_id": _CLIENT_ID, "program_code": _PROGRAM,
         "scope": {"type": "string", "enum": ["in_scope", "out_of_scope", "prospective"]},
         "note": {"type": "string"}},
        ("client_id", "program_code", "scope"),
    ),
    *_write_pair(
        "base_year_set", "Set a location's base year and recalculate the client from it.",
        {"client_id": _CLIENT_ID, "unit_id": {"type": "string"}, "base_year": _TAX_YEAR},
        ("client_id", "unit_id", "base_year"),
    ),
    *_write_pair(
        "claim_package_create", "Build the claim package for a client-year.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR},
        ("client_id", "tax_year"), needs_year=True,
    ),
)

#: Tools the API never answers by name over the wire to a channel caller; the
#: gateway holds what they need (the conversation's facts) or they are plumbing.
GATEWAY_LOCAL = "gateway-local"
INTERNAL = "internal"

_PACKAGE_TOOLS: tuple[CapabilitySpec, ...] = (
    CapabilitySpec(
        name="claim_package_link",
        description=(
            "A short-lived, single-use download link for a client-year's claim package, bound to "
            "the person who asked. Build the package first with claim_package_create."
        ),
        kind=READ, needs_client=True, needs_year=True,
        schema=_object({"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR}, ("client_id", "tax_year")),
    ),
    CapabilitySpec(
        name="claim_package_redeem",
        description="Plumbing for the gateway's download route: spend a link ticket. Not offered to callers.",
        kind=READ, needs_client=False, needs_year=False, tags=(INTERNAL,),
        schema=_object(
            {"ticket": {"type": "string", "minLength": 16, "maxLength": 128},
             "expected_user_oid": {"type": "string", "maxLength": 64,
                                   "description": "Set when the downloader proved who they are; checked before the ticket is spent."}},
            ("ticket",),
        ),
    ),
)


#: Every tool, reads first. Names are the contract the orchestrator, the Cowork
#: connector and the tests share.
CATALOG: tuple[CapabilitySpec, ...] = (
    _read(
        "book_rank", "WHOLE BOOK only: which clients to call across every client, ranked by a named reason, in the page's own order. Needs no client. Never use it for a question about one client (a client named, or \"them\" or \"this client\"): use that client's tools.",
        {"limit": {"type": "integer", "minimum": 1, "maximum": 25, "default": 8}},
        needs_client=False, chat_intent="book",
    ),
    _read(
        "client_resolve", "Resolve a name or a pronoun to one client (resolved=true) or return candidates to ask about. One exact name resolves; never guess.",
        {"name_or_text": {"type": "string"},
         "history": {"type": "array", "items": _object({"role": {"type": "string"}, "text": {"type": "string"}}, ("role", "text"))},
         "current_client_id": {"type": ["integer", "null"]}},
        ("name_or_text",), needs_client=False,
    ),
    _read(
        "client_situation", "ONE client (needs a client): a brief on why it is worth calling: reasons, programmes and years, from recorded claims. Use for \"brief me on X\", \"why call them\".",
        {"client_id": _CLIENT_ID, "year": _TAX_YEAR}, ("client_id",), chat_intent="situation",
    ),
    _read(
        "client_eligibility", "ONE client (needs a client): the credit figure and headcount for one client-year.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE, "method": _METHOD},
        ("client_id", "tax_year"), needs_year=True, chat_intent="eligibility",
    ),
    _read(
        "client_trend", "ONE client (needs a client): how it has moved across years, and whether it has been eligible since its base year.",
        {"client_id": _CLIENT_ID}, ("client_id",), chat_intent="trend",
    ),
    _read(
        "client_at_risk", "ONE client (needs a client): counted jobs close enough to a statutory floor that they could fall out of the credit.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE, "method": _METHOD},
        ("client_id", "tax_year"), needs_year=True, sensitive=True, chat_intent="at_risk",
    ),
    _read(
        "client_discovery", "ONE client (needs a client): other programmes it may qualify for, from the rule-pack library.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE},
        ("client_id",), chat_intent="discovery",
    ),
    _read(
        "simulate", "ONE client (needs a client): what-if at one location: add or remove headcount, or change hours or wages.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "worksite_id": {"type": "string"},
         "action": {"type": "string", "enum": list(ACTIONS), "default": "add_headcount"},
         "magnitude": {"type": "number", "default": 1}, "state": _STATE,
         "method": {"type": "string", "enum": ["min_max", "pay_period"], "default": "min_max"},
         "hire_weekly_hours": {"type": "number", "exclusiveMinimum": 0, "maximum": 80},
         "hire_hourly_rate": {"type": "number", "exclusiveMinimum": 0, "maximum": 500}},
        ("client_id", "tax_year", "worksite_id"), needs_year=True, chat_intent="simulate",
    ),
    _read(
        "calc_walkthrough", "ONE client (needs a client): the calculation trail for a client-year: step, inputs, formula, output, citation, SHA-256.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE, "method": _METHOD},
        ("client_id", "tax_year"), needs_year=True, chat_intent="explain",
    ),
    _read(
        "employee_drill", "One employee's derivation for a client-year, by opaque record token.",
        {"client_id": _CLIENT_ID, "record_token": _TOKEN, "tax_year": _TAX_YEAR, "state": _STATE},
        ("client_id", "record_token", "tax_year"), needs_year=True, sensitive=True,
    ),
    _read(
        "findings_list", "ONE client (needs a client): open findings for a client-year that need a human decision.",
        {"client_id": _CLIENT_ID, "tax_year": _TAX_YEAR, "state": _STATE},
        ("client_id", "tax_year"), needs_year=True, sensitive=True,
    ),
    _read(
        "claim_cell_history", "ONE client (needs a client): one claim cell and everything that ever happened to it.",
        {"client_id": _CLIENT_ID, "program_code": _PROGRAM, "tax_year": _TAX_YEAR},
        ("client_id", "program_code", "tax_year"), needs_year=True,
    ),
    *DATA_TOOLS,
    CapabilitySpec(
        name="verify_figures",
        description=(
            "Check draft text: which numerals are not in this conversation's tool facts. "
            "Pass the reader's own numerals as allowed_context."
        ),
        kind=READ, needs_client=False, needs_year=False, tags=(GATEWAY_LOCAL,),
        schema=_object(
            {"draft_text": {"type": "string", "maxLength": 20000},
             "allowed_context": {"type": "array", "items": {"type": "string", "maxLength": 500}, "maxItems": 50}},
            ("draft_text",),
        ),
    ),
    *_PACKAGE_TOOLS,
    *_WRITES,
)

BY_NAME: dict[str, CapabilitySpec] = {spec.name: spec for spec in CATALOG}

if len(BY_NAME) != len(CATALOG):
    raise ValueError("duplicate capability name in CATALOG")


def get(name: str) -> CapabilitySpec:
    """The spec for `name`, or a `KeyError` naming it."""
    try:
        return BY_NAME[name]
    except KeyError:
        raise KeyError(f"unknown capability {name!r}") from None


def implemented() -> tuple[CapabilitySpec, ...]:
    """Every capability that is built, in catalog order."""
    return tuple(spec for spec in CATALOG if spec.implemented)


def offered() -> tuple[CapabilitySpec, ...]:
    """What a channel caller may be shown: built, and not plumbing."""
    return tuple(spec for spec in implemented() if INTERNAL not in spec.tags)


def offered_or_declared() -> tuple[CapabilitySpec, ...]:
    """Everything but plumbing, built or not, so a caller sees what is coming and `implemented` says what is here."""
    return tuple(spec for spec in CATALOG if INTERNAL not in spec.tags)
