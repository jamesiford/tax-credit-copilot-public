"""Reads one client's figures from `tcc_gold`: the connection, the retry and the batch."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.fabric_warehouse import FabricWarehouseConnection
from infrastructure.persistence.gold_reader.columns import Statement, _CONNECTION_LOST_STATES, _rows
from infrastructure.persistence.gold_reader.stmt_runs import _stmt_latest_run, _stmt_run_in_flight


def _first(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The first row of a result set, or None; an empty set is an answer, not an error."""
    return rows[0] if rows else None


class ReaderBase:
    """Reads one client's figures from `tcc_gold`: the connection, the retry and the batch."""

    def __init__(self, connection: FabricWarehouseConnection | None = None) -> None:
        self._connection = connection or FabricWarehouseConnection()

    @property
    def connection(self) -> FabricWarehouseConnection:
        return self._connection

    def scope(self):
        """Run a page's reads on ONE connection.

        Every read opens its own, which is right for a single query and
        wrong for a page: the unit drill made six. Wrapping the endpoint body in
        this collapses them without touching any of the reads.
        """
        return self._connection.scope()

    def _retrying(self, work):
        """Run a read, reopening once if the connection had died while parked.

        Connections are reused between requests, so the first statement of a
        page can land on a link Fabric closed server-side. Every caller here is
        a SELECT, so re-running it is safe; this deliberately does not wrap
        writes, where a retry is a second attempt at a state change.
        """
        import pyodbc

        try:
            return work()
        except pyodbc.Error as exc:
            state = exc.args[0] if exc.args else ""
            if state not in _CONNECTION_LOST_STATES:
                raise
            self._connection.invalidate()
            return work()

    def _many(self, statement: Statement) -> list[dict[str, Any]]:
        sql, values = statement

        def work() -> list[dict[str, Any]]:
            with self._connection.connect() as connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(sql, values)
                    return _rows(cursor)
                finally:
                    # A pooled link must go back with no statement active, or
                    # the next borrower gets "Connection is busy with results
                    # for another command" — intermittently, on GC timing.
                    cursor.close()

        return self._retrying(work)

    def _one(self, statement: Statement) -> dict[str, Any] | None:
        found = self._many(statement)
        return found[0] if found else None

    def _batch(self, statements: list[Statement]) -> list[list[dict[str, Any]]]:
        """Several statements, ONE round trip.

        Each query here is already near the engine's floor — `SELECT 1` costs
        125ms against this warehouse, and a real read ~300ms — so issuing eight
        of them serially spends the round trip eight times. Batched, the same
        eight cost one. Measured 1,127ms -> 403ms on the units page.

        Result sets come back in statement order and are walked with
        `nextset()`. A statement returning no rows still returns a set, so the
        positional mapping holds and the caller can unpack by position.
        """
        sql = ";\n".join(s for s, _ in statements)
        values = [v for _, vs in statements for v in vs]

        def work() -> list[list[dict[str, Any]]]:
            out: list[list[dict[str, Any]]] = []
            with self._connection.connect() as connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(sql, values)
                    for index in range(len(statements)):
                        out.append(_rows(cursor))
                        if index < len(statements) - 1 and not cursor.nextset():
                            break
                finally:
                    cursor.close()
            return out

        return self._retrying(work)

    def latest_run(self, client_id: int) -> dict[str, Any] | None:
        """The live run for a client, or None when it has never been calculated.

        Live means completed successfully and not yet superseded. `None` is the
        `not_calculated` state and callers must not render it as a zero.

        Takes no tax year: a run is current for a client, and the year selects
        ROWS rather than runs. See `_stmt_latest_run`.
        """
        return self._one(_stmt_latest_run(client_id))

    def run_in_flight(self, client_id: int) -> dict[str, Any] | None:
        """A run that has started and not finished, or None.

        `run_completed_at IS NULL` is the marker: the manifest is written at the
        START of a run and stamped on completion. A row still sitting here long
        after it began is a run that died without saying so, which is worth
        showing rather than hiding.
        """
        return self._one(_stmt_run_in_flight(client_id))
