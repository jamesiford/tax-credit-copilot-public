# Scale S5 log: persisting a run to the operational store

Running log for branch `scale/s5-bulk-persist` (worktree `tcc-scale-s5`, from local `main` @ 1b23316, which already carries S1 to S4). Local commits only; nothing is pushed.
Machine: ARM64 Windows workstation shared with other sessions; every timing carries noise and the log says which runs are comparable.

## Baseline (main @ 1b23316, before any change)

From `dotnet\`, `TCC_PYTHON=C:\Projects\py312-oracle\.venv\Scripts\python.exe`:

- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors (42 s).
- `dotnet format TaxCredit.slnx --verify-no-changes`: exit 0.
- `dotnet test TaxCredit.slnx`: all green. Ai 167, Architecture 16, Domain 18, Shadow 8, Orchestrator 431, Auth 147, Gateway 103, Sources 189 (+4 opt-in skipped),
  Persistence 145, Api 438, Parity 152.

## What the code did

`GoldWriter.WriteRun` commits the manifest alone, then `Publish` runs in one serializable transaction: retire prior current rows, insert each Gold table through
`SqlSession.Insert`, validate (section 9), supersede. In production that `Transact` is nested inside `RunPublication.Publish`'s transaction, so the Gold publish,
the claim assessment and the queue completion all commit together at the outer commit.

`SqlSession.InsertRows` for SQL Server-family dialects sent multi-row `INSERT ... VALUES (?,...)` of `min(500, 2090 / columns)` rows: 104 rows for the 20-column
`employee_period_fact`, one statement at a time on one connection. SQLite used a prepared single-row statement.

## Findings that shaped the design

- **Nothing in a Gold read selects an old run's employee rows.** Every reader resolves `LatestRun` (a successful, unsuperseded manifest) and passes that `run_id`
  (`GoldReader`, `PeopleReads`, `RiskReads`, `SeriesReads`, `UnitReads`; the governed query catalogue pins `live_run`, `GoldQueryWhere.cs:20`; the Application callers take
  `run["run_id"]` from the envelope; no route accepts a run id). The Python readers do the same (`gold_reader/stmt_runs._stmt_latest_run`).
- **Retention cannot run "after the publish commit" from inside `WriteRun` alone**, because in production the outermost transaction is the use case's. `PersistenceDatabase.AfterCommit`
  queues housekeeping until the outermost commit (immediately when none is open) and drops it on a rollback or an ambiguous commit.
- Fabric Warehouse documents `SqlBulkCopy`/bcp as a supported ingestion path (BCP API, preview); it ignores `CheckConstraints`, `TableLock`, `KeepNulls` and `FireTriggers`.
  Source: <https://learn.microsoft.com/en-us/fabric/data-warehouse/ingest-data-bulk-copy>. Not verified live here (see below).

## S5.1 Harness

`PersistBench` (`Persistence.Tests/GoldWrite`, opt-in `TCC_RUN_BENCH=1`, sizes `TCC_BENCH_SIZES`, default 100000,400000,1000000, output `dotnet/artifacts/bench/persist-<label>.txt`).
It persists a synthetic payload (the committed golden run with the employee-grain tables scaled: `employee_period_fact` to N rows, eligibility and matrix to N/38 rows) through
`GoldWriter.WriteRun` and reports seconds, rows/s and statements per table from the S4 `RunSpans` (`persist.insert`, `sql.insert-batch`, `sql.bulk-copy`).
Targets: SQLite always; a SQL Server instance when `TCC_SQLSERVER_TEST` is set (statements, then bulk); the live Warehouse only when `TCC_LIVE_PROFILE=yes` and `az account show` works, on a
throwaway client id (>= 9,000,000,000,000) that is deleted afterwards and verified empty.

SQL Server target here: SQL Server 2025 LocalDB (17.0.4025.3). The ARM64 host cannot load LocalDB's x64 `SQLUserInstance.dll`, so the tests connect through the instance's named pipe
(`sqllocaldb i MSSQLLocalDB`, "Instance pipe name"), which changes on each start.


## Benchmark decision (17 Nov, 22:00)

The old statement path was measured at 100,000 rows (218.4 s, 966 statements) and 400,000 rows (836.5 s, 3,840 statements, about 500 rows/s) on LocalDB; the 1,000,000-row
run was stopped after the user decided it was not worth 35 minutes. **The 1,000,000-row baseline is therefore extrapolated, not measured: about 2,000 s at ~500 rows/s (estimate).**
`PersistBench` now measures the statement path only up to `BENCH_STATEMENTS_MAX_ROWS` (default 400000; 0 skips it) and prints an "EXTRAPOLATED, NOT MEASURED" line above it. No later run repeated the
slow baseline (all later runs used `BENCH_STATEMENTS_MAX_ROWS=0`). Raw outputs: `dotnet/artifacts/bench/persist-baseline-statements.txt` (old path),
`persist-after.txt` (SQLite, LocalDB bulk, retention), `persist-live.txt` and `persist-live-1m.txt` (live Warehouse, throwaway client, deleted and verified empty afterwards).
The user authorised the live run by asking for `TCC_LIVE_PROFILE=yes`.

## S5.2 Strategy

(a) `SqlBulkCopy` worked first on SQL Server and on the live Warehouse, inside the publish transaction, so (b) `COPY INTO` and (c) parallel staging were not built.
Selection is through `ISqlDialect.Bulk` (`BulkLoadPolicy`): SQLite is `Off` and keeps `InsertPrepared`. Settings: `TCC_BULK_LOAD` (on/off), `TCC_BULK_LOAD_MIN_ROWS` (1000), `TCC_BULK_TIMEOUT_SECONDS` (3600).
`TenantBinding.CheckInsert` still validates every row before any bulk byte is sent. Decimals are converted to CLR `decimal` (all deployed decimals are at most 19 digits); a value that does not fit sends the table down the statement path.
Stored rows proved identical (statements vs bulk) by a SHA-256 dump of every Gold table and `run_manifest` on LocalDB (`BulkLoadTests`).

## S5.3 Retention

`GoldRetention` (`TCC_RETAIN_SUPERSEDED_RUNS`, default 2, `all` disables, minimum 1): after the outermost commit (`PersistenceDatabase.AfterCommit`) the employee-grain tables `employee_period_fact`, `onezero_matrix`, `employee_eligibility`
of superseded runs older than the newest N are deleted, at most 5 runs per pass, one transaction per run, `employee_eligibility` last (it is the marker). The manifest, `unit_year_master`, `unit_credit_installment`,
`unit_month_summary` and `run_method_summary` are kept. A failed pass is logged and swallowed. `GoldWriter` defaults to retention off; the host turns it on from settings.

## S5.0 Lease renewal

Found: the lease was only heartbeated when an item started and at the publication boundaries, and the whole calculation and Gold write ran in one transaction that also wrote the queue row. Renewing from another
connection would have blocked (SQL Server) or conflicted (Warehouse snapshot isolation) against that transaction, so the publication was split: with a keeper, the calculation and write commit without touching the queue row,
the lease is verified right before that commit, then a short transaction finishes the item. A crash between the two is reconciled by the durable `run_work_identity` and the accepted manifest.
`RunLeaseKeeper` renews every `RUN_LEASE_RENEW_SECONDS` (default a third of `RUN_LEASE_SECONDS`, default 600) on its own task; the Gold writer checks `RunLeaseScope` at table and batch boundaries.
SQLite has one writer, so a renewal cannot land during the write there: `RenewalsReachTheQueue` is false, the clock fence is off and the lease is reinstated just before completion (`IRunBatchRepository.Reinstate`).
The local SQLite store now uses WAL. Test first: `LeaseRenewalTests.A_write_longer_than_the_lease...` failed on the pre-fix behaviour (renewal switched off) with `RunLeaseLost` and passes with renewal.
## Gates (S5.4)

From `dotnet\`, `TCC_PYTHON` set, `TCC_SQLSERVER_TEST` pointing at LocalDB:
- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors. `dotnet format TaxCredit.slnx --verify-no-changes`: exit 0.
- `dotnet test TaxCredit.slnx -m:1`: Architecture 16, Domain 18, Gateway 103, Ai 167, Auth 147, Sources 189 (+4 opt-in skipped), Orchestrator 431, Shadow 8, Parity 152 (unmodified, 7 m 39 s), Persistence 163 (was 145: +11 bulk, +6 retention, +1 bench that returns at once), Api 441 (was 438: +3 lease renewal).
- Two things went wrong in the first full run and were not product failures: LocalDB had idled out (its pipe name changes on each start), so the four SQL Server `BulkLoadTests` failed once and passed on a fresh start (all 11 and the whole Persistence suite pass);
  and `QueuedRunCostTests.A_queued_calculation_sends_no_statement_with_thousands_of_parameters` enumerated a list that spans from a concurrently running test were appending to (the listener is process-wide). That is a race in the test, exposed by the new slower lease tests running alongside it;
  it now reads a snapshot under the lock the writer already used. Its assertions are unchanged. Api 441/441 afterwards.
- Existing queue, publication, fault-injection, Parity and Shadow tests were not modified.
- No later run repeated the slow statement baseline.
