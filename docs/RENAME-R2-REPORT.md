# R2 report: the data map

Status: **R2.1 to R2.6 done for schemas, tables and Lakehouse columns; R2.7 (Warehouse column names) stopped with
`NEEDS-HUMAN-REVIEW`.** Branch `rename/r2-data-map` in worktree `..\tcc-rename-r2`, commits local only, nothing pushed.
Step-by-step record: [`rename-r2-log.md`](rename-r2-log.md).

## What a customer can do now

* Name every **database, schema, table and Lakehouse column** once, in one complete JSON file, and change them
  with a restart, no rebuild (`DATA_MAP_FILE`). Nothing in their databases is renamed.
* Map to Warehouse and Lakehouse tables they already have, under their own table and schema names, or provision
  ours under names they choose (`scripts/render-schema.py`, `scripts/apply-migrations.py`).
* **Not yet:** different names for Warehouse **columns** (`run_id`, `client_id`, ...). A map that tries is refused at
  start-up naming the column, in both hosts, so nothing is silently ignored.

## Map format and precedence

See [`DATA-MAP.md`](DATA-MAP.md). One file, `version 1`, `lakehouse` and `warehouse` sections, logical keys, physical
values, complete (38 Warehouse tables and 498 columns, 10 Lakehouse tables with every column, type, `required`,
`engine`). Shipped example `docs/data/data-map.json`, generated from the DDL and the source mapping
(`scripts/generate-data-map.py --defaults`; a test proves equality). Database name precedence: environment setting,
then the map, then the built-in default. Servers and credentials are never in the map.

Setting: `DATA_MAP_FILE` (path; unset = embedded shipped map; no inline JSON). Python keeps `SOURCE_MAPPING_FILE` as a
deprecated alias for a complete map; the .NET host does not read it (the deployed contract keeps it unsupported).
`/api/ready` reports `data_map: {status, source, sha256}` in the .NET host.

## Mechanism

* **.NET.** `TaxCredit.Domain.DataMap` (`DataMap`, `DataMapLoader`, `PhysicalNames`). Statements spell tables as
  `{ops.run_manifest}` tokens and table arguments as logical keys (`"ops.run_manifest"`); the dialects (`SqlDialect`,
  the single choke point) resolve them just before the provider, flattening to `<schema>_<table>` on SQLite.
  `PersistenceSchema` reads the DDL into logical keys; the seed importer, the capability evidence labels, the Lakehouse
  `SourceMapping` and scanner defaults, Terraform and the deployment staging all follow the map. An architecture test
  (`DataMapLiteralTests`) fails if a physical schema name appears in `dotnet/src`. Before: 218 literal lines in 49
  files; after: none.
* **Python.** `backend/data_map_load.py` (same rules), `backend/data_map.py` (accessors `names.ops.run_manifest`),
  `config.GOLD_SCHEMA/OPS_SCHEMA/SOURCE_SCHEMA` are views of the map (env overrides kept). 118 `{OPS_SCHEMA}.table`
  sites in 27 files became accessors; a test bans the old form.
* **DDL.** The shipped SQL files are **not** turned into placeholders. `schema_migration` records the SHA-256 of the
  shipped text; placeholders would change those bytes, so every recorded hash would stop verifying (a hard stop). The
  renderer (`backend/data_map_render.py`, the one place that rewrites finished SQL, a single-pass regex over schema,
  `schema.table` and `INFORMATION_SCHEMA` pairs) maps shipped names to the customer's. Under the shipped map it is the
  identity, byte for byte, for every DDL file (test). This also fixes a gap: migrations were never schema-renamed before.

## Customer workflow

Copy `docs/data/data-map.json` (or `generate-data-map.py --from-database`), complete the `_todo` entries,
`validate-data-map.py --check-database`, set `DATA_MAP_FILE`, restart. To provision under new names: render the DDL and
`0100` with `render-schema.py`, apply. An existing database under default names: `plan-data-map-change.py` prints review
SQL (never runs it, refuses anything destructive) and the manual steps are in `DATA-MAP.md`.

## Proof

| Check | Result |
| --- | --- |
| .NET build `-warnaserror`, `dotnet format --verify-no-changes` | clean |
| Persistence tests (163 + 1 renamed-map test) incl. bulk-load and provider-binding tests that assert `[tcc_ops].[manual_override]` and bulk destinations | pass |
| Renamed-map SQLite test: every schema and two tables renamed, claims written and read | 38 `cust_*` tables, no `tcc_*` table |
| Static statement identity (`scripts/maintainer/r2-verify-statement-identity.py d088ff7`) | 185 replaced lines resolve to exactly the line replaced; 25 hand-edited hunks (capability labels, seeds, retention, `GoldQueryBuild`, dialect) reviewed and covered by tests |
| Python: DDL renderer identity for all DDL files; renamed render leaves no `tcc_*` | pass |
| Python gate and standards ratchet | baseline tightened only |
| Terraform `fmt -check`, `validate`, `test` (`infra-dotnet` 14/14), `validate` (`infra`) | pass |

Results of the final full runs are in the log. Pre-existing failures, not caused by R2: the Python pin-check and
`mcp` conformance tests need packages absent here, `docs/ROUTES-READS-REPORT.md` has a dead link, and the deploy
configuration inventory test already failed on the R1 tip. Four .NET API tests are timing-sensitive under a loaded
machine (3 to 6 minutes each when the whole solution runs in parallel) and passed when re-run alone.

**Not done in this run, and why:** no SQL Server instance was available, so the LocalDB/SQL Server and bulk-path
comparison of Gold SHA-256 dumps, and the two-start "same build, different `DATA_MAP_FILE`" demonstration with a Worker
end-to-end run, were **not run**; the SQLite proof above is what exists. The recorded-statement dump (stage R2.6.1)
was replaced by the static identity check plus the unmodified persistence tests; a recording-connection dump of a
fixed scenario before and after is the open item to close that gap.

## R2.7: NEEDS-HUMAN-REVIEW (Warehouse column names)

Spike, no code shipped. 159 `session.*` call sites in 72 .NET files and about 184 Python `execute` sites spell column
names in statement text, results are read by name (`row["run_id"]`), 8 lines use `SELECT *` or `alias.*`, and
`GoldColumns`, `WarehouseVocabulary`, `PersistenceSchema` and the bulk copy `ColumnMappings` all key columns by name.
* **Text rewrite at the choke point** (tokenizer that skips literals and comments, rewrites a bare identifier only in
  the context of its table, aliases back with `AS <logical>`, expands `*`): needs a real SQL parser for correct table
  context across joins, CTEs and aliases. A regex cannot meet the safety bar; a parser is a new component with its own
  risk surface and no existing test corpus for the 340 statements.
* **Logical column constants / a statement builder** (preferred): rewrites every statement in 72 files and 184 Python
  sites by hand, plus result mapping. Safe, and large; best done directory by directory with the statement dump as the
  oracle.
* Either needs the recording-connection dump first (the missing proof above), so the first step is shared.

Decision for the owner: build the statement builder, or accept tables-only mapping for the first customer. Until then
the loader refuses a renamed Warehouse column.

## Still hardcoded

Azure resource names and the `tcc-dotnet` validation, `TaxCredit.*` namespaces, assemblies and telemetry names, the
Python package `tcc_shared`, the SQLite function names `tcc_decimal_sum`/`tcc_decimal_valid` and collation
`TCC_DECIMAL`, `backend/application/data/model_excluded.py` (documentation keyed by the shipped DDL names), the
literal DDL text and its recorded hashes (by design, above), Warehouse column names (R2.7), and the two
local-development seed tables `seed_table` and `seed_row` (SQLite only, placed in the source schema, not in the map).

## Customer section (email-ready)

> You can tell the application which names to use for your databases, schemas, tables and Lakehouse columns by
> editing one JSON file, `data-map.json`, and pointing `DATA_MAP_FILE` at it. The file lists everything the
> application uses, including entries that already have your names, so you can see exactly what to map. Nothing in your
> databases is renamed or dropped: we simply read and write the objects you name. Start from the shipped file, or run
> `generate-data-map.py --from-database` against your Lakehouse and Warehouse (read-only) for a first draft, finish the
> entries it marks, and check it with `validate-data-map.py --check-database`. A restart picks up a change.
> One limit today: Warehouse **column** names must stay as shipped; table, schema and database names and all Lakehouse
> column names can be yours.

## Files changed outside the repo

None. The S1 to S5 and R1 prompts in `GHCP-Prompts-DotNet\Scale-Reads` were not touched (outside the repository).
