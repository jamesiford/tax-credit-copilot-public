# Source mapping

The engine reads **logical** entities and fields (`Payroll.pay_period_start`, `Account.account_id`). The lakehouse
holds **physical** tables and columns, named by whoever built it. The source mapping is the one description of the
link, so that a rename, a prefix, a casing difference or an unused field is a configuration change and not a code
change.

```
logical contract  ──►  mapping (JSON)  ──►  resolver  ──►  every consumer
(what the engine        default.json         data.source    Delta reader · Delta writer · SQL fast path ·
 knows how to read)     + optional file      .mapping       governed data-query model · tenant allow-list · grants
```

## What a mapping can and cannot do

| Config only | Needs code, or a named transform |
| --- | --- |
| Physical table names, prefixes, lower/upper casing | A new column the engine must use (a field in the schema and a use in the projection) |
| Column names and their case | A change in what a column means (`LocationId` versus `WorksiteLocationId`; `PaycheckDate` versus another date) |
| Type widening (a number stored as text is read with coercion) | A different grain |
| Adding or removing columns the engine does not use | |
| Per-environment overrides | |

A mapping that names a field the engine does not know is refused at load, with that sentence. A required field the lake
does not carry is a named error at read time (`SourceSchemaMismatch`, a 503 with the remedy), never a silent `None`.

## Files

- `backend/data/source/mapping/default.json` is the contract: per logical table its physical `table`, whether it is
  account-scoped (`tenant_field`), its `partition_by`, whether the table is optional (`optional_reason`), and per field
  its `column`, Arrow `type` and `required`.
- A **layered file** (`SOURCE_MAPPING_FILE`) says only what differs: `naming` (`table_prefix`, `table_case`),
  per-table `table`, per-field overrides under `fields`, `drop_fields` for an unused optional field, and `transforms`.
  A deployment keeps its own file outside the tracked tree.
- `SOURCE_TABLE_PREFIX`, `SOURCE_TABLE_CASE` and `SOURCE_TABLE_MAP` remain as per-environment overrides of the table names
  (`SOURCE_TABLE_MAP` wins).

Table name resolution: `SOURCE_TABLE_MAP` (verbatim) else prefix + the mapping's table name, with the case rule
applied to the whole result. A physical name must be a plain identifier; column names are bracket-quoted in SQL, so a
reserved word (`union`) is safe.

## Resolution

`data.source.mapping` is what consumers import: `physical_table`, `column`, `tenant_column`, `partition_columns`,
`spec`, `quoted` (a bracket-quoted reference), `describe`. The governed data-query package is pure and cannot import it,
so the composition root installs it (`bootstrap/data_wiring.py`, `application/data/source_names.py`).

**Case.** A Delta filter is case-sensitive. The reader resolves each mapped column to the table's actual spelling from
its own schema at first read (cached), so `Accountid` and `AccountId` both work and the same rule drives the validation
report.

**Projection.** The reader reads only the mapped columns that exist, keyed by logical field.

## Named transforms

| Transform | Choices | Why it is a transform |
| --- | --- | --- |
| `worksite_location` (`WORKSITE_LOCATION_SOURCE`) | `worksite_then_location` (default), `location_only`, `worksite_only` | Which location a row's jobs are counted at is a statutory-affecting meaning. Open question for the data owner |
| `null_pay_date` (`NULL_PAY_DATE_POLICY`) | `period_end` (default), `exclude` | The paycheck date is nullable. The period end stands in (the row is flagged `_Pay_Date_Imputed` and counted) or the row is excluded and counted. Never a crash, never silent |

Each has a Python form (the projection) and a SQL form (the aggregates in `source_queries.py`); tests assert they agree.
The projection controls report how many rows each policy touched, and the load logs it.

## Validation

`python scripts/validate-source-schema.py` compares the mapping with the lake (schemas only, no rows):

- **errors** (exit 1): a required table or a required field's column is absent, or a required column's type cannot be read as mapped;
- **warnings**: an optional table or field is absent (reads as empty), a column's case differs, a column is stored as another
  type but is coerced, or the lake carries columns the mapping does not use.

`--print-effective` prints the mapping in force; `--root DIR [--schema S]` checks a lakehouse on local disk;
`--json` is machine-readable. The same check runs at start (`SOURCE_SCHEMA_VALIDATION`: `off`, `warn` default, `fail`)
and its verdict is in `/api/ready` under `source_schema`.

## Adding a column the engine must use

1. Add the field to the logical schema (`data/source/schema.py`) and to `default.json` with its type and `required`.
2. Use it in the projection (`to_bcs.py`); add a named transform if its meaning is a choice.
3. If it is a SQL aggregate input, add it to `source_queries.py` through `quoted(...)`.
4. A test fails if a physical column is spelled in code outside the mapping (`tests/test_source_mapping.py`).
