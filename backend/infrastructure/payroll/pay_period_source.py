"""Payroll access. The only place that knows where rows physically come from.

Three sources sit behind one function, selected by `DATA_SOURCE`:

- ``lakehouse`` the customer's source schema in the Fabric lakehouse. Multi-tenant.
- ``fabric``    an early flattened single-tenant table. Kept for ingestion tests.
- ``csv``       a local file, so a clone runs offline.

This lived in `api/_payperiods.py`, which made `tools/portfolio.py` import from
the presentation layer to read payroll — a dependency pointing outward, and the
kind that only reveals itself as an import cycle under one entry point.

The HTTP concern stayed behind: `require_pay_periods` translates an empty result
into a 404 or a 503, which is a presentation decision and belongs in `api/`.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Any

_PAY_PERIODS_CSV = Path(__file__).resolve().parents[2] / "data" / "payroll_pay_periods.csv"


def configured_account_id() -> int:
    """The tenant a single-tenant data source represents."""
    return int(os.getenv("FLEX_ACCOUNT_ID", "1001"))


def load_pay_periods(account_id: int | None = None) -> list[dict[str, Any]]:
    """Load the BCS-shaped pay-period rows with typed numeric columns.

    `account_id` selects the tenant. It is a *parameter* rather than pure
    configuration because scope is a dimension of the request: an operator
    switching client in the UI must not require a redeploy.

    **The `csv` and `fabric` sources hold exactly one tenant**, and asking them
    for a different one returns `[]` rather than that tenant's rows. Ignoring the
    argument would be worse than an error — a caller asking for client 42 would
    receive client 1001's payroll and could go on to compute, or record, figures
    for the wrong company entirely. That has happened; it is now a returned empty
    list and a 404 above.

    Returns an empty list when the source is absent or holds no rows for that
    tenant. The caller decides whether that is fatal.
    """
    from tools.fabric_source import FabricEmployeesAdapter, active_data_source

    source = active_data_source()

    if source == "lakehouse":
        from data.source.from_fabric import FabricLakehouseReader

        resolved = account_id if account_id is not None else configured_account_id()
        return FabricLakehouseReader().bcs_rows(resolved)

    # Single-tenant sources below. A mismatched tenant is empty, never somebody
    # else's payroll.
    if account_id is not None and account_id != configured_account_id():
        return []

    if source == "fabric":
        # Adapter yields rows already in this shape and typed. Degrades to []
        # when unconfigured.
        return list(FabricEmployeesAdapter().rows())

    if not _PAY_PERIODS_CSV.exists():
        return []
    rows: list[dict[str, Any]] = []
    with _PAY_PERIODS_CSV.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            row["Tax_Year"] = int(row["Tax_Year"])
            row["Hours_Worked"] = float(row["Hours_Worked"])
            row["Gross_Wages"] = float(row["Gross_Wages"])
            rows.append(row)
    return rows


def load_portfolio_pay_periods() -> dict[int, list[dict[str, Any]]]:
    """Every tenant's rows, keyed by account id — the portfolio scope.

    Rows stay **partitioned by tenant** rather than concatenated. A single flat
    list would make it trivially easy to sum one client's headcount into
    another's, and headcount is what the credit is computed from. A caller who
    wants a cross-client figure has to aggregate deliberately.

    Sources without a tenant dimension return a single partition, so callers do
    not branch on the data source.
    """
    from tools.fabric_source import active_data_source

    if active_data_source() != "lakehouse":
        rows = load_pay_periods()
        return {configured_account_id(): rows} if rows else {}

    from data.source.from_fabric import FabricLakehouseReader

    reader = FabricLakehouseReader()
    out: dict[int, list[dict[str, Any]]] = {}
    for account in reader.list_accounts():
        account_id = int(account["AccountId"])
        rows = reader.bcs_rows(account_id)
        if rows:
            out[account_id] = rows
    return out
