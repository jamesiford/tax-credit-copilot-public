"""The tenant-scoped query helper and the write-conflict retry. [DATA-3, DATA-4]

All against fakes: the point is that a statement that could cross tenants is
refused before it reaches a cursor, and that a conflict is retried while any
other error is not.
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from infrastructure.persistence import tenant_sql as ts


class Cursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=None):
        self.log.append(("execute", sql, params))
        return self

    def executemany(self, sql, rows):
        self.log.append(("executemany", sql, rows))
        return self

    def close(self):
        pass


# ------------------------------------------------------------------ binding


def test_the_tenant_marker_becomes_a_bound_client_predicate():
    sql, params = ts.TenantScopedQuery(42).bind(
        "SELECT * FROM t WHERE {tenant} AND year = ? AND code IN (?, ?)", [2024, "A", "B"]
    )
    assert sql == "SELECT * FROM t WHERE client_id = ? AND year = ? AND code IN (?, ?)"
    assert params == [42, 2024, "A", "B"]


def test_parameters_before_the_marker_keep_their_position():
    sql, params = ts.TenantScopedQuery(7).bind(
        "UPDATE t SET effective_to = ? WHERE {tenant} AND code = ?", ["2026-01-01", "GA"]
    )
    assert sql == "UPDATE t SET effective_to = ? WHERE client_id = ? AND code = ?"
    assert params == ["2026-01-01", 7, "GA"]


def test_an_aliased_marker_in_a_join_binds_each_side():
    sql, params = ts.TenantScopedQuery(5).bind(
        "SELECT * FROM a JOIN b ON {tenant:b} AND b.k = a.k WHERE {tenant:a} AND a.y = ?", [2024]
    )
    assert sql == "SELECT * FROM a JOIN b ON b.client_id = ? AND b.k = a.k WHERE a.client_id = ? AND a.y = ?"
    assert params == [5, 5, 2024]


def test_a_question_mark_inside_a_string_literal_is_not_a_parameter():
    sql, params = ts.TenantScopedQuery(1).bind("SELECT '?' AS q FROM t WHERE {tenant} AND x = ?", [9])
    assert params == [1, 9]


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM t",                                  # no predicate at all
        "SELECT * FROM t WHERE year = ? AND {tenant}",      # not the FIRST term
        "SELECT * FROM t WHERE ({tenant}) AND year = ?",    # wrapped: not anchored
        "SELECT * FROM t WHERE client_id = ? AND year = ?", # hand-written, unbound by the helper
    ],
)
def test_a_statement_that_could_cross_tenants_is_refused(sql):
    with pytest.raises(ts.TenantScopeViolation):
        ts.TenantScopedQuery(1).bind(sql, [2024] if sql.count("?") == 1 else [1, 2024])


def test_a_parameter_count_mismatch_is_refused():
    with pytest.raises(ts.TenantScopeViolation, match="parameter"):
        ts.TenantScopedQuery(1).bind("SELECT * FROM t WHERE {tenant} AND y = ?", [])


@pytest.mark.parametrize("bad", [None, "42", 4.2, True])
def test_the_tenant_must_be_an_integer(bad):
    with pytest.raises(ts.TenantScopeViolation):
        ts.TenantScopedQuery(bad)


def test_execute_runs_the_bound_statement():
    log = []
    ts.TenantScopedQuery(3).execute(Cursor(log), "DELETE FROM t WHERE {tenant}")
    assert log == [("execute", "DELETE FROM t WHERE client_id = ?", [3])]


# ------------------------------------------------------------------ inserts


def test_insert_writes_only_this_clients_rows():
    log = []
    q = ts.TenantScopedQuery(3)
    assert q.insert(Cursor(log), "ops.t", ["id", "client_id"], [["a", 3]]) == 1
    assert log == [("execute", "INSERT INTO ops.t (id, client_id) VALUES (?, ?)", ["a", 3])]
    assert q.insert(Cursor(log), "ops.t", ["id", "client_id"], [["b", 3], ["c", 3]]) == 2
    assert log[-1][0] == "executemany"
    assert q.insert(Cursor(log), "ops.t", ["id", "client_id"], []) == 0


def test_insert_refuses_another_clients_row_or_no_client_column():
    q = ts.TenantScopedQuery(3)
    with pytest.raises(ts.TenantScopeViolation, match="refusing"):
        q.insert(Cursor([]), "ops.t", ["id", "client_id"], [["a", 3], ["b", 4]])
    with pytest.raises(ts.TenantScopeViolation, match="no client_id"):
        q.insert(Cursor([]), "ops.t", ["id"], [["a"]])


# ---------------------------------------------------------------- exemption


def test_an_exemption_needs_a_reason_and_logs_every_use(caplog):
    with pytest.raises(ts.TenantScopeViolation):
        ts.tenant_exempt("  ")
    log = []
    exempt = ts.tenant_exempt("portfolio spans clients")
    with caplog.at_level(logging.INFO, logger="tcc.tenant_sql"):
        exempt.execute(Cursor(log), "SELECT * FROM t WHERE y = ?", [2024])
        exempt.execute(Cursor(log), "SELECT 1")
    assert log == [("execute", "SELECT * FROM t WHERE y = ?", [2024]), ("execute", "SELECT 1", None)]
    assert [r.message for r in caplog.records].count("tenant-exempt SQL (portfolio spans clients): SELECT 1") == 1
    assert sum("portfolio spans clients" in r.message for r in caplog.records) == 2


# -------------------------------------------------------------------- retry


class ConflictError(Exception):
    pass


class Conn:
    def __init__(self, failures):
        self.failures = list(failures)
        self.commits = 0
        self.rollbacks = 0
        self.autocommit = True

    def cursor(self):
        return Cursor([])

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


FABRIC_CONFLICT = ConflictError(
    "40001",
    "[40001] [Microsoft][ODBC Driver 18 for SQL Server][SQL Server]Snapshot isolation transaction "
    "aborted due to update conflict. Using snapshot isolation to access table 'program_claim' "
    "directly or indirectly in database 'wh' can cause update conflicts (24556) (SQLExecDirectW)",
)


@pytest.mark.parametrize(
    "error, expected",
    [
        (FABRIC_CONFLICT, True),
        (ConflictError("40001", "[SQL Server]Transaction was deadlocked ... (1205)"), True),
        (ConflictError("40001", "[SQL Server]... update conflict ... (3960)"), True),
        (ConflictError("42S02", "[SQL Server]Invalid object name 'x'. (208)"), False),
        (ValueError("bad input"), False),
    ],
)
def test_write_conflicts_are_recognised_by_number_and_message(error, expected):
    assert ts.is_write_conflict(error) is expected


def test_a_conflict_is_retried_with_capped_backoff_then_commits():
    conn = Conn([])
    calls = {"n": 0}
    sleeps: list[float] = []

    def work(cursor):
        calls["n"] += 1
        if calls["n"] < 4:
            raise FABRIC_CONFLICT
        return "ok"

    assert ts.run_in_transaction(conn, work, sleep=sleeps.append) == "ok"
    assert calls["n"] == 4 and conn.commits == 1 and conn.rollbacks == 3
    assert sleeps == [0.2, 0.4, 0.8]
    assert conn.autocommit is True, "the connection's mode is restored"


def test_retries_stop_at_five_attempts():
    conn = Conn([])
    sleeps: list[float] = []

    def work(cursor):
        raise FABRIC_CONFLICT

    with pytest.raises(ConflictError):
        ts.run_in_transaction(conn, work, sleep=sleeps.append)
    assert len(sleeps) == 4 and conn.commits == 0 and conn.rollbacks == 5
    assert max(sleeps) <= 3.2


def test_any_other_error_is_raised_at_once_and_rolled_back():
    conn = Conn([])
    sleeps: list[float] = []

    def work(cursor):
        raise ValueError("not a conflict")

    with pytest.raises(ValueError):
        ts.run_in_transaction(conn, work, sleep=sleeps.append)
    assert sleeps == [] and conn.rollbacks == 1 and conn.commits == 0


# ---------------------------------------------- the Warehouse adapters' SQL


class RecordingConnection:
    """A Warehouse stand-in that records statements and serves canned rows."""

    def __init__(self, rows=None, fail_times=0):
        self.statements: list[tuple[str, list]] = []
        self.rows = rows or []
        self.fail_times = fail_times
        self.autocommit = False
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        outer = self

        class C:
            description = None

            def execute(self, sql, params=None):
                outer.statements.append((sql, list(params or [])))
                if outer.fail_times and sql.startswith("INSERT"):
                    outer.fail_times -= 1
                    raise FABRIC_CONFLICT
                if sql.lstrip().startswith("SELECT"):
                    # pyodbc sets a description for ANY select, empty or not.
                    self.description = [(k,) for k in (outer.rows[0] if outer.rows else {"c": None})]
                return self

            def executemany(self, sql, rows):
                outer.statements.append((sql, rows))

            def fetchall(self):
                return [tuple(r.values()) for r in outer.rows]

            def close(self):
                pass

        return C()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakeWarehouse:
    def __init__(self, conn):
        self.conn = conn

    @contextmanager
    def connect(self):
        yield self.conn


def test_the_claim_write_is_close_then_insert_in_one_retried_transaction(monkeypatch):
    from domain.claims import ClaimStatus, ProgramClaim, Provenance
    from infrastructure.persistence import tenant_sql
    from infrastructure.persistence.warehouse_claims import WarehouseClaimRepository

    monkeypatch.setattr(tenant_sql.time, "sleep", lambda s: None)
    conn = RecordingConnection(fail_times=1)
    repo = WarehouseClaimRepository(connection=FakeWarehouse(conn))
    claim = ProgramClaim(
        client_id=11, program_code="GA_JTC", tax_year=2024, status=ClaimStatus.ASSESSED,
        provenance=Provenance.COMPUTED, identified_usd=Decimal("10"), is_base_year=True,
        effective_from=datetime(2026, 3, 1, 12, tzinfo=timezone.utc),
    )
    repo.record(claim)

    kinds = [s.split()[0] for s, _ in conn.statements]
    assert kinds == ["UPDATE", "INSERT", "UPDATE", "INSERT"], "the conflict re-ran close AND insert"
    assert conn.rollbacks == 1 and conn.commits == 1
    update_sql, update_params = conn.statements[0]
    assert "WHERE client_id = ? AND program_code = ?" in update_sql
    assert update_params[1] == 11
    insert_sql, insert_params = conn.statements[-1]
    assert "is_base_year" in insert_sql and True in insert_params


def test_portfolio_coverage_is_the_logged_exemption(caplog):
    from infrastructure.persistence.warehouse_claims import WarehouseClaimRepository

    conn = RecordingConnection()
    repo = WarehouseClaimRepository(connection=FakeWarehouse(conn))
    with caplog.at_level(logging.INFO, logger="tcc.tenant_sql"):
        assert repo.portfolio_coverage(client_ids=[1, 2]) == []
    assert any("portfolio coverage spans clients" in r.message for r in caplog.records)
    assert "client_id IN (?, ?)" in conn.statements[0][0]


def test_money_comes_back_in_its_shortest_exact_form():
    from infrastructure.persistence.warehouse_claims import from_db_money

    assert str(from_db_money(Decimal("31000.0000"))) == "31000"
    assert str(from_db_money(Decimal("31500.2500"))) == "31500.25"
    assert str(from_db_money(None)) == "0"
