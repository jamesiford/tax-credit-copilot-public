"""Which clients a batch covers: ids, a portfolio filter, or everyone. Never reads payroll. [ADR-012]

A group is resolved from the client book and the portfolio page (claims, engagements and the footprint),
the same instrument the portfolio screen uses, so "the filtered group" in a batch is exactly the group the
screen showed. There is no server-side saved view: the filter travels in the request.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from application.runs.errors import EmptyScope, RunBatchRefused, UnknownClients
from domain.runs import ScopeKind

#: Filter keys a batch accepts. The first six are the portfolio page's own filters; the rest narrow its rows.
PAGE_FILTERS = ("program", "year", "outcome", "scope", "status", "near")
ROW_FILTERS = ("band", "state", "unassessed", "unavailable")
FILTER_KEYS = PAGE_FILTERS + ROW_FILTERS
_ID_LIST_IN_SPEC = 50


@dataclass(frozen=True)
class Scope:
    """Which clients a batch covers, before it is resolved against the book."""
    kind: ScopeKind
    client_ids: tuple[int, ...] = ()
    filter: Mapping[str, Any] = field(default_factory=dict)

    def validated(self) -> "Scope":
        if self.kind in (ScopeKind.ONE, ScopeKind.LIST) and not self.client_ids:
            raise EmptyScope("No client ids were given.")
        if self.kind is ScopeKind.ONE and len(self.client_ids) != 1:
            raise RunBatchRefused("scope 'one' takes exactly one client id.", "Use scope 'list' for several.")
        unknown = sorted(set(self.filter) - set(FILTER_KEYS))
        if unknown:
            raise RunBatchRefused(f"Unknown filter key(s): {', '.join(unknown)}.", f"Use: {', '.join(FILTER_KEYS)}.")
        return self


@dataclass(frozen=True)
class Resolution:
    """The client ids a scope resolved to, with names for display."""
    client_ids: tuple[int, ...]
    names: dict[int, str | None]


def _book() -> list[dict[str, Any]]:
    from application import client_book

    return client_book.clients_checked()


def _portfolio_page(**kwargs: Any) -> dict[str, Any]:
    from application.queries.get_portfolio_page import GetPortfolioPageQuery
    from application.services import get_mediator

    return get_mediator().send(GetPortfolioPageQuery(limit=10_000_000, offset=0, **kwargs))


def _portfolio(**kwargs: Any) -> list[dict[str, Any]]:
    return list(_portfolio_page(**kwargs)["items"])


def unavailable_among(
    ids: tuple[int, ...], names: dict[int, Any], read_page: Callable[[], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Which of these clients the portfolio cannot read claims for right now, and why.

    "Unavailable" is a different statement from "not assessed": the store could not answer, so whether the client was
    assessed is unknown. A preview that cannot find out says so (`checked: false`) instead of reporting none.
    """
    from application.errors import DependencyUnavailable

    try:
        page = (read_page or _portfolio_page)()
    except DependencyUnavailable as failure:
        return {"checked": False, "items": [], "reason": failure.reason}
    why = {d["dependency"]: d.get("impact") for d in page.get("degraded") or []}
    wanted = set(ids)
    items = [
        {"client_id": int(r["client_id"]), "client_name": names.get(int(r["client_id"])),
         "dependency": r.get("unavailable_dependency"),
         "reason": why.get(r.get("unavailable_dependency")) or "the claim figures cannot be loaded right now"}
        for r in page.get("items") or [] if r.get("data_unavailable") and int(r["client_id"]) in wanted
    ]
    return {"checked": True, "items": items}


#: One check per row filter, so adding a filter is one line and no function grows.
_ROW_CHECKS = {
    "band": lambda row, v: row.get("priority_band") == v,
    "state": lambda row, v: str(v).upper() in {s.upper() for s in row.get("states") or []},
    "unassessed": lambda row, v: (row.get("status") == "not_assessed") == bool(v),
    "unavailable": lambda row, v: bool(row.get("data_unavailable")) == bool(v),
}


def _row_matches(row: Mapping[str, Any], f: Mapping[str, Any]) -> bool:
    return all(check(row, f[key]) for key, check in _ROW_CHECKS.items() if f.get(key) not in (None, ""))


def _explicit(scope: Scope, names: dict[int, Any]) -> tuple[int, ...]:
    ids = tuple(dict.fromkeys(int(i) for i in scope.client_ids))
    unknown = tuple(i for i in ids if i not in names)
    if unknown:
        raise UnknownClients(unknown)
    return ids


def _filtered(scope: Scope, names: dict[int, Any], portfolio: Callable[..., list[dict[str, Any]]] | None) -> tuple[int, ...]:
    page_args = {k: v for k, v in scope.filter.items() if k in PAGE_FILTERS and v is not None}
    found = (portfolio or _portfolio)(**page_args)
    return tuple(dict.fromkeys(
        int(r["client_id"]) for r in found if _row_matches(r, scope.filter) and int(r["client_id"]) in names
    ))


def _entitled(ids: tuple[int, ...], scope: Scope) -> tuple[int, ...]:
    """The clients the caller may act for. A named client they may not is refused; a group quietly excludes them.

    A person who asks for "all clients" means all they may see, so the group is narrowed. A person who names a client
    they may not touch has asked for something specific, and a silent skip would hide that it was refused.
    """
    from application.identity import ANONYMOUS, NotAuthorized, ambient_principal
    from application.services import get_client_authorizer

    authorizer, principal = get_client_authorizer(), ambient_principal() or ANONYMOUS
    allowed = tuple(i for i in ids if authorizer.is_authorized(principal, i))
    if len(allowed) != len(ids) and scope.kind in (ScopeKind.ONE, ScopeKind.LIST):
        refused = sorted(set(ids) - set(allowed))
        raise NotAuthorized(f"not authorized for client {refused[0]}")
    return allowed


def resolve_clients(
    scope: Scope, *, book: Callable[[], list[dict[str, Any]]] | None = None,
    portfolio: Callable[..., list[dict[str, Any]]] | None = None,
) -> Resolution:
    """The client ids a scope covers, in a stable order, with names for display."""
    scope = scope.validated()
    names = {int(c["account_id"]): c.get("name") for c in (book or _book)()}
    if scope.kind in (ScopeKind.ONE, ScopeKind.LIST):
        ids = _explicit(scope, names)
    elif scope.kind is ScopeKind.ALL:
        ids = tuple(sorted(names))
    else:
        ids = _filtered(scope, names, portfolio)
    ids = _entitled(ids, scope)
    if not ids:
        raise EmptyScope()
    return Resolution(ids, {i: names.get(i) for i in ids})


def scope_spec(scope: Scope, ids: tuple[int, ...]) -> dict[str, Any]:
    """What is stored on the batch: small and deterministic, so two identical requests match byte for byte."""
    digest = hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()[:16]
    spec: dict[str, Any] = {"client_count": len(ids), "clients_sha256": digest}
    if scope.filter:
        spec["filter"] = {k: scope.filter[k] for k in sorted(scope.filter)}
    if len(ids) <= _ID_LIST_IN_SPEC:
        spec["client_ids"] = sorted(ids)
    return spec
