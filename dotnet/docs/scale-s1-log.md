# Scale S1 log: a bounded, guarded footprint

Running log for branch `scale/s1-footprint` (worktree `tcc-scale-s1`). Local commits only; nothing is pushed.

## Baseline (main @ 966aaab, before any change)

From `dotnet\`, with `TCC_PYTHON=C:\Projects\py312-oracle\.venv\Scripts\python.exe`:

- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors.
- `dotnet format TaxCredit.slnx --verify-no-changes`: exit 0.
- `dotnet test TaxCredit.slnx`: the baseline run overlapped my first edits, so only the projects that finished before
  them are a clean record: Domain 18, Auth 147, Ai 167, Shadow 8, Sources 109, Persistence 141, Parity 152, all passed.
  Api.Tests could not be baselined cleanly; its result after the change (below) is the evidence instead.

## S1.1 Design

### What Python does (the behaviour being ported)

- `footprint_guard.py`: modes `auto` | `on` | `off`; `auto` asks for a row estimate that does not scan
  (Delta log stats, else `sys.dm_db_partition_stats`) and refuses above `PORTFOLIO_FOOTPRINT_MAX_ROWS`; no
  estimate means "run under the timeout"; `on` always runs under the timeout; `off` never runs. The timeout is the
  driver statement timeout, so the server cancels the statement. Refusal/timeout/off are a typed
  `DependencyUnavailable("source_sql", reason, remedy, impact=...)`.
- `portfolio_reads.footprint`: that failure becomes a `degraded` entry on the page (`dependency`, `impact`,
  `remedy`); the page still answers with empty states. A guard decision is remembered for an hour.
- `runs/pairs.py`: an unreadable footprint makes the planner give every client one program-less item.
  `runs/selection.py`: a `state` filter reads the portfolio page, whose states are empty when degraded.

### Decisions where .NET deliberately differs or chooses

- Only the SQL catalogue estimate is ported (no Delta reader in .NET, per the brief). No estimate = scan under timeout.
- Planner: the brief asks for a typed actionable refusal. Matched from Python: the exception type/fields
  (`source_sql`, reason, remedy naming the settings), the modes, the limits, the timeout semantics. Not matched:
  Python's silent "one program-less item per client" fallback and its "state filter matches nothing" outcome. In
  .NET the planner refuses (HTTP 503 `{code, dependency, remedy}` through the existing `SourceFailureException`
  mapping) **only when it needed the footprint and could not get it**, because queueing N items that all decline,
  or reporting "matches no clients", is worse than being told why. Healthy path unchanged.
- Python remembers a guard decision for an hour. .NET caches the row **estimate** for
  `PORTFOLIO_FOOTPRINT_CACHE_SECONDS` (default 300, as asked) and also remembers a **timeout** for the same period,
  so a polled page does not re-pay 20 s per load against a table known to be too slow.

### Port shape

`ISourceReader`:

- `Footprint()` stays, meaning "every client in the book", implemented as `Footprint(ListAccounts() ids)`: never an
  untenanted scan.
- New `Footprint(IReadOnlyCollection<long> accountIds)`. It is a default interface method that filters the
  parameterless answer, so existing fakes in unmodified tests keep compiling; `SqlClientSource` and
  `CsvClientSource` override it.

`SourceQueries.Footprint(ids)` returns one `AnalyticsQuery` per batch of at most `SourceScanner.IdBatchSize` (900)
ids, `... WHERE <span> AND p.[account_id] IN (@p0,...)`, ids bound as parameters (never concatenated), with
`FilterField/FilterValues` set so the offline fixture transport can honour it. Results are merged per account.

### Guard

`FootprintGuard` (Infrastructure.Sources, singleton, registered in `RuntimeSourceRegistration`; optional constructor
argument of `SqlClientSource`, so code that does not register it behaves exactly as before):

- Reads `PORTFOLIO_FOOTPRINT_MODE` (`auto` default), `PORTFOLIO_FOOTPRINT_MAX_ROWS` (50,000,000),
  `PORTFOLIO_FOOTPRINT_TIMEOUT_SECONDS` (20), `PORTFOLIO_FOOTPRINT_CACHE_SECONDS` (300) through
  `IRuntimeConfiguration`, on every call (so the contract hook overlay applies). Invalid values fall back to defaults.
- `Decide(estimate)` is a pure function (the mutation-tested decision): `off` refuses; `on` allows; `auto` refuses when
  an estimate exists and exceeds the limit.
- The estimate is `SELECT SUM(CAST(row_count AS BIGINT)) FROM sys.dm_db_partition_stats WHERE object_id =
  OBJECT_ID(@p0) AND index_id IN (0,1)` run only in `auto` mode; any `SourceFailureException` means "no estimate".
  Cached by the guard singleton (the source itself is scoped per request).
- Timeout: `AnalyticsQuery.TimeoutSeconds` (optional, default null = the transport's global timeout, so nothing else
  changes). `SqlAnalyticsTransport.Read` sets `CommandTimeout` from it and maps a driver timeout (error -2) on such a
  query to `SourceTimedOut`, which is not a `SourceUnavailable`, so fiscal fallback is not enabled.
  `SqlClientSource.Footprint` turns it into `SourceFootprintUnavailable` (code `footprint_timeout`).

### Typed failures (all `SourceFailureException`, dependency `source_sql`)

- `SourceTimedOut` (transport level, generic remedy).
- `SourceFootprintUnavailable` with `Reason`, `Impact`, and codes `footprint_off`, `footprint_too_large`,
  `footprint_timeout`; remedies name the settings.

### Callers

- `GetPortfolio`: build and sort rows as today; slice the page; request the footprint **for the page ids only**
  (none when the page is empty); fill `states` / `priceable_states` on those rows. `SourceFootprintUnavailable` =>
  states `[]` on the page rows and `degraded = [{dependency:"source_sql", impact, remedy}]`, HTTP 200. Healthy path
  serializes identically (`degraded: []`).
- `BatchPlanner.Plan`: authorize first, then read the footprint lazily and only for clients that need it: for a
  `state` filter criterion, the authorized candidate set; for program derivation, the final selected ids, and not at
  all when an explicit `program_code` is given. A refusal propagates (typed, 503).
- The DegradedBanner already renders `{dependency, impact, remedy}`; no frontend change.

## Results after the change

- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors. `dotnet format --verify-no-changes`: exit 0.
- Full `dotnet test TaxCredit.slnx` (TCC_PYTHON set): Domain 18, Shadow 8 (replay unmodified), Architecture 16, Ai 167,
  Orchestrator 431, Auth 147, Sources 127 (109 + 18 new), Gateway 103, Persistence 141, Parity 152 all passed.
  Api.Tests: 413 of 419 in the all-projects run; the 6 failures were `HttpRequestException: Error while copying
  content to a stream` in heavy P2-staged tests while ten other projects ran in parallel (not an assertion).
  Re-run alone (`dotnet test tests\TaxCredit.Api.Tests --no-build`): **419 of 419 passed**, none of the existing Api
  tests modified.

## Decisions and notes (running)

- Edited three existing test files without changing any assertion: `SourceTestData.cs` (optional guard argument,
  estimate and timeout hooks on the recording transport), `CertifiedSourceTests.cs` (two CSV assertions added).
  `TaxCredit.Api.Tests` existing files and the Shadow replay are untouched.
- A footprint refusal inside `SqlClientSource` happens for named-client reads too, not only the whole book: the cost
  driver is the payroll table size, not the id count.
- `Footprint()` keeps an account in the result even when none of its rows carry a state (empty list), as before.
- `ENV-VARS.md` documents the Python host only (no .NET mention), so it is not edited; the runbook carries the .NET
  settings.
- Mutations run (each seen red, then restored): page read -> all rows; planner always loads; limit `<=` -> `<`;
  chunk 900 -> 100000; `-2` mapping disabled; degrade catch disabled; remembered timeout and estimate cache
  disabled. Compile-time-visible mutations (constant filters, an unused field) were rejected by the analyzers, so
  runtime-equivalent ones were used instead.
- No hard stop was hit: no healthy-path response changed, no Python edit, no package, no rule pack or engine change.