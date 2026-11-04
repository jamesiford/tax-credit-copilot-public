"""The people at one location, and the drawer that shows them."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.gold_reader.columns import Statement
from infrastructure.persistence.gold_reader.reader_base import ReaderBase, _first
from infrastructure.persistence.gold_reader.stmt_run_summary import _stmt_client_year_rows
from infrastructure.persistence.gold_reader.stmt_runs import _stmt_latest_run, _stmt_run_in_flight
from infrastructure.persistence.gold_reader.stmt_unit_people import _stmt_unit_employees, _stmt_unit_near_threshold
from infrastructure.persistence.gold_reader.stmt_units import _stmt_unit, _stmt_unit_months


def _empty_drill(run: dict[str, Any] | None, in_flight: dict[str, Any] | None, year_held: bool) -> dict[str, Any]:
    """The drawer when there is nothing to list: no live run, or none holding this year."""
    return {"run": run, "in_flight": in_flight,
            "unit": None, "employees": [], "months": None,
            "near_threshold": [], "employees_total": 0, "near_total": 0,
            "year_held": year_held}


def _unfiltered_total(rows: list[dict[str, Any]], asked: str | None, read_total: Any) -> int:
    """The population behind a cohort: the next count read when it was filtered, else the rows themselves."""
    if not asked:
        return len(rows)
    found = next(read_total, None)
    return int(found[0]["total"]) if found else len(rows)


class UnitPeopleReads(ReaderBase):
    """The people at one location, and the drawer that shows them."""

    def unit_employees(
        self,
        client_id: int,
        worksite_id: str,
        *,
        tax_year: int,
        method: str,
        run_id: str,
        month: int | None = None,
    ) -> list[dict[str, Any]]:
        """Employees allocated to one unit, optionally NARROWED to one month.

        `month` filters, it does not merely annotate. A drawer headed "Month 5"
        that lists everyone at the unit and counts them all is telling the
        operator the wrong number: at Cascade's GA_GA-001 that is 29 people
        where the statutory answer is 25.

        The join to `employee_eligibility` carries the hours and wages the
        matrix does not hold, so a page can sort on effort without a second
        round trip. It is 1:1 on the full key and does not fan out.
        """
        return self._many(
            _stmt_unit_employees(client_id, worksite_id, tax_year, method, run_id, month)
        )

    def unit_near_threshold(
        self,
        client_id: int,
        worksite_id: str,
        *,
        tax_year: int,
        method: str,
        run_id: str,
    ) -> list[dict[str, Any]]:
        """Employees at this unit who did NOT qualify — the actionable cohort.

        `onezero_matrix` holds only the qualified, so no join to it can surface
        a near miss: the cusp count comes back zero at every unit on every
        client. The people one shift short are in `employee_eligibility`, which
        has no worksite; `employee_period_fact` places them.

        DISTINCT because period_fact is one row per pay period. Nobody in the
        reference data spans two worksites, so this does not fan out — but the
        DISTINCT is what makes that a property of the query rather than a
        property of the current data.
        """
        return self._many(
            _stmt_unit_near_threshold(client_id, worksite_id, tax_year, method, run_id)
        )

    def unit_drill(
        self,
        client_id: int,
        worksite_id: str,
        *,
        tax_year: int,
        method: str,
        month: int | None = None,
        sort: str | None = None,
        order: str | None = None,
        near_min_hours: float | None = None,
        limit: int | None = None,
        employee_filters: str | None = None,
        near_filters: str | None = None,
    ) -> dict[str, Any]:
        """Everything the unit drawer renders, in TWO round trips.

        `unit` rides in the first batch even though the early exits may discard
        it: the trip is already being made, and a third trip costs more than the
        wasted statement.

        The two cohorts filter INDEPENDENTLY. They are different questions about
        different populations, and one shared filter would let a narrowing of
        the qualified list silently change the near-miss count under a tab
        nobody was looking at.
        """
        run_rows, in_flight_rows, unit_rows, year_rows = self._batch([
            _stmt_latest_run(client_id),
            _stmt_run_in_flight(client_id),
            _stmt_unit(client_id, worksite_id, tax_year, method),
            _stmt_client_year_rows(client_id, tax_year, method),
        ])
        run, in_flight, unit = _first(run_rows), _first(in_flight_rows), _first(unit_rows)
        year_held = bool(year_rows and int(year_rows[0]["total"]) > 0)
        if run is None or not year_held:
            return _empty_drill(run if year_held else None, in_flight, year_held)

        employees, months, near = self._batch([
            _stmt_unit_employees(
                client_id, worksite_id, tax_year, method, run["run_id"], month,
                sort=sort, order=order, limit=limit, filters=employee_filters,
            ),
            _stmt_unit_months(client_id, worksite_id, tax_year, method, run["run_id"]),
            _stmt_unit_near_threshold(
                client_id, worksite_id, tax_year, method, run["run_id"],
                sort=sort, order=order, near_min_hours=near_min_hours, limit=limit,
                filters=near_filters,
            ),
        ])
        # The denominator behind "12 of 37". Only issued when a filter is in
        # force: unfiltered, the rows on screen ARE the population, and a count
        # that can only ever agree with len(rows) is a statement nobody needs.
        totals: list[Statement] = []
        if employee_filters:
            totals.append(_stmt_unit_employees(
                client_id, worksite_id, tax_year, method, run["run_id"], month,
                count_only=True,
            ))
        if near_filters:
            totals.append(_stmt_unit_near_threshold(
                client_id, worksite_id, tax_year, method, run["run_id"],
                near_min_hours=near_min_hours, count_only=True,
            ))
        counted = self._batch(totals) if totals else []
        read_total = iter(counted)

        return {
            "run": run,
            "in_flight": in_flight,
            "unit": unit,
            "employees": employees,
            "months": _first(months),
            "near_threshold": near,
            "employees_total": _unfiltered_total(employees, employee_filters, read_total),
            "near_total": _unfiltered_total(near, near_filters, read_total),
            "year_held": True,
        }
