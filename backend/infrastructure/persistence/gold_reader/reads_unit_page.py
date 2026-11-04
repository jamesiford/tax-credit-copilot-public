"""The units grid in as few round trips as the screen allows."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.gold_reader.columns import UNIT_YEAR_MASTER_COLUMNS
from infrastructure.persistence.gold_reader.reader_base import ReaderBase, _first
from infrastructure.persistence.gold_reader.stmt_runs import _stmt_latest_run, _stmt_run_in_flight
from infrastructure.persistence.gold_reader.stmt_units import _MONTH_COLUMNS, _stmt_credit_columns, _stmt_credit_grid, _stmt_month_summaries, _stmt_unit_grid, _stmt_unit_lifetime, _stmt_unit_totals, _stmt_unit_years, _stmt_unit_years_count


def _empty_page(in_flight: dict[str, Any] | None) -> dict[str, Any]:
    """A client with no live run: nothing to draw, and no reason to have paid for the other reads."""
    return {"run": None, "in_flight": in_flight, "items": [], "total": 0,
            "months": [], "installments": [], "unit_totals": []}


def _grid_month(row: dict[str, Any]) -> dict[str, Any] | None:
    """The unit-year's month grain, or None when no summary row was joined.

    A unit-year with no summary row joined is not a month of zeroes; it is a month
    grain that does not exist, and the grid draws those differently.
    """
    if row["month_total"] is None and all(row[column] is None for column in _MONTH_COLUMNS):
        return None
    return {
        "client_id": row["client_id"],
        "tax_year": row["tax_year"],
        "method": row["method"],
        "run_id": row["run_id"],
        "worksite_id": row["worksite_id"],
        **{column: row[column] for column in _MONTH_COLUMNS},
        "total": row["month_total"],
        "average_headcount": row["month_average_headcount"],
        "months_with_headcount": row["months_with_headcount"],
        "unreachable_months": row["unreachable_months"],
    }


def _read_grid(grid: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Split the one joined grid into unit-year rows, month rows and one totals row per unit."""
    items: list[dict[str, Any]] = []
    months: list[dict[str, Any]] = []
    totals: dict[str, dict[str, Any]] = {}
    for row in grid:
        worksite = row["worksite_id"]
        items.append({
            **{column: row[column] for column in UNIT_YEAR_MASTER_COLUMNS},
            "months_with_headcount": row["months_with_headcount"],
            "unreachable_months": row["unreachable_months"],
        })
        month = _grid_month(row)
        if month is not None:
            months.append(month)
        if worksite not in totals:
            totals[worksite] = {
                "worksite_id": worksite,
                "total_annual_credit_usd": row["total_annual_credit_usd"],
                "final_high_water_mark": row["final_high_water_mark"],
                "total_tranche_lifetime_usd": None,
            }
    return items, months, totals


def _read_credits(credits: list[dict[str, Any]], totals: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """The credit stream, with each unit's lifetime total moved onto its totals row."""
    installments = []
    for row in credits:
        lifetime = row.pop("total_tranche_lifetime_usd")
        installments.append(row)
        if row["worksite_id"] in totals:
            totals[row["worksite_id"]]["total_tranche_lifetime_usd"] = lifetime
    return installments


class UnitPageReads(ReaderBase):
    """The units grid in as few round trips as the screen allows."""

    def _unit_page_whole(
        self, client_id: int, method: str, program_code: str | None, limit: int, offset: int
    ) -> dict[str, Any]:
        """The grid in ONE round trip, for the shape the screen actually asks for.

        The UI never sends a year — `fetchClientUnits` omits it — because the
        grid draws every year a location has. That makes the item rows and the
        per-unit money the same row set, so the money can be a window over the
        rows already being read instead of two more scans of the same table.

        Four statements, one trip: the run, the run in flight, the grid, the
        credit stream. The month summary is joined on `m.run_id` rather than on
        a resolved run id, so nothing here waits for the first result.
        """
        run_rows, in_flight_rows, grid, credits = self._batch([
            _stmt_latest_run(client_id),
            _stmt_run_in_flight(client_id),
            _stmt_unit_grid(client_id, method, program_code, limit, offset),
            _stmt_credit_grid(client_id, method, program_code),
        ])
        run, in_flight = _first(run_rows), _first(in_flight_rows)
        if run is None:
            return _empty_page(in_flight)

        items, months, totals = _read_grid(grid)
        installments = _read_credits(credits, totals)
        return {
            "run": run,
            "in_flight": in_flight,
            "items": items,
            "total": int(grid[0]["total_rows"]) if grid else 0,
            "months": months,
            "installments": installments,
            "unit_totals": [totals[key] for key in sorted(totals)],
        }

    def unit_page(
        self,
        client_id: int,
        *,
        method: str,
        tax_year: int | None = None,
        program_code: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Everything the units grid renders, in TWO round trips.

        The same six reads the endpoint used to make one at a time. Each is
        already a plain SELECT off pre-computed Gold and runs near the engine's
        floor; the page cost was the eight trips, not the work — 2,334ms of
        which roughly 1,000ms was floor.

        It is two trips and not one because `month_summaries` is keyed by the
        run id that the first trip resolves. Folding `latest_run` into the
        second batch as a subquery would remove the dependency, and also remove
        the early exit: a client with no run must not pay for six reads whose
        answer is already known to be empty.
        """
        if tax_year is None:
            return self._unit_page_whole(client_id, method, program_code, limit, offset)

        run_rows, in_flight_rows = self._batch([
            _stmt_latest_run(client_id),
            _stmt_run_in_flight(client_id),
        ])
        run, in_flight = _first(run_rows), _first(in_flight_rows)
        if run is None:
            return _empty_page(in_flight)
        return {
            "run": run,
            "in_flight": in_flight,
            **self._year_page(client_id, method, tax_year, program_code, limit, offset, run["run_id"]),
        }

    def _year_page(
        self, client_id: int, method: str, tax_year: int, program_code: str | None,
        limit: int, offset: int, run_id: str,
    ) -> dict[str, Any]:
        """The second trip for a named year: rows, month summaries and the credit stream, six reads in one batch."""
        counted, items, months, installments, totals, lifetime_rows = self._batch([
            _stmt_unit_years_count(client_id, method, tax_year, program_code),
            _stmt_unit_years(client_id, method, tax_year, program_code, limit, offset),
            _stmt_month_summaries(client_id, method, run_id, tax_year),
            _stmt_credit_columns(client_id, method, program_code),
            _stmt_unit_totals(client_id, method, program_code),
            _stmt_unit_lifetime(client_id, method, program_code),
        ])
        lifetime = {r["worksite_id"]: r["total_tranche_lifetime_usd"] for r in lifetime_rows}
        for row in totals:
            row["total_tranche_lifetime_usd"] = lifetime.get(row["worksite_id"])

        return {
            "items": items,
            "total": int(counted[0]["total"]) if counted else 0,
            "months": months,
            "installments": installments,
            "unit_totals": totals,
        }
