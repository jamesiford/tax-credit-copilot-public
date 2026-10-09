"""One-off: prove the added columns did not move which rows appear, and that
the unit filter narrows in SQL rather than in Python.

Run from backend/ with Fabric credentials available.
"""
from __future__ import annotations

import json
import time

from dotenv import load_dotenv

load_dotenv()

from infrastructure.persistence.gold_reader import (  # noqa: E402
    EMPLOYEE_FILTERS,
    GoldReader,
    _stmt_unit_employees,
)
from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA  # noqa: E402

CLIENT = 1001
YEAR = 2023


def main() -> None:
    reader = GoldReader()
    with reader.scope():
        run = reader.latest_run(CLIENT)
        run_id = run["run_id"]
        print(f"run_id                {run_id}")

        with reader.connection.connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT COUNT(DISTINCT employee_id) FROM {GOLD_SCHEMA}.employee_eligibility "
                f"WHERE client_id = ? AND tax_year = ? AND run_id = ?",
                [CLIENT, YEAR, run_id],
            )
            print(f"employees             {cursor.fetchone()[0]}")

            for method in ("min_max", "pay_period"):
                cursor.execute(
                    f"SELECT COUNT(DISTINCT employee_id) FROM {GOLD_SCHEMA}.employee_eligibility "
                    f"WHERE client_id = ? AND tax_year = ? AND run_id = ? "
                    f"AND method = ? AND eligible = 1",
                    [CLIENT, YEAR, run_id, method],
                )
                print(f"{method:<21} {cursor.fetchone()[0]}")

            # A unit with enough people to make the point.
            cursor.execute(
                f"SELECT TOP 1 worksite_id, COUNT(*) AS n FROM {GOLD_SCHEMA}.onezero_matrix "
                f"WHERE client_id = ? AND tax_year = ? AND run_id = ? AND method = 'min_max' "
                f"GROUP BY worksite_id ORDER BY COUNT(*) DESC",
                [CLIENT, YEAR, run_id],
            )
            unit, held = cursor.fetchone()
        print(f"\nbusiest unit          {unit} ({held} counted)")

        def timed(**kwargs):
            statement, values = _stmt_unit_employees(
                CLIENT, unit, YEAR, "min_max", run_id, None, **kwargs
            )
            began = time.perf_counter()
            rows = reader._many((statement, values))
            return rows, (time.perf_counter() - began) * 1000, statement, values

        rows, ms, _, _ = timed()
        print(f"unfiltered            {len(rows)} rows in {ms:.0f}ms")

        wire = "avg_weekly_hours:>=35;weeks_worked:>=26"
        narrowed, ms, statement, values = timed(filters=wire)
        print(f"filter={wire}")
        print(f"                      {len(narrowed)} rows in {ms:.0f}ms")

        counted, ms, _, _ = timed(count_only=True)
        print(f"unfiltered count      {counted[0]['total']} in {ms:.0f}ms  (the \"of N\" denominator)")

        print("\nSQL")
        print(statement)
        print(f"params {values}")

        print("\ncolumns now on the row")
        print(json.dumps(
            {k: v for k, v in narrowed[0].items() if not k.startswith("month_")},
            indent=2, default=str,
        ))
        print("\nfilterable", sorted(EMPLOYEE_FILTERS))


if __name__ == "__main__":
    main()
