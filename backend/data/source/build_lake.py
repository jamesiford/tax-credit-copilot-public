"""Build a lakehouse in a target shape from source datasets, and prove nothing was lost. [05]

The shape (table names, column names and case, types, partition) is whatever the SOURCE MAPPING in force says, so the same
datasets land in the default shape or in any other by choosing a mapping file. Nothing here spells a table or a column.

Targets
-------
`root=<dir>`  a lakehouse laid out on local disk (`<root>/Tables/<schema>/<physical table>`), no credentials, for tests,
               development and the scale generator
`root=None`   the configured Fabric lakehouse over OneLake (the script that drives this refuses to run it without being asked)

The app-owned lookups (the tables the mapping marks optional: `PayFrequency`, `EntityFiscalYearRules`) are written only on
request. The default leaves them out, so absent-lookup behaviour can be tested end to end. `Employment` is optional for the
headcount but is data, not a lookup, and is written.

Reconciliation compares, per table, the row count and a checksum of the LOGICAL values before (from the datasets) and after
(read back from the lake through the same column resolution the reader uses). A lake that loses or alters a row cannot pass.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from .mapping import column, mapping, physical_table, spec
from .mapping.columns import resolve_for
from .schema import SourceDataset
from .to_delta import PARTITION_BY, TABLE_SPECS, _rows_for, _to_arrow

#: App-owned lookups: tables the customer's schema does not carry, written only on request.
LOOKUP_TABLES = ("PayFrequency", "EntityFiscalYearRules")


@dataclass(frozen=True)
class TablePlan:
    logical: str
    physical: str
    rows: int
    columns: tuple[str, ...]
    partition_by: tuple[str, ...]
    skipped: str = ""


@dataclass
class BuildReport:
    """What a build did (or, for a dry run, would do), and whether the lake matches the datasets."""

    dry_run: bool
    plan: list[TablePlan] = field(default_factory=list)
    reconciliation: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r["rows_match"] and r["checksum_match"] for r in self.reconciliation)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run, "reconciled": bool(self.reconciliation) and self.ok,
            "plan": [t.__dict__ | {"columns": list(t.columns), "partition_by": list(t.partition_by)} for t in self.plan],
            "reconciliation": self.reconciliation,
        }


def tables_to_write(include_lookups: bool) -> list[str]:
    return [t for t in TABLE_SPECS if include_lookups or t not in LOOKUP_TABLES]


def _norm(value: Any) -> str:
    """One text form per logical value, so a dataset value and its Delta round trip compare equal."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value.quantize(Decimal("0.01")))
    if isinstance(value, datetime):
        return value.replace(microsecond=0).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:.6f}"
    return str(value)


def checksum(rows: Iterable[dict[str, Any]], fields: Iterable[str]) -> str:
    """Order-independent digest of the rows over the given logical fields."""
    names = sorted(fields)
    digests = sorted(hashlib.sha256("\x1f".join(_norm(r.get(n)) for n in names).encode()).hexdigest() for r in rows)
    return hashlib.sha256("".join(digests).encode()).hexdigest()


def _dataset_rows(datasets: list[SourceDataset], table: str) -> list[dict[str, Any]]:
    attr = TABLE_SPECS[table][0]
    return [{f: getattr(rec, f, None) for f in spec(table)} for ds in datasets for rec in _rows_for(ds, attr)]


def table_path(root: Path, table: str, schema: str) -> Path:
    base = Path(root) / "Tables" / schema if schema else Path(root) / "Tables"
    return base / physical_table(table)


def read_back(root: Path, table: str, schema: str) -> list[dict[str, Any]]:
    """A table from the local lake as rows keyed by logical field, through the reader's own column resolution."""
    from deltalake import DeltaTable

    dt = DeltaTable(str(table_path(root, table, schema)))
    found = resolve_for(mapping(), table, [f.name for f in dt.schema().fields]).found
    inverse = {actual: name for name, actual in found.items()}
    arrow = dt.to_pyarrow_table(columns=list(found.values()))
    return arrow.rename_columns([inverse[c] for c in arrow.column_names]).to_pylist()


def plan_build(datasets: list[SourceDataset], include_lookups: bool = False) -> list[TablePlan]:
    plan = []
    for table in TABLE_SPECS:
        if table in LOOKUP_TABLES and not include_lookups:
            plan.append(TablePlan(table, physical_table(table), 0, (), (), "app-owned lookup: not written"))
            continue
        fields = spec(table)
        partition = tuple(PARTITION_BY.get(table) or ())
        plan.append(TablePlan(table, physical_table(table), len(_dataset_rows(datasets, table)),
                              tuple(column(table, f) for f in fields), partition))
    return plan


def build_local(datasets: list[SourceDataset], root: Path, *, schema: str = "", include_lookups: bool = False,
                dry_run: bool = False) -> BuildReport:
    """Write the datasets to a local lake in the mapping's shape (overwriting, so a re-run is idempotent) and reconcile."""
    report = BuildReport(dry_run, plan_build(datasets, include_lookups))
    if dry_run:
        return report
    import pyarrow as pa
    from deltalake import write_deltalake

    for table in tables_to_write(include_lookups):
        parts = [_to_arrow(ds, table) for ds in datasets]
        combined = pa.concat_tables(parts) if len(parts) > 1 else parts[0]
        target = table_path(root, table, schema)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_deltalake(str(target), combined, mode="overwrite", partition_by=PARTITION_BY.get(table), schema_mode="overwrite")
    report.reconciliation = reconcile(datasets, root, schema, include_lookups)
    return report


def reconcile(datasets: list[SourceDataset], root: Path, schema: str, include_lookups: bool) -> list[dict[str, Any]]:
    """Per table: rows and checksum before (the datasets) against after (the lake)."""
    out = []
    for table in tables_to_write(include_lookups):
        fields = spec(table)
        before = _dataset_rows(datasets, table)
        after = read_back(root, table, schema)
        b, a = checksum(before, fields), checksum(after, fields)
        out.append({"table": table, "physical": physical_table(table), "rows_before": len(before), "rows_after": len(after),
                    "rows_match": len(before) == len(after), "checksum_before": b[:16], "checksum_after": a[:16], "checksum_match": b == a})
    return out


def quality_report(datasets: list[SourceDataset]) -> dict[str, Any]:
    """Data-quality findings over the datasets: row counts, nulls in required fields, orphan keys, date range."""
    payroll = [p for ds in datasets for p in ds.payroll]
    locations = {loc.location_id for ds in datasets for loc in ds.locations}
    codes = {c.pay_code_id for ds in datasets for c in ds.pay_codes}
    entities = {e.entity_id for ds in datasets for e in ds.entities}
    nulls = {name: sum(1 for p in payroll if getattr(p, name) is None) for name in ("pay_date", "hours", "wages", "pay_code_id", "worksite_location_id")}
    ids = [p.payroll_id for p in payroll]
    return {
        "accounts": len(datasets), "payroll_rows": len(payroll),
        "duplicate_payroll_ids": len(ids) - len(set(ids)),
        "payroll_null_counts": nulls,
        "orphan_location_ids": len({p.location_id for p in payroll} - locations),
        "orphan_pay_code_ids": len({p.pay_code_id for p in payroll if p.pay_code_id is not None} - codes),
        "orphan_entity_ids": len({p.entity_id for p in payroll} - entities),
        "pay_date_range": [min((p.pay_date for p in payroll if p.pay_date), default=None), max((p.pay_date for p in payroll if p.pay_date), default=None)],
    }
