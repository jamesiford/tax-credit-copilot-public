"""The client book and the programme catalogue, as the application sees them.

These lived in `api/scope.py`, which meant anything that wanted "who are our
clients" or "which programmes can we price" had to import a router. The chat did
(`_chat_clients`), the portfolio read did (`_client_book`), and a channel
gateway cannot. The logic is unchanged; it moved here and the router now calls
it, so there is still exactly one answer to both questions.
"""
from __future__ import annotations

from typing import Any

from infrastructure.payroll.pay_period_source import configured_account_id


def is_placeholder_year(program_code: str, tax_year: int) -> bool:
    from tools.credit_math import resolve_statutory_floors

    try:
        return bool(resolve_statutory_floors(program_code, tax_year).prototype_verify)
    except Exception:  # noqa: BLE001 - a year that cannot resolve is not a placeholder
        return False


def programs() -> list[dict[str, Any]]:
    """Every program we hold a rule pack for, with its authored years.

    `authored_years` is the list the engine can actually price. A program with
    an empty list can be described but not calculated, and saying so here is
    cheaper than letting a screen render an empty grid.
    """
    from tools.credit_math import PROGRAM_CODE_TO_PACK, _load_pack, _program_name, authored_years

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
        placeholder_years = [y for y in years if is_placeholder_year(code, y)]

        out.append({
            "program_code": code,
            "name": credit.get("name") or code,
            "citation": credit.get("statutory_citation") or "",
            # Derived, not selectable: a program belongs to exactly one
            # jurisdiction, so offering both invites a contradictory selection.
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


def clients() -> list[dict[str, Any]]:
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

    accounts = accounts_from_warehouse()
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


def accounts_from_warehouse() -> list[dict[str, Any]]:
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


def clients_or_empty() -> list[dict[str, Any]]:
    """The book, or nothing when the source is unreachable.

    Callers that decorate a result with a name or a count would rather render
    what they have than fail whole; an absent book understates, it never
    invents.
    """
    try:
        return clients()
    except Exception:  # noqa: BLE001 - a missing book must not take a page down
        return []


def client_name(client_id: int, book: Any = clients_or_empty) -> str | None:
    """The display name for one client, or None when the book does not hold it."""
    return next(
        (c.get("name") for c in book() if int(c["account_id"]) == int(client_id)),
        None,
    )
