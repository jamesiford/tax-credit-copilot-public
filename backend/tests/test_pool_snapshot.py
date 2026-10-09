"""A pooled connection must not carry its read snapshot into the next request.

pyodbc connects with autocommit off, so the first SELECT opens a transaction.
Nothing on a read path ends it. Fabric Warehouse reads under snapshot isolation,
so that transaction pins the snapshot it started with -- and once connections are
pooled AND kept alive, it is pinned for the life of the process.

Observed: client 2002's completed run kept reading as `running` and its
superseded run kept reading as live, across every request, while the warehouse
itself had the right answer.
"""
from __future__ import annotations

import pytest

from infrastructure.persistence import fabric_warehouse as fw


class _Connection:
    def __init__(self, rollback_fails=False):
        self.rollbacks = 0
        self.closed = False
        self._rollback_fails = rollback_fails

    def rollback(self):
        if self._rollback_fails:
            raise RuntimeError("link gone")
        self.rollbacks += 1

    def close(self):
        self.closed = True

    def cursor(self):
        return _Cursor()


class _Cursor:
    def execute(self, *args):
        return self

    def fetchall(self):
        return [(1,)]

    def close(self):
        pass


@pytest.fixture(autouse=True)
def _empty_pool():
    with fw._POOL_LOCK:
        fw._POOL[:] = []
    yield
    with fw._POOL_LOCK:
        fw._POOL[:] = []


def test_releasing_a_connection_ends_its_read_transaction():
    connection = _Connection()
    fw.FabricWarehouseConnection().release(connection)

    assert connection.rollbacks == 1, (
        "an open read transaction pins the snapshot for the connection's life"
    )
    assert not connection.closed
    assert len(fw._POOL) == 1


def test_a_connection_that_cannot_end_its_transaction_is_not_pooled():
    connection = _Connection(rollback_fails=True)
    fw.FabricWarehouseConnection().release(connection)

    assert connection.closed
    assert fw._POOL == [], "a link that cannot roll back must not be handed on"


def test_the_keepalive_touch_does_not_leave_a_transaction_open():
    """The touch is itself a read. Left open it would pin a fresh snapshot every
    thirty seconds, forever."""
    connection = _Connection()
    with fw._POOL_LOCK:
        fw._POOL[:] = [(connection, 0.0)]

    fw.FabricWarehouseConnection().keepalive()

    assert connection.rollbacks >= 1
    assert not connection.closed


def test_a_discarded_connection_is_not_rolled_back_first():
    """`reusable=False` means the link already failed; touching it again is
    pointless and can raise."""
    connection = _Connection(rollback_fails=True)
    fw.FabricWarehouseConnection().release(connection, reusable=False)

    assert connection.closed
