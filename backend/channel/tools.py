"""Gateway-local tools and argument checks. [CH-06]

Two tools are answered here and never by the API: `verify_figures`, because only the
gateway holds the conversation's facts, and the diagnostic `channel_ping`, which
exists to answer "who does the platform think is calling, and by which rule" during
the identity spikes. Both are DEFINED in the catalog (`catalog.CHANNEL_PING`; `channel_ping` sits
outside `CATALOG` because the API has no capability behind it) and offered only through
`catalog.offered_for_channel`, with the diagnostic only when `CHANNEL_DEBUG_WHOAMI` is on.

The catalog's schemas are the contract, so the same JSON-Schema that the API
enforces is enforced here for the local tools.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator

from application.capabilities import catalog
from channel.config import GatewaySettings

#: Defined in the catalog with the other tools; named here because the gateway answers it itself.
PING_SPEC = catalog.CHANNEL_PING


def offered_tools(settings: GatewaySettings) -> tuple[catalog.CapabilitySpec, ...]:
    """Every tool a caller may be shown: the built catalog, and the diagnostic when it is on."""
    return catalog.offered_for_channel(debug=settings.debug_whoami)


def check_arguments(spec: catalog.CapabilitySpec, args: Mapping[str, Any]) -> str | None:
    """The first few schema problems as one sentence, or None when `args` fit."""
    errors = sorted(Draft202012Validator(spec.schema).iter_errors(dict(args)), key=lambda e: list(e.absolute_path))
    if not errors:
        return None
    return "; ".join(f"{'.'.join(str(p) for p in e.absolute_path) or 'arguments'}: {e.message}" for e in errors[:3])


def client_and_year(args: Mapping[str, Any]) -> tuple[int | None, int | None]:
    """The client and tax year a call names, including inside a commit's `arguments`."""
    def pick(name: str) -> int | None:
        for source in (args, args.get("arguments")):
            value = source.get(name) if isinstance(source, Mapping) else None
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return None

    return pick("client_id"), pick("tax_year")
