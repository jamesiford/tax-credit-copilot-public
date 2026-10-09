"""A pooled connection goes back with no statement active.

Found by the sweep on 24 Sep: an employee drill returned 500 with "Connection
is busy with results for another command". The readers never closed their
cursors — and `fetchone()` leaves a statement ACTIVE by design — so a link was
rolled back, pooled, and handed to the next request still holding a result.
It failed intermittently, on garbage-collection timing, which is the worst way
for anything to fail in front of a room.
"""
from __future__ import annotations

from contextlib import contextmanager

import pytest


class _Cursor:
    def __init__(self, log, *, fail=False):
        self.log, self.fail, self.closed = log, fail, False
        self.description = [("x",)]
        self.rowcount = 0
        log.append(self)

    def execute(self, *_a, **_k):
        if self.fail:
            raise RuntimeError("statement failed")

    def fetchall(self):
        return [(1,)]

    def fetchone(self):
        return None

    def nextset(self):
        return True

    def close(self):
        self.closed = True


class _Conn:
    def __init__(self, log, fail=False):
        self.log, self.fail = log, fail

    def cursor(self):
        return _Cursor(self.log, fail=self.fail)

    def commit(self):
        pass


class _Pool:
    def __init__(self, fail=False):
        self.cursors: list[_Cursor] = []
        self.fail = fail

    @contextmanager
    def connect(self):
        yield _Conn(self.cursors, self.fail)

    @contextmanager
    def scope(self):
        yield None


@pytest.mark.parametrize("fail", [False, True], ids=["ok", "statement-fails"])
def test_gold_reader_closes_every_cursor(fail):
    from infrastructure.persistence.gold_reader import GoldReader

    pool = _Pool(fail=fail)
    reader = GoldReader(connection=pool)
    for call in (
        lambda: reader._many(("SELECT 1", [])),
        lambda: reader._batch([("SELECT 1", []), ("SELECT 2", [])]),
    ):
        try:
            call()
        except RuntimeError:
            assert fail
    assert pool.cursors and all(c.closed for c in pool.cursors)


@pytest.mark.parametrize("fail", [False, True], ids=["ok", "statement-fails"])
def test_run_manifest_reads_close_their_cursor(fail):
    """`latest()` runs on nearly every page; `fetchone` leaves it active."""
    from infrastructure.persistence.fabric_warehouse import FabricRunManifestRepository

    pool = _Pool(fail=fail)
    repo = FabricRunManifestRepository(connection=pool)
    for call in (lambda: repo.latest(2001), lambda: repo.get("r"), lambda: repo.count()):
        try:
            call()
        except (RuntimeError, TypeError):
            pass
    assert pool.cursors and all(c.closed for c in pool.cursors)
