# Data map

One complete JSON file names every database, schema, table and column the application uses, for the
Lakehouse (payroll source) and the Warehouse (operational store). **Nothing in your databases is renamed.**
The map only tells the application which actual names to use for each stable logical name the code speaks.
You may map to tables you already have, with your own names, or provision ours under names you choose.

Files: [`data/data-map.json`](data/data-map.json) (the shipped example, today's names, embedded in both hosts),
[`data/data-map.schema.json`](data/data-map.schema.json) (JSON Schema), `scripts/generate-data-map.py`,
`scripts/validate-data-map.py`, `scripts/render-schema.py`, `scripts/plan-data-map-change.py`.

## Shape

```
version                      1
lakehouse.database           { logical: "source", name: null | "<db>" }
lakehouse.schema             physical schema holding the source tables
lakehouse.naming/transforms  as in the former source mapping
lakehouse.tables.<Logical>   { table, dataset_attr, tenant_field?, partition_by?, optional_reason?,
                               columns.<logical>: { column, type, required, engine } }
warehouse.database           { logical: "warehouse", name: null | "<db>" }
warehouse.schemas            { gold: "<schema>", ops: "<schema>" }
warehouse.tables."gold.x"    { schema, table, columns.<logical>: { column, type } }
```

* **Keys are logical and never change; only the physical values do.** Warehouse table keys are `<gold|ops>.<logical table>`.
* **Complete, no hidden defaults.** Every entry the application uses must be present, including entries whose
  physical name equals the logical name (38 Warehouse tables, 498 columns; 10 Lakehouse tables). A missing or
  unknown key stops start-up and names the first one.
* Identifiers match `^[A-Za-z_][A-Za-z0-9_\-]{0,127}$`. Two logical tables mapped to one physical name in a
  schema, two logical columns mapped to one physical column in a table, and `gold` equal to `ops` are errors.
* Warehouse `type` is read-only information; the loader ignores it. Keys starting with `_` are notes.
* **Warehouse column names cannot be renamed yet** (stage R2.7 is open, see `RENAME-R2-REPORT.md`). A map that
  changes a Warehouse `column` value is refused at start-up rather than silently ignored. Lakehouse columns,
  and all schema and table names, are fully mapped.
* **Databases:** `database.name` is `null` (use the environment setting) or a name. Precedence: environment
  setting (`SOURCE_SQL_DATABASE`, `FABRIC_SQL_DATABASE`; Python `LAKEHOUSE_SQL_*`, `WAREHOUSE_*`), then the map,
  then the built-in default. Servers, credentials and endpoints are never in the map.
* `SOURCE_SCHEMA`, `GOLD_SCHEMA` and `OPS_SCHEMA` still override a schema name (deprecated; name it in the map).

## Where it is read

Both hosts read `DATA_MAP_FILE` once at start-up (a restart picks up a change; there is no hot reload). Unset
means the embedded shipped map. `SOURCE_MAPPING_FILE` is a deprecated alias in the Python backend and must now
hold a complete map; the .NET host does not read it. `GET /api/ready` reports
`data_map: { status, source: "embedded" | "file", sha256 }`, never the values. Deployed, the file ships next to
the rule packs (`resources/data-map.json`) and `DATA_MAP_FILE` may point at it or at a path you mount; with
Terraform set `data_map_file` (the setting is emitted only when non-empty).

## Producing your file

1. Copy `docs/data/data-map.json`, or run
   `python scripts/generate-data-map.py --from-database --lakehouse-conn "<odbc>" --warehouse-conn "<odbc>" --out my-map.json`
   (read-only, `INFORMATION_SCHEMA` only). It pairs entries by case-insensitive exact name and writes every
   unmatched entry with a `null` physical value and a `_todo` note; it never guesses.
2. Complete every `_todo`.
3. Validate: `python scripts/validate-data-map.py my-map.json --check-database --lakehouse-conn ... --warehouse-conn ...`
   (read-only; prints every missing table or column).

## Provisioning a new database under your names

```
python scripts/render-schema.py docs/data/schema/tcc-schema.fabric.sql --map my-map.json > my-schema.sql
python scripts/render-schema.py dotnet/deploy/sql/0100_dotnet_operational_objects.sql --map my-map.json > my-0100.sql
```

or run `DATA_MAP_FILE=my-map.json python scripts/apply-migrations.py` (bootstrap on a new Warehouse, then pending
migrations) which renders the same way. The shipped SQL files are left as they are, on purpose: `schema_migration`
records each migration's SHA-256 of the shipped text, so an already-provisioned database still verifies and
renaming never invalidates a recorded migration. The renderer is the one place that rewrites finished SQL.

## An existing database that holds our objects under the default names

The application never renames or drops objects. If you now want different names:
`python scripts/plan-data-map-change.py --current current-map.json --new my-map.json` prints (never runs) review
SQL: a check per object plus the `ALTER SCHEMA ... TRANSFER` / `sp_rename` statements as comments for an
operator. It refuses to emit anything destructive. Run what you accept by hand, with writers stopped.

If the database does not match the map, requests fail with the database's own error naming the missing object
(for example an invalid object name); `validate-data-map.py --check-database` finds all of them before you start.

## Regenerating the shipped file

`python scripts/generate-data-map.py --defaults` rebuilds `docs/data/data-map.json` and the backend's copy from the
Warehouse DDL and the Lakehouse source mapping; `--check` fails if either differs.
`backend/tests/test_data_map_shipped.py` and `dotnet/tests/TaxCredit.Domain.Tests/DataMapTests.cs` prove it lists
every table and column in the DDL and the source mapping, and nothing else.
