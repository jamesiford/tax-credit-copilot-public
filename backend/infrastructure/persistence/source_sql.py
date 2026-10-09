"""Aggregate reads over the source tables, in SQL rather than in Python.

The lakehouse Delta files are reachable two ways, and the difference is not
small. `data/source/from_fabric.py` opens them with `deltalake` over
`abfss://onelake...`, which on this capacity takes ~132s cold and has been seen
to exceed the 120s `object_store` budget outright. The Fabric SQL endpoint reads
the *same files* and counts all 384,433 payroll rows for the reference client in
169ms. Same bytes, same capacity, two access paths, three orders of magnitude.

So this is not a copy of the data and no data was moved. It is the second route
to it, used for the questions that are aggregates.

**Why this exists at all.** `load_pay_periods` materialises every payroll row as
a 17-key dict — 384,433 of them, ~3s of pure CPU and ~292MB, on every call, and
it is called from 20+ places. `/api/scope/client/{id}` paid that to answer three
questions it could have asked in one `GROUP BY`. Worse, the projection is
GIL-bound: four threads take 3.6x as long as one, so concurrent requests do not
overlap and a cheap neighbouring call gets starved behind them.

The engine still reads full rows, and must — the certified calculation is pure
functions over lists of dicts [ADR-003] and every statutory rule needs the row
grain. This is for the read paths that only ever wanted a `DISTINCT`.

**The projection semantics are reproduced here, not reinvented.** Where this
disagrees with `source_to_bcs_rows` the answer changes, so each rule is matched
deliberately and noted. `tests/test_source_sql_scope.py` asserts the two agree.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from config import SOURCE_SCHEMA
from infrastructure.persistence.fabric_warehouse import (
    FabricWarehouseConnection,
    WarehouseNotConfigured,
)


@dataclass(frozen=True, slots=True)
class PayrollScope:
    """What `/api/scope/client/{id}` needs, and nothing else.

    `pay_dates` is DISTINCT dates, not rows: the coverage calculation buckets
    them by month inside a fiscal window, and two years of payroll has a few
    hundred distinct dates against a third of a million rows.
    """

    total_rows: int
    tax_years: list[int]
    states: list[str]
    pay_dates: list[str]


#: `source_to_bcs_rows` skips a period with no span, so the row population this
#: aggregates over has to skip it too or the totals disagree.
_HAS_SPAN = "p.PayPeriodStart IS NOT NULL AND p.PayPeriodEnd IS NOT NULL"

#: `Tax_Year` in the projection is the pay date's year, falling back to the
#: period end when the pay date is null (Q1).
_TAX_YEAR = "YEAR(COALESCE(p.PayDate, p.PayPeriodEnd))"

#: The projection resolves state through Location -> Address -> StateCountyZip
#: with a Python `or` chain, which treats '' as missing. `COALESCE` treats only
#: NULL as missing, so the empty strings are nulled out first to match.
_STATE = "UPPER(COALESCE(NULLIF(s.StateAbbr, ''), NULLIF(a.StateOriginal, ''), ''))"

#: Q3: `WorksiteLocationId` is nullable, `LocationId` is not.
_LOCATION = "COALESCE(p.WorksiteLocationId, p.LocationId)"

#: One connection instance for the process, so `scope()` can span the several
#: readers a single endpoint builds. `scope()` keys off `threading.local` on the
#: INSTANCE, so separate instances each open their own link and the sharing
#: silently does nothing.
_SHARED_CONNECTION: FabricWarehouseConnection | None = None

#: The client book and the fiscal calendars are slow-changing DIMENSIONS — they
#: move when someone reloads the lakehouse, not per request — so they get the
#: same process-lifetime cache `_DATASET_CACHE` already uses for Delta reads.
#: Without it, `client_scope` spent 5.9s asking for one client's fiscal rule
#: seven times, once per priceable year, and 0.8s re-reading the book it had
#: already read to validate the account id.
#:
#: The payroll aggregate is deliberately NOT cached. It is the answer, not a
#: dimension, and it is one 143-row round trip.
_ACCOUNTS_CACHE: dict[str, list[dict[str, Any]]] = {}
_FISCAL_CACHE: dict[tuple[str, int], list[Any]] = {}
_FOOTPRINT_CACHE: dict[str, dict[int, list[str]]] = {}


def clear_cache() -> None:
    """Drop the dimension caches. The reload path, and tests."""
    _ACCOUNTS_CACHE.clear()
    _FISCAL_CACHE.clear()
    _FOOTPRINT_CACHE.clear()


def shared_connection() -> FabricWarehouseConnection:
    global _SHARED_CONNECTION
    if _SHARED_CONNECTION is None:
        _SHARED_CONNECTION = FabricWarehouseConnection()
    return _SHARED_CONNECTION


@contextmanager
def shared_scope() -> Iterator[None]:
    """One connection for an endpoint, or nothing at all when it cannot be used.

    Gated on the active data source as well as configuration. The warehouse
    credentials outlive a switch to the CSV fixture, so `is_configured()` alone
    stays true and the scope opens a connection the request will never read —
    which in the test suite is a login timeout on a wholly offline test.

    `FabricWarehouseConnection.scope()` opens eagerly and raises without a
    server, so an unguarded `with` here would 500 every CSV-backed request.
    """
    from tools.fabric_source import active_data_source

    if active_data_source() != "lakehouse" or not SourceSqlReader().is_configured():
        yield
        return
    with shared_connection().scope():
        yield


class SourceSqlReader:
    """Aggregate reads over the source tables through the warehouse SQL endpoint."""

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or shared_connection()

    @property
    def lakehouse(self) -> str:
        return (os.getenv("FABRIC_LAKEHOUSE") or "").strip()

    @property
    def schema(self) -> str:
        return SOURCE_SCHEMA

    def is_configured(self) -> bool:
        """Whether a SQL read can be attempted at all.

        False is not an error: the CSV fixture and the flattened `fabric` slice
        have no lakehouse behind them, and callers fall back to the row path.
        """
        if not self.lakehouse:
            return False
        try:
            self._connection.require_configuration()
        except WarehouseNotConfigured:
            return False
        return True

    def scope(self):
        return self._connection.scope()

    def _query(self, sql: str, params: list[Any]) -> list[tuple]:
        with self._connection.connect() as live:
            cursor = live.cursor()
            try:
                cursor.execute(sql, params)
                return cursor.fetchall()
            finally:
                cursor.close()

    def list_accounts(self) -> list[dict[str, Any]]:
        """The client book."""
        cached = _ACCOUNTS_CACHE.get(self.lakehouse)
        if cached is not None:
            return cached
        rows = self._query(
            f"SELECT AccountId, Name, BillingState, ActualNumberOfEmployees, IndustryTypeId "
            f"FROM [{self.lakehouse}].[{self.schema}].[Account]",
            [],
        )
        accounts = [
            {
                "AccountId": r[0],
                "Name": r[1],
                "BillingState": r[2],
                "ActualNumberOfEmployees": r[3],
                "IndustryTypeId": r[4],
            }
            for r in rows
        ]
        _ACCOUNTS_CACHE[self.lakehouse] = accounts
        return accounts

    def payroll_scope(self, account_id: int) -> PayrollScope:
        """Years, states and pay dates for one client, in one round trip.

        Grouped rather than DISTINCT-per-column so the three answers come from
        one scan and cannot disagree about which rows they counted.

        `FORMAT()` is deliberately absent. Bucketing the month with
        `FORMAT(PayDate,'yyyy-MM')` measured 1,021ms against 346ms for the same
        query without it, on identical output — it is the single most expensive
        thing in this statement's history. The date is grouped as a date and
        rendered in Python, for the same reason.
        """
        lh = self.lakehouse
        sch = self.schema
        rows = self._query(
            f"""
            SELECT {_TAX_YEAR} AS tax_year,
                   {_STATE} AS work_state,
                   p.PayDate AS pay_date,
                   COUNT_BIG(*) AS rows_in
            FROM [{lh}].[{sch}].[Payroll] p
            LEFT JOIN [{lh}].[{sch}].[Location] l ON l.LocationId = {_LOCATION}
            LEFT JOIN [{lh}].[{sch}].[Address] a ON a.AddressId = l.AddressId
            LEFT JOIN [{lh}].[{sch}].[StateCountyZip] s
                   ON s.StateCountyZipId = a.StateCountyZipId
            WHERE p.AccountId = ? AND {_HAS_SPAN}
            GROUP BY {_TAX_YEAR}, {_STATE}, p.PayDate
            """,
            [account_id],
        )
        return PayrollScope(
            total_rows=sum(int(r[3]) for r in rows),
            tax_years=sorted({int(r[0]) for r in rows if r[0] is not None}),
            states=sorted({r[1] for r in rows if r[1]}),
            pay_dates=sorted({str(r[2])[:10] for r in rows if r[2]}),
        )

    def footprint(self) -> dict[int, list[str]]:
        """Which states each client holds payroll in — every client, one query.

        The book needs this per row, and asking `payroll_scope` per client would
        be one scan per client on an endpoint that already answers in one. It is
        cached for the process like the account list, because a payroll
        footprint does not move between requests.
        """
        cached = _FOOTPRINT_CACHE.get(self.lakehouse)
        if cached is not None:
            return cached

        lh = self.lakehouse
        sch = self.schema
        rows = self._query(
            f"""
            SELECT p.AccountId AS account_id, {_STATE} AS work_state
            FROM [{lh}].[{sch}].[Payroll] p
            LEFT JOIN [{lh}].[{sch}].[Location] l ON l.LocationId = {_LOCATION}
            LEFT JOIN [{lh}].[{sch}].[Address] a ON a.AddressId = l.AddressId
            LEFT JOIN [{lh}].[{sch}].[StateCountyZip] s
                   ON s.StateCountyZipId = a.StateCountyZipId
            WHERE {_HAS_SPAN}
            GROUP BY p.AccountId, {_STATE}
            """,
            [],
        )
        out: dict[int, list[str]] = {}
        for account_id, state in rows:
            if account_id is None or not state:
                continue
            out.setdefault(int(account_id), []).append(str(state))
        for key in out:
            out[key] = sorted(set(out[key]))
        _FOOTPRINT_CACHE[self.lakehouse] = out
        return out

    def fiscal_year_rules(self, account_id: int) -> list[Any]:
        """The client's `EntityFiscalYearRules`, reached through `Entity`.

        This one small table was costing the whole dataset. `client_fiscal_window`
        called `for_account()`, which opens ten Delta tables including 384,433
        payroll rows over OneLake — ~132s cold, and observed to exceed the 120s
        `object_store` budget outright — to read at most a handful of rows that
        say when the client's year begins.

        Ordered by key so the window chosen is stable. `client_fiscal_window`
        takes the first rule that parses, so an unstable order would be an
        unstable fiscal year, and the fiscal year decides the base year.
        """
        from data.source.schema import EntityFiscalYearRules

        key = (self.lakehouse, int(account_id))
        cached = _FISCAL_CACHE.get(key)
        if cached is not None:
            return cached

        lh = self.lakehouse
        sch = self.schema
        rows = self._query(
            f"""
            SELECT DISTINCT r.FiscalYearRulesId, r.Name, r.FiscalYearBegin,
                            r.FiscalYearEnd, r.RuleExpression, r.Inferred
            FROM [{lh}].[{sch}].[EntityFiscalYearRules] r
            JOIN [{lh}].[{sch}].[Entity] e ON e.FiscalYearRulesId = r.FiscalYearRulesId
            WHERE e.AccountId = ?
            ORDER BY r.FiscalYearRulesId
            """,
            [account_id],
        )
        rules = [
            EntityFiscalYearRules(
                fiscal_year_rules_id=r[0],
                name=r[1] or "",
                fiscal_year_begin=r[2],
                fiscal_year_end=r[3],
                rule_expression=r[4],
                inferred=bool(r[5]) if r[5] is not None else True,
            )
            for r in rows
        ]
        _FISCAL_CACHE[key] = rules
        return rules


def payroll_scope_from_rows(rows: list[dict[str, Any]]) -> PayrollScope:
    """The same shape, derived from already-materialised BCS rows.

    The fallback for the CSV fixture and the flattened `fabric` slice, and the
    thing the SQL above is tested against.
    """
    from domain.calculation.headcount import states_present

    return PayrollScope(
        total_rows=len(rows),
        tax_years=sorted({int(r["Tax_Year"]) for r in rows}),
        states=states_present(rows),
        pay_dates=sorted({str(r["Pay_Date"])[:10] for r in rows if r.get("Pay_Date")}),
    )
