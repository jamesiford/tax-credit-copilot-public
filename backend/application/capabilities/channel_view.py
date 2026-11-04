"""How the catalog presents a tool to a channel: words, hints and the schema a model is shown. [RM-07]

Every adapter (the MAF tools in the orchestrator, the MCP facade, the portal) builds its tool list from
these functions rather than from a literal of its own, so a description or a schema cannot be edited in
one surface and stay unchanged in another. Pure data in, pure data out, standard library only; vendored
into the orchestrator with the catalog.
"""
from __future__ import annotations

from typing import Any

from application.capabilities.catalog_types import (
    DEBUG, GATEWAY_LOCAL, OWNED_CLIENT, READ, WRITE_COMMIT, WRITE_PREPARE, CapabilitySpec, _object,
)

#: Tools the gateway answers itself and offers only on request. They are not in `CATALOG` (the API has no
#: capability behind them and the portal never lists them), but they are defined HERE, with the rest of
#: the catalog's words, so a channel's tool list has one source.
CHANNEL_PING = CapabilitySpec(
    name="channel_ping",
    description="Diagnostics: the gateway's version, who it believes is calling and by which rule, and whether the API answers.",
    kind=READ, needs_client=False, needs_year=False, tags=(GATEWAY_LOCAL, DEBUG),
    schema=_object({}),
)
DIAGNOSTICS: tuple[CapabilitySpec, ...] = (CHANNEL_PING,)

PREVIEW_SENTENCE = (
    "Returns a preview — nothing is changed until the matching commit tool is called with the "
    "returned token after the user confirms."
)
COMMIT_SENTENCE = "Call only after the user has confirmed the preview from the matching prepare tool."


def channel_description(spec: CapabilitySpec) -> str:
    """What a channel that offers BOTH halves of a write says: the preview changes nothing, the commit follows a confirmation."""
    if spec.kind == WRITE_PREPARE:
        return f"{spec.description} {PREVIEW_SENTENCE}"
    if spec.kind == WRITE_COMMIT:
        return f"{spec.description} {COMMIT_SENTENCE}"
    return spec.description


def behaviour_hints(spec: CapabilitySpec) -> dict[str, bool]:
    """MCP-style behaviour annotations, derived from the tool's kind alone."""
    read = spec.kind == READ
    return {"readOnlyHint": read, "destructiveHint": spec.kind == WRITE_COMMIT, "idempotentHint": read, "openWorldHint": False}


def model_schema(spec: CapabilitySpec) -> dict[str, Any]:
    """The schema a MODEL is shown: the catalog's, less what the reader owns.

    The client is written in by code, so it is not offered at all. A year, a method or a what-if size
    is the reader's: it stays visible (a model may propose one) but is never `required`, so a call
    that omits it reaches the rules, which ask the reader instead of bouncing back to the model to
    guess. Extra properties are tolerated at this door and judged against the catalog's own strict
    schema (`spec.schema`) by the schema check, after the overrides have been written in.
    """
    hidden = {o.name for o in spec.owned(OWNED_CLIENT)}
    owned = {o.name for o in spec.owned()}
    shown = {**spec.schema, "properties": {k: v for k, v in spec.schema["properties"].items() if k not in hidden}}
    shown["required"] = [name for name in spec.schema.get("required", []) if name not in owned]
    shown["additionalProperties"] = True
    return shown
