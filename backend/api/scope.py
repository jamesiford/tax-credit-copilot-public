"""The scope dimension: which clients, which programs, which years.

Scope is **persistent and orthogonal**, not a view. Every calculating screen
renders at some point in `client x program x year`, and the operator moves
through that space rather than navigating to a different page to change client.

Three axes, and the third is the one people forget:

    client   portfolio (all tenants) <-> one account
    program  all programs <-> one. Jurisdiction is DERIVED from the program and
             is never selected independently — a program belongs to exactly one
             jurisdiction, so offering both invites a contradictory selection
             ("Georgia" + "Federal WOTC") that means nothing.
    year     a single tax year <-> a retroactive window

Year is first-class because statute is year-scoped [ADR-005]. A figure without a
tax year is not a statutory figure, so the axis cannot be optional and the API
has to be honest about which years it can actually price: `authored_years` per
program comes from the rule packs on disk, not from a range.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from api._payperiods import configured_account_id, load_pay_periods

router = APIRouter(prefix="/api/scope", tags=["scope"])

# The window the retroactive audit works over: a base year plus five. The
# amendment window (how far back a return may be amended) is a DIFFERENT
# mechanism and is still open with the partner — see plan.md. This is the credit's own
# tranche duration, which is what `baseyear.py` implements.
RETROACTIVE_WINDOW_YEARS = 6


def _is_placeholder_year(program_code: str, tax_year: int) -> bool:
    from tools.credit_math import resolve_statutory_floors

    try:
        return bool(resolve_statutory_floors(program_code, tax_year).prototype_verify)
    except Exception:  # noqa: BLE001 - a year that cannot resolve is not a placeholder
        return False


def _programs() -> list[dict[str, Any]]:
    """Every program we hold a rule pack for, with its authored years.

    `authored_years` is the list the engine can actually price. A program with
    an empty list can be described but not calculated, and saying so here is
    cheaper than letting a screen render an empty grid.
    """
    from tools.credit_math import PROGRAM_CODE_TO_PACK, _load_pack, _program_name, authored_years
    from pathlib import Path

    out: list[dict[str, Any]] = []

    for code, pack_file in sorted(PROGRAM_CODE_TO_PACK.items()):
        try:
            pack = _load_pack(pack_file)
        except FileNotFoundError:
            continue

        credit = pack.get("credit") or {}
        jurisdiction = pack.get("jurisdiction") or {}
        program = _program_name(pack_file)
        years = authored_years(pack_file)
        # Authored, but not published statute: a year whose pack carries
        # `_prototype_verify` (TY2026 for Georgia). Priceable, and flagged.
        placeholder_years = [y for y in years if _is_placeholder_year(code, y)]

        out.append({
            "program_code": code,
            "name": credit.get("name") or code,
            "citation": credit.get("statutory_citation") or "",
            # Derived, not selectable. See the module docstring.
            "jurisdiction": {
                "level": jurisdiction.get("level") or "state",
                "code": jurisdiction.get("code") or "",
                "name": jurisdiction.get("name") or "",
            },
            "authored_years": years,
            "placeholder_years": placeholder_years,
            "year_scoped": bool(years),
            # A program without authored years is describable but not
            # calculable. The UI should show it disabled with this reason
            # rather than omitting it, which would look like it does not exist.
            "calculable": bool(years),
            "not_calculable_reason": (
                "" if years else
                f"No year-scoped rule packs authored for {program}. "
                f"ADR-005: statute is not inherited across years."
            ),
        })
    return out


def _clients() -> list[dict[str, Any]]:
    """Every tenant the active data source can see."""
    from tools.fabric_source import active_data_source

    if active_data_source() != "lakehouse":
        # Single-tenant fixture sources still present a one-entry portfolio, so
        # the UI has one code path rather than two.
        return [{
            "account_id": configured_account_id(),
            "name": "Reference Dataset Client",
            "billing_state": "GA",
            "employees": None,
            "synthetic": False,
            "industry": None,
        }]

    from data.source.industry import industry_name

    accounts = _accounts_from_warehouse()
    return sorted(
        (
            {
                "account_id": int(a["AccountId"]),
                "name": a.get("Name") or f"Account {a['AccountId']}",
                "billing_state": a.get("BillingState") or "",
                "employees": a.get("ActualNumberOfEmployees"),
                # Account ids below 2000 are real client data under a codename;
                # 2000+ are generated. Surfacing it prevents a demo figure being
                # quoted as a client result.
                "synthetic": int(a["AccountId"]) >= 2000,
                # WI-20. Display-only; None where we do not hold it.
                "industry": industry_name(a.get("IndustryTypeId")),
            }
            for a in accounts
        ),
        key=lambda c: (c["synthetic"], c["name"]),
    )


def _accounts_from_warehouse() -> list[dict[str, Any]]:
    """The client book, over the SQL endpoint rather than OneLake.

    This was the last Delta read left in the request path and cost 8.3s on a
    cold start. The lakehouse is reachable from the warehouse connection by
    three-part naming, so it is the same data over the connection every other
    read already uses — and it inherits the cached token.

    Falls back to the Delta reader when the warehouse is not configured, which
    is the case for `DATA_SOURCE=csv` developers and for the test suite.
    """
    from infrastructure.persistence.source_sql import SourceSqlReader

    reader = SourceSqlReader()
    if not reader.is_configured():
        from data.source.from_fabric import FabricLakehouseReader

        return FabricLakehouseReader().list_accounts()
    return reader.list_accounts()


def _payroll_scope(account_id: int):
    """Years, states and pay dates for one client.

    Asked as a `GROUP BY` where the source supports one. The row path is still
    correct and still used by the fixture sources, but it materialises 384,433
    dicts to answer three `DISTINCT`s — ~3s of GIL-bound CPU per request, on an
    endpoint that returns half a kilobyte.
    """
    from infrastructure.persistence.source_sql import SourceSqlReader, payroll_scope_from_rows
    from tools.fabric_source import active_data_source

    if active_data_source() == "lakehouse":
        reader = SourceSqlReader()
        if reader.is_configured():
            return reader.payroll_scope(account_id)
    return payroll_scope_from_rows(load_pay_periods(account_id))


def _fiscal_window_for(account_id: int, tax_year: int, programs: list[dict[str, Any]]):
    """The client's fiscal window for a tax year, or None if nothing resolves.

    The programme supplies the labelling convention, so a non-calendar filer's
    tax year is the one the statute would assign rather than the calendar year
    its paychecks happen to fall in.
    """
    from infrastructure.payroll.fiscal_source import client_fiscal_window
    from tools.credit_math import resolve_tax_year_convention

    program = next((p for p in programs if tax_year in p["authored_years"]), None)
    if program is None:
        return None
    try:
        convention = resolve_tax_year_convention(program["program_code"], tax_year)
        return client_fiscal_window(account_id, tax_year, convention["label"])
    except (FileNotFoundError, ValueError, KeyError):
        return None


@router.get("")
def scope_options() -> dict[str, Any]:
    """Everything needed to render the scope selector, in one round trip."""
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
        "data_source": __import__("tools.fabric_source", fromlist=["x"]).active_data_source(),
    }


@router.get("/client/{account_id}")
def client_scope(account_id: int) -> dict[str, Any]:
    """What one client's data actually supports.

    The years here come from the client's PAYROLL, and are intersected with the
    years the programs can be priced for. Those two sets are routinely different
    — payroll runs past the last published wage table — and the difference is
    reported rather than hidden, because "we hold your 2026 payroll but cannot
    price it yet" is a real answer.
    """
    # Three reads follow — the client book, the payroll aggregate, and one
    # fiscal-rule lookup per priceable year. One connection for all of them.
    from infrastructure.persistence.source_sql import shared_scope

    with shared_scope():
        return _client_scope(account_id)


def _client_scope(account_id: int) -> dict[str, Any]:
    known = {c["account_id"] for c in _clients()}
    if account_id not in known:
        # Checked BEFORE loading. Single-tenant fixture sources ignore the
        # account id entirely, so without this an unknown client would return
        # the default tenant's payroll under the requested client's name —
        # one client's figures presented as another's.
        raise HTTPException(
            status_code=404,
            detail=(
                f"Unknown client {account_id}. Known accounts: "
                f"{', '.join(str(a) for a in sorted(known))}."
            ),
        )

    rows = _payroll_scope(account_id)
    if not rows.total_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No payroll for account {account_id} in the active data source.",
        )

    payroll_years = rows.tax_years
    states = rows.states
    if not states:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Account {account_id} has {rows.total_rows:,} payroll rows but no "
                f"resolvable work state. Every credit is jurisdictional, so scope "
                f"cannot be established. Check Worksite_ID prefixes and Work_State."
            ),
        )

    programs = [p for p in _programs() if p["jurisdiction"]["code"] in states or p["jurisdiction"]["level"] == "federal"]
    priceable = sorted({y for p in programs for y in p["authored_years"]})

    # Months of payroll inside each tax year's FISCAL WINDOW, not inside the
    # calendar year of the same name. Candle Bottle's 2023 fiscal year runs
    # 2023-07-28 to 2024-08-02, so bucketing by calendar year split one tax
    # year into "TY2023 · 5mo" and "TY2024 · 8mo" — two partial years where the
    # client has one complete one.
    coverage: dict[int, int] = {}
    window_ends: dict[int, Any] = {}
    for year in priceable:
        window = _fiscal_window_for(account_id, year, programs)
        if window is None:
            continue
        begin, end = window.begin.isoformat(), window.end.isoformat()
        window_ends[year] = window.end
        months = {day[:7] for day in rows.pay_dates if begin <= day <= end}
        if months:
            # Clamped because the UI reads this as "out of 12"; a 53-week year
            # legitimately touches 13 or 14 distinct calendar months.
            coverage[year] = min(len(months), 12)

    # A year is calculable only if we HOLD payroll for it as well as statute.
    # A stray pay date in a window (December periods paid in January) is not a
    # year of payroll — that became visible the moment TY2026 was authored.
    calculable = sorted(y for y in coverage if y in payroll_years)

    complete = [y for y in calculable if coverage.get(y, 0) >= 12]
    # Years whose fiscal window has not ended. Read to date, never claimed.
    from application.open_year import is_open

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
