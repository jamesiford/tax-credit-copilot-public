"""The warehouse port, its two adapters, and the connection that authenticates.

Everything here except the last test runs with no ODBC driver, no Azure
credential and no Fabric capacity. The live round trip is opt-in behind
`TCC_FABRIC_TESTS=1`, so CI never needs a warehouse.
"""
from __future__ import annotations

import os
import struct
import time
import uuid
from datetime import date, datetime, timezone

import pytest

from domain.warehouse import RunManifest
from infrastructure.persistence.fabric_warehouse import (
    FabricWarehouseConnection,
    WarehouseNotConfigured,
)
from infrastructure.persistence.memory_runs import InMemoryRunManifestRepository


def _requires_fabric():
    if os.getenv("TCC_FABRIC_TESTS") != "1":
        pytest.skip("set TCC_FABRIC_TESTS=1 to run tests that reach live Fabric")


def _manifest(**overrides) -> RunManifest:
    base = {
        "run_id": uuid.uuid4().hex,
        "client_id": 1001,
        "program_code": "GA_JTC",
        "tax_year": 2023,
        "fiscal_year_begin": date(2023, 7, 28),
        "fiscal_year_end": date(2024, 7, 31),
        "run_started_at": datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc),
        "run_status": "success",
    }
    base.update(overrides)
    return RunManifest(**base)


# --- the value object polices what the warehouse will not ------------------


def test_run_status_is_checked_here_because_fabric_does_not_enforce_it():
    with pytest.raises(ValueError, match="run_status"):
        _manifest(run_status="finished")


def test_a_fiscal_window_must_move_forwards():
    with pytest.raises(ValueError, match="fiscal window"):
        _manifest(fiscal_year_begin=date(2024, 7, 31), fiscal_year_end=date(2023, 7, 28))


# --- the in-memory adapter honours the same contract -----------------------


def test_memory_adapter_round_trips_a_manifest():
    repo = InMemoryRunManifestRepository()
    manifest = _manifest()

    assert repo.count() == 0
    repo.record(manifest)

    assert repo.count() == 1
    assert repo.get(manifest.run_id) == manifest
    assert repo.get("never-recorded") is None


def test_memory_adapter_refuses_a_duplicate_run_id():
    repo = InMemoryRunManifestRepository()
    manifest = _manifest()
    repo.record(manifest)

    with pytest.raises(ValueError, match="already recorded"):
        repo.record(manifest)


def test_the_stand_in_admits_it_is_not_durable():
    """The whole reason a memory default is tolerable is that it says so."""
    from infrastructure.persistence.fabric_warehouse import FabricRunManifestRepository

    assert InMemoryRunManifestRepository.is_durable is False
    assert FabricRunManifestRepository.is_durable is True


# --- connection: configuration and the token dance -------------------------


def test_the_adapter_refuses_to_guess_where_the_warehouse_is(monkeypatch):
    monkeypatch.delenv("WAREHOUSE_SERVER", raising=False)
    monkeypatch.delenv("WAREHOUSE_DATABASE", raising=False)

    with pytest.raises(WarehouseNotConfigured, match="WAREHOUSE_SERVER"):
        FabricWarehouseConnection().connection_string()


def test_the_connection_string_carries_no_credential():
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")
    rendered = connection.connection_string()

    assert "ODBC Driver 18 for SQL Server" in rendered
    assert "example.com,1433" in rendered
    assert "Encrypt=Yes" in rendered
    # The token travels as attribute 1256. Anything resembling a secret in the
    # string itself would end up in a connection log.
    for leaked in ("Pwd", "Password", "Authentication=", "token"):
        assert leaked not in rendered


class _PoolConnection:
    def __init__(self, log):
        self._log = log
        self.rollbacks = 0

    def rollback(self):
        # Parking a connection ends its read transaction, or the pool would hand
        # on a pinned snapshot. See tests/test_pool_snapshot.py.
        self.rollbacks += 1

    def close(self):
        self._log.append(self)


def _pooled(monkeypatch, opened):
    """A connection whose `open` is counted and whose pool starts empty."""
    from infrastructure.persistence import fabric_warehouse as fw

    monkeypatch.setattr(fw, "_POOL", [])
    closed = []
    monkeypatch.setattr(
        FabricWarehouseConnection,
        "open",
        lambda self: (opened.append(1), _PoolConnection(closed))[1],
    )
    return closed


def test_a_scope_returns_its_connection_to_the_pool_rather_than_closing_it(monkeypatch):
    """Opening per request is the whole problem.

    Measured against this warehouse: six threads opening at once cost 6.1-6.8s
    EACH, while borrowing an already-open link costs 122ms. A page fires three
    or four requests at once, so a connection per request is a storm on every
    navigation — fast for one person, nine seconds for the next.
    """
    opened = []
    closed = _pooled(monkeypatch, opened)
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")

    with connection.scope():
        pass
    with connection.scope():
        pass
    with connection.scope():
        pass

    assert len(opened) == 1, "the second and third scopes must borrow, not build"
    assert closed == [], "a healthy connection is returned, never closed"


def test_the_pool_is_bounded_so_it_cannot_exhaust_the_server(monkeypatch):
    """Fabric answers 'maximum allowed connections' and drops the link."""
    from infrastructure.persistence import fabric_warehouse as fw

    opened = []
    closed = _pooled(monkeypatch, opened)
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")

    live = [connection.open() for _ in range(fw._POOL_MAX_IDLE + 3)]
    for one in live:
        connection.release(one)

    assert len(fw._POOL) == fw._POOL_MAX_IDLE
    assert len(closed) == 3, "the surplus is closed rather than hoarded"


def test_a_connection_whose_scope_failed_is_discarded_not_reused(monkeypatch):
    """Returning a link that just errored hands the fault to the next request."""
    from infrastructure.persistence import fabric_warehouse as fw

    opened = []
    closed = _pooled(monkeypatch, opened)
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")

    with pytest.raises(RuntimeError):
        with connection.scope():
            raise RuntimeError("the link died mid-read")

    assert fw._POOL == [], "a suspect connection must not go back in the pool"
    assert len(closed) == 1


def test_a_stale_pooled_connection_is_rebuilt_rather_than_gambled_on(monkeypatch):
    """Fabric closes idle links server-side."""
    from infrastructure.persistence import fabric_warehouse as fw

    opened = []
    closed = _pooled(monkeypatch, opened)
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")
    stale = connection.open()
    fw._POOL.append((stale, time.time() - fw._POOL_MAX_AGE_S - 1))

    borrowed = connection.acquire()

    assert borrowed is not stale
    assert stale in closed


def test_a_nested_scope_does_not_release_the_connection_it_borrowed(monkeypatch):
    """The outer scope owns the lifetime; an inner one must not return it early."""
    from infrastructure.persistence import fabric_warehouse as fw

    opened = []
    _pooled(monkeypatch, opened)
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")

    with connection.scope() as outer:
        with connection.scope() as inner:
            assert inner is outer
        assert fw._POOL == [], "the inner scope released a connection it did not own"
    assert len(fw._POOL) == 1
    assert len(opened) == 1


def test_prewarm_fills_the_pool_one_connection_at_a_time(monkeypatch):
    """Serially, at startup. It is the CONCURRENT opens that cost 6-7s each."""
    from infrastructure.persistence import fabric_warehouse as fw

    opened = []
    _pooled(monkeypatch, opened)
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")

    assert connection.prewarm(3) == 3
    assert len(fw._POOL) == 3


def test_prewarm_gives_up_quietly_when_the_warehouse_will_not_answer(monkeypatch):
    """A cold capacity must not block startup."""
    from infrastructure.persistence import fabric_warehouse as fw

    monkeypatch.setattr(fw, "_POOL", [])
    monkeypatch.setattr(
        FabricWarehouseConnection, "open",
        lambda self: (_ for _ in ()).throw(RuntimeError("capacity is asleep")),
    )
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")

    assert connection.prewarm(4) == 0
    assert fw._POOL == []


def test_a_refused_connection_is_retried_once(monkeypatch):
    """Fabric refuses connections under load. A blip must not 500 a page.

    `08001` prelogin failure was reaching the browser as a 500 on
    `/api/scope/client/{id}` — the open itself failed, so the read-path retry
    never got a chance.
    """
    # The driver ships in requirements, so CI runs this. Skipped rather than
    # failed where it is absent: a missing driver is not a broken retry.
    pyodbc = pytest.importorskip("pyodbc")

    from infrastructure.persistence import fabric_warehouse as fw

    monkeypatch.setattr(fw, "_RECONNECT_PAUSE_S", 0)
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")
    attempts = []

    def refuse_then_succeed(self):
        attempts.append(1)
        if len(attempts) == 1:
            raise pyodbc.OperationalError("08001", "prelogin failure")
        return "a connection"

    monkeypatch.setattr(FabricWarehouseConnection, "_open_once", refuse_then_succeed)

    assert connection.open() == "a connection"
    assert len(attempts) == 2


def test_a_second_refusal_is_reported_rather_than_retried_forever(monkeypatch):
    """A real outage must surface, not become a hang."""
    pyodbc = pytest.importorskip("pyodbc")

    from infrastructure.persistence import fabric_warehouse as fw

    monkeypatch.setattr(fw, "_RECONNECT_PAUSE_S", 0)
    connection = FabricWarehouseConnection(server="example.com", database="warehouse")
    attempts = []

    def always_refuse(self):
        attempts.append(1)
        raise pyodbc.OperationalError("08001", "prelogin failure")

    monkeypatch.setattr(FabricWarehouseConnection, "_open_once", always_refuse)

    with pytest.raises(pyodbc.Error):
        connection.open()
    assert len(attempts) == 2


def test_a_rejected_request_is_not_retried(monkeypatch):
    """Only transport states retry. A bad credential is not a blip."""
    pyodbc = pytest.importorskip("pyodbc")

    connection = FabricWarehouseConnection(server="example.com", database="warehouse")
    attempts = []

    def reject(self):
        attempts.append(1)
        raise pyodbc.ProgrammingError("42000", "login failed for user")

    monkeypatch.setattr(FabricWarehouseConnection, "_open_once", reject)

    with pytest.raises(pyodbc.Error):
        connection.open()
    assert len(attempts) == 1, "a rejection retried is a rejection twice"


def test_the_access_token_is_packed_as_utf16le_with_a_length_prefix():
    """The exact shape msodbcsql expects. Wrong encoding fails as 'login failed'."""

    class _Token:
        token = "header.payload.signature"
        #: Real AccessTokens carry this; the cache ages out against it.
        expires_on = 4102444800  # 2100-01-01

    class _Credential:
        def __init__(self):
            self.scopes = []

        def get_token(self, *scopes):
            self.scopes.extend(scopes)
            return _Token()

    credential = _Credential()
    connection = FabricWarehouseConnection(
        server="example.com", database="warehouse", credential=credential
    )
    packed = connection._access_token_attribute()

    expected_raw = _Token.token.encode("utf-16-le")
    length = struct.unpack("<I", packed[:4])[0]
    assert length == len(expected_raw)
    assert packed[4:] == expected_raw
    # The SQL data plane, not the storage or Fabric audience.
    assert credential.scopes == ["https://database.windows.net/.default"]


def test_the_token_is_fetched_once_and_reused_until_it_nears_expiry():
    """`DefaultAzureCredential` does not cache — measured 1.1s on EVERY call.

    On a developer machine the chain resolves to `AzureCliCredential`, which
    spawns `az account get-access-token`. Six queries a page meant six
    subprocesses and ~6.6s before a row was read.
    """

    class _Token:
        token = "header.payload.signature"
        expires_on = 4102444800

    class _Credential:
        def __init__(self):
            self.calls = 0

        def get_token(self, *_scopes):
            self.calls += 1
            return _Token()

    credential = _Credential()
    connection = FabricWarehouseConnection(
        server="example.com", database="warehouse", credential=credential
    )

    first = connection._access_token_attribute()
    for _ in range(5):
        assert connection._access_token_attribute() == first
    assert credential.calls == 1


def test_a_token_that_reports_no_expiry_is_never_cached():
    """Better slow than holding a bearer token we cannot age out."""

    class _Token:
        token = "header.payload.signature"

    class _Credential:
        def __init__(self):
            self.calls = 0

        def get_token(self, *_scopes):
            self.calls += 1
            return _Token()

    credential = _Credential()
    connection = FabricWarehouseConnection(
        server="example.com", database="warehouse", credential=credential
    )
    connection._access_token_attribute()
    connection._access_token_attribute()
    assert credential.calls == 2


def test_an_expired_token_is_refreshed():
    class _Expired:
        token = "old"
        expires_on = 1  # 1970

    class _Fresh:
        token = "new"
        expires_on = 4102444800

    class _Credential:
        def __init__(self):
            self.calls = 0

        def get_token(self, *_scopes):
            self.calls += 1
            return _Expired() if self.calls == 1 else _Fresh()

    credential = _Credential()
    connection = FabricWarehouseConnection(
        server="example.com", database="warehouse", credential=credential
    )
    first = connection._access_token_attribute()
    second = connection._access_token_attribute()
    assert first != second
    assert credential.calls == 2


# --- the composition root selects, and refuses to guess --------------------


def test_the_default_store_is_the_one_that_needs_no_warehouse(monkeypatch):
    import application.wiring as wiring

    monkeypatch.delenv("RUN_MANIFEST_STORE", raising=False)
    wiring.set_run_manifest_repository(None)

    assert isinstance(wiring.get_run_manifest_repository(), InMemoryRunManifestRepository)
    wiring.set_run_manifest_repository(None)


def test_an_unknown_store_name_raises_rather_than_falling_back(monkeypatch):
    import application.wiring as wiring

    monkeypatch.setenv("RUN_MANIFEST_STORE", "postgres")
    wiring.set_run_manifest_repository(None)

    with pytest.raises(ValueError, match="RUN_MANIFEST_STORE"):
        wiring.get_run_manifest_repository()
    wiring.set_run_manifest_repository(None)


# --- the live round trip ---------------------------------------------------


def test_a_manifest_survives_a_write_to_the_real_warehouse():
    """Opt-in. Writes one row, reads it back, and always removes it again."""
    _requires_fabric()

    from infrastructure.persistence.fabric_warehouse import (
        OPS_SCHEMA,
        FabricRunManifestRepository,
    )

    repo = FabricRunManifestRepository()
    manifest = _manifest(triggered_by="tests/test_warehouse_adapter.py")

    before = repo.count()
    repo.record(manifest)
    try:
        assert repo.count() == before + 1

        stored = repo.get(manifest.run_id)
        assert stored is not None
        assert stored.run_id == manifest.run_id
        assert stored.client_id == 1001
        assert stored.program_code == "GA_JTC"
        assert stored.tax_year == 2023
        assert stored.fiscal_year_begin == date(2023, 7, 28)
        assert stored.run_status == "success"
    finally:
        with repo.connection.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"DELETE FROM {OPS_SCHEMA}.run_manifest WHERE run_id = ?",
                [manifest.run_id],
            )
            connection.commit()

    assert repo.count() == before
    assert repo.get(manifest.run_id) is None
