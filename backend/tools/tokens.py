"""Opaque per-employee handles.

Employee IDs may be displayed after authentication but must never enter a URL
path, a log line, telemetry or a prompt, so every drill-in is keyed by this
instead.

It lives here, and not in the two places that mint it, because a token minted by
one read has to resolve in another: the per-client eligibility view renders rows
and the sealed workspace serves the drill those rows link to. When the two
derived it differently the drill returned 404 for every row on screen.
"""
from __future__ import annotations

import hashlib


def record_token(
    account_id: int | None, program_code: str, tax_year: int, employee_id: str
) -> str:
    """A stable opaque handle for one employee within one client-programme-year."""
    seed = f"{account_id}\0{program_code}\0{tax_year}\0{employee_id}"
    return hashlib.sha256(seed.encode()).hexdigest()[:24]
