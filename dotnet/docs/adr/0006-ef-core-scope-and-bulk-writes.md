# ADR 0006: EF Core scope, bulk writes and Fabric Warehouse

Status: accepted for scope; bulk-copy support **unverified**. Date: 2026-11-14.

## Decision

- **EF Core only where it fits:** the `tcc_ops` operational tables (claims, findings, run manifests, overrides, audit),
  with **tenant isolation through global query filters** once an employer binding exists. Reads of Gold (`tcc_gold`) are
  hand-written SQL through ADO.NET behind the `GoldReadPort` equivalent: the grids are projections, whitelisted filters and
  aggregates, not entity graphs, and every money column must stay `decimal`/string end to end.
- **Never EF Core migrations against Fabric Warehouse.** Warehouse DDL is forward-only SQL applied by a migration runner
  (Python: `scripts/apply-migrations.py`, `tcc_ops.schema_migration`); Warehouse's T-SQL surface lacks features migrations
  assume. The .NET port reuses the same migration files and runner contract.
- **Bulk writes.** The Python adapter sends one multi-row `INSERT ... VALUES` per batch, measured 24x faster than
  `executemany` on Fabric, under the 2,100-parameter ceiling. The .NET adapter will do the same (a batch builder bound to
  the same ceiling).
- **Open question (not verified in this spike): is `SqlBulkCopy` supported against Fabric Warehouse?** It is only tested
  against SQL Server or SQLite, never Fabric, and must not be assumed. Until verified the multi-row `INSERT` is the contract.

## Consequences

EF Core stays out of the calculation and read paths, so the engine and the displayed figures never depend on change
tracking, tracking-query materialisation or provider decimal mapping.
