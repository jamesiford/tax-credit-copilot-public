"""The pool must not hand out connections the ODBC pool has already timed out.

A connection is hot after 30s idle (120ms) and dead after 90s (3,216ms — a full
handshake). That timeout is what made page loads erratic: click through quickly
and everything is fast, pause to talk and the next page costs four seconds.
"""
from __future__ import annotations

import time

import pytest

from application.warmup import keepalive_interval_s, touch_warehouse
from infrastructure.persistence import fabric_warehouse as fw
from infrastructure.persistence.fabric_warehouse import FabricWarehouseConnection


class _Link:
    def __init__(self, alive=True):
        self.alive = alive
        self.touched = 0
        self.closed = False
        self.rollbacks = 0

    def cursor(self):
        if not self.alive:
            raise fw_error()
        self.touched += 1
        return _Cursor()

    def rollback(self):
        # Parking or touching a connection ends its read transaction, or the
        # pool hands on a pinned snapshot. See tests/test_pool_snapshot.py.
        if not self.alive:
            raise fw_error()
        self.rollbacks += 1

    def close(self):
        self.closed = True


class _Cursor:
    def execute(self, *_a, **_k):
        return None

    def fetchall(self):
        return [(1,)]

    def close(self):
        return None


def fw_error():
    import pyodbc

    return pyodbc.OperationalError("08S01", "link died while idle")


@pytest.fixture
def pool(monkeypatch):
    monkeypatch.setattr(fw, "_POOL", [])
    return fw._POOL


def test_the_age_bound_sits_under_the_odbc_idle_timeout():
    """Four minutes handed out corpses; the real timeout is sixty seconds."""
    assert fw._POOL_MAX_AGE_S < 60, (
        "a pooled connection older than the ODBC idle timeout is already dead, "
        "and acquire() would hand it to a request"
    )


def test_the_keepalive_interval_stays_inside_the_timeout():
    assert keepalive_interval_s() < 60


def test_a_touched_connection_is_kept_and_its_clock_restarts(pool, monkeypatch):
    """A touched link is as good as a new one, so age must not keep counting."""
    connection = FabricWarehouseConnection(server="e.com", database="w")
    link = _Link()
    pool.append((link, time.time() - 40))

    assert connection.keepalive() == 1
    assert link.touched == 1
    assert len(fw._POOL) == 1
    assert time.time() - fw._POOL[0][1] < 5, "the age clock did not restart"


def test_a_dead_connection_is_dropped_rather_than_handed_to_a_request(pool):
    connection = FabricWarehouseConnection(server="e.com", database="w")
    dead, live = _Link(alive=False), _Link()
    pool.extend([(dead, time.time()), (live, time.time())])

    assert connection.keepalive() == 1
    assert dead.closed
    assert [entry[0] for entry in fw._POOL] == [live]


def test_the_keepalive_never_exceeds_the_pool_bound(pool):
    connection = FabricWarehouseConnection(server="e.com", database="w")
    for _ in range(fw._POOL_MAX_IDLE + 3):
        pool.append((_Link(), time.time()))

    connection.keepalive()

    assert len(fw._POOL) == fw._POOL_MAX_IDLE


def test_the_keepalive_does_not_run_without_the_warm_switch(monkeypatch):
    """Tests and CI have no warehouse; a background task opening one is flake."""
    monkeypatch.setenv("TCC_WARM_ON_START", "0")

    assert touch_warehouse() == 0


def test_a_single_read_borrows_from_the_pool_rather_than_opening(monkeypatch, pool):
    """`connect()` outside a scope was opening its own link every time.

    That is why /runs/latest built a fresh connection on warm requests while
    /units built none — the manifest repository never enters a scope.
    """
    opened = []
    monkeypatch.setattr(
        FabricWarehouseConnection, "open",
        lambda self: (opened.append(1), _Link())[1],
    )
    connection = FabricWarehouseConnection(server="e.com", database="w")

    with connection.connect():
        pass
    with connection.connect():
        pass
    with connection.connect():
        pass

    assert len(opened) == 1, "the second and third reads must borrow, not build"
    assert len(fw._POOL) == 1, "and the link goes back for the next caller"


def test_a_read_that_failed_does_not_return_its_connection(monkeypatch, pool):
    monkeypatch.setattr(FabricWarehouseConnection, "open", lambda self: _Link())
    connection = FabricWarehouseConnection(server="e.com", database="w")

    with pytest.raises(RuntimeError):
        with connection.connect():
            raise RuntimeError("the read failed")

    assert fw._POOL == []
