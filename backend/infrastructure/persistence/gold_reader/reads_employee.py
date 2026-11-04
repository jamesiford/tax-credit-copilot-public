"""Who qualifies, and one employee's derivation."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA
from infrastructure.persistence.gold_reader.columns import _rows, month_ends_of
from infrastructure.persistence.gold_reader.reader_base import ReaderBase
from infrastructure.persistence.gold_reader.stmt_drill import _stmt_drill_periods, _stmt_drill_segments, _stmt_drill_verdicts
from infrastructure.persistence.gold_reader.stmt_eligibility import _stmt_eligibility_matching, _stmt_eligibility_page, _stmt_eligibility_summary
from infrastructure.persistence.gold_reader.stmt_run_summary import _stmt_method_summary


class EmployeeReads(ReaderBase):
    """Who qualifies, and one employee's derivation."""

    def eligibility_population(
        self,
        client_id: int,
        *,
        tax_year: int,
        min_weekly_hours: float,
        min_weekly_wages: float,
        band: float = 0.05,
        status: str = "all",
        near_floor: bool = False,
        q: str = "",
        limit: int = 50,
        offset: int = 0,
        sort: str = "employee_id",
        order: str = "asc",
    ) -> dict[str, Any]:
        """Who qualifies, READ from the run that decided it.

        This used to replay both certified methods over every employee on each
        page load. The answer was already in `employee_eligibility` — written by
        the run, under the rule pack the run recorded — so recomputing it risked
        a second opinion about a number that has already been certified, and
        cost an engine pass over 10,236 employees to get there.

        Three statements in one round trip: the summary, which the filters must
        never move, the page, and how many rows the filter matched.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "summary": None, "rows": [], "matching": 0}

        summary_rows, page_rows, matching_rows = self._batch([
            _stmt_eligibility_summary(
                client_id, tax_year, run["run_id"],
                min_weekly_hours, min_weekly_wages, band,
            ),
            _stmt_eligibility_page(
                client_id, tax_year, run["run_id"],
                min_weekly_hours, min_weekly_wages, band,
                status, near_floor, q, limit, offset, sort, order,
            ),
            _stmt_eligibility_matching(
                client_id, tax_year, run["run_id"],
                min_weekly_hours, min_weekly_wages, band,
                status, near_floor, q,
            ),
        ])
        summary = summary_rows[0] if summary_rows else None
        # A run exists but holds no row for THIS year. The client was assessed;
        # this year was not, and those are different answers.
        if summary is None or not int(summary.get("employees_evaluated") or 0):
            return {"run": run, "summary": None, "rows": [], "matching": 0}
        return {
            "run": run,
            "summary": summary,
            "rows": page_rows,
            "matching": int(matching_rows[0]["total"]) if matching_rows else 0,
        }

    def employee_drill(
        self, client_id: int, *, tax_year: int, record_token: str
    ) -> dict[str, Any]:
        """One employee's derivation, READ, in a single round trip.

        Resolution is a LOOKUP: `record_token` is stored on every employee-grain
        table. The old path re-minted a token for all 10,236 employees in the
        client-year and matched — on top of loading the payroll twice and
        replaying both certified methods, per click.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "verdicts": [], "segments": [], "periods": []}

        verdicts, segments, periods, summary_rows = self._batch([
            _stmt_drill_verdicts(client_id, tax_year, run["run_id"], record_token),
            _stmt_drill_segments(client_id, tax_year, run["run_id"], record_token),
            _stmt_drill_periods(client_id, tax_year, run["run_id"], record_token),
            # The run's measuring dates, as the matrix beside the drill reads
            # them. Both methods measure the same twelve, so one row answers.
            _stmt_method_summary(client_id, tax_year, "min_max", run["run_id"]),
        ])
        return {
            "run": run,
            "verdicts": verdicts,
            "segments": segments,
            "periods": periods,
            "month_ends": month_ends_of(summary_rows[0] if summary_rows else None),
        }

    def employee(
        self, record_token: str, *, client_id: int, tax_year: int, run_id: str
    ) -> list[dict[str, Any]]:
        """One employee's eligibility rows — one per method — for a run."""
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    f"SELECT * FROM {GOLD_SCHEMA}.employee_eligibility "
                    f"WHERE record_token = ? AND client_id = ? AND tax_year = ? "
                    f"AND run_id = ? ORDER BY method",
                    [record_token, client_id, tax_year, run_id],
                )
                return _rows(cursor)
            finally:
                cursor.close()

    def employee_units(
        self, record_token: str, *, client_id: int, tax_year: int, run_id: str, method: str
    ) -> list[dict[str, Any]]:
        """One employee's allocation to each unit, month by month, for one method of a run."""
        months =  ", ".join(f"month_{index:02d}" for index in range(1, 13))
        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    f"SELECT worksite_id, entity_fein, first_pps, last_ppe, weight, {months} "
                    f"FROM {GOLD_SCHEMA}.onezero_matrix "
                    f"WHERE record_token = ? AND client_id = ? AND tax_year = ? "
                    f"AND run_id = ? AND method = ? ORDER BY worksite_id",
                    [record_token, client_id, tax_year, run_id, method],
                )
                return _rows(cursor)
            finally:
                cursor.close()
