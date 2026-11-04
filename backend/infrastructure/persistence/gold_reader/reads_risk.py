"""The employees near a floor, and the pay periods behind a handful of them."""
from __future__ import annotations

from typing import Any

from infrastructure.persistence.gold_reader.reader_base import ReaderBase
from infrastructure.persistence.gold_reader.stmt_drill import _stmt_cohort_periods
from infrastructure.persistence.gold_reader.stmt_risk import _stmt_at_risk, _stmt_at_risk_counts, _stmt_proximity_candidates, _stmt_proximity_counts


def _risk_result(run: dict[str, Any], rows: list[dict[str, Any]], counts_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The cohort rows with the counts they sit in, kept apart so a denominator is never taken over the rows."""
    return {
        "run": run,
        "rows": rows,
        "counts": counts_rows[0] if counts_rows else None,
    }


class RiskReads(ReaderBase):
    """The employees near a floor, and the pay periods behind a handful of them."""

    def at_risk(
        self,
        client_id: int,
        *,
        tax_year: int,
        method: str,
        min_weekly_hours: float,
        min_weekly_wages: float,
        band: float = 0.10,
    ) -> dict[str, Any]:
        """Qualified employees sitting barely above a floor, READ.

        "Which of the net-new jobs counted toward the credit might fall out of
        it" is a question about the people already INSIDE, and no near-miss
        read can answer it: that cohort is everybody outside.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "rows": [], "counts": None}

        counts_rows, rows = self._batch([
            _stmt_at_risk_counts(client_id, tax_year, method, run["run_id"]),
            _stmt_at_risk(
                client_id, tax_year, method, run["run_id"],
                min_weekly_hours, min_weekly_wages, band,
            ),
        ])
        return _risk_result(run, rows, counts_rows)

    def proximity_candidates(
        self,
        client_id: int,
        *,
        tax_year: int,
        method: str,
        min_weekly_hours: float,
        min_weekly_wages: float,
        widest_band_hours: float,
    ) -> dict[str, Any]:
        """Everyone who could still reach the band, and the counts they sit in.

        This used to replay `run_min_max_method` over the whole client payroll
        on every ClientPage load — 61 seconds for the reference client, on a
        screen that ran two more replays behind the forecast. Every field the
        assessment needs was already written by the run.

        NOT `proximity_population`: `rows` is bounded to the reachable band and
        is emphatically not the population. `counts` is, and the two are
        separate statements so that a denominator can never be quietly taken
        over the filtered set.
        """
        run = self.latest_run(client_id)
        if run is None:
            return {"run": None, "rows": [], "counts": None}

        counts_rows, rows = self._batch([
            _stmt_proximity_counts(
                client_id, tax_year, method, run["run_id"],
                min_weekly_hours, min_weekly_wages,
            ),
            _stmt_proximity_candidates(
                client_id, tax_year, method, run["run_id"],
                float(min_weekly_hours) - float(widest_band_hours),
            ),
        ])
        return _risk_result(run, rows, counts_rows)

    def cohort_periods(
        self, client_id: int, *, tax_year: int, run_id: str, tokens: list[str]
    ) -> dict[str, list[dict[str, Any]]]:
        """Pay periods for a handful of employees, grouped by record token.

        The near-the-line cohort is ten rows. One statement for all of them;
        the rest-of-year reading needs each one's periods up to the checkpoint.
        """
        wanted = [t for t in dict.fromkeys(tokens) if t]
        if not wanted:
            return {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in self._many(_stmt_cohort_periods(client_id, tax_year, run_id, wanted)):
            grouped.setdefault(str(row["record_token"]), []).append(row)
        return grouped
