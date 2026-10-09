"""Re-run every client so Gold holds the employee grain for every year.

The replay always computed `all_averages`, `total_hours_and_wages`,
`employee_unit_matrix` and the payroll rows for each priceable year, then
persisted only the unit grain. `employee_eligibility`, `onezero_matrix` and
`employee_period_fact` therefore held ONE year while `unit_year_master` held
six, and the read path had to re-run the engine to answer for the rest.

The write now persists all of it. This backfills what earlier runs discarded.

    cd backend
    $env:PYTHONPATH="."; python tools/backfill_gold.py            # report only
    $env:PYTHONPATH="."; python tools/backfill_gold.py --run      # write

Slow by design. A run replays every year twice (once per method) and writes the
largest table in the warehouse; the reads it buys are the ones a person waits
for.
"""
from __future__ import annotations

import argparse
import sys
import time

from dotenv import load_dotenv

load_dotenv()

from infrastructure.persistence.fabric_warehouse import GOLD_SCHEMA  # noqa: E402
from infrastructure.persistence.gold_reader import GoldReader  # noqa: E402

_TABLES = (
    "unit_year_master", "employee_eligibility", "onezero_matrix",
    "employee_period_fact", "run_method_summary",
)


def coverage() -> dict[str, dict[int, set[int]]]:
    """Which years each table holds, per client."""
    reader = GoldReader()
    out: dict[str, dict[int, set[int]]] = {}
    with reader.scope(), reader.connection.connect() as connection:
        cursor = connection.cursor()
        for table in _TABLES:
            current = " AND is_current = 1" if table == "unit_year_master" else ""
            cursor.execute(
                f"SELECT client_id, tax_year FROM {GOLD_SCHEMA}.{table} "
                f"WHERE 1 = 1{current} GROUP BY client_id, tax_year"
            )
            held: dict[int, set[int]] = {}
            for client_id, tax_year in cursor.fetchall():
                held.setdefault(int(client_id), set()).add(int(tax_year))
            out[table] = held
    return out


def report() -> list[int]:
    """Print the gap and return the clients that have one."""
    held = coverage()
    master = held["unit_year_master"]
    behind: list[int] = []
    print(f"{'client':>8}  {'unit_year':>18}  {'eligibility':>18}  {'period_fact':>18}  {'summary':>18}")
    for client_id in sorted(master):
        years = master[client_id]
        elig = held["employee_eligibility"].get(client_id, set())
        fact = held["employee_period_fact"].get(client_id, set())
        summary = held["run_method_summary"].get(client_id, set())
        if (years - elig) or (years - fact) or (years - summary):
            behind.append(client_id)
        print(
            f"{client_id:>8}  {_span(years):>18}  {_span(elig):>18}  "
            f"{_span(fact):>18}  {_span(summary):>18}"
            f"{'   <- behind' if client_id in behind else ''}"
        )
    return behind


def _span(years: set[int]) -> str:
    if not years:
        return "none"
    ordered = sorted(years)
    return f"{len(ordered)}y {ordered[0]}-{ordered[-1]}"


def backfill(client_ids: list[int]) -> None:
    from application.queries._client_run import ClientRunNotAvailable
    from application.commands.run_client_calculation import RunClientCalculationCommand
    from application.wiring import get_mediator

    mediator = get_mediator()
    for client_id in client_ids:
        # The requested year only picks which year is computed directly; the
        # replay covers the rest either way. The latest held year is the safest
        # ask because it is certain to resolve.
        years = sorted(coverage()["unit_year_master"].get(client_id, set()))
        if not years:
            print(f"{client_id}: no unit rows to take a year from; skipped")
            continue
        began = time.perf_counter()
        try:
            result = mediator.send(RunClientCalculationCommand(
                client_id=client_id, tax_year=years[-1], state="GA",
                actor="tools/backfill_gold.py",
            ))
        except ClientRunNotAvailable as exc:
            print(f"{client_id}: declined - {exc}")
            continue
        elapsed = time.perf_counter() - began
        counts = result.get("counts") or {}
        written = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()) if v)
        print(f"{client_id}: {elapsed:6.1f}s  {written}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true", help="write, rather than report")
    parser.add_argument("--client", type=int, action="append", help="limit to one client")
    args = parser.parse_args()

    behind = report()
    targets = args.client or behind
    if not args.run:
        print(f"\nreport only. {len(targets)} client(s) would be re-run: {targets}")
        print("re-run with --run to write.")
        return 0
    if not targets:
        print("\nnothing to do.")
        return 0
    print(f"\nre-running {targets} ...")
    backfill(targets)
    print()
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
