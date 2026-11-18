# Scale S4 log: where does one client calculation spend its time

Running log for branch `scale/s4-profile` (worktree `tcc-scale-s4`, from `main` @ c6a4b63). Local commits only; nothing is pushed.
All timings are wall-clock on a shared 12-core / 32 GB workstation that other sessions were also using, so every number carries noise;
the log says which runs are comparable.

## Baseline (main @ c6a4b63, before any change)

From `dotnet\`, `TCC_PYTHON=C:\Projects\py312-oracle\.venv\Scripts\python.exe`:

- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors (46 s).
- `dotnet format TaxCredit.slnx --verify-no-changes`: exit 0 (2 min 30 s).
- `dotnet test TaxCredit.slnx`: Domain 18, Architecture 16, Ai 167, Shadow 8, Auth 147, Orchestrator 431, Gateway 103, Sources 127, Parity 152
  passed. Three tests failed in that run: `GoldQueryTimeoutTests.Governed_query_actively_interrupts_SQLite...` (Persistence), and in Api.Tests
  `CalculationRecordingTests.Forecast_preserves_staged_source_values(2004)` and `RuntimeResetTests.P2_uses_staged_source_catalogue...`.
  The run overlapped one of my builds and the machine was loaded; all three are timing-bound, see "Test-suite noise" below.

## S4.1 Harness and spans

- `RunSpans` (`TaxCredit.Application/Hosting`): one `ActivitySource` named `TaxCredit.Run`. `RunSpans.Start(name)` returns `null` when nothing
  listens, so with telemetry off a span costs one volatile read and allocates nothing. `ServiceDefaults` now also subscribes the OpenTelemetry
  tracer to `TaxCredit.Run`, so the same spans reach a collector with no new package.
- Spans: `item`, `resolve`, `calculate`, `unchanged-check`, `run.calculation` (the Domain run, whole), `source.load` > `source.read` >
  `source.scan[table]` and `source.project`, `fingerprint`, `gold.write`, `gold.prepare[table]`, `persist.manifest|retire|insert[table]|validate|supersede|observation`,
  `sql.insert-batch[table]` (rows, bytes, parameters), `sql.execute`, `sql.query`, `db.begin`, `db.commit`, `publish`, `gold.validate`.
  Nothing was added inside `TaxCredit.Domain` (the engine's time is `run.calculation` minus its instrumented children).
- Harness: `tests/TaxCredit.Api.Tests/Bench` (opt-in, `TCC_RUN_BENCH=1`; otherwise the test returns immediately).
  `SyntheticAnalyticsTransport` is a fake `IAnalyticsTransport` serving one synthetic client (account 5001, three years of bi-weekly payroll,
  100 locations, staff hired across the years) in the real source shape; the real worker executor, real mediator pipeline, SQLite store.
  `GoldDump` hashes every stored Gold row (run id and `*_at` columns excluded: a fresh identity and the clock, not figures).
- Gate: `.\dotnet\bench-run.ps1` prints the table for 100k, 400k and 1M rows (`-Sizes`, `-Label`, `-DumpGold <dir>`).
- Artifacts: `dotnet\artifacts\bench\bench-<label>.txt` (not committed).

### Observations while building it

- A queued item at 1M rows outlived the 600 s lease (`RunLeaseLost`) in the first attempt, so the harness sets `LeaseSeconds = 7200`.
  Lease handling is reported in `SCALE-S4-REPORT.md`.
- The live-lakehouse profile was **not run**: `TCC_LIVE_PROFILE` is not set. Live figures in the report are derived from the harness, not measured.

## S4.2 Attribution

See `RUN-PROFILE.md`. Short form: one INSERT statement of 110 to 500 rows carries up to 2,090 named parameters, and Microsoft.Data.Sqlite
resolves each named parameter by a linear scan of the parameter list, so each statement costs about 20 ms regardless of the table's constraints
(`InsertCostProbe`: real schema with CHECKs and index 3.64 s, same columns with no CHECK and no index 3.70 s, per 20,000 rows).

## S4.3 Fixes

1. SQLite inserts re-bind one prepared single-row statement (`SqlSession.InsertPrepared`). SQL Server path unchanged.
2. `ScopedPayrollMemo`: one payroll read per scope (request or queued item) instead of four.

Both: stored Gold rows hash-identical before and after at 100k, 400k and 1M rows (hashes in the report).

## Final gates (on the committed tree, `TCC_PYTHON` set)

- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors.
- `dotnet format TaxCredit.slnx --verify-no-changes`: exit 0.
- `dotnet test TaxCredit.slnx`, one run on a quieter machine, all green: Domain 18, Architecture 16, Ai 167, Shadow 8, Orchestrator 431, Auth 147,
  Gateway 103, Sources 127, Persistence 145, Api 424, Parity 152 (unmodified).
- An earlier full run on the loaded machine had timing-bound failures that all passed in isolation and in this run (listed in `SCALE-S4-REPORT.md`).

## Test-suite noise

The Persistence, Api and Shadow tests involved include hard time bounds (an interrupt must fire within seconds) and subprocess oracles. With other sessions saturating the
CPU they fail without any code difference; reruns of exactly those tests alone passed.
