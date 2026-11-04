"""The grid's pieces: unit-year rows, month summaries, credit tranches and per-unit money."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA
from infrastructure.persistence.gold_reader.columns import _rows
from infrastructure.persistence.gold_reader.reader_base import ReaderBase
from infrastructure.persistence.gold_reader.stmt_units import _stmt_credit_columns, _stmt_month_summaries, _stmt_unit, _stmt_unit_lifetime, _stmt_unit_months, _stmt_unit_totals, _stmt_unit_years, _stmt_unit_years_count


class UnitFigureReads(ReaderBase):
    """The grid's pieces: unit-year rows, month summaries, credit tranches and per-unit money."""

    def unit_years(
        self,
        client_id: int,
        *,
        method: str,
        tax_year: int | None = None,
        program_code: str | None = None,
        limit: int = 25,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Unit-year rows for the live run, with the month-grain columns joined.

        Every `unit_year_master` column is returned, including `per_job_usd` and
        `tranche_years` — without the rate, `annual_credit_usd` cannot be checked
        against `eligible_jobs` from the row itself, which is the whole point of
        the credit layer living in Gold.
        """
        counted, items = self._batch([
            _stmt_unit_years_count(client_id, method, tax_year, program_code),
            _stmt_unit_years(client_id, method, tax_year, program_code, limit, offset),
        ])
        return items, int(counted[0]["total"]) if counted else 0

    def unit(
        self, client_id: int, worksite_id: str, *, tax_year: int, method: str
    ) -> dict[str, Any] | None:
        """One unit-year row, or None when the run holds no such unit."""
        return self._one(_stmt_unit(client_id, worksite_id, tax_year, method))

    def unit_months(
        self, client_id: int, worksite_id: str, *, tax_year: int, method: str, run_id: str
    ) -> dict[str, Any] | None:
        return self._one(_stmt_unit_months(client_id, worksite_id, tax_year, method, run_id))

    def month_summaries(
        self, client_id: int, *, method: str, run_id: str, tax_year: int | None = None
    ) -> list[dict[str, Any]]:
        """Every unit's monthly row for the run — the grid's twelve columns."""
        return self._many(_stmt_month_summaries(client_id, method, run_id, tax_year))

    def installments(
        self, client_id: int, *, method: str, program_code: str | None = None
    ) -> list[dict[str, Any]]:
        """The credit tranches: creation year x claimable year, per unit.

        A job created once pays out across its window, so this is a different
        grain from `unit_year_master` and cannot be derived from it. Without it
        the grid has no YR1..YRn columns to show.
        """
        statement = (
            f"SELECT * FROM {GOLD_SCHEMA}.unit_credit_installment "
            f"WHERE client_id = ? AND method = ? AND is_current = 1"
        )
        values: list[Any] = [client_id, method]
        if program_code:
            statement += " AND program_code = ?"
            values.append(program_code)
        statement += " ORDER BY worksite_id, creation_year, tax_year"

        with self._connection.connect() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, values)
                return _rows(cursor)
            finally:
                cursor.close()

    def credit_columns(
        self, client_id: int, *, method: str, program_code: str | None = None
    ) -> list[dict[str, Any]]:
        """Claimable dollars per unit per YEAR, summed across creation years.

        Several tranches can pay out in the same year, so the grid's YR1..YRn
        column is a SUM over `unit_credit_installment`. It is done here because
        adding money in a browser means adding it as a float.

        `projected` is true if ANY contributing installment is a forecast — a
        column mixing observed and assumed dollars must not read as observed.
        """
        return self._many(_stmt_credit_columns(client_id, method, program_code))

    def unit_totals(
        self, client_id: int, *, method: str, program_code: str | None = None
    ) -> list[dict[str, Any]]:
        """Per-unit money, summed IN SQL rather than on screen.

        The roll-up strip is counts and totals, never a re-derivation of dollars
        — so the sum happens once, here, over the same rows the grid renders.
        """
        totals, lifetime_rows = self._batch([
            _stmt_unit_totals(client_id, method, program_code),
            _stmt_unit_lifetime(client_id, method, program_code),
        ])
        lifetime = {r["worksite_id"]: r["total_tranche_lifetime_usd"] for r in lifetime_rows}
        for row in totals:
            row["total_tranche_lifetime_usd"] = lifetime.get(row["worksite_id"])
        return totals
