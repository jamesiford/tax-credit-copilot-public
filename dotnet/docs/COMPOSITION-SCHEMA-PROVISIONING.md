# Composition schema provisioning

> **Names:** `tcc_ops`, `tcc_gold` and the table names below are the shipped defaults. The hosts resolve them through the data map (`DATA_MAP_FILE`, [`docs/DATA-MAP.md`](../../docs/DATA-MAP.md)). To provision under your own names, render the DDL with `backend/data_map_render.py` (it is the identity under the shipped map) and apply `0100_dotnet_operational_objects.sql` rendered the same way; the migration hashes recorded in `schema_migration` are of the shipped text and stay valid. Warehouse column names cannot be renamed yet.

## Scope and proof boundary

The existing Python migration/grant tools are unchanged. This document is the
handoff for a forward-only deployed migration, **not evidence of an applied or
live-tested Warehouse migration**. SQLite initialization/upgrades are implemented
and tested by `OperationalSchema.Initialize` / `OverrideOrder.UpgradeLocal`;
native runtime registration never silently initializes these tables.

Start from the existing product schema. Provision these additions in the same
operational database as the Gold publication transaction, with writers stopped
and the usual backup/change approval. Keep UTC `DATETIME2(3)` fields, existing
public IDs and monetary `DECIMAL(19,4)` unchanged.

| Object | Required columns / invariant |
| --- | --- |
| `tcc_ops.write_sequence` | `sequence_name VARCHAR(64) NOT NULL`, `last_value BIGINT NOT NULL`; exactly one row named `manual_override` |
| `tcc_ops.manual_override.write_order` | `BIGINT`, populated for every historical row, allocated transactionally for each new append |
| `tcc_ops.run_work_identity` | `client_id BIGINT NOT NULL`, `item_id VARCHAR(64) NOT NULL`, `run_id VARCHAR(64) NOT NULL`; unique logical `(client_id,item_id)` |
| `tcc_ops.run_source_observation` | `client_id BIGINT NOT NULL`, `run_id VARCHAR(64) NOT NULL`, `observation_json VARCHAR(8000) NOT NULL`; unique logical `(client_id,run_id)` |
| `tcc_ops.finding_audit` | `audit_id VARCHAR(64)`, `client_id BIGINT`, `finding_id VARCHAR(128)`, `action VARCHAR(16)`, `actor VARCHAR(256)`, `at VARCHAR(40)`, all NOT NULL |

The observation is the small source fingerprint JSON, not payroll or an employee
export. Retain the application's parameterized bindings. If a target requires a
different supported bounded string declaration, verify round-trip capacity
before enabling writers; do not truncate evidence.

## Upgrade order and historical tie policy

1. Stop **all** API/Worker writers. Check the sequence/table additions are absent
   or already match the intended migration; never reset an existing counter.
2. Add the sequence table/row and nullable `write_order`. Under the migration's
   exclusive maintenance window, assign missing orders after the existing high
   water mark, deterministically ordered by `created_at, override_id, client_id`.
   Set `last_value` at least as high as the maximum assigned value. Require one
   sequence row and no null/duplicate assigned orders before resuming.
3. Provision the identity, observation and finding-audit tables. Apply the
   database's supported integrity constraints and explicit operational grants.
   Fabric constraints may be NOT ENFORCED; that is not proof of uniqueness.
4. Verify counts, exact existing IDs/timestamps, and that running the migration
   again is a no-op. Verify save/change/clear/later-save at one timestamp across
   two independent connections and tenants, then verify publication recovery.
5. Resume writers only after the actual provider's transaction/conflict
   semantics and permissions have been verified in an approved environment.

Historical true order among identical timestamps was **never stored**. Sorting
old IDs is only deterministic migration behavior, not a reconstruction of user
intent. An owner must review affected overrides, especially clear events. The
new order guarantees apply to new writes. Local upgrade tests prove idempotent
backfill/reopen but cannot certify the historical decisions.

## Runtime protocol

Each append updates the shared sequence row, reads its value and inserts the
override in the **same serializable transaction**. This is not unprotected
`MAX+1`, a process counter, random GUID order or a SQLite rowid. SQL errors 24556,
3960 and 1205 use the existing confirmed-abort retry boundary. A missing or
duplicated sequence row fails explicitly. Do not repair it by accepting a
success-shaped fallback.

`run_work_identity` is durable before calculation. The accepted manifest is
checked before re-executing; Gold, manifest, claims and terminal queue state
publish atomically. An ambiguous acknowledgement is reconciled from reopened
terminal/manifest state; an unproved outcome is not blindly retried.

Hermetic native SQL tests verify statements, parameter types, tenant binding and
ordering. They do **not** establish deployed DDL compatibility, conflict/lock
behavior, managed-identity grants, pooling refresh, or cross-replica uniqueness.
Those are operator validation prerequisites, not gates claimed by this session.

## Stage S5 (bulk persist and retention): what it needs

- **No new table, staging table, schema change or storage account.** The bulk load (`SqlBulkCopy`) writes straight into the existing `tcc_gold` tables on the connection and inside the transaction the publish already uses.
- **Permissions.** The bulk protocol needs the same `INSERT` right on `tcc_gold.*` the statement path needed (Warehouse: the workspace role plus the existing T-SQL grants); nothing extra was needed on the live Warehouse used for the measurements.
- **Retention** (`RETAIN_SUPERSEDED_RUNS`, default 2) additionally uses `DELETE` on `tcc_gold.employee_period_fact`, `tcc_gold.onezero_matrix` and `tcc_gold.employee_eligibility`. Where the identity has no `DELETE`, a pass fails, is logged and skipped and nothing else is affected; set the setting to `all` to switch it off.
- `RUN_LEASE_SECONDS` and `RUN_LEASE_RENEW_SECONDS` need nothing from the database beyond the `UPDATE` on `tcc_ops.run_batch_item` the queue already uses.
