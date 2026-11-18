# R2 log: data map

Worktree `..\tcc-rename-r2`, branch `rename/r2-data-map` from `main` (d088ff7). Never pushed.

## Baseline (before any R2 change)

* `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors. `dotnet format --verify-no-changes`: clean.
* `dotnet test`: suites seen passing include Infrastructure.Ai 167, Domain 18, Architecture 16, Orchestrator 431,
  Shadow 8, Auth 147, Gateway 104 (full per-suite totals appended below when the run finished).
* Literal count in `dotnet/src`: 218 lines with `tcc_(gold|ops|source)` in 49 files. Python: 178 lines with `GOLD_SCHEMA|OPS_SCHEMA` in `backend/`.
* Warehouse DDL inventory (parsed from `tcc-schema.fabric.sql`, migrations 0001-0005 and `0100`): 38 tables (7 gold, 31 ops), 498 columns.

## R2.1 design (done)

* `docs/DATA-MAP.md`, `docs/data/data-map.schema.json`, `docs/data/data-map.json` (generated, 78 KB).
* `scripts/data_map_ddl.py` parses the DDL; `scripts/generate-data-map.py --defaults [--check]` / `--from-database`.
* Gate test `backend/tests/test_data_map_shipped.py`: schema validates, inventory equals DDL + `default.json`, generator reproduces the file byte for byte.
* Shape decisions: Lakehouse `fields` become `columns` (lossless: `dataset_attr`, `partition_by`, `optional_reason`,
  `required`, `engine` kept); Warehouse columns are `{column, type}`; warehouse table keys are `gold.x` / `ops.x`.

## Remaining

R2.2 to R2.8 not started. See the bottom of this file for status.
