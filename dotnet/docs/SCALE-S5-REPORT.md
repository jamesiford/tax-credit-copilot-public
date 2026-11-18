# Scale S5 report: persisting a run to the operational store

Branch `scale/s5-bulk-persist` (from local `main`, which carries S1 to S4). Working log: `docs/scale-s5-log.md`. Local commits only; nothing pushed.

## Result in one paragraph

A client run's Gold write on the live Fabric Warehouse went from about 500 rows/s (multi-row INSERT, one statement of 104 rows at a time) to about 14,000 to 16,000 rows/s for `employee_period_fact`
with `SqlBulkCopy` inside the same publish transaction. A 400,000-row payload persists in 58 s in total (the old path measured 836 s on a local SQL Server and, per the user's live observation, more than 35 minutes on the Warehouse: **about 52x faster on the local SQL Server, and about 43x against the live 42-minute figure**); 1,000,000 rows takes 99 s. Stored rows are identical to the old path, atomicity is unchanged, and a running item now
keeps its queue lease for as long as it runs. **Live-Warehouse timings of the old path were not re-measured by this work**: the 35+ minute (42 minute) figure is the user's own live observation for a 384,418-row client; the
old-path numbers below are from LocalDB.

## Method

`PersistBench` (`Persistence.Tests`, opt-in `TCC_RUN_BENCH=1`) persists a synthetic payload through `GoldWriter.WriteRun`: the committed golden run with `employee_period_fact` scaled to N rows and eligibility and matrix to N/38 rows
(the measured client has about 38 pay-period rows per employee). Timings come from the S4 `RunSpans` (`persist.insert[table]`, `sql.insert-batch`, `sql.bulk-copy`). Targets: SQLite; SQL Server 2025 LocalDB
(`TCC_SQLSERVER_TEST`, ARM64 host, via the instance's named pipe); the live Warehouse (`TCC_LIVE_PROFILE=yes` and `az account show`) on a throwaway client id (at least 9,000,000,000,000) deleted and verified empty afterwards.
Peak working set is the process peak so far, not per case. All timings are wall clock on a shared workstation.

The old statement path was measured at 100,000 and 400,000 rows only; **1,000,000 rows of the old path is extrapolated, not measured** (about 2,000 s at ~500 rows/s, an estimate).
`BENCH_STATEMENTS_MAX_ROWS` (default 400000, 0 skips) governs this.

## Before and after

### Old path (multi-row INSERT), local SQL Server

| rows (`employee_period_fact`) | total s | `employee_period_fact` s (rows/s, statements) | eligibility s | matrix s | statements in total |
|---|---|---|---|---|---|
| 100,000 | 218.4 | 204.0 (490/s, 910) | 4.4 | 7.6 | 966 |
| 400,000 | 836.5 | 776.7 (515/s, 3,637) | 19.3 | 32.3 | 3,840 |
| 1,000,000 | **~2,000 (extrapolated, not measured)** | | | | |

### New path (bulk load), local SQL Server

| rows | total s | `employee_period_fact` s (rows/s) | eligibility s | matrix s | validate s | bulk loads |
|---|---|---|---|---|---|---|
| 100,000 | 5.3 | 2.49 (40,142) | 0.12 | 0.14 | 1.22 | 8 |
| 400,000 | 16.1 | 9.41 (42,494) | 0.25 | 0.35 | 1.65 | 8 |
| 1,000,000 | 36.8 | 23.50 (42,555) | 0.57 | 0.68 | 2.24 | 8 |

Speed-up against the old path on the same server: 41x at 100,000 rows, 52x at 400,000 rows (1,000,000: about 54x against the estimate).

### New path (bulk load), live Fabric Warehouse

| rows | total s | `employee_period_fact` s (rows/s) | eligibility s | matrix s | small tables s (each) | validate s | bulk loads | peak MB so far |
|---|---|---|---|---|---|---|---|---|
| 100,000 | 37.0 | 7.68 (13,017) | 1.24 | 1.29 | 0.40 to 0.50 | 11.59 | 8 | 552 |
| 400,000 | 58.1 | 28.30 (14,132) | 1.65 | 2.04 | 0.40 to 0.56 | 10.75 | 8 | 552 |
| 1,000,000 | 99.1 | 63.37 (15,781) | 2.55 | 3.96 | 0.43 to 0.58 | 10.90 | 8 | 1,279 |

On the Warehouse every small table costs about 0.4 s regardless of size (a fixed per-statement cost), and the section-9 validation costs about 11 s (a fixed cost: it scans the store). Those two are now a visible share of the total.
The old path's live cost for a 384,418-row client was more than 35 minutes (the user's observation, 42 minutes), so the gate of 20x on the 400,000-row case is met against that figure
(2,520 s / 58 s is about 43x); the like-for-like old-path number on the Warehouse itself was **not** measured.

### SQLite (unchanged path, for reference)

| rows | total s | `employee_period_fact` s (rows/s) | peak MB so far |
|---|---|---|---|
| 100,000 | 2.4 to 2.8 | 1.4 to 1.5 (about 66,000) | 282 to 336 |
| 400,000 | 10.0 to 10.5 | 5.9 (about 68,000) | 470 to 495 |
| 1,000,000 | 28.3 | 15.95 (62,685) | 1,019 |

SQLite keeps `InsertPrepared`; the figures differ from the baseline file only by noise.

### Retention (4 runs of 100,000 rows, keep 1 superseded)

Prune passes (seconds), one per publish: SQLite 0.01, 0.00, 0.25, 0.25. LocalDB 0.02, 0.02, 1.85, 1.35. Live Warehouse 3.94, 5.84, 12.76, 10.21 (the third and fourth publishes each prune one run of about 105,000 employee rows, in separate transactions after the publish commit; the first two have nothing to prune but still cost a manifest read and an existence probe).

## Strategy chosen and why the others were ruled out

- **(a) `SqlBulkCopy`: chosen.** Microsoft documents it as supported on the Warehouse (BCP API, preview; it ignores `CheckConstraints`, `TableLock`, `KeepNulls`, `FireTriggers`). It was verified live: inside the explicit publish transaction, on the Warehouse and on SQL Server, same code path.
  Values are converted exactly as statement parameters are (`StorageColumn.ConvertValue` already ran; decimals become CLR `decimal`, dates `DateTime`), rows keep their order, `TenantBinding.CheckInsert` runs for every row first.
  Equivalence is proved by a SHA-256 dump of every Gold table and `run_manifest` after a statement-path run and a bulk-path run (`BulkLoadTests`, LocalDB). Fault injection after each stage on SQL Server leaves no rows and no current-run flip; the existing SQLite fault-injection tests pass unmodified.
- **(b) `COPY INTO` from staged files: not built.** It needs a staging location and identity grants and (a) already met the goal; it stays the documented upgrade ("for the highest throughput, stage files") if the 28 to 63 s for the big table ever matters.
- **(c) parallel batches into a staging table: not built.** It is the fallback if a Warehouse ever rejects the bulk protocol; the kill switch `TCC_BULK_LOAD=off` restores the old behaviour meanwhile.
- SQLite is untouched (`InsertPrepared`). Azure SQL uses the same `SqlServerDialect` as the Warehouse; it was exercised through SQL Server (LocalDB), not an Azure SQL instance (**untested live**).

Settings: `TCC_BULK_LOAD` (on, off), `TCC_BULK_LOAD_MIN_ROWS` (1000), `TCC_BULK_TIMEOUT_SECONDS` (3600). Below the minimum, or when a connection or value cannot be bulk loaded, the statement path is used.

## Retention behaviour (S5.3)

`TCC_RETAIN_SUPERSEDED_RUNS` (default 2; `all` switches it off; minimum 1 so a reader that resolved the current run an instant before a newer publish supersedes it still finds its rows).
After the outermost commit, the employee rows (`employee_period_fact`, `onezero_matrix`, `employee_eligibility`) of superseded runs beyond the newest N for that client and program are deleted, at most 5 runs per pass, one transaction per run,
`employee_eligibility` last as the marker so an interrupted pass is finished by the next. Never inside the publish transaction; skipped on a rollback or an ambiguous commit; a failed pass is logged and ignored. Kept: manifests, `unit_year_master`, `unit_credit_installment` (history through `is_current`), `unit_month_summary`, `run_method_summary`.

Reader audit (why this is safe): every Gold read resolves `LatestRun` (a successful, unsuperseded manifest) and uses that run's id (`GoldReader`, `PeopleReads`, `RiskReads`, `SeriesReads`, `UnitReads`); the governed query catalogue pins employee datasets to `live_run`;
the Application callers take the id from the run envelope; no route accepts a run id; the Python readers use `_stmt_latest_run` too. A "named run" port member (`Employee(..., runId)` etc.) given a pruned run returns no rows, the same shape as an unknown run.
Tests (`GoldRetentionTests`): newest runs untouched and older pruned; other client and program untouched; a refused delete (trigger) leaves the published run intact and the pass atomic per run, and the next publish finishes it; pruning waits for the outer commit and never follows a rollback;
every reader result for the current run (about 25 calls, both methods) is byte-identical with and without retention.

**Skip when unchanged (recommendation only, not implemented).** Reusing the previous run's employee rows by reference when the source fingerprint is unchanged would need either a `source_run_id` pointer column on the employee tables or a reader change from `run_id = ?` to a manifest join; both are schema or reader-contract changes. The queue already skips an unchanged item (`SkipUnchanged`); only a forced re-run pays the write. Estimate: 3 to 5 days including the Python readers and a backfill, saving a full write (now 30 to 100 s) only for forced re-runs of unchanged data. With bulk loading it is low value; retention bounds the storage.

## S5.0 Lease renewal

The incident: a 384,418-row write took 42 minutes, the 600 s lease lapsed, the attempt rolled back, the item was reaped and re-claimed, and the Worker started again.
Cause: the lease was heartbeated only when an item started and at publication boundaries, and the calculation and Gold write ran inside one transaction that also wrote the queue row, so another connection could neither renew without blocking (SQL Server) nor without a write-write conflict at commit (Warehouse snapshot isolation).

Fix:
- `RunLeaseKeeper` renews on its own task and connection every `RUN_LEASE_RENEW_SECONDS` (default a third of `RUN_LEASE_SECONDS`, default 600, unchanged), until the item finishes or fails.
- With a keeper, `RunPublication.Publish` commits the calculation and Gold write without touching the queue row, verifies the lease immediately before that commit (fenced by the clock: the lease is trusted only until the last renewed expiry minus one renewal interval, and a claimant cannot take the item before that expiry), then finishes the item in a short transaction. A crash between the two is reconciled by the durable run identity and the accepted manifest (the same path as an ambiguous acknowledgement).
- A failed renewal ends the item with `RunLeaseLost`; the Gold writer checks the lease at every table and batch boundary and stops, rolling back. (A bulk load of one table is not interruptible mid-table; it is bounded by that table's time.)
- SQLite has a single writer, so a renewal cannot land during the write transaction there; the clock fence is off for it, nobody can claim the item during that write either, and the lease is reinstated just before completion. The local SQLite store now uses WAL.
- Without a keeper, `Publish` is unchanged (the existing tests pin it).

Tests (`LeaseRenewalTests`): a Gold write of 8 s against a 3 s lease succeeds with one attempt, one identity and one manifest (it failed with `RunLeaseLost` when renewal was switched off, which is the pre-fix behaviour);
a renewal that finds the lease gone makes the keeper throw and `RunLeaseScope` stop a write; an attempt that loses its lease commits nothing and the next attempt publishes the same single run (`run_work_identity` still holds one run id, one manifest).
The existing queue and publication tests pass unmodified.

## Gates

See the final section of `docs/scale-s5-log.md` for the build, format and test results.

## What is untested live

- Azure SQL (same dialect as the Warehouse; exercised on SQL Server only).
- Lease renewal against a live Warehouse (snapshot isolation conflicts): proven by construction and on SQLite, not by a 40-minute live write.
- The old statement path on the live Warehouse was not re-measured; the live old-path figure is the user's observation.
- Retention against the Warehouse was timed; the `DELETE` permission it needs is the identity's, which worked for the throwaway client.

## Recommendations for the data owner (for the customer email)

1. **Sizing and growth.** Each run writes a full copy of the employee-grain tables: for a client with 384,418 payroll rows that is about 384,000 `employee_period_fact` rows plus about 10,000 eligibility and matrix rows, per run, and a client with several tax years multiplies it. Without retention the store grows by that amount on every run, forced or not.
2. **Keep every run's employee snapshot?** Nothing in the product reads a superseded run's employee rows; the manifest and unit-level tables already carry the history that audit needs. Recommended: keep the current run plus the two before it (the default), and rely on the manifest for older runs. Say so if the customer wants a longer forensic window or none (set to `all`).
3. **Permissions and staging storage.** The bulk path needs nothing new: the same `INSERT` right as before and no staging storage. Retention needs `DELETE` on the three employee-grain tables. If the customer later wants the highest-throughput load (`COPY INTO`), it would need a OneLake or ADLS staging location and the host identity's access to it.
4. **Capacity.** The remaining fixed costs on the Warehouse are about 0.4 s per small table and about 11 s of section-9 validation per publish; these do not grow with the payroll size.
