"""A database whose groups have chosen sizes, for the small-group rule. [RM-01]

`tests/data_fixture.py` holds two people per client, which cannot show a group of five being kept
and a group of four being left out. This builds the shared database and then rewrites ONE client's
rows in the employee-level tables so each worksite holds exactly the people a test names.
"""
from __future__ import annotations

import sqlite3
from typing import Any

from application.channel_wiring import set_writer_entitlement
from application.data.limits import QueryLimits
from application.data.semantic_model import Source
from application.data.service import DataQueryService
from application.data_wiring import set_data_query_service
from infrastructure.persistence.sqlite_data_query import SqliteDataQueryExecutor
from tests.data_caps_fixture import MODEL, Writers
from tests.data_fixture import CLIENT_A, build_database

#: Worksite -> people. W-EDGE is exactly K; W-ONE and W-TWO are the singletons.
WORKSITES = {"W-BIG": 6, "W-EDGE": 5, "W-SMALL": 3, "W-ONE": 1, "W-TWO": 1}
RUN = f"run-{CLIENT_A}"


def _template(conn: sqlite3.Connection, table: str, where: str) -> dict[str, Any]:
    cursor = conn.execute(f"SELECT * FROM {table} WHERE {where} LIMIT 1")
    return dict(zip([d[0] for d in cursor.description], cursor.fetchone()))


def _replace(conn: sqlite3.Connection, table: str, where: str, rows: list[dict[str, Any]]) -> None:
    conn.execute(f"DELETE FROM {table} WHERE {where}")
    columns = list(rows[0])
    conn.executemany(
        f"INSERT INTO {table} ({', '.join(chr(34) + c + chr(34) for c in columns)}) VALUES ({', '.join('?' for _ in columns)})",
        [[r[c] for c in columns] for r in rows],
    )


def people(worksites: dict[str, int] = WORKSITES) -> list[tuple[str, int, str]]:
    """`(worksite, person number, person id)` for every person, numbered across the whole client."""
    out, n = [], 0
    for site, count in worksites.items():
        for _ in range(count):
            n += 1
            out.append((site, n, f"emp-{n:03d}"))
    return out


def populate(conn: sqlite3.Connection) -> sqlite3.Connection:
    """Rewrite client A's One/Zero matrix, pay-period fact and payroll so groups have the sizes above."""
    where = f"client_id = {CLIENT_A} AND run_id = '{RUN}'"
    base = _template(conn, "tcc_gold.onezero_matrix", where)
    matrix = [
        {**base, "employee_id": pid, "record_token": f"tok-{n:03d}", "worksite_id": site, "method": "min_max",
         "tax_year": 2023, "weight": 1.0 if n % 3 else 0.5}
        for site, n, pid in people()
    ]
    _replace(conn, "tcc_gold.onezero_matrix", where, matrix)
    fact = _template(conn, "tcc_gold.employee_period_fact", where)
    # W-SMALL: three people with four pay periods each, so twelve ROWS but only three PEOPLE.
    facts = [
        {**fact, "employee_id": pid, "record_token": f"tok-{n:03d}", "worksite_id": site, "tax_year": 2023,
         "pay_period_start": f"2023-0{period}-01"}
        for site, n, pid in people() for period in range(1, 5 if site == "W-SMALL" else 2)
    ]
    _replace(conn, "tcc_gold.employee_period_fact", where, facts)
    _populate_payroll(conn)
    return conn


def _populate_payroll(conn: sqlite3.Connection) -> None:
    """Payroll rows paid in 2022 (three people) and 2023 (six): the derived `pay_year` groups them."""
    where = f"AccountId = {CLIENT_A}"
    base = _template(conn, "tcc_source.Payroll", where)
    rows = [{**base, "EmployeeId": n, "PayDate": f"{2022 if n <= 3 else 2023}-06-15"} for n in range(1, 10)]
    _replace(conn, "tcc_source.Payroll", where, rows)


def make_service(min_group_size: int | None = None) -> DataQueryService:
    """The real service over the sized database; K is the default 5 unless a test says otherwise."""
    executor = SqliteDataQueryExecutor(lambda db=populate(build_database(MODEL)): db)
    limits = QueryLimits() if min_group_size is None else QueryLimits(min_group_size=min_group_size)
    return DataQueryService(MODEL, {Source.WAREHOUSE: executor, Source.LAKEHOUSE: executor}, limits=limits)


def install(min_group_size: int | None = None) -> DataQueryService:
    """Make the sized service the process's, with the shared writer entitlement."""
    service = make_service(min_group_size)
    set_data_query_service(service)
    set_writer_entitlement(Writers())
    return service
