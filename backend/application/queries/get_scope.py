"""The scope dimension: which clients, which programs, which years.

Scope is **persistent and orthogonal**, not a view. Every calculating screen renders at
some point in `client x program x year`, and the operator moves through that space
rather than navigating to a different page to change client.

Year is first-class because statute is year-scoped [ADR-005]. A figure without a tax
year is not a statutory figure, so the API has to be honest about which years it can
actually price: `authored_years` per program comes from the rule packs on disk, not from
a range. Jurisdiction is DERIVED from the program and is never selected independently.

This was `api/scope.py`. The router now maps the three ways a client's scope cannot be
established onto status codes; the arithmetic and the lookups are here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from application.client_book import clients as _clients
from application.client_book import programs as _programs
from application.mediator import Query
from application.open_year import is_open
from application.source_ports import client_fiscal_window, payroll_scope, shared_scope

# The window the retroactive audit works over: a base year plus five. The
# amendment window (how far back a return may be amended) is a DIFFERENT
# mechanism and is still open with the partner — see plan.md. This is the credit's own
# tranche duration, which is what `baseyear.py` implements.
RETROACTIVE_WINDOW_YEARS = 6


class UnknownClient(LookupError):
    """The account is not in the client book."""


class NoPayrollForScope(LookupError):
    """The client is known but the active data source holds no payroll for it."""


class NoResolvableWorkState(ValueError):
    """Payroll exists but no work state resolves, so no jurisdictional credit can be scoped."""


@dataclass(frozen=True)
class GetScopeOptionsQuery(Query):
    """Everything needed to render the scope selector, in one round trip."""


@dataclass(frozen=True)
class GetClientScopeQuery(Query):
    """What one client's data actually supports."""

    account_id: int


def handle_get_scope_options(query: GetScopeOptionsQuery) -> dict[str, Any]:
    """The clients, the programmes with their authored years, and the active data source."""
    from tools.fabric_source import active_data_source

    programs = _programs()
    calculable_years = sorted({y for p in programs for y in p["authored_years"]})
    return {
        "clients": _clients(),
        "programs": programs,
        "years": {
            "authored": calculable_years,
            "latest": calculable_years[-1] if calculable_years else None,
            "window_years": RETROACTIVE_WINDOW_YEARS,
            # The default retroactive window: the most recent authored year and
            # the five before it, clipped to what is actually authored so the UI
            # cannot offer a year the engine would refuse.
            "default_window": (
                [y for y in calculable_years if y > calculable_years[-1] - RETROACTIVE_WINDOW_YEARS]
                if calculable_years else []
            ),
        },
        "data_source": active_data_source(),
    }


def _fiscal_window_for(account_id: int, tax_year: int, programs: list[dict[str, Any]]):
    """The client's fiscal window for a tax year, or None if nothing resolves.

    The programme supplies the labelling convention, so a non-calendar filer's
    tax year is the one the statute would assign rather than the calendar year
    its paychecks happen to fall in.
    """
    from tools.credit_math import resolve_tax_year_convention

    program = next((p for p in programs if tax_year in p["authored_years"]), None)
    if program is None:
        return None
    try:
        convention = resolve_tax_year_convention(program["program_code"], tax_year)
        return client_fiscal_window(account_id, tax_year, convention["label"])
    except (FileNotFoundError, ValueError, KeyError):
        return None


def _require_known_client(account_id: int) -> None:
    known = {c["account_id"] for c in _clients()}
    if account_id not in known:
        # Checked BEFORE loading. Single-tenant fixture sources ignore the
        # account id entirely, so without this an unknown client would return
        # the default tenant's payroll under the requested client's name —
        # one client's figures presented as another's.
        raise UnknownClient(
            f"Unknown client {account_id}. Known accounts: "
            f"{', '.join(str(a) for a in sorted(known))}."
        )


def _coverage(
    account_id: int, priceable: list[int], programs: list[dict[str, Any]], pay_dates: list[str],
) -> tuple[dict[int, int], dict[int, Any]]:
    """Months of payroll inside each tax year's FISCAL WINDOW, and where each window ends.

    Not inside the calendar year of the same name. Candle Bottle's 2023 fiscal year
    runs 2023-07-28 to 2024-08-02, so bucketing by calendar year split one tax
    year into "TY2023 · 5mo" and "TY2024 · 8mo" — two partial years where the
    client has one complete one.
    """
    coverage: dict[int, int] = {}
    window_ends: dict[int, Any] = {}
    for year in priceable:
        window = _fiscal_window_for(account_id, year, programs)
        if window is None:
            continue
        begin, end = window.begin.isoformat(), window.end.isoformat()
        window_ends[year] = window.end
        months = {day[:7] for day in pay_dates if begin <= day <= end}
        if months:
            # Clamped because the UI reads this as "out of 12"; a 53-week year
            # legitimately touches 13 or 14 distinct calendar months.
            coverage[year] = min(len(months), 12)
    return coverage, window_ends


def _client_scope(account_id: int) -> dict[str, Any]:
    _require_known_client(account_id)

    rows = payroll_scope(account_id)
    if not rows.total_rows:
        raise NoPayrollForScope(f"No payroll for account {account_id} in the active data source.")

    payroll_years = rows.tax_years
    states = rows.states
    if not states:
        raise NoResolvableWorkState(
            f"Account {account_id} has {rows.total_rows:,} payroll rows but no "
            f"resolvable work state. Every credit is jurisdictional, so scope "
            f"cannot be established. Check Worksite_ID prefixes and Work_State."
        )

    programs = [
        p for p in _programs()
        if p["jurisdiction"]["code"] in states or p["jurisdiction"]["level"] == "federal"
    ]
    priceable = sorted({y for p in programs for y in p["authored_years"]})
    coverage, window_ends = _coverage(account_id, priceable, programs, rows.pay_dates)

    # A year is calculable only if we HOLD payroll for it as well as statute.
    # A stray pay date in a window (December periods paid in January) is not a
    # year of payroll — that became visible the moment TY2026 was authored.
    calculable = sorted(y for y in coverage if y in payroll_years)
    complete = [y for y in calculable if coverage.get(y, 0) >= 12]
    # Years whose fiscal window has not ended. Read to date, never claimed.
    open_years = [y for y in calculable if y in window_ends and is_open(window_ends[y])]
    # The year to open on: the most recent COMPLETE year, falling back to the
    # most recent calculable one. Opening on a partial year shows $0 for a
    # client with real value, which is the worst possible first impression and
    # is also simply misleading.
    default_year = complete[-1] if complete else (calculable[-1] if calculable else None)

    return {
        "account_id": account_id,
        "states": states,
        "programs": programs,
        "payroll_years": payroll_years,
        "calculable_years": calculable,
        "payroll_without_statute": [y for y in payroll_years if y not in priceable],
        "months_of_payroll": coverage,
        "complete_years": complete,
        "open_years": open_years,
        "default_year": default_year,
        "rows": rows.total_rows,
    }


def handle_get_client_scope(query: GetClientScopeQuery) -> dict[str, Any]:
    # Three reads follow — the client book, the payroll aggregate, and one
    # fiscal-rule lookup per priceable year. One connection for all of them.
    with shared_scope():
        return _client_scope(query.account_id)
