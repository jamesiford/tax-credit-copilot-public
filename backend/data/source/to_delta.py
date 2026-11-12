"""Write source-schema datasets to a Fabric Lakehouse as Delta tables.

Lands the four tenants in the customer's source shape so the app reads what it
will eventually be handed, rather than a flattened demo export.

Layout
------
Written under the configured source schema (`SOURCE_SCHEMA`, default
`tcc_source`), alongside the existing `dbo` demo tables rather than over them:

    Tables/<schema>/Account          Tables/<schema>/Employment
    Tables/<schema>/Entity           Tables/<schema>/PayCode
    Tables/<schema>/Location         Tables/<schema>/PayFrequency
    Tables/<schema>/Address          Tables/<schema>/EntityFiscalYearRules
    Tables/<schema>/StateCountyZip   Tables/<schema>/Payroll

`Payroll` is partitioned by `AccountId`, mirroring the customer's own
`PayrollRange_PS([Accountid])`. That is the tenant boundary in their estate and
in ours, and it means a per-tenant read touches only that tenant's files.

Auth is `DefaultAzureCredential` against the OneLake storage scope — the same
path `tools/fabric_source.py` reads through. No keys, no connection strings.

Types
-----
Real types, deliberately. The demo lakehouse stored dates as `M/D/YYYY` strings
and currency as `'$2,061.19 '`; both are defects the source schema does not have
and neither does this. Dates land as `date32`, money as `decimal128(18, 2)`.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields as dataclass_fields
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from config import SOURCE_SCHEMA, get_settings

from .mapping import column, default_mapping, partition_columns, spec as mapped_spec
from .onelake import storage_options, storage_token, table_uri  # noqa: F401 - table_uri is re-exported for its callers
from .schema import SourceDataset

# The LOGICAL contract: which fields each table has and their types, taken from the default mapping so
# there is one list. Physical names (and which optional fields a lake carries) come from the mapping in
# force, through the resolver: nothing in this module spells a column.
_DECIMAL_18_2 = "decimal128(18, 2)"

TABLE_SPECS: dict[str, tuple[str, dict[str, str]]] = {
    # table name -> (dataset attribute, {field: arrow type})
    name: (table.dataset_attr, {f: m.type for f, m in table.fields.items()})
    for name, table in default_mapping().tables.items()
}


class _PartitionView(Mapping):
    """`PARTITION_BY[table]`: the physical partition columns under the mapping in force.

    Mirrors the partner's `PayrollRange_PS([Accountid])`: the tenant boundary is the physical partition, so
    a per-tenant read never scans another tenant's files.
    """

    def __getitem__(self, table: str) -> list[str]:
        columns = partition_columns(table)
        if columns is None:
            raise KeyError(table)
        return columns

    def __iter__(self):
        return (t for t in TABLE_SPECS if partition_columns(t) is not None)

    def __len__(self) -> int:
        return sum(1 for _ in self)


PARTITION_BY: Mapping[str, list[str]] = _PartitionView()


def _rows_for(dataset: SourceDataset, attr: str) -> list[Any]:
    value = getattr(dataset, attr)
    return [value] if not isinstance(value, list) else value


def _to_arrow(dataset: SourceDataset, table: str):
    """Build one Arrow table with an explicit schema, under the mapping's physical names and types."""
    import pyarrow as pa

    attr = TABLE_SPECS[table][0]
    spec = mapped_spec(table)
    records = _rows_for(dataset, attr)

    type_map = {
        "int64": pa.int64(), "int32": pa.int32(), "string": pa.string(), "bool": pa.bool_(),
        "double": pa.float64(), "date32": pa.date32(),
        "timestamp[us]": pa.timestamp("us"), _DECIMAL_18_2: pa.decimal128(18, 2),
    }
    physical = {f: column(table, f) for f in spec}
    schema = pa.schema([(physical[f], type_map[t]) for f, t in spec.items()])

    columns: dict[str, list[Any]] = {physical[f]: [] for f in spec}
    for rec in records:
        present = {f.name for f in dataclass_fields(rec)}
        for f in spec:
            columns[physical[f]].append(getattr(rec, f) if f in present else None)

    return pa.Table.from_pydict(columns, schema=schema)


def _required(value: str | None, name: str) -> str:
    """A setting the write cannot guess; unset raises `KeyError` naming it, as the direct read did."""
    if value is None:
        raise KeyError(name)
    return value


def _storage_options() -> dict[str, str]:
    return storage_options(storage_token())


def write_datasets(
    datasets: Iterable[SourceDataset],
    *,
    workspace: str | None = None,
    lakehouse: str | None = None,
    schema: str = SOURCE_SCHEMA,
    mode: str = "overwrite",
    tables: Iterable[str] | None = None,
    predicates: dict[str, str] | None = None,
) -> dict[str, int]:
    """Write every source table for every tenant. Returns rows written per table.

    Tenants are concatenated per table — one `Payroll` table holding all four
    accounts, partitioned by `AccountId`, which is how the customer stores it
    and what makes the tenant boundary physical rather than a predicate.

    `tables` restricts the write to named tables. A metadata correction — an
    account renamed, a location recoded — should not require rewriting hundreds
    of thousands of rows of confidential payroll to land.

    `predicates` maps a table to a Delta replace-where expression. With one, an
    overwrite replaces ONLY the matching rows and the schema is left alone, so
    one tenant can be rewritten without touching another's — which a plain
    overwrite cannot do, because it replaces the whole table with whatever
    datasets were passed in.
    """
    from deltalake import write_deltalake
    import pyarrow as pa

    configured = get_settings().data_source
    workspace = workspace or _required(configured.fabric_workspace, "FABRIC_WORKSPACE")
    lakehouse = lakehouse or _required(configured.fabric_lakehouse, "FABRIC_LAKEHOUSE")
    datasets = list(datasets)
    options = _storage_options()
    written: dict[str, int] = {}

    selected = list(TABLE_SPECS) if tables is None else list(tables)
    unknown = [t for t in selected if t not in TABLE_SPECS]
    if unknown:
        raise ValueError(f"unknown table(s): {', '.join(unknown)}")

    for table in selected:
        parts = [_to_arrow(ds, table) for ds in datasets]
        combined = pa.concat_tables(parts) if len(parts) > 1 else parts[0]
        predicate = (predicates or {}).get(table)
        write_deltalake(
            table_uri(table, workspace=workspace, lakehouse=lakehouse, schema=schema),
            combined,
            mode=mode,
            partition_by=PARTITION_BY.get(table),
            storage_options=options,
            predicate=predicate,
            schema_mode="overwrite" if mode == "overwrite" and predicate is None else None,
        )
        written[table] = combined.num_rows

    return written
