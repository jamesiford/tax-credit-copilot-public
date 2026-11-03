"""Give an agent caller's user a name, when the channel supplied none. [CH-15a]

Authentication proves WHO called; this fills in what the person is CALLED, for the audit
trail and for the author of a write. It runs only for an agent caller (Teams, Copilot
Chat) whose name is missing or the orchestrator's placeholder: a delegated (Cowork)
token already carries `name` and `preferred_username`, so that path never reaches Graph.

It is fail-soft by construction. A resolver that errors, or one that is switched off,
returns the caller untouched and the request carries on with the name it arrived with.
The resolved name and UPN are never logged; only the OID appears in the warning.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import replace

from application.display_names import DisplayNameResolver, needs_resolution
from channel.auth import Caller

log = logging.getLogger("tcc.channel.people")


class CallerPeople:
    """Names an agent caller's user through a `DisplayNameResolver`, or leaves the caller alone."""

    def __init__(self, resolver: DisplayNameResolver | None) -> None:
        self._resolver = resolver

    async def enrich(self, caller: Caller) -> Caller:
        """`caller`, with the person's directory name and UPN where those were missing."""
        acting = caller.acting
        if self._resolver is None or caller.kind != "agent" or not needs_resolution(acting):
            return caller
        try:
            person = await asyncio.to_thread(self._resolver.resolve, acting.oid)
        except Exception as exc:  # noqa: BLE001 - a lookup must never stop the request
            log.warning("display-name resolution failed for oid=%s: %s", acting.oid, type(exc).__name__)
            return caller
        if person is None:
            return caller
        # the UPN the channel already asserted, if any, outranks the directory's
        named = replace(acting, display_name=person.display_name or acting.display_name, upn=acting.upn or person.upn)
        return replace(caller, acting=named)
