"""Per-run grain check: does every year row have its month row, in the LIVE run?

Raw table counts mislead. `unit_year_master` carries `is_current` and keeps
superseded rows; `unit_month_summary` is keyed by `run_id` and keeps every run's
rows with no currency flag. Comparing the two totals therefore compares
different populations. The question that matters is per run.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from infrastructure.persistence.fabric_warehouse import (  # noqa: E402
    GOLD_SCHEMA,
    OPS_SCHEMA,
    FabricWarehouseConnection,
)


def rows(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


with FabricWarehouseConnection().scope() as conn:
    cur = conn.cursor()

    print("-- live run per client")
    live = rows(cur, f"""
        SELECT client_id, run_id, tax_year, run_status
        FROM {OPS_SCHEMA}.run_manifest
        WHERE run_status = 'success' AND superseded_by_run_id IS NULL
              AND run_completed_at IS NOT NULL
    """)
    for r in live:
        print("   ", r)

    print("\n-- year rows vs month rows, BY RUN")
    for r in rows(cur, f"""
        SELECT y.run_id,
               MAX(y.client_id) AS client_id,
               COUNT(DISTINCT y.tax_year) AS year_count,
               COUNT(*) AS year_rows
        FROM {GOLD_SCHEMA}.unit_year_master y GROUP BY y.run_id
    """):
        cur.execute(
            f"SELECT COUNT(*), COUNT(DISTINCT tax_year) FROM {GOLD_SCHEMA}.unit_month_summary "
            f"WHERE run_id = ?", [r["run_id"]],
        )
        month_rows, month_years = cur.fetchone()
        flag = "OK " if month_rows == r["year_rows"] else "!! "
        print(f"    {flag}{r['client_id']} run={r['run_id'][:10]} "
              f"year_rows={r['year_rows']:>5} ({r['year_count']}y)  "
              f"month_rows={month_rows:>5} ({month_years}y)")

    print("\n-- CURRENT year rows (is_current=1) vs live-run month rows, per client")
    for r in live:
        cur.execute(
            f"SELECT COUNT(*) FROM {GOLD_SCHEMA}.unit_year_master "
            f"WHERE client_id = ? AND is_current = 1", [r["client_id"]],
        )
        year_current = cur.fetchone()[0]
        cur.execute(
            f"SELECT COUNT(*) FROM {GOLD_SCHEMA}.unit_month_summary WHERE run_id = ?",
            [r["run_id"]],
        )
        month_live = cur.fetchone()[0]
        flag = "OK " if year_current == month_live else "!! "
        print(f"    {flag}{r['client_id']}  current_year_rows={year_current:>5}  "
              f"live_run_month_rows={month_live:>5}")

    print("\n-- gold years present per client (current)")
    for r in rows(cur, f"""
        SELECT client_id, COUNT(DISTINCT tax_year) AS years,
               MIN(tax_year) AS first_year, MAX(tax_year) AS last_year, COUNT(*) AS rows_
        FROM {GOLD_SCHEMA}.unit_year_master WHERE is_current = 1
        GROUP BY client_id ORDER BY client_id
    """):
        print("   ", r)
