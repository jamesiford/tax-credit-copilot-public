"""Run one capability by name, for a caller that is not Python. [CH-06]

The portal calls capability functions directly; the channel calls them over HTTP
as `POST /api/capabilities/{tool}`. This module is everything between "a name and
a bag of JSON" and "a `ToolResult`": look the tool up, validate its arguments
against the catalog's own schema, hand the caller's principal to the tools that
need one, and turn each way it can fail into one stable shape.

Framework-free on purpose (no FastAPI): the router only parses and shapes, and
this is what a test, a notebook or another transport would call.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from jsonschema import Draft202012Validator

from application.capabilities import catalog, registry
from application.capabilities.data_access import refuse_user_lane
from application.capabilities.envelope import ToolResult
from application.capabilities.errors import (
    Ambiguous, CapabilityError, ClaimNotFound, ClientNotFound, DataQueryRefused, InvalidArguments, NotCalculated,
    YearNotAuthored,
)
from application.confirmations import ConfirmationError
from application.identity import NotAuthorized, Principal
from config import resolve_environ

log = logging.getLogger("tcc.capabilities")

_CLIENT_KEYS = ("client_id", "account_id")

#: Each confirmation refusal is a different thing to tell a person, and a
#: different status: unknown is 404, someone else's is 403, a mismatch is 422,
#: and one that cannot be used again is 409.
_CONFIRMATION_STATUS = {
    "unknown": 404, "wrong_user": 403, "wrong_tool": 422, "wrong_args": 422,
    "expired": 409, "replayed": 409, "idempotency_conflict": 409,
}


class CapabilityFailure(Exception):
    """A capability call that did not produce a result, in the shape the wire carries."""

    def __init__(
        self, status: int, code: str, message: str, retryable: bool = False,
        extra: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message
        self.retryable, self.extra = retryable, dict(extra or {})

    def body(self) -> dict[str, Any]:
        """`{"error": {"code", "message", "retryable"}}`, plus any detail a caller can act on."""
        return {"error": {"code": self.code, "message": self.message, "retryable": self.retryable, **self.extra}}


#: Most specific first: the first match decides. A bare `ValueError` is a rejected request.
_BY_TYPE: tuple[tuple[type, int, str], ...] = (
    (NotAuthorized, 403, "not_authorized"),
    (ClientNotFound, 404, "client_not_found"),
    (ClaimNotFound, 404, "claim_not_found"),
    (NotCalculated, 409, "not_calculated"),
    (YearNotAuthored, 422, "year_not_authored"),
    (InvalidArguments, 422, "invalid_arguments"),
    (CapabilityError, 422, "capability_error"),
    (ValueError, 422, "rejected"),
)


def failure_for(exc: BaseException) -> CapabilityFailure:
    """Map what a capability can raise to its status and stable code. Nothing unknown leaks its text."""
    if isinstance(exc, CapabilityFailure):
        return exc
    if isinstance(exc, ConfirmationError):
        return CapabilityFailure(_CONFIRMATION_STATUS.get(exc.code, 422), f"confirmation_{exc.code}", str(exc))
    if isinstance(exc, Ambiguous):
        return CapabilityFailure(409, "ambiguous", str(exc), extra={"candidates": list(exc.candidates)})
    if isinstance(exc, DataQueryRefused):
        return CapabilityFailure(exc.status, exc.code, str(exc), exc.retryable, exc.extra)
    for kind, status, code in _BY_TYPE:
        if isinstance(exc, kind):
            return CapabilityFailure(status, code, str(exc) or code.replace("_", " "))
    log.exception("capability failed unexpectedly: %s", type(exc).__name__)
    return CapabilityFailure(500, "internal_error", "the capability failed unexpectedly", retryable=True)


def resolve(tool: str) -> catalog.CapabilitySpec:
    """The spec of a tool this process can run, or the refusal that says why not."""
    try:
        spec = catalog.get(tool)
    except KeyError:
        raise CapabilityFailure(404, "unknown_tool", f"no such tool: {tool}") from None
    if not spec.implemented:
        raise CapabilityFailure(501, "not_implemented", f"{tool} is declared but not built yet")
    if catalog.GATEWAY_LOCAL in spec.tags:
        raise CapabilityFailure(501, "gateway_local", f"{tool} is answered by the channel gateway, which holds the conversation")
    return spec


def merge_commit_arguments(
    spec: catalog.CapabilitySpec, args: Mapping[str, Any], *, idempotency_key: str | None, confirmation_token: str | None,
) -> dict[str, Any]:
    """A commit's schema carries its token and key; the envelope's own fields fill what `args` omits.

    Both places may name the same field only if they agree, so a request cannot
    say one thing in the body and another in the arguments.
    """
    merged = dict(args)
    if spec.kind != catalog.WRITE_COMMIT:
        return merged
    if "arguments" not in merged and not {"idempotency_key", "confirmation_token"} & merged.keys():
        merged = {"arguments": merged}  # the prepare's own arguments, with the token and key beside them
    for name, value in (("idempotency_key", idempotency_key), ("confirmation_token", confirmation_token)):
        if value is None:
            continue
        if merged.setdefault(name, value) != value:
            raise CapabilityFailure(422, "invalid_arguments", f"{name} is given twice and the two differ")
    return merged


def validate(spec: catalog.CapabilitySpec, args: Mapping[str, Any]) -> None:
    """Check `args` against the catalog's JSON-Schema; the first few problems are named."""
    errors = sorted(Draft202012Validator(spec.schema).iter_errors(dict(args)), key=lambda e: list(e.absolute_path))
    if errors:
        said = "; ".join(f"{'.'.join(str(p) for p in e.absolute_path) or 'arguments'}: {e.message}" for e in errors[:3])
        raise CapabilityFailure(422, "invalid_arguments", said)


DEFAULT_TIMEOUT_SECONDS = 25.0


def timeout_seconds(env: Mapping[str, str] | None = None) -> float:
    """`CAPABILITY_TIMEOUT_SECONDS`: how long one call may take before the caller is told so.

    A bad value raises rather than falling back, since a silent default would hide
    a typo that decides whether callers hang.
    """
    raw = (resolve_environ(env).get("CAPABILITY_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        seconds = float(raw)
    except ValueError as exc:
        raise ValueError(f"CAPABILITY_TIMEOUT_SECONDS must be a number; got {raw!r}") from exc
    if not 1 <= seconds <= 600:
        raise ValueError("CAPABILITY_TIMEOUT_SECONDS must be between 1 and 600")
    return seconds


def client_ids(args: Mapping[str, Any]) -> set[int]:
    """Every client id a request names, including inside a commit's `arguments`."""
    found: set[int] = set()
    for source in (args, args.get("arguments")):
        if isinstance(source, Mapping):
            for key in _CLIENT_KEYS:
                value = source.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    found.add(value)
    return found


def invoke(tool: str, args: Mapping[str, Any], principal: Principal) -> ToolResult:
    """Run `tool` with already-merged `args`. Raises `CapabilityFailure`, never anything else.

    Every result passes `refuse_user_lane` before it leaves: the API's own check that a caller whose model
    reads tool text is never handed employee rows, whatever the gateway in front of it did or did not do.
    """
    spec = resolve(tool)
    validate(spec, args)
    function = registry.get(tool)
    try:
        result = function(principal, **args) if tool in registry.NEEDS_PRINCIPAL else function(**args)
        refuse_user_lane(principal, result)
        return result
    except Exception as exc:  # noqa: BLE001 - every failure leaves as one typed shape
        raise failure_for(exc) from exc
