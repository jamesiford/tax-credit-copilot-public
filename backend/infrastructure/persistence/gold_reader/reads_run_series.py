"""What the run recorded across months and years: headcount, the year series, the One/Zero matrix."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.gold_reader.columns import month_ends_of
from infrastructure.persistence.gold_reader.reader_base import ReaderBase
from infrastructure.persistence.gold_reader.stmt_run_summary import _stmt_client_year_credit, _stmt_client_year_series, _stmt_method_summary, _stmt_month_totals, _stmt_onezero_matrix, _stmt_unit_fein_summary


def _unreachable_positions(row: dict[str, Any]) -> list[int]:
    """0-based positions no pay period reaches; for an open year the trailing ones have not happened yet."""
    return [
        int(part) for part in str(row.get("unreachable_months") or "").split(",")
        if part.strip().isdigit()
    ]


def _year_entry(row: dict[str, Any], credit: dict[str, Any]) -> dict[str, Any]:
    """One tax year of the series: what the run concluded, joined to the credit summed across units."""
    return {
        "tax_year": int(row["tax_year"]),
        "annual_average": float(row["annual_average"] or 0),
        "eligible_employees": int(row["eligible_employees"] or 0),
        "employees_evaluated": int(row["employees_evaluated"] or 0),
        "annual_credit_usd": (
            str(credit["annual_credit_usd"])
            if credit.get("annual_credit_usd") is not None else None
        ),
        "is_base_year": bool(credit.get("has_base_year")),
        "qualified_units": (
            int(credit["qualified_units"])
            if credit.get("qualified_units") is not None else 0
        ),
        "units": int(credit["units"]) if credit.get("units") is not None else 0,
    }


class RunSeriesReads(ReaderBase):
    """What the run recorded across months and years: headcount, the year series, the One/Zero matrix."""

    def headcount_series(
        self, client_id: int, *, tax_year: int, method: str
    ) -> dict[str, Any]:
        """The monthly headcount series and the annual average, READ.

        The in-year forecast replayed the whole payroll TWICE to get these —
        once for the year being projected and once for the prior-year base. Both
        were already written by the run. The forecast itself still computes,
        because projecting to an arbitrary as-of date is a genuine derivation
        rather than a re-derivation of a certified figure.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "months": [], "annual_average": None, "month_ends": []}

        month_rows, summary_rows = self._batch([
            _stmt_month_totals(client_id, tax_year, method, run["run_id"]),
            _stmt_method_summary(client_id, tax_year, method, run["run_id"]),
        ])
        row = month_rows[0] if month_rows else {}
        months = [float(row.get(f"month_{index:02d}") or 0.0) for index in range(1, 13)]
        summary = summary_rows[0] if summary_rows else None
        return {
            "run": run,
            "months": months,
            "month_ends": month_ends_of(summary),
            "unreachable_months": _unreachable_positions(row),
            "annual_average": (
                float(summary["annual_average"]) if summary and summary.get("annual_average") is not None
                else None
            ),
        }

    def client_year_series(
        self, client_id: int, *, method: str = "pay_period"
    ) -> dict[str, Any]:
        """Every year the run holds for a client, and what each concluded.

        The cross-year view: annual average, eligible count and credit per tax
        year, plus which year the base was set. "Have they been eligible since
        their base year" is a question about a SERIES, and answering it from a
        single-year read is how a chat ends up describing one year as though it
        were the whole history.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "years": []}

        summary_rows, credit_rows = self._batch([
            _stmt_client_year_series(client_id, method, run["run_id"]),
            _stmt_client_year_credit(client_id, method),
        ])
        credit_by_year = {int(r["tax_year"]): r for r in credit_rows}
        years = [
            _year_entry(row, credit_by_year.get(int(row["tax_year"]), {})) for row in summary_rows
        ]
        return {"run": run, "years": years, "method": method}

    def onezero_matrix(
        self, client_id: int, *, tax_year: int, method: str
    ) -> dict[str, Any]:
        """The One/Zero allocation for one client-year-method, READ.

        The screen states four things that belong to the run rather than to any
        row — annual average, eligible count, matrix rows and CONTESTED months.
        `run_method_summary` holds them because nothing else could: the matrix
        is deduped before it is written, so a contest leaves no trace in the
        rows it produced.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "summary": None, "matrix": [], "units": []}

        summary_rows, matrix_rows, unit_rows = self._batch([
            _stmt_method_summary(client_id, tax_year, method, run["run_id"]),
            _stmt_onezero_matrix(client_id, tax_year, method, run["run_id"]),
            _stmt_unit_fein_summary(client_id, tax_year, method, run["run_id"]),
        ])
        summary = summary_rows[0] if summary_rows else None
        if summary is None:
            return {"run": run, "summary": None, "matrix": [], "units": []}
        return {
            "run": run,
            "summary": summary,
            "matrix": matrix_rows,
            "units": unit_rows,
        }
