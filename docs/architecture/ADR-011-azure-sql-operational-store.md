# ADR-011 — Azure SQL Database as an alternative operational store

**Date** 2026-11-12 · **Status** Proposed (implemented offline; not yet run against a live Azure SQL database) ·
**Relates to** [ADR-007](ADR-007-warehouse-operational-store.md) (the Warehouse is the only operational store). This
ADR changes *which engine* "the Warehouse" can be; it does not add a second store or a second adapter.

## Context

`tcc_ops` (claims, findings, run manifests, overrides, channel state, artifacts, lookup overrides) and `tcc_gold`
(the display layer the pages read) are held in "the Warehouse", which has so far meant the Fabric Warehouse. The
persistence adapters are plain ODBC with a Microsoft Entra token for `https://database.windows.net/.default`, which is
also the Azure SQL audience, and the SQL is portable T-SQL by construction (no `MERGE`, `IDENTITY`, hints or
`CREATE INDEX`). A SQL Server DDL variant is already generated from the Fabric DDL by
`scripts/generate-schema-variants.py`.

A deployment may want the operational store on Azure SQL Database rather than on Fabric: the customer's platform team
already operates and governs Azure SQL, the operational store should not depend on Fabric capacity (which a
deployment may pause), or the Warehouse's lack of enforced keys is unwelcome for data that lands on a filed return.

## Decision

Support Azure SQL Database as the store for `tcc_ops` and `tcc_gold`, selected by configuration, **default unchanged**:

- `WAREHOUSE_PLATFORM=fabric|azure_sql` (default `fabric`). The store settings (`CLAIM_STORE=warehouse` and the
  others) keep the adapter name `warehouse`; `azure_sql` and `sql` are accepted as aliases of it, as `fabric` is.
  A deployed process still refuses any non-durable store.
- The payroll **lakehouse stays in Fabric**. Its SQL aggregate reads use their own connection
  (`LakehouseSqlConnection`, `LAKEHOUSE_SQL_SERVER` / `LAKEHOUSE_SQL_DATABASE`), so the lakehouse and the Warehouse may
  be different hosts. This was previously an unstated assumption that the two shared one.
- **Schema and migration tooling is platform-aware.** For `azure_sql` the target guard compares the configured server
  FQDN and database to an allow-list instead of resolving a Fabric item (`schema_platform.py`,
  `scripts/sql_common.py`). The destructive bootstrap keeps its rules: it runs at most once, only where
  `tcc_ops.schema_migration` does not exist, and only on a target approved for it (`TCC_SQL_CREATED=true` when Terraform
  just created the database, or a pinned target with `bootstrap_approved`). A mismatch raises before any statement runs.
- **The Fabric T-SQL subset is valid SQL Server except `NOT ENFORCED`.** The bootstrap uses the generated SQL Server
  DDL; every numbered migration is applied with `NOT ENFORCED` removed at apply time, so a migration added later is
  covered without a second file that could fall behind. The recorded hash is the file's, so both platforms agree.
- **Database users are T-SQL, not Terraform.** `scripts/grant-sql.py --platform azure_sql` creates each identity
  `FROM EXTERNAL PROVIDER` (idempotently) and then applies the same `api` and `gateway` grants as
  `grant-warehouse-sql.py`. Entra authentication only: no SQL login and no password exist anywhere. The server's Entra
  admin (or a principal allowed to create external users) must run it.
- **Terraform** gets a module `infra/modules/azure_sql` (Entra-only server with an admin group, TLS 1.2, a database
  with a SKU variable, auditing to Log Analytics, and a private endpoint or firewall rules) chosen by
  `warehouse_platform`, off by default. It feeds `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE` and `WAREHOUSE_PLATFORM`.
- **Adapter behaviour.** Pool size and age can be overridden (`WAREHOUSE_POOL_MAX_IDLE`,
  `WAREHOUSE_POOL_MAX_AGE_SECONDS`); the defaults stay the Fabric measurements until Azure SQL is measured. The
  write-conflict retry (24556, 3960, 1205) is unchanged. Duplicate-key errors (2627, 2601) are recognised and reported
  as the same "already recorded" outcome the pre-check gives, because Azure SQL enforces keys and a race between the
  check and the insert now surfaces as an error rather than as a silent duplicate. Readiness
  (`/api/ready`, `scripts/check-operational-store.py`) names the Azure SQL remedy: create the user from the external
  provider, run the migration, add the firewall rule.

## What changes

- The configuration, tooling, Terraform and tests above. No route, response shape or certified figure changes.
- Primary keys become **enforced** on Azure SQL, and the "one current row" rule can become a filtered unique index.
  Neither is created automatically: promoting the constraint-intent blocks is a deliberate decision, as in
  `generate-schema-variants.py`.
- The append-only write path and "close the live row, insert the new one" transaction are unchanged in shape. Under
  Azure SQL's default isolation a concurrent writer waits on a lock where Fabric aborts with 24556; both are
  survivable, and the retry covers 1205 (deadlock).

## What is lost

- **Direct Lake over Gold is not native.** Fabric semantic models read a Fabric Warehouse directly. Mirroring the Azure
  SQL database into Fabric restores a read-only copy for analytics.
- **A mirrored database cannot host `tcc_gold` or `tcc_ops`**: mirroring is one-way and read-only. The operational
  store must be the Azure SQL database itself, with the mirror as a consumer.
- One more platform to operate and keep migrated.

## What is gained

- Enforced keys and, optionally, a filtered unique index for data that lands on a filed return.
- An operational store that does not depend on Fabric capacity (which a deployment may pause), so claims, findings
  and the channel audit stay writable when the capacity is off.
- Governance, backup and network controls the customer's platform team already runs.

## Operational prerequisites

ODBC Driver 18 for SQL Server; a firewall rule or a private endpoint (and its DNS zone, `privatelink.database.windows.net`)
between the API and the server; an Entra admin group on the server; Entra-only users created by `grant-sql.py`; the
schema loaded by `apply-migrations.py` (never by hand).

## Not yet done

No live Azure SQL run has been made. The checks to make, in order: acquire a token and connect; run `grant-sql.py`
as the Entra admin; run `apply-migrations.py --bootstrap`, then again (0 pending); run
`scripts/check-operational-store.py`; run the contract suite with `TCC_SQL_TESTS=1` against a test database (its rows
use a client_id block of their own and are deleted afterwards); run a realistic Gold load and measure insert throughput
(the 2,100-parameter ceiling is shared with SQL Server); review `warehouse_data_query.py` and the semantic model's SQL
against Azure SQL; measure idle-connection lifetime before changing the pool defaults.
