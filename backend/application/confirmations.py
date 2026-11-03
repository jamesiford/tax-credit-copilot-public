"""Prepare/commit: the only way a channel write happens. [CH-05, ADR-008]

A write through the channel is two steps. **Prepare** checks the request, shows
what would change and mints a single-use token bound to the person, the tool and
the exact arguments; nothing is written. **Commit** presents the token, the same
arguments and an idempotency key; the change is made once.

Why a token at all: the person agreeing in chat is agreeing to what they were
shown. A token that names a different person, a different tool or different
arguments is refused, so a confirmation cannot be reused for something else.

- Only the token's SHA-256 is stored; the token itself exists in the prepare
  reply and nowhere else.
- Single use. `consume` is an atomic compare-and-set; of two concurrent commits
  exactly one proceeds.
- A retry with the same idempotency key replays the first outcome and writes
  nothing, so a dropped reply is safe to repeat.
- Every refusal is a distinct, named error: "expired" and "somebody else's" are
  different things to tell a person.
- If the process dies after consuming a token and before recording the result,
  a retry is REFUSED as replayed rather than risking a second write; the audit
  trail's `pending` row is what a human reads to settle it. A change that failed
  after the token was consumed also needs a fresh prepare.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from application.capabilities.envelope import json_safe
from application.channel_audit import request_sha256
from application.identity import NotAuthorized, Principal
from domain.channel import Confirmation, ConfirmationRepository, utcnow


class ConfirmationError(Exception):
    """A confirmation cannot be used. `code` says why, for a caller to act on."""

    code = "invalid"


class UnknownConfirmation(ConfirmationError):
    """No such token: never issued, or issued by another instance."""

    code = "unknown"


class ExpiredConfirmation(ConfirmationError):
    """The token's time ran out before it was committed."""

    code = "expired"


class ReplayedConfirmation(ConfirmationError):
    """The token was already used; a token commits at most once."""

    code = "replayed"


class WrongUser(ConfirmationError):
    """The person committing is not the person who previewed."""

    code = "wrong_user"


class WrongTool(ConfirmationError):
    """The commit names a different tool than the preview did."""

    code = "wrong_tool"


class ArgumentsChanged(ConfirmationError):
    """The commit's arguments differ from the previewed ones: what was agreed is not what lands."""

    code = "wrong_args"


class IdempotencyConflict(ConfirmationError):
    """The idempotency key was already used for a different request."""

    code = "idempotency_conflict"


@dataclass(frozen=True)
class Prepared:
    """A preview that was recorded: the id to look it up and the single-use token to commit it."""

    confirmation_id: str
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class Committed:
    """The outcome of a commit; `replayed` is True when an idempotent retry returned the first result."""

    result: dict[str, Any]
    replayed: bool
    confirmation_id: str = ""


def token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ConfirmationService:
    """Prepare and commit a write: the preview a person agrees to is the row that lands."""

    def __init__(
        self, repository: ConfirmationRepository, authorize: Callable[[Principal], None],
        *, ttl_seconds: int = 600, clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self._repo, self._authorize, self._ttl, self._clock = repository, authorize, ttl_seconds, clock

    @staticmethod
    def _person(principal: Principal) -> str:
        oid = principal.effective_oid
        if not oid:
            raise NotAuthorized("a confirmation needs a named user")
        return oid

    def authorize(self, principal: Principal) -> None:
        """Refuse a person who may not write, before anything is read or minted."""
        self._person(principal)
        self._authorize(principal)

    def prepare(self, tool: str, principal: Principal, args: Mapping[str, Any]) -> Prepared:
        """Mint a token for `tool` over `args`. Call only after the preview succeeded."""
        oid = self._person(principal)
        self._authorize(principal)
        now, token = self._clock(), secrets.token_urlsafe(32)
        confirmation = Confirmation(
            confirmation_id=uuid.uuid4().hex, token_sha256=token_sha256(token), user_oid=oid,
            tool_name=tool, args_sha256=request_sha256(args), created_at=now,
            expires_at=now + timedelta(seconds=self._ttl),
        )
        self._repo.create(confirmation)
        return Prepared(confirmation.confirmation_id, token, confirmation.expires_at)

    def commit(
        self, tool: str, principal: Principal, args: Mapping[str, Any], token: str,
        idempotency_key: str, run: Callable[[], dict[str, Any]],
    ) -> Committed:
        """Run `run()` once for a valid token, or replay the first outcome."""
        oid = self._person(principal)
        if not idempotency_key or not idempotency_key.strip():
            raise ValueError("an idempotency key is required")
        confirmation = self._repo.find_by_token_hash(token_sha256(token or ""))
        if confirmation is None:
            raise UnknownConfirmation("that confirmation is not recognised")
        self._check_binding(confirmation, oid, tool, args)
        replay = self._replay(confirmation, oid, idempotency_key)
        if replay is not None:
            return replay
        if confirmation.consumed_at is not None:
            raise ReplayedConfirmation("that confirmation has already been used")
        if confirmation.is_expired(self._clock()):
            raise ExpiredConfirmation("that confirmation has expired; prepare the change again")
        self._authorize(principal)
        if not self._repo.consume(confirmation.confirmation_id, self._clock(), idempotency_key):
            raise ReplayedConfirmation("that confirmation has already been used")
        return self._run(confirmation, run)

    @staticmethod
    def _check_binding(c: Confirmation, oid: str, tool: str, args: Mapping[str, Any]) -> None:
        if c.user_oid != oid:
            raise WrongUser("that confirmation belongs to another user")
        if c.tool_name != tool:
            raise WrongTool("that confirmation was issued for a different change")
        if c.args_sha256 != request_sha256(args):
            raise ArgumentsChanged("the change differs from the one that was confirmed")

    def _replay(self, c: Confirmation, oid: str, key: str) -> Committed | None:
        """The first outcome, when this key already committed this confirmation."""
        earlier = self._repo.find_by_idempotency_key(oid, key)
        if earlier is None:
            return None
        if earlier.confirmation_id != c.confirmation_id:
            raise IdempotencyConflict("that idempotency key was used for a different change")
        if earlier.outcome == "ok" and earlier.result_json:
            return Committed(json.loads(earlier.result_json), True, c.confirmation_id)
        raise ReplayedConfirmation("that confirmation was used and the change did not complete; prepare it again")

    def _run(self, c: Confirmation, run: Callable[[], dict[str, Any]]) -> Committed:
        try:
            result = json_safe(run())
        except Exception as exc:
            self._repo.record_result(c.confirmation_id, "error", f"{type(exc).__name__}: {exc}"[:500])
            raise
        self._repo.record_result(c.confirmation_id, "ok", json.dumps(result, sort_keys=True))
        return Committed(result, False, c.confirmation_id)
