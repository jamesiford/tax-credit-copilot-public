"""Whose answer this is: scope resolution, the client clarification, state detection.

The scope refusal is about answering for the wrong company, not about routing, so
nothing here depends on a model being up.
"""
from __future__ import annotations

import logging
from typing import Any, AsyncIterator

from api.chat.models import ChatRequest, _normalise_chat_method
from api.chat.sse import _sse

log = logging.getLogger(__name__)


def _detect_state(message: str) -> str:
    m = f" {message.lower()} "
    if "georgia" in m or " ga " in m or "atlanta" in m or "savannah" in m or "macon" in m:
        return "GA"
    if "new york" in m or " ny " in m:
        return "NY"
    if "south carolina" in m or " sc " in m or " charleston" in m or "greenville" in m:
        return "SC"
    if "texas" in m or " tx " in m or "austin" in m or "houston" in m or " dallas" in m:
        return "TX"
    if "north carolina" in m or " nc " in m or "charlotte" in m or "raleigh" in m:
        return "NC"
    if "tennessee" in m or " tn " in m or "nashville" in m or "memphis" in m:
        return "TN"
    if "florida" in m or " fl " in m or "jacksonville" in m or "miami" in m or "orlando" in m:
        return "FL"
    if " ohio" in m or " oh " in m or "columbus" in m or "cincinnati" in m or "cleveland" in m:
        return "OH"
    if "colorado" in m or " co " in m or "denver" in m or "boulder" in m:
        return "CO"
    if "virginia" in m or " va " in m or "tysons" in m or "richmond" in m or "arlington" in m:
        return "VA"
    return "GA"


def _request_scope(req: ChatRequest) -> dict[str, Any]:
    if req.client_id is None or req.tax_year is None:
        raise ValueError(
            "This answer needs the selected client and tax year from the page. "
            "I will not guess against the default tenant."
        )

    method = _normalise_chat_method(req.method)
    state = (req.state or _detect_state(req.message) or "GA").upper()
    from application.queries._client_run import resolve_statute

    # NOT `resolve_client_run`. Every field below is statute or calendar; the
    # payroll it used to load was never read — `scope["run"]` had no consumer —
    # so every chat message paid a full client payroll read for metadata.
    run = resolve_statute(account_id=req.client_id, state=state, tax_year=req.tax_year)
    return {
        "state": run.state,
        "account_id": run.account_id,
        "tax_year": run.tax_year,
        "method": method,
        "program_code": run.program_code,
        "window": run.window,
        "floors": run.floors,
    }


def _chat_clients() -> list[Any]:
    """The book, as the resolver needs it. Empty rather than failing the turn."""
    from application import client_book
    from application.chat_scope import ClientName

    try:
        return [ClientName(int(c["account_id"]), str(c["name"])) for c in client_book.clients()]
    except Exception:  # noqa: BLE001 — no client list means no names to match
        log.warning("chat: client list unavailable; clarification disabled", exc_info=True)
        return []


def _referent(req: ChatRequest) -> Any:
    """Whose answer this is, or None when the reader already chose."""
    from application.chat_scope import resolve_referent

    if req.client_confirmed:
        return None
    clients = _chat_clients()
    if not clients:
        return None
    referent = resolve_referent(
        req.message, [t.model_dump() for t in req.history], req.client_id, clients,
    )
    return (referent, clients) if referent.clarify else None


def _candidate_year(client_id: int, req: ChatRequest) -> int | None:
    """The tax year a clarifying button would answer for, stated on the button.

    The page's year for the page's client. Otherwise the year the book ranks
    that client on — the cell carrying its reason to call, which is the year
    the row's own Ask button uses — so a button and the row agree. A client
    with no claims falls back to its latest calculation; one no run has reached
    offers no year, and its button cannot be pressed.
    """
    if client_id == req.client_id and req.tax_year is not None:
        return req.tax_year
    try:
        from application.queries.get_client_situation import GetClientSituationQuery
        from application.services import get_mediator

        lead = get_mediator().send(GetClientSituationQuery(client_id=client_id)).get("lead_tax_year")
        if lead is not None:
            return int(lead)
    except Exception:  # noqa: BLE001
        pass
    try:
        from application.services import get_run_manifest_repository

        manifest = get_run_manifest_repository().latest(client_id)
        return int(manifest.tax_year) if manifest is not None else None
    except Exception:  # noqa: BLE001
        return None


def _clarify_question(referent: Any, names: list[str]) -> str:
    listed = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" or {names[-1]}"
    if referent.reason == "names a different client from the one this chat is about":
        return (
            f"You asked about **{names[0]}**, but this chat is about **{names[1]}**. "
            f"Which one should I answer for?"
        )
    if len(names) == 1:
        return (
            f"Do you mean **{names[0]}**? No client is selected on the page, and I "
            f"won't guess — confirm and I'll answer for them."
        )
    if referent.reason == "no client is selected":
        return (
            f"Which client do you mean — {listed}? No client is selected on the page, "
            f"and I won't guess."
        )
    return (
        f"Which client do you mean — {listed}? I answer about one client at a time, "
        f"and I won't pick one for you."
    )


async def _clarify_stream(req: ChatRequest, referent: Any, clients: list[Any]) -> AsyncIterator[str]:
    """Ask which client, with one choice per candidate. Emits no `done`."""
    by_id = {c.client_id: c.name for c in clients}
    choices = [
        {"client_id": cid, "name": by_id.get(cid, f"Account {cid}"), "tax_year": _candidate_year(cid, req)}
        for cid in referent.candidates
    ]
    text = _clarify_question(referent, [c["name"] for c in choices])
    yield _sse("status", {"phase": 1, "echo": req.message, "clarify": True, "reason": referent.reason})
    yield _sse("agent_start", {"agent": "OrchestratorAgent"})
    yield _sse("token", {"agent": "OrchestratorAgent", "content": text})
    yield _sse("clarify", {"message": req.message, "reason": referent.reason, "choices": choices})
    yield _sse("agent_end", {"agent": "OrchestratorAgent"})


async def _clarify_only(req: ChatRequest, referent: Any, clients: list[Any]) -> AsyncIterator[str]:
    async for frame in _clarify_stream(req, referent, clients):
        yield frame
    yield _sse("done", {})


async def _missing_scope_stream(message: str, *, detail: str | None = None) -> AsyncIterator[str]:
    text = detail or (
        "This answer needs the selected client and tax year from the page. "
        "I will not guess against the default tenant or silently answer for the wrong scope."
    )
    yield _sse("status", {"phase": 1, "echo": message, "scope_missing": True, "note": text})
    yield _sse("agent_start", {"agent": "OrchestratorAgent"})
    yield _sse("token", {"agent": "OrchestratorAgent", "content": text})
    yield _sse("agent_end", {"agent": "OrchestratorAgent"})
    yield _sse("done", {})
