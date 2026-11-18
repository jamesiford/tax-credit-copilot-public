# Data map

One complete JSON file names every database, schema, table and column the application uses, for the
Lakehouse (payroll source) and the Warehouse (operational store). **Nothing in your databases is renamed.**
The map only tells the application which actual names to use for each stable logical name the code speaks.

Files: [`data/data-map.json`](data/data-map.json) (the shipped example, with today's names),
[`data/data-map.schema.json`](data/data-map.schema.json) (JSON Schema), `scripts/generate-data-map.py`.

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

* **Keys are logical and never change; only the physical values do.** Warehouse table keys are
  `<gold|ops>.<logical table>`.
* **Complete, no hidden defaults.** Every entry the application uses must be present, including entries whose
  physical name equals the logical name. A missing or unknown key is a start-up error naming the key.
* Identifiers match `^[A-Za-z_][A-Za-z0-9_\-]{0,127}$`. Two logical tables mapped to one physical name in a
  schema, two logical columns mapped to one physical column in a table, and `gold` equal to `ops` are errors.
* Warehouse `type` is read-only information (what the column holds); the loader ignores it. Keys starting
  with `_` are notes and are ignored.
* **Databases:** `database.name` is `null` (use the environment setting) or a name. Precedence: environment
  setting, then the map's name, then the built-in default. Servers, credentials and endpoints are never in the
  map (`SOURCE_SQL_SERVER`, `FABRIC_SQL_SERVER`).

## Producing your file

1. Copy `docs/data/data-map.json`, or run
   `python scripts/generate-data-map.py --from-database --lakehouse-conn "<odbc>" --warehouse-conn "<odbc>" --out my-map.json`
   (read-only, `INFORMATION_SCHEMA` only). It pairs entries by case-insensitive exact name and writes every
   unmatched entry with a `null` physical value and a `_todo` note; it never guesses.
2. Complete every `_todo`.
3. Validate: `python scripts/validate-data-map.py my-map.json --check-database` (read-only; prints every
   missing table or column).

## Regenerating the shipped file

`python scripts/generate-data-map.py --defaults` rebuilds it from the Warehouse DDL and the Lakehouse source
mapping; `--check` fails if it differs. `backend/tests/test_data_map_shipped.py` proves it lists every table and
column in the DDL and the source mapping and nothing else.

Status of the remaining stages (resolver, DDL renderer, plan script, column mapping) is in
[`rename-r2-log.md`](rename-r2-log.md).
