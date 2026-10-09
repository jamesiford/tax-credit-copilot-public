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

import os
from dataclasses import fields as dataclass_fields
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterable

from config import SOURCE_SCHEMA

from .schema import SourceDataset

# Column order and Arrow type per table. Explicit rather than inferred: an
# inferred schema changes shape when a column happens to be all-null in one
# batch, which is exactly the silent drift a source contract should not have.
_DECIMAL_18_2 = "decimal128(18, 2)"

TABLE_SPECS: dict[str, tuple[str, dict[str, str]]] = {
    # table name -> (dataset attribute, {field: arrow type})
    "Account": ("account", {
        "account_id": "int64", "account_eid": "int64", "name": "string",
        "billing_state": "string", "billing_city": "string",
        "billing_postal_code": "string", "industry_type_id": "int64",
        "account_status_id": "int64", "account_type_id": "int64",
        "actual_number_of_employees": "int64", "external_name": "string",
        "create_date": "timestamp[us]",
    }),
    "StateCountyZip": ("state_county_zips", {
        "state_county_zip_id": "int64", "state_abbr": "string",
        "state_name": "string", "county_name": "string", "zip_code": "string",
    }),
    "Address": ("addresses", {
        "address_id": "int64", "street_address_1": "string", "city_name": "string",
        "state_county_zip_id": "int64", "zip_code_original": "string",
        "state_original": "string", "latitude": "double", "longitude": "double",
    }),
    "EntityFiscalYearRules": ("fiscal_year_rules", {
        "fiscal_year_rules_id": "int64", "name": "string",
        "fiscal_year_begin": "date32", "fiscal_year_end": "date32",
        "rule_expression": "string", "inferred": "bool",
    }),
    "Entity": ("entities", {
        "entity_id": "int64", "account_id": "int64", "name": "string",
        "federal_tax_id": "string", "state_tax_id": "string",
        "parent_entity_id": "int64", "entity_business_type_id": "int64",
        "fiscal_year_rules_id": "int64", "inception_date": "date32",
        "dissolution_date": "date32",
    }),
    "Location": ("locations", {
        "location_id": "int64", "account_id": "int64", "entity_id": "int64",
        "location_name": "string", "address_id": "int64",
        "client_location_id": "string", "dba": "string",
        "open_date": "date32", "close_date": "date32",
        "location_status_id": "int64", "screening_status_id": "int64",
    }),
    "PayFrequency": ("pay_frequencies", {
        "pay_frequency_id": "int64", "name": "string", "inferred": "bool",
    }),
    "PayCode": ("pay_codes", {
        "pay_code_id": "int64", "account_id": "int64", "pay_code": "string",
        "description": "string", "is_aca": "bool", "is_futa": "bool",
        "pay_code_category_id": "int64",
    }),
    "Employment": ("employments", {
        "employment_id": "int64", "employee_id": "int64",
        "hire_location_id": "int64", "current_location_id": "int64",
        "status": "string", "job_title": "string", "hire_date": "date32",
        "start_date": "date32", "termination_date": "date32",
        "termination_reason": "string", "employment_type": "string",
        "wage_type": "string", "employment_status": "string",
        "department_number": "string", "department_name": "string",
    }),
    "Payroll": ("payroll", {
        "payroll_id": "int64", "account_id": "int64", "employee_id": "int64",
        "entity_id": "int64", "location_id": "int64",
        "pay_frequency_id": "int64", "pay_period_start": "date32",
        "pay_period_end": "date32", "pay_date": "date32",
        "hours": _DECIMAL_18_2, "wages": _DECIMAL_18_2,
        "client_employee_id": "string", "hourly_rate": _DECIMAL_18_2,
        "is_full_time": "bool", "is_salaried": "bool", "pay_code_id": "int64",
        "worksite_location_id": "int64", "inload_payroll_id": "int64",
        "create_date": "timestamp[us]", "modify_date": "timestamp[us]",
        "created_by": "int64", "modified_by": "int64",
    }),
}

# Mirrors the partner's PayrollRange_PS([Accountid]) — the tenant boundary is the
# physical partition, so a per-tenant read never scans another tenant's files.
# Named in the written (PascalCase) form, since that is what the Delta schema
# carries.
PARTITION_BY: dict[str, list[str]] = {"Payroll": ["AccountId"]}


def _pascal(name: str) -> str:
    """`pay_period_start` -> `PayPeriodStart`. Column names match the source DDL
    so a query written against the partner's database reads the same here."""
    return "".join(part.capitalize() for part in name.split("_"))


def _rows_for(dataset: SourceDataset, attr: str) -> list[Any]:
    value = getattr(dataset, attr)
    return [value] if not isinstance(value, list) else value


def _to_arrow(dataset: SourceDataset, table: str):
    """Build one Arrow table with an explicit schema."""
    import pyarrow as pa

    attr, spec = TABLE_SPECS[table]
    records = _rows_for(dataset, attr)

    type_map = {
        "int64": pa.int64(), "string": pa.string(), "bool": pa.bool_(),
        "double": pa.float64(), "date32": pa.date32(),
        "timestamp[us]": pa.timestamp("us"), _DECIMAL_18_2: pa.decimal128(18, 2),
    }
    schema = pa.schema([(_pascal(f), type_map[t]) for f, t in spec.items()])

    columns: dict[str, list[Any]] = {_pascal(f): [] for f in spec}
    for rec in records:
        present = {f.name for f in dataclass_fields(rec)}
        for f in spec:
            columns[_pascal(f)].append(getattr(rec, f) if f in present else None)

    return pa.Table.from_pydict(columns, schema=schema)


def _storage_options() -> dict[str, str]:
    from azure.identity import DefaultAzureCredential

    token = DefaultAzureCredential().get_token("https://storage.azure.com/.default").token
    return {"bearer_token": token, "use_fabric_endpoint": "true"}


def table_uri(table: str, *, workspace: str, lakehouse: str, schema: str = SOURCE_SCHEMA) -> str:
    """OneLake presents as ADLS Gen2, so a Delta table is a directory path."""
    return (
        f"abfss://{workspace}@onelake.dfs.fabric.microsoft.com/"
        f"{lakehouse}.Lakehouse/Tables/{schema}/{table}"
    )


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

    workspace = workspace or os.environ["FABRIC_WORKSPACE"]
    lakehouse = lakehouse or os.environ["FABRIC_LAKEHOUSE"]
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
