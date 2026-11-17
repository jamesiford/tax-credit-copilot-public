# Scale S2 log: row cap setting, row cost, bounded portfolio load

Running log for branch `scale/s2-row-cap` (worktree `tcc-scale-s2`, from `main` @ c6a4b63). Local commits only; nothing is pushed.

## Baseline (main @ c6a4b63, before any change)

From `dotnet\`, `TCC_PYTHON=C:\Projects\py312-oracle\.venv\Scripts\python.exe`:

- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors (42 s).
- `dotnet format TaxCredit.slnx --verify-no-changes`: exit 0.
- `dotnet test TaxCredit.slnx`: all green, 12 min wall. Architecture 16, Ai 167, Domain 18, Shadow 8, Auth 147,
  Orchestrator 431, Gateway 103, Sources 127, Persistence 141, Parity 152, Api 419 passed; 0 failed, 0 skipped.

## S2.1 The setting

- Read the code: `SourceScanner` already throws `SourceTooLarge` one row past `maximumRows` (the check is before `output.Add`), per `Scan`
  call. `RuntimeSourceRegistration` built it with the default, so there was no setting.
- Added `SourceLimitSettings` (names/defaults, Application) and `SourceLimits` (parse + validate, Infrastructure.Sources).
  `SourceLimits.From(IRuntimeConfiguration)` runs once in `AddRuntimeSources`, so a bad value stops the host at startup with
  `InvalidOperationException("SOURCE_MAX_ACCOUNT_ROWS must be a whole number of at least 1,000.")`, the same style as the other parsed settings.
  Blank means default. Default stays **1,000,000**.
- `SourceTooLarge` remedy now names the setting and the limit. `MaterializedAnalyticsTransport` also threw `SourceTooLarge` for a
  decompressed-**byte** ceiling; it now passes `bytes: true` so its remedy does not claim a row limit.
- Mapping: `HostMiddleware` already returned 422 with `{code, dependency, remedy}` for `SourceTooLarge`; the remedy was the only thing lost
  (it was "Review the account row limit before retrying."). Only the remedy text changed. No healthy-path body changed.
- Tests: `SourceLimitTests` (default, override, 9 invalid values, remedy, read stops at limit + 1 row and disposes the stream),
  `SourceLimitResponseTests` (host defaults, host override, host invalid value stops startup, HTTP 422 body).

## S2.2 Row cost

See `SCALE-S2-REPORT.md` for the table. Method and gotchas:

- `RowCostBenchmark` (skipped unless `TCC_RUN_BENCH=1`) streams a synthetic client from a fake `IAnalyticsTransport` that yields a fresh
  `Dictionary<string, object?>` per row, as `SqlAnalyticsTransport.Materialize` does, so the table itself is never resident.
  It runs the real `SourceDatasetReader.Load` and `PayrollProjector.Project`. One size per test, one test per process (`dotnet test -c Release`).
- First numbers said the dataset was retained after being dropped (retained = scan + projection). That was the test, not the product: an
  unoptimized (Tier-0) test method keeps temporaries alive. Each phase now runs in its own `NoInlining` frame and a `WeakReference` proves the
  dataset was collected before "retained" is read.
- Timings vary 2-4x between runs on this shared machine; the memory figures reproduce within 1%.
- Optional compaction prototyped **in the benchmark only** (`CompactRow`, shared column-name array): scan 929 -> 480 B/row, peak -16% at 400k.
  Not adopted in production; see the report.

## S2.3 Portfolio load

- Python: `load_portfolio_pay_periods()` loops `list_accounts()` and reads every account's rows; the only bound is the per-account
  `SOURCE_MAX_ACCOUNT_ROWS`. Nothing bounds the number of accounts or the total. So .NET goes beyond Python here, as the brief requires.
- `SqlClientSource.LoadPortfolioPayPeriods`: lists accounts, refuses `SourcePortfolioTooLarge` (accounts) if the count is over
  `SOURCE_PORTFOLIO_MAX_ACCOUNTS`; then per account reads `PayrollScope(id).TotalRows` (the SQL aggregate), adds to a running total, refuses
  (rows) if over `SOURCE_PORTFOLIO_MAX_ROWS`, and only then reads that account's payroll. Small books: same keys, same rows.
- `SourcePortfolioTooLarge` code `portfolio_too_large`, mapped to 422 beside `SourceTooLarge`. Remedy: "Select fewer clients, or raise <setting>".
- Tests: accounts limit, rows limit stops before the crossing account's payroll scan (only account 7 scanned, two scope queries),
  first account over the limit reads no payroll at all, small book identical to unbounded, HTTP 422 body.
- Prove-it-fails mutations (each made the named tests fail, then reverted):
  reading payroll before the scope check (2 tests), scanner overshoot of +500 rows (1 test), dropping the minimum (4 tests).
  (Gotcha: restoring a file with `Copy-Item` kept its old timestamp, so an incremental build reused the mutated assembly and the host test
  saw a stale limit. Touch files after restoring.)

## NEEDS-HUMAN-REVIEW

None triggered: no calculation, healthy-path response, Domain, rule-pack, Python or package change. One flag for a human, not a hard stop:
the requested default `SOURCE_PORTFOLIO_MAX_ROWS` of 5,000,000 projected rows is about 13 GB (2.57 KB/row held at once); see the report.

## Final gates

From `dotnet\`, `TCC_PYTHON` set, after the last code change:

- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors.
- `dotnet format TaxCredit.slnx --verify-no-changes`: exit 0 (one missing final newline in the new benchmark file was fixed with `dotnet format`).
- `dotnet test TaxCredit.slnx` (12 min): Domain 18, Ai 167, Architecture 16, Shadow 8, Auth 147, Orchestrator 431, Gateway 103,
  Sources 144 passed + 4 skipped (the opt-in benchmarks), Persistence 141, **Parity 152 (unmodified)** all passed.
  Api.Tests: 420 of 423 passed in the solution run; a second full-suite run had 5 failures.
- Every failure was `HttpRequestException: Error while copying content to a stream` (a test-server request timeout) in a different
  slow staged-source test each run (`RuntimeResetTests.P2_...`, `ClientRunTests.Rebase_...`, `CalculationRecordingTests.Forecast_...(2004)`,
  `ClaimTests.Portfolio_...`, `BatchTests.Each_dispatch_...`). The machine was under memory pressure (about 6 GB free of 31 GB, other
  applications running). Each of those tests **passes when run alone** (22 tests of those three classes together: all passed; the other
  three singly), and `Each_dispatch_...` takes 1 m 5 s with this change against 1 m 38 s on an untouched `main` build under the same load,
  so the change does not slow it. I judge them load flakes, not regressions; a re-run on a quiet machine is the proper confirmation.
- New tests: Sources 17 (`SourceLimitTests`) + 4 benchmarks (skipped without `TCC_RUN_BENCH=1`), Api 4 (`SourceLimitResponseTests`).
- The Shadow replay and every other pre-existing test ran unmodified; no existing test file was edited except the `SourceTestData.Source`
  helper, which gained an optional `limits` argument.
