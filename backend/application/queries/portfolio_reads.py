"""The portfolio page's reads of external state, and how each outage is reported. [03.7]

The client book, the payroll footprint, the priceable-state set and the claim store are the four things
`get_portfolio.portfolio_page` reads that can be down. Each raises a typed `DependencyUnavailable` (or, for
the claim store, is recorded in the page's `degraded` list) instead of being swallowed: an outage is not an
empty page. A bug in our own code is never reported as an outage; it propagates.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from application import client_book
from application.errors import DependencyUnavailable, as_dependency_failure
from domain.claims import EngagementScope, ProgramClaim

log = logging.getLogger(__name__)


def client_book_rows() -> list[dict[str, Any]]:
    """Every client we hold payroll for, assessed or not.

    One reader, because a second is a second answer to "who are our clients".
    Raises `DependencyUnavailable` when the source cannot give the book; `portfolio_page`
    reports that as degraded. An empty list means the source answered and holds no clients.
    """
    return client_book.clients_checked()


#: A footprint that failed is not retried for this long. It is a scan of every client's payroll,
#: and a page that is polled while the source is down would otherwise repeat that scan on every view.
FOOTPRINT_RETRY_SECONDS = 60.0
_footprint_failure: tuple[float, Any] | None = None


def footprint() -> dict[int, list[str]]:
    """Payroll states for every client, in one scan.

    `{}` when the source is not the lakehouse or SQL is not configured (there is nothing to scan).
    A scan that fails raises `DependencyUnavailable("source_sql")`, which `portfolio_page` reports
    as degraded: a book that cannot say where a client operates is still usable, but it must say so.
    """
    import time

    from application.errors import as_dependency_failure
    from application.source_ports import new_source_reader
    from tools.fabric_source import active_data_source

    global _footprint_failure
    if active_data_source() != "lakehouse":
        return {}
    reader = new_source_reader()
    if not reader.is_configured():
        return {}
    if _footprint_failure and time.monotonic() - _footprint_failure[0] < FOOTPRINT_RETRY_SECONDS:
        raise _footprint_failure[1]
    try:
        result = reader.footprint()
    except Exception as exc:  # noqa: BLE001 - classified below; a bug in our code is re-raised
        failure = as_dependency_failure(
            "source_sql", exc,
            impact="where each client operates is unknown, so the footprint map and state filters are empty",
        )
        if failure is None:
            raise
        log.warning("payroll footprint unavailable: %s: %s", type(exc).__name__, str(exc)[:200])
        _footprint_failure = (time.monotonic(), failure)
        raise failure from exc
    _footprint_failure = None
    return result


def priceable_states() -> set[str]:
    """States a rule pack can actually price.

    A state we hold payroll in but cannot price is a real gap in statutory
    coverage, and the map is the one screen that shows it. Deriving the set here
    keeps the two halves of that distinction from being authored twice.
    """
    from application.errors import DependencyUnavailable
    from tools.credit_math import PROGRAM_CODE_TO_PACK, _load_pack, authored_years

    try:
        out: set[str] = set()
        for pack_file in set(PROGRAM_CODE_TO_PACK.values()):
            try:
                pack = _load_pack(pack_file)
            except FileNotFoundError:
                continue
            jurisdiction = pack.get("jurisdiction") or {}
            code = (jurisdiction.get("code") or "").upper()
            if code and authored_years(pack_file):
                out.add(code)
        return out
    except (OSError, ValueError) as exc:
        raise DependencyUnavailable(
            "rule_packs", f"a rule pack is unreadable ({type(exc).__name__}).",
            "Check the rule packs under backend/rules are present and valid JSON.",
            impact="no state is marked as priceable",
        ) from exc


def _unique(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, Any]] = []
    for entry in entries:
        key = (entry["dependency"], entry["impact"])
        if key not in seen:
            seen.add(key)
            out.append(entry)
    return out


def _tolerating(read: Callable[[], Any], empty: Any, degraded: list[dict[str, Any]]) -> Any:
    """`read()`, or `empty` with the failure recorded. Only a typed outage is tolerated: a bug propagates."""
    try:
        return read()
    except DependencyUnavailable as exc:
        degraded.append(exc.as_degraded())
        return empty


_CLAIMS_IMPACT = (
    "claim and credit figures are unavailable, so every client is listed as unavailable: whether it was "
    "assessed is unknown, which is not the same as not assessed"
)


def _read_claims(degraded: list[dict[str, Any]]) -> tuple[Any, list[ProgramClaim]]:
    """The claim repository and every claim in it, or (None, []) with the outage recorded.

    Claims are app-owned operational data with no copy anywhere else, so there is nothing to fall
    back to: the answer is a degraded page, never a read from another store.
    """
    from application.services import get_claim_repository

    try:
        repo = get_claim_repository()
        # Read every year ONCE, then narrow. The page needs two different views of
        # the same claims and they must not come from two reads.
        return repo, repo.portfolio_coverage(tax_years=None)
    except Exception as exc:  # noqa: BLE001 - classified below; a bug in our code is re-raised
        failure = as_dependency_failure("claims_store", exc, impact=_CLAIMS_IMPACT)
        if failure is None:
            raise
        if failure is not exc:
            log.warning("claims store unavailable: %s: %s", type(exc).__name__, str(exc)[:200])
        degraded.append(failure.as_degraded(_CLAIMS_IMPACT))
        return None, []


def _engagements(repo: Any, client_id: int, degraded: list[dict[str, Any]]) -> dict[str, EngagementScope] | None:
    """One client's engagement scopes, or None when they could not be read (recorded as degraded)."""
    if repo is None:
        return None
    try:
        return {e.program_code: e.scope for e in repo.engagements(client_id)}
    except Exception as exc:  # noqa: BLE001 - classified below; a bug in our code is re-raised
        failure = as_dependency_failure("claims_store", exc, impact="engagement scope is unknown")
        if failure is None:
            raise
        degraded.append(failure.as_degraded())
        return None
