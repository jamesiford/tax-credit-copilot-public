# R2 log: data map

Worktree `..\tcc-rename-r2`, branch `rename/r2-data-map` from `main`/R1 tip (d088ff7). Never pushed.

## Baseline (before any R2 change)

* `dotnet build -warnaserror` clean; `dotnet format --verify-no-changes` clean.
* `dotnet test` (run while I was also building, so one Api failure is unreliable): Domain 18, Architecture 16, Ai 167,
  Orchestrator 431, Shadow 8, Auth 147, Gateway 104, Sources 189 (4 skipped), Persistence 163, Api 456 pass and 1 fail,
  Parity 152.
* Literals in `dotnet/src`: 218 lines with `tcc_(gold|ops|source)` in 49 files; Python 178 lines with `GOLD_SCHEMA|OPS_SCHEMA`.
* Warehouse DDL inventory: 38 tables (7 gold, 31 ops), 498 columns.
* Pre-existing, not R2: Python `test_orch_requirements` (2, package pins), `mcp`/`httpx2` missing so
  `test_gw_mcp_conformance` cannot be collected, `test_doc_links` (dead link in `dotnet/docs/ROUTES-READS-REPORT.md`),
  deploy configuration test `test_inventory_covers_every_documented_input_output_and_old_name` (fails on the R1 tip too).

## Stages

* **R2.1** design, schema, shipped file, generator, gate tests. Done.
* **R2.2** .NET: `Domain/DataMap` (model, loader, completeness, `PhysicalNames`), dialect choke point, logical tokens in
  38 files (mechanical script, then hand edits), host wiring (`DATA_MAP_FILE`, databases precedence, readiness
  `data_map`), Lakehouse mapping from the map, architecture test, loader tests, renamed-map SQLite test. Done.
* **R2.3** Python: `data_map_load.py`, `data_map.py`, config views, 118 sites in 27 files, tests, ratchet tightened. Done.
* **R2.4** renderer (identity under the shipped map for every DDL file), `render-schema.py`, apply-migrations/run-sql
  use it (migrations were never schema-renamed before), Terraform `data_map_file`, deploy staging and Dockerfiles,
  configuration inventory and docs. Design change recorded: DDL files stay literal to keep recorded migration hashes.
* **R2.5** `plan-data-map-change.py`, docs. Done.
* **R2.6** static statement identity (185 lines identical, 25 hand-edited hunks reviewed), SQLite renamed-map proof.
  **Not run:** SQL Server/LocalDB comparison, bulk-path Gold SHA-256 comparison, two-start `DATA_MAP_FILE` demo,
  Worker end-to-end with an alternate map (no SQL Server here; the Worker run was out of reach in this session).
* **R2.7** spike only, **NEEDS-HUMAN-REVIEW**; loader refuses Warehouse column renames in both hosts.
* **R2.8** gates below; report `docs/RENAME-R2-REPORT.md`.

## Final gates

* `dotnet build -warnaserror` 0 warnings, 0 errors; `dotnet format --verify-no-changes` clean.
* `dotnet test` full: Domain 27, Architecture 17, Ai 167, Shadow 8, Orchestrator 431, Auth 147, Gateway 104,
  Sources 189 (4 skipped), Persistence 164, Parity 152 all pass. Api 455 pass, 2 failed in the parallel run (5+ minute
  durations under load) and passed alone; baseline had the same kind of flake.
* Python full run before the last edits: 6892 passed; the 8 failures were the 3 pre-existing above plus mine, all fixed
  (adapters test, scripts index/hyphens, standards ratchet, schema-admin and failure-semantics stubs); targeted
  re-runs pass. A final full Python run was not repeated after the renderer/scripts commit; the targeted subsets
  (scripts, migrations, data_map, architecture, standards, schema) pass.
* Terraform: `fmt -check` clean, `validate` both stacks, `infra-dotnet` tests 14/14.
* Zero-remaining: `dotnet/src` has no physical schema name in `.cs` (test); remaining `tcc_` literals are the shipped map
  and DDL, tests of defaults, `model_excluded.py`, the SQLite function names, CHANGELOG and historical reports.
