"""[F2/F3 · ROADMAP-V] Microsoft Fabric Lakehouse source — the "read Fabric
instead of the local CSV" seam.

The partner's production payroll lands in a Fabric Lakehouse (`employees` table);
the app reads it over the lakehouse **SQL endpoint** with three-part naming,
through the same connection the warehouse uses (payroll never leaves the
partner's tenant). The real `employees` shape differs from the prototype CSV:

  * `Worksite_ID` is NOT state-prefixed (`WS069`) — a separate `Work_State`
    column carries the state.
  * per-location `FEIN`, real pay codes (`Regular`/`Overtime`/`PTO`/`Bonus`…),
    `Check_Date` (paycheck date), `Hours`, and `Gross_Wages` as a currency
    string (`"$1,306.74 "`).
  * no `Tax_Year` column — the fiscal year is derived from the paycheck date.

`map_fabric_employees_row` maps one raw Fabric row to the **prototype
pay-period dict shape** the engine + `tools/canonical.py:to_canonical` already
read, so the rest of the pipeline is unchanged. It **state-prefixes**
`Worksite_ID` (`WS069` + `Work_State=NC` → `NC_WS069`) so the existing per-state
filtering (`Worksite_ID.startswith("GA_")`) keeps working without touching the
engine — that lets us adopt Fabric data incrementally.

WHY T-SQL AND NOT A STORAGE READ:
  The partner's source payroll lives in SQL Server. A table read over T-SQL follows
  them there as a connection-string change; a table read over object storage has
  to be rewritten. The lakehouse SQL endpoint and the warehouse are two databases
  on ONE server, so `[lakehouse].[schema].[table]` reaches this table on the
  connection the persistence layer already opens — one SDK, one auth scope
  (`https://database.windows.net`), one driver.

DESIGN NOTES / SCOPE:
  * This module is **import-safe + dependency-free** at import time. The live
    read (`_fetch_raw`) lazily imports the warehouse connection and is guarded
    behind `DATA_SOURCE=fabric` + `FABRIC_LAKEHOUSE`. With no config it degrades
    to an empty result (offline demo stays deterministic).
  * The mapper is **pure** and fully unit-tested against the real Fabric schema.
  * Wiring `resolve`/the adapter into `api/_payperiods.py` (the F1 loader swap +
    `Work_State`-based state derivation) is deliberately NOT done here — that
    swap is gated on live Fabric access (Private Link + service principal, GSO
    pending) and a branch, so the polished GA demo stays intact.
"""
from __future__ import annotations

import csv
import os
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Iterable

_SEED_EMPLOYEES = Path(__file__).resolve().parent.parent / "data" / "fabric_seed" / "Employees.csv"


# ---------------------------------------------------------------------------
# Field mapping — Fabric `employees` row -> prototype pay-period dict
# ---------------------------------------------------------------------------

# Fabric column -> prototype pay-period field (documentation + the join key set).
FABRIC_FIELD_MAP: dict[str, str] = {
    "Employee_ID": "Employee_ID",
    "Job_Title": "Job_Title",
    "Worksite_ID": "Worksite_ID",   # value is state-prefixed on map (Work_State + '_' + raw)
    "Work_State": "Work_State",
    "Pay_Period_Start": "Pay_Period_Start",
    "Pay_Period_End": "Pay_Period_End",
    "Check_Date": "Pay_Date",       # paycheck date -> cash-basis fiscal anchor
    "FEIN": "Entity_FEIN",
    "Hours": "Hours_Worked",
    "Gross_Wages": "Gross_Wages",   # currency string -> float
    "Earning_Code": "Pay_Code",
}


def _parse_date(value: Any) -> str:
    """Normalize a Fabric date to ISO `YYYY-MM-DD`.

    Fabric ships `M/D/YYYY` (e.g. `8/10/2026`); already-ISO values pass through.
    Returns `""` for blank/unparseable input (the downstream pipeline skips
    rows with unparseable dates).
    """
    s = str(value or "").strip()
    if not s:
        return ""
    # Already ISO (YYYY-MM-DD…)?
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    for sep in ("/", "-"):
        if sep in s:
            parts = s.split(sep)
            if len(parts) == 3 and len(parts[0]) <= 2:
                m, d, y = parts
                try:
                    return date(int(y), int(m), int(d)).isoformat()
                except ValueError:
                    return ""
    return ""


def _parse_money(value: Any) -> float:
    """Parse a Fabric currency string (`"$1,306.74 "`) to a float.

    Handles the `$`, thousands commas, trailing spaces, and plain numerics.
    Blank/unparseable -> 0.0.
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("$", "").replace(",", "").strip()
    if not s:
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _parse_hours(value: Any) -> float:
    try:
        return float(str(value).strip() or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _bracket(identifier: str | None) -> str:
    """One SQL identifier, safely quoted. `]` is escaped by doubling."""
    return "[" + str(identifier or "").replace("]", "]]") + "]"


def map_fabric_employees_row(raw: dict[str, Any]) -> dict[str, Any]:
    """Map one raw Fabric `employees` row to the prototype pay-period dict shape.

    The returned dict carries the 11 engine fields (plus `Work_State` and
    `Location_ID` for the future `Work_State`-based derivation / worksite join),
    with `Worksite_ID` **state-prefixed** for compatibility with the existing
    per-state filtering. `Tax_Year` is derived from the paycheck date
    (cash-basis, DATA-06).
    """
    work_state = str(raw.get("Work_State", "") or "").strip().upper()
    raw_worksite = str(raw.get("Worksite_ID", "") or "").strip()
    # State-prefix so the engine's `Worksite_ID.startswith("GA_")` keeps working.
    worksite_id = f"{work_state}_{raw_worksite}" if work_state and raw_worksite else raw_worksite

    pay_date = _parse_date(raw.get("Check_Date"))
    tax_year = int(pay_date[:4]) if pay_date else 0

    return {
        "Tax_Year": tax_year,
        "Employee_ID": str(raw.get("Employee_ID", "") or "").strip(),
        "Job_Title": str(raw.get("Job_Title", "") or "").strip(),
        "Worksite_ID": worksite_id,
        "Work_State": work_state,
        "Location_ID": str(raw.get("Location_ID", "") or "").strip(),
        "Pay_Period_Start": _parse_date(raw.get("Pay_Period_Start")),
        "Pay_Period_End": _parse_date(raw.get("Pay_Period_End")),
        "Pay_Date": pay_date,
        "Entity_FEIN": str(raw.get("FEIN", "") or "").strip(),
        "Hours_Worked": _parse_hours(raw.get("Hours")),
        "Gross_Wages": _parse_money(raw.get("Gross_Wages")),
        "Pay_Code": str(raw.get("Earning_Code", "Regular") or "Regular").strip(),
    }


# ---------------------------------------------------------------------------
# Data-source selection (DATA_SOURCE env flag)
# ---------------------------------------------------------------------------


def active_data_source() -> str:
    """`'lakehouse'` (default), `'fabric'`, or `'csv'` from the `DATA_SOURCE` flag.

    * ``lakehouse`` — the customer's **source schema** (`Tables/<SOURCE_SCHEMA>/*`,
      default `tcc_source`), read via `data.source.FabricLakehouseReader` and
      projected by the same code path proven lossless against the reference
      dataset. This is the shape production receives, and it is the default:
      the product reads Fabric or it does not run, rather than silently
      falling back to a local file.
    * ``flex``    — **deprecated alias for ``lakehouse``.** The source schema
      used to be named after the customer's internal shape ("Flex"); this
      resolves identically to ``lakehouse`` and emits a `DeprecationWarning`
      so a caller can find and update the setting.
    * ``fabric`` — the flattened demo `employees` Delta table; an early slice
      kept only because the ingestion tests exercise it.
    * ``csv``    — a local FIXTURE, not a data source. `tests/conftest.py` pins
      it so the suite stays offline and deterministic; nothing that ships
      selects it. See `backend/data/payroll_pay_periods.csv`.
    """
    value = resolve_data_source_alias(os.getenv("DATA_SOURCE", "lakehouse").strip().lower())
    return value if value in {"fabric", "csv"} else "lakehouse"


def resolve_data_source_alias(value: str) -> str:
    """Alias the retired `flex` `DATA_SOURCE` name to `lakehouse`.

    Shared by every reader of `DATA_SOURCE` (this module's `active_data_source`
    and `tools/reference_workspace.py`'s `source_kind`) so the alias and its
    deprecation warning cannot drift between them. Any other value, recognised
    or not, is returned unchanged — validating it is each caller's job.
    """
    if value != "flex":
        return value
    warnings.warn(
        "DATA_SOURCE=flex is deprecated; set DATA_SOURCE=lakehouse instead. "
        "'flex' is accepted as an alias and resolves identically to "
        "'lakehouse'.",
        DeprecationWarning,
        stacklevel=3,
    )
    return "lakehouse"


# ---------------------------------------------------------------------------
# Fabric Lakehouse adapter (SQL endpoint, three-part naming)
# ---------------------------------------------------------------------------


@dataclass
class FabricEmployeesAdapter:
    """Reads the Fabric `employees` table over the lakehouse **SQL endpoint** and
    yields **mapped** prototype pay-period rows (a `tools.canonical.SourceAdapter`).

    Config from env (never hardcoded):
      * ``DATA_SOURCE=fabric``      — arm the adapter (else it degrades to []).
      * ``FABRIC_LAKEHOUSE``        — the lakehouse DATABASE name on the endpoint.
      * ``FABRIC_EMPLOYEES_TABLE``  — default ``dbo/employees``; ``schema/table``.
      * ``WAREHOUSE_SERVER``        — the shared SQL endpoint (see 5A adapter).

    `workspace` is retained because it still names the Fabric workspace in
    provenance and `.env`, but it takes no part in the read: a SQL Server target
    has no workspace, and requiring one would defeat the point of reading over
    T-SQL at all.
    """

    workspace: str | None = None
    lakehouse: str | None = None
    employees_table: str | None = None

    def __post_init__(self) -> None:
        self.workspace = self.workspace or os.getenv("FABRIC_WORKSPACE")
        self.lakehouse = self.lakehouse or os.getenv("FABRIC_LAKEHOUSE")
        self.employees_table = self.employees_table or os.getenv(
            "FABRIC_EMPLOYEES_TABLE", "dbo/employees"
        )

    def is_configured(self) -> bool:
        return active_data_source() == "fabric" and bool(self.lakehouse)

    def qualified_table(self) -> str:
        """`[database].[schema].[table]` for the employees table.

        The identifiers come from configuration, so each part is bracket-quoted
        and any embedded `]` doubled — they are names, and a name is not a place
        to concatenate unvalidated text into SQL.
        """
        schema, _, table = str(self.employees_table or "").partition("/")
        if not table:
            schema, table = "dbo", schema
        return ".".join(_bracket(part) for part in (self.lakehouse, schema, table))

    def rows(self) -> Iterable[dict[str, Any]]:
        """Yield mapped prototype pay-period rows, or `[]` when not configured
        (offline / demo stays deterministic)."""
        if not self.is_configured():
            return []
        return [map_fabric_employees_row(r) for r in self._fetch_raw()]

    # -- live path (guarded; not exercised without a configured SQL endpoint) --
    def _fetch_raw(self) -> list[dict[str, Any]]:
        """Every column of the employees table, as dicts.

        `SELECT *` rather than a column list on purpose: the mapper reads by key
        and tolerates absent ones, so the read stays as schema-agnostic as the
        Delta read it replaces. Naming columns here would add a second place to
        update when the source schema gains one.
        """
        from infrastructure.persistence.fabric_warehouse import FabricWarehouseConnection

        with FabricWarehouseConnection().connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT * FROM {self.qualified_table()}")
            columns = [column[0] for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


@dataclass
class FabricCsvAdapter:
    """Reads a Fabric-shaped `Employees.csv` (the seed from
    `data/generate_fabric_employees.py`) and yields **mapped** prototype rows.

    This exercises the FULL Fabric `employees` shape -> engine pipeline offline
    (no SQL endpoint), and lets the round-trip reconcile to the CSV baseline
    (POC-02): the seed is the SAME MeridianCore data reshaped into the Fabric
    schema, so reading it back reproduces every demo number.
    """
    path: Path = _SEED_EMPLOYEES

    def rows(self) -> Iterable[dict[str, Any]]:
        if not self.path.exists():
            return []
        out: list[dict[str, Any]] = []
        with self.path.open(newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                out.append(map_fabric_employees_row(r))
        return out
