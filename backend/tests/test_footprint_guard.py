"""The footprint read is guarded: size estimate first, a server-side timeout, and never a scan it should not run. [03b.2]"""
from __future__ import annotations

import pytest
from local_lakehouse import use_local_lakehouse, write_lakehouse

from application.errors import DependencyUnavailable
from application.queries import portfolio_reads
from config import load_settings, override_settings
from data.source import from_fabric
from data.source.synth import SYNTHETIC_CLIENTS, build_synthetic_dataset
from infrastructure.persistence import footprint_guard, source_sql


class _Reader:
    """Just what the guard needs of a `SourceSqlReader`: a name, table names and a query."""

    lakehouse = "lh"

    def __init__(self, result=None, error=None):
        self.result, self.error = result if result is not None else [(1, "GA"), (1, "NC"), (2, "GA"), (1, "GA")], error
        self.statements: list[tuple[str, int | None]] = []

    def _table(self, logical):
        return f"[lh].[dbo].[{logical}]"

    def _query(self, sql, params, timeout=None):
        self.statements.append((" ".join(sql.split()), timeout))
        if self.error:
            raise self.error
        return self.result

    @property
    def scans(self):
        return [s for s in self.statements if "GROUP BY" in s[0]]


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    source_sql.clear_cache()
    monkeypatch.setattr(portfolio_reads, "_footprint_failure", None)
    yield
    source_sql.clear_cache()


def _estimate(monkeypatch, rows):
    monkeypatch.setattr(footprint_guard, "_delta_rows", lambda: rows)
    monkeypatch.setattr(footprint_guard, "_catalogue_rows", lambda reader: None)


def _run(reader, mode="auto", max_rows=50_000_000, timeout=20):
    return footprint_guard.read_footprint(reader, mode=mode, max_rows=max_rows, timeout_seconds=timeout)


# ----------------------------------------------------------------- the guard


def test_a_small_table_is_read_and_the_result_is_what_it_always_was(monkeypatch):
    _estimate(monkeypatch, 384_433)
    reader = _Reader()
    assert _run(reader) == {1: ["GA", "NC"], 2: ["GA"]}
    assert len(reader.scans) == 1


def test_a_table_over_the_limit_is_not_scanned_and_says_why(monkeypatch):
    _estimate(monkeypatch, 9_344_821_235)
    reader = _Reader()
    with pytest.raises(DependencyUnavailable) as caught:
        _run(reader)
    assert reader.scans == [], "the scan was never run"
    assert caught.value.dependency == "source_sql"
    assert "9,344,821,235" in caught.value.reason and "PORTFOLIO_FOOTPRINT_MAX_ROWS" in caught.value.reason
    assert "footprint map" in caught.value.impact


def test_the_limit_is_the_setting_not_a_constant(monkeypatch):
    _estimate(monkeypatch, 1_000)
    with pytest.raises(DependencyUnavailable):
        _run(_Reader(), max_rows=999)
    assert _run(_Reader(), max_rows=1_000)


def test_with_no_estimate_it_runs_under_the_timeout(monkeypatch):
    _estimate(monkeypatch, None)
    reader = _Reader()
    _run(reader, timeout=7)
    assert reader.scans[0][1] == 7


def test_a_statement_that_times_out_is_unavailable_and_was_cancelled_by_the_driver(monkeypatch):
    _estimate(monkeypatch, None)
    reader = _Reader(error=RuntimeError("('HYT00', '[HYT00] Query timeout expired (0) (SQLExecDirectW)')"))
    with pytest.raises(DependencyUnavailable) as caught:
        _run(reader, timeout=20)
    assert "cancelled on the server" in caught.value.reason and "20s" in caught.value.reason
    assert source_sql._FOOTPRINT_CACHE == {}, "a timed-out scan caches nothing"


def test_an_error_that_is_not_a_timeout_is_left_to_the_caller(monkeypatch):
    _estimate(monkeypatch, None)
    with pytest.raises(RuntimeError, match="boom"):
        _run(_Reader(error=RuntimeError("boom")))


def test_off_never_estimates_and_never_scans(monkeypatch):
    def forbidden():
        raise AssertionError("the estimate was consulted")

    monkeypatch.setattr(footprint_guard, "_delta_rows", forbidden)
    reader = _Reader()
    with pytest.raises(DependencyUnavailable) as caught:
        _run(reader, mode="off")
    assert reader.statements == [] and "PORTFOLIO_FOOTPRINT_MODE=off" in caught.value.reason


def test_on_always_runs_under_the_timeout_without_asking_for_an_estimate(monkeypatch):
    monkeypatch.setattr(footprint_guard, "_delta_rows", lambda: (_ for _ in ()).throw(AssertionError("estimated")))
    reader = _Reader()
    _run(reader, mode="on", max_rows=1, timeout=5)
    assert reader.scans[0][1] == 5


def test_a_cached_footprint_is_returned_without_any_check(monkeypatch):
    _estimate(monkeypatch, None)
    _run(_Reader())
    monkeypatch.setattr(footprint_guard, "_delta_rows", lambda: 10**12)
    again = _Reader()
    assert _run(again) == {1: ["GA", "NC"], 2: ["GA"]} and again.statements == []


# ---------------------------------------------------------------- the estimate


def test_the_catalogue_estimate_is_none_when_the_endpoint_cannot_say():
    assert footprint_guard._catalogue_rows(_Reader(error=RuntimeError("Invalid object name 'sys.dm_db_partition_stats'"))) is None
    assert footprint_guard._catalogue_rows(_Reader(result=[(None,)])) is None
    assert footprint_guard._catalogue_rows(_Reader(result=[(12345,)])) == 12345


def test_the_delta_estimate_wins_and_the_catalogue_is_the_fallback(monkeypatch):
    monkeypatch.setattr(footprint_guard, "_delta_rows", lambda: 5)
    monkeypatch.setattr(footprint_guard, "_catalogue_rows", lambda r: 9)
    assert footprint_guard.estimated_payroll_rows(_Reader()) == 5
    monkeypatch.setattr(footprint_guard, "_delta_rows", lambda: None)
    assert footprint_guard.estimated_payroll_rows(_Reader()) == 9


def test_the_delta_log_statistics_give_the_row_count_without_reading_data(tmp_path, monkeypatch):
    dataset = build_synthetic_dataset(SYNTHETIC_CLIENTS[0])
    write_lakehouse(tmp_path, dataset, schema="dbo")
    use_local_lakehouse(monkeypatch, tmp_path)
    reader = from_fabric.FabricLakehouseReader(workspace="ws", lakehouse="lh", schema="dbo")
    assert reader.table_row_estimate("Payroll") == len(dataset.payroll)
    monkeypatch.setattr(from_fabric.FabricLakehouseReader, "_read", lambda *a, **k: (_ for _ in ()).throw(AssertionError("data read")))
    assert reader.table_row_estimate("Payroll") == len(dataset.payroll), "cached, and still no data read"


# ----------------------------------------------------- the real reader and settings


class _Cursor:
    """Like pyodbc's: it has no `timeout` attribute, and takes the connection's limit when it is created."""

    __slots__ = ("limit",)
    seen: tuple | None = None

    def __init__(self, limit):
        self.limit = limit

    def execute(self, sql, params):
        type(self).seen = (self.limit, sql)

    def fetchall(self):
        return []

    def close(self):
        pass


class _Live:
    """Like pyodbc's connection: `timeout` is a connection property, read when a cursor is created."""

    def __init__(self):
        self.timeout = 0
        self.history = []

    def cursor(self):
        self.history.append(self.timeout)
        return _Cursor(self.timeout)


class _Connection:
    def __init__(self):
        self.live = _Live()

    def connect(self):
        import contextlib

        @contextlib.contextmanager
        def ctx():
            yield self.live

        return ctx()


def test_the_statement_timeout_is_set_on_the_connection_before_the_cursor_and_reset_after():
    connection = _Connection()
    reader = source_sql.SourceSqlReader(connection=connection)
    reader._query("SELECT 1", [], timeout=20)
    assert _Cursor.seen[0] == 20, "the cursor was created with the limit, so the driver cancels on the server"
    assert connection.live.timeout == 0, "the pooled connection must not keep the limit"
    reader._query("SELECT 1", [])
    assert _Cursor.seen[0] == 0, "no timeout unless asked for"


def test_the_connection_limit_is_reset_even_when_the_statement_fails():
    connection = _Connection()

    class _Boom(_Cursor):
        __slots__ = ()

        def execute(self, sql, params):
            raise RuntimeError("HYT00 Query timeout expired")

    connection.live.cursor = lambda: _Boom(connection.live.timeout)
    reader = source_sql.SourceSqlReader(connection=connection)
    try:
        reader._query("SELECT 1", [], timeout=5)
    except RuntimeError:
        pass
    assert connection.live.timeout == 0


def test_the_defaults_and_bad_values():
    portfolio = load_settings({}).portfolio
    assert (portfolio.footprint_mode, portfolio.footprint_max_rows, portfolio.footprint_timeout_seconds) == ("auto", 50_000_000, 20)
    assert load_settings({"PORTFOLIO_FOOTPRINT_MODE": " OFF "}).portfolio.footprint_mode == "off"
    for bad in ({"PORTFOLIO_FOOTPRINT_MODE": "maybe"}, {"PORTFOLIO_FOOTPRINT_MAX_ROWS": "0"},
                {"PORTFOLIO_FOOTPRINT_TIMEOUT_SECONDS": "-3"}, {"PORTFOLIO_FOOTPRINT_MAX_ROWS": "lots"}):
        with pytest.raises(ValueError):
            load_settings(bad).portfolio


# ------------------------------------------------ the application's use of it


class _SqlReader:
    def __init__(self, behaviour):
        self.behaviour, self.calls = behaviour, []

    def is_configured(self):
        return True

    def footprint(self, **kwargs):
        self.calls.append(kwargs)
        return self.behaviour()


@pytest.fixture
def lakehouse(monkeypatch):
    monkeypatch.setattr("tools.fabric_source.active_data_source", lambda: "lakehouse")


def _install(monkeypatch, reader):
    monkeypatch.setattr("application.source_ports.new_source_reader", lambda: reader)


def test_the_settings_reach_the_reader(lakehouse, monkeypatch):
    reader = _SqlReader(lambda: {1: ["GA"]})
    _install(monkeypatch, reader)
    with override_settings({"PORTFOLIO_FOOTPRINT_MODE": "on", "PORTFOLIO_FOOTPRINT_MAX_ROWS": "9", "PORTFOLIO_FOOTPRINT_TIMEOUT_SECONDS": "3"}):
        assert portfolio_reads.footprint() == {1: ["GA"]}
    assert reader.calls == [{"mode": "on", "max_rows": 9, "timeout_seconds": 3}]


def _refuse():
    raise DependencyUnavailable("source_sql", "too big.", "Raise the limit.", impact="map empty")


def test_a_guard_decision_is_not_retried_for_an_hour(lakehouse, monkeypatch):
    reader = _SqlReader(_refuse)
    _install(monkeypatch, reader)
    for _ in range(3):
        with pytest.raises(DependencyUnavailable):
            portfolio_reads.footprint()
    assert len(reader.calls) == 1
    assert portfolio_reads._footprint_failure[1] == portfolio_reads.FOOTPRINT_GUARD_RETRY_SECONDS


def test_an_ordinary_failure_is_retried_after_a_minute(lakehouse, monkeypatch):
    reader = _SqlReader(lambda: (_ for _ in ()).throw(OSError("connection timed out")))
    _install(monkeypatch, reader)
    with pytest.raises(DependencyUnavailable):
        portfolio_reads.footprint()
    assert portfolio_reads._footprint_failure[1] == portfolio_reads.FOOTPRINT_RETRY_SECONDS


def test_the_portfolio_says_the_footprint_is_unavailable_and_still_answers(lakehouse, monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from bootstrap import wiring
    from infrastructure.persistence.sqlite_claims import SqliteClaimRepository
    from main import app

    monkeypatch.setattr("application.client_book.clients", lambda: [{"account_id": 1, "name": "A", "industry": None}])
    _install(monkeypatch, _SqlReader(_refuse))
    repo = SqliteClaimRepository(tmp_path / "c.db")
    wiring.set_claim_repository(repo)
    try:
        body = TestClient(app).get("/api/v2/portfolio").json()
    finally:
        repo.close()
        wiring.set_claim_repository(None)
    (entry,) = body["degraded"]
    assert entry["dependency"] == "source_sql" and entry["impact"] == "map empty" and body["total"] == 1
    assert body["items"][0]["states"] == []
