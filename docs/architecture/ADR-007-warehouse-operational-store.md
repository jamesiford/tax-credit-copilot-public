# ADR-007 — The Fabric Warehouse is the only operational store; Cosmos DB is retired

**Date** 2026-10-08 · **Status** Accepted · **Supersedes**
[ADR-002](ADR-002-production-persistence.md) §1 (the document store as the
operational / decision store). ADR-002's ports-and-adapters decision, and its
analytical store, stand.

## Context

ADR-002 gave the system three stores: a document database (Cosmos DB) for
decisions, the Fabric Warehouse for calculation output and run provenance, and
SQLite for development and CI. Eight weeks in, the split had not earned its
cost:

1. **The Warehouse already held almost everything.** `run_manifest`,
   `manual_override` and the whole of Gold were written there by
   `fabric_warehouse.py` and `warehouse_gold.py`. Of the ten document
   containers provisioned, exactly three were ever written by application code:
   program claims, engagements and finding resolutions — and all three already
   had a table in the Warehouse schema (`program_claim`, `program_engagement`,
   `agent_finding_resolution`).
2. **Two stores meant two security models.** The document store's data-plane
   RBAC is a separate system from Azure RBAC and from Fabric's workspace roles.
   Every environment needed both granted, and a gap in either failed only at
   the first write.
3. **The customer's platform team asked for one store** they already operate
   and can govern, back up and query with tools they own.

## Decision

**The Fabric Warehouse is the only operational store.** Claims, engagements,
finding resolutions, run manifests, overrides, Gold and (from Platform v2) the
artifact registry all live in `tcc_ops` / `tcc_gold`. Cosmos DB is removed from
code, configuration, infrastructure and dependencies.

| Former container | Used | Now |
|---|---|---|
| `programClaims` | yes | `tcc_ops.program_claim` (+ `is_base_year`) |
| `engagements` | yes | `tcc_ops.program_engagement` |
| `findings` | yes | `tcc_ops.agent_finding_resolution` |
| `runManifests`, `snapshots` | no | already `tcc_ops.run_manifest`, `source_snapshot` |
| `tenants`, `decisions`, `proposals`, `scenarios`, `checkpoints` | no | dropped: never written |

Adapters: `WarehouseClaimRepository` (`warehouse_claims.py`) and
`WarehouseFindingRepository` (`warehouse_findings.py`), behind the same ports as
the SQLite adapters and held to the same shared contract suite
(`backend/tests/contracts/`). SQLite remains the local and CI adapter. A
deployed environment (`ENVIRONMENT != local`) refuses to start unless every
store is `warehouse`.

## The trade-offs this accepts, and how each is handled

### Partition key → predicate

The document store partitioned by tenant, so a query physically could not reach
another client's documents. The Warehouse has no partitions: one forgotten
predicate returns every client's rows.

The replacement is a rule the code cannot route around rather than a habit:

- `infrastructure/persistence/tenant_sql.py` builds every tenant-scoped
  statement. A statement carries a `{tenant}` marker as the **first** term of
  its `WHERE`/`ON` clause and the helper binds `client_id` itself; a statement
  without one is refused before it reaches a cursor. Inserts are checked row by
  row against the tenant.
- Crossing tenants is explicit: `tenant_exempt(reason)`, logged on every use.
  The portfolio coverage matrix, the stranded-run reaper, the section 9
  validation sweep, the connection keep-alive and run lookups by globally unique
  `run_id` are the only exemptions.
- `tests/test_architecture.py` fails the build if any
  `infrastructure/persistence/warehouse_*.py` or `fabric_warehouse.py` calls
  `execute` other than through the helper, and carries mutation checks proving
  the rule fires.
- The contract suites include cross-tenant cases: data written for client A is
  never returned for, or closed by a write for, client B.

This is weaker than physical partitioning against a determined bug in the
helper itself, and stronger against the common failure — a forgotten predicate
in a new query — because that query now cannot be written.

### Conflict retry instead of ETags

Fabric Warehouse writes run under snapshot isolation with table-level locking.
Two concurrent writers to the same table can abort one another with an update
conflict (error 24556). Every append-only write — close the live row, insert
the new one — runs in **one explicit transaction** (`run_in_transaction`), and a
conflict (24556, SQL Server's 3960, or deadlock 1205) is retried from the top
with capped exponential backoff (0.2 s doubling, cap 3.2 s, five attempts).
Re-running is safe because the close re-reads whichever row is live at that
moment. Any other error rolls back and is raised at once.

### Date grain on history

`program_claim.effective_from/effective_to` and the engagement equivalents are
`DATE` in the Warehouse, where SQLite keeps the instant. Two changes to one cell
on the same day share a date; history orders by date, then the live row last,
then `decided_at`. The contract suite asserts only what both adapters promise.

### No TTL, no change feed

Neither was in use: the only TTL container (`checkpoints`) was never written,
and nothing consumed a change feed.

## Consequences

- One store to provision, grant, back up and monitor. Access is a Fabric
  workspace role plus T-SQL grants on `tcc_ops` / `tcc_gold`.
- The schema is DDL v2.0 (`docs/data/schema/tcc-schema.fabric.sql`): a
  destructive bootstrap that runs once per Warehouse, then forward-only
  migrations recorded in `tcc_ops.schema_migration` (D22).
- Writes are slower than a document upsert and can conflict; the retry absorbs
  the conflicts that concurrency at this scale produces.
- A paused Fabric capacity now stops decisions as well as reads. The runbook
  covers the `ArtifactNotFound` symptom.
