"""A run that dies must stop advertising itself as in flight.

Two different deaths, and only one of them can be caught in process:

  * the write RAISES         -> `write_run` marks the manifest failed itself
  * the PROCESS dies         -> no handler runs; only a later sweep can close it

The second is what stranded two real runs for client 1001. These tests pin both
halves, plus the read-time age guard that stops a strand from being believed
before the sweep gets to it.
"""
from __future__ import annotations

import pytest

from infrastructure.persistence import gold_reader
from infrastructure.persistence.fabric_warehouse import STRANDED_RUN_MINUTES
from infrastructure.persistence.warehouse_gold import GoldWriter


class _FakeCursor:
    def __init__(self, recorder, rowcount=0):
        self._recorder = recorder
        self.rowcount = rowcount

    def execute(self, sql, values=None):
        self._recorder.append((" ".join(sql.split()), list(values or [])))
        return self

    def close(self):
        """Pooled reads close their cursor so no statement stays active."""


class _FakeConnection:
    def __init__(self, recorder, rowcount=0):
        self._recorder = recorder
        self._rowcount = rowcount
        self.committed = 0

    def cursor(self):
        return _FakeCursor(self._recorder, self._rowcount)

    def commit(self):
        self.committed += 1


class _FakeScope:
    def __init__(self, connection):
        self._connection = connection

    def __enter__(self):
        return self._connection

    def __exit__(self, *exc):
        return False


class _FakeWarehouse:
    def __init__(self, recorder, rowcount=0):
        self.connection_obj = _FakeConnection(recorder, rowcount)

    def connect(self):
        return _FakeScope(self.connection_obj)


# --- the sweep -------------------------------------------------------------


def test_a_run_left_running_past_the_threshold_is_marked_failed():
    recorded: list = []
    writer = GoldWriter(connection=_FakeWarehouse(recorded, rowcount=2))

    assert writer.reap_stranded_runs() == 2

    sql, values = recorded[0]
    assert "SET run_status = 'failed'" in sql
    assert "run_status = 'running'" in sql
    assert values == [-STRANDED_RUN_MINUTES]


def test_the_sweep_leaves_run_completed_at_null():
    """The run never completed. Inventing a completion time would be a lie in
    the audit record, and the readers filter on status anyway."""
    recorded: list = []
    GoldWriter(connection=_FakeWarehouse(recorded, rowcount=1)).reap_stranded_runs()

    sql, _ = recorded[0]
    assert "run_completed_at" not in sql.split("WHERE")[0]
    assert "run_completed_at IS NULL" in sql


def test_the_sweep_never_deletes_a_manifest_row():
    """A failed run is a real audit record; the manifest is append-only."""
    recorded: list = []
    GoldWriter(connection=_FakeWarehouse(recorded, rowcount=1)).reap_stranded_runs()

    sql, _ = recorded[0]
    assert sql.upper().startswith("UPDATE")
    assert "DELETE" not in sql.upper()


def test_the_sweep_is_general_rather_than_targeted():
    """TOP 1 in the reader means fixing only the newest strand makes the banner
    come back looking like a regression. The sweep is not scoped to a client."""
    recorded: list = []
    GoldWriter(connection=_FakeWarehouse(recorded, rowcount=2)).reap_stranded_runs()

    sql, _ = recorded[0]
    assert "client_id" not in sql


def test_a_young_run_is_not_reaped():
    recorded: list = []
    GoldWriter(connection=_FakeWarehouse(recorded)).reap_stranded_runs(older_than_minutes=5)

    _, values = recorded[0]
    assert values == [-5]


def test_the_sweep_compares_against_utc_because_that_is_how_runs_are_stamped():
    """`gold_projection.utc_now` writes naive UTC. GETDATE() would compare it
    against server local time and reap the wrong rows."""
    recorded: list = []
    GoldWriter(connection=_FakeWarehouse(recorded, rowcount=1)).reap_stranded_runs()

    sql, _ = recorded[0]
    assert "SYSUTCDATETIME()" in sql
    assert "GETDATE()" not in sql


# --- the read-time guard ---------------------------------------------------


def test_a_stranded_run_does_not_read_as_in_flight():
    sql, values = gold_reader._stmt_run_in_flight(1001)
    flat = " ".join(sql.split())

    assert "DATEADD(minute, ?, SYSUTCDATETIME())" in flat
    assert values == [1001, -STRANDED_RUN_MINUTES]


# --- the writer still marks its own failures -------------------------------


def test_a_run_that_raises_mid_write_marks_itself_failed():
    """This half already worked. It is pinned because the sweep is not a
    licence to stop marking failures at the moment they happen."""
    marked: list[str] = []

    class _Writer(GoldWriter):
        def _insert(self, table, columns, rows):
            raise RuntimeError("link died")

        def _mark_failed(self, run_id):
            marked.append(run_id)

        def _drop_connection(self):
            pass

    payload = {
        "client_id": 1001,
        "program_code": "GA_JTC",
        "run_id": "deadbeef",
        "run_manifest_columns": ("run_id",),
        "run_manifest_row": ("deadbeef",),
    }

    with pytest.raises(RuntimeError, match="link died"):
        _Writer(connection=_FakeWarehouse([])).write_run(payload)

    assert marked == ["deadbeef"]
