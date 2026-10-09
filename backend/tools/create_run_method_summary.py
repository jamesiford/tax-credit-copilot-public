"""Create `tcc_gold.run_method_summary` if it is not there yet.

The table holds what one method concluded about one client-year as a WHOLE —
annual average, eligible count, matrix rows, and how many employee-months were
contested. Nothing else in Gold can carry them: the matrix is deduped before it
is written, so a contest leaves no trace in the rows it produced, and the One/
Zero screen had to re-run the engine on every page load to recover a number the
run had already known.

    cd backend
    $env:PYTHONPATH="."; python tools/create_run_method_summary.py

Idempotent. Safe to run against a warehouse that already has the table.
"""
from __future__ import annotations

from dotenv import load_dotenv

load_dotenv()

from infrastructure.persistence.fabric_warehouse import (  # noqa: E402
    GOLD_SCHEMA,
    FabricWarehouseConnection,
)

_DDL = f"""
CREATE TABLE {GOLD_SCHEMA}.run_method_summary
(
    client_id             BIGINT         NOT NULL,
    tax_year              INT            NOT NULL,
    method                VARCHAR(16)    NOT NULL,
    run_id                VARCHAR(64)    NOT NULL,
    program_code          VARCHAR(32)    NOT NULL,
    annual_average        DECIMAL(12,2)  NOT NULL,
    eligible_employees    INT            NOT NULL,
    employees_evaluated   INT            NOT NULL,
    matrix_rows           INT            NOT NULL,
    unit_fein_rows        INT            NOT NULL,
    contested_months      INT            NOT NULL,
    month_ends            VARCHAR(256)   NOT NULL,
    appended_at           DATETIME2(6)   NOT NULL
)
"""


def main() -> int:
    # Server and database come from WAREHOUSE_* in the environment.
    connection = FabricWarehouseConnection()
    with connection.connect() as link:
        cursor = link.cursor()
        cursor.execute(
            f"SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
            f"WHERE TABLE_SCHEMA = '{GOLD_SCHEMA}' AND TABLE_NAME = 'run_method_summary'"
        )
        if cursor.fetchone()[0]:
            print("run_method_summary already exists; nothing to do.")
            return 0
        cursor.execute(_DDL)
        link.commit()
    print(f"created {GOLD_SCHEMA}.run_method_summary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
