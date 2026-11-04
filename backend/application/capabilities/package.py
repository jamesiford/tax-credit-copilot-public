"""A claim package, handed over by a ticket instead of a storage URL. [CH-06, BLOB-4]

`claim_package_link` mints a short-lived, single-use ticket for one person and one
artifact and returns the gateway path it is redeemed at. `claim_package_redeem`
spends it. The browser (a Teams card opens the link in one) therefore never sees a
storage address or a SAS: it holds a capability that works once, for a quarter of
an hour, and the bytes are streamed through the artifact service as before.

Tickets live in the confirmation store (`tcc_ops.channel_confirmation`) because it
already is "a secret handed out once, kept only as a hash, spent atomically", and
it is durable, so a gateway restart does not strand a link. The row's `result_json`
carries the context the redeeming side needs and nothing sensitive: which artifact
and which conversation the person was in.
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import timedelta
from typing import Any

from application.capabilities import _support as s
from application.capabilities.envelope import Provenance, ToolResult
from application.capabilities.errors import NotCalculated
from application.channel_audit import request_sha256
from application.claim_package_service import latest_package
from application.confirmations import (
    ConfirmationError, ExpiredConfirmation, ReplayedConfirmation, UnknownConfirmation, WrongUser, token_sha256,
)
from application.identity import NotAuthorized, Principal
from domain.channel import Confirmation, utcnow

TICKET_TOOL = "claim_package_download"
TICKET_MINUTES = 15
#: Where a ticket is redeemed. The gateway serves it; the API only names it.
GATEWAY_DOWNLOAD_PATH = "/channel/v1/downloads/{ticket}"


def _repository() -> Any:
    from application.services import get_confirmation_repository

    return get_confirmation_repository()


def _context(principal: Principal, client_id: int, artifact_id: str) -> dict[str, Any]:
    acting = principal.as_acting_user()
    return {
        "client_id": client_id, "artifact_id": artifact_id,
        "name": acting.display_name if acting else None,
        "channel": acting.channel if acting else None,
        "conversation_id": acting.conversation_id if acting else None,
        "assurance": acting.assurance if acting else None,
    }


def claim_package_link(principal: Principal, client_id: int, tax_year: int) -> ToolResult:
    """A single-use link to the newest package for the client-year, bound to the asker."""
    oid = principal.effective_oid
    if not oid:
        raise NotAuthorized("a download link needs a named user")
    artifact = latest_package(client_id, tax_year)
    if artifact is None:
        raise NotCalculated(
            f"no claim package has been built for client {client_id}, tax year {tax_year}; "
            "build it with claim_package_create first"
        )
    ticket, now = secrets.token_urlsafe(32), utcnow()
    ticket_row = Confirmation(
        confirmation_id=uuid.uuid4().hex, token_sha256=token_sha256(ticket), user_oid=oid,
        tool_name=TICKET_TOOL, args_sha256=request_sha256({"client_id": client_id, "artifact_id": artifact.artifact_id}),
        created_at=now, expires_at=now + timedelta(minutes=TICKET_MINUTES),
    )
    _repository().create(ticket_row)
    _repository().record_result(
        ticket_row.confirmation_id, "issued", json.dumps(_context(principal, client_id, artifact.artifact_id)),
    )
    facts = {
        "client_id": client_id, "tax_year": tax_year, "file_name": artifact.file_name,
        "sha256": artifact.sha256, "size_bytes": artifact.size_bytes,
        "download_path": GATEWAY_DOWNLOAD_PATH.format(ticket=ticket),
        "expires_at": ticket_row.expires_at.isoformat(), "ticket_minutes": TICKET_MINUTES, "single_use": True,
    }
    blocks = [
        s.heading("Claim package download"),
        s.table(("File", "SHA-256"), [(artifact.file_name, artifact.sha256)]),
        s.callout(f"The link works once, for you only, for {TICKET_MINUTES} minutes."),
    ]
    return s.result(
        "claim_package_link", facts, blocks, provenance=Provenance(run_id=artifact.run_id, source="artifact store"),
    )


def _open_ticket(ticket: str, expected_user_oid: str | None) -> Confirmation:
    """The live ticket row, or the named reason it cannot be used. Spends nothing."""
    row = _repository().find_by_token_hash(token_sha256(ticket or ""))
    if row is None or row.tool_name != TICKET_TOOL:
        raise UnknownConfirmation("that download link is not recognised")
    if expected_user_oid and row.user_oid.lower() != expected_user_oid.lower():
        raise WrongUser("that download link belongs to another user")
    if row.consumed_at is not None:
        raise ReplayedConfirmation("that download link has already been used")
    if row.is_expired(utcnow()):
        raise ExpiredConfirmation("that download link has expired; ask for a new one")
    return row


def claim_package_redeem(principal: Principal, ticket: str, expected_user_oid: str | None = None) -> ToolResult:
    """Spend a ticket once. Plumbing for the gateway's download route; never offered to a caller.

    `expected_user_oid` is set when the downloader proved who they are, and is
    checked BEFORE the ticket is spent, so a wrong person cannot burn somebody
    else's link.
    """
    row = _open_ticket(ticket, expected_user_oid)
    if not _repository().consume(row.confirmation_id, utcnow()):
        raise ReplayedConfirmation("that download link has already been used")
    context = json.loads(row.result_json or "{}")
    _repository().record_result(row.confirmation_id, "redeemed", row.result_json)
    return s.result(
        "claim_package_redeem", {"user_oid": row.user_oid, **context},
        provenance=Provenance(source="download ticket; spent"),
    )


__all__ = ["ConfirmationError", "claim_package_link", "claim_package_redeem"]
