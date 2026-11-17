# Scale S1 report: a bounded, guarded payroll footprint

Branch `scale/s1-footprint`. Application code only (`dotnet/`); no Python, rule pack, engine, package or customer data touched.

## What changed

| Area | Change |
|---|---|
| Port (`ISourceReader`) | New `Footprint(IReadOnlyCollection<long> accountIds)`. The parameterless `Footprint()` stays and means "every client in the book" (`SqlClientSource` reads the account list, then the bounded form: never an untenanted scan). The bounded method is a default interface method that narrows the parameterless answer, so other implementations and the existing tests compile unchanged. |
| SQL (`SourceQueries.Footprint(ids)`) | One tenant-filtered `GROUP BY` per batch of at most `SourceScanner.IdBatchSize` (900) ids, `AND p.[account_id] IN (@p0,...)`. Ids are bound parameters, never concatenated. Results are merged per account. |
| `CsvClientSource` | Implements both overloads; results identical to before. |
| `GetPortfolio` | Rows are built and sorted as before, then paged, and `states` / `priceable_states` are filled **for the page rows only**. An empty page reads nothing. |
| `BatchPlanner.Plan` | Authorization first, then a lazy footprint: only for a `state` filter criterion (the authorized candidates) and only for program derivation (the selected clients). An explicit `program_code` with no state criterion reads nothing. A client read for a state filter is not read again for programs. |
| Guard (`FootprintGuard`) | `PORTFOLIO_FOOTPRINT_MODE`, `_MAX_ROWS`, `_TIMEOUT_SECONDS`, `_CACHE_SECONDS`, read through `IRuntimeConfiguration` on every call. Registered as a singleton in `RuntimeSourceRegistration`; `SqlClientSource` takes it as an optional argument, so a source built without it behaves exactly as before. |
| Estimate | `sys.dm_db_partition_stats` (`index_id IN (0,1)`) for the payroll table, only in `auto` mode, cached for the cache window (the estimate itself, including "no estimate"). Any source failure means no estimate. |
| Timeout | `AnalyticsQuery.TimeoutSeconds` (optional; null keeps the transport's 120 s). `SqlAnalyticsTransport.Read` sets `CommandTimeout` from it, so the driver cancels the statement on the server; a driver timeout (-2) on such a query becomes `SourceTimedOut`, which is not a `SourceUnavailable`, so it cannot enable fiscal fallback. |
| Typed failures | `SourceTimedOut` (transport) and `SourceFootprintUnavailable` (codes `footprint_off`, `footprint_too_large`, `footprint_timeout`; `Reason`, `Impact`, remedy names the settings). Both are `SourceFailureException` with dependency `source_sql`. |
| HTTP | `HostMiddleware` renders `SourceFootprintUnavailable` as 503 with the existing `{code, dependency, remedy}` plus `reason` and `impact`. Every other source failure keeps its exact body. |
| Frontend | None. `DegradedBanner.jsx` already renders `{dependency, impact, remedy}`. |

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `PORTFOLIO_FOOTPRINT_MODE` | `auto` | `auto` refuses above the limit when an estimate exists; `on` always runs under the timeout; `off` never runs. Unknown values mean `auto`. |
| `PORTFOLIO_FOOTPRINT_MAX_ROWS` | 50000000 | Largest estimated payroll table `auto` will scan. |
| `PORTFOLIO_FOOTPRINT_TIMEOUT_SECONDS` | 20 | Statement timeout for the footprint (and estimate) query. |
| `PORTFOLIO_FOOTPRINT_CACHE_SECONDS` | 300 | How long the estimate, and a timeout, are remembered. |

Invalid or non-positive values fall back to the default.

## Behaviour

| Situation | Portfolio | Batch planner (preview / start) |
|---|---|---|
| Healthy (small data, guard satisfied) | 200, byte-identical to before: `states`, `priceable_states`, `degraded: []`. | Same plan as before. |
| Over the limit (`auto`, estimate > max) | 200, `states: []` and `priceable_states: []` on the page rows, `degraded: [{dependency:"source_sql", impact, remedy}]`. No scan runs. | If the footprint is needed: 503 `{code:"footprint_too_large", dependency:"source_sql", remedy, reason, impact}`. If not needed (explicit program, no state filter): unaffected. |
| Timeout (statement cancelled at the limit) | Same degraded page, `footprint_timeout`; the next calls inside the cache window fail fast without scanning again. | 503 `footprint_timeout`, same shape. |
| `off` | Same degraded page, `footprint_off`, no query. | 503 `footprint_off` when needed. |
| No estimate available (endpoint lacks the view) | Scans under the timeout. | Same. |
| `on` | Scans under the timeout, no estimate query. | Same. |

## What was matched from Python, and where .NET differs

Matched: the three modes, the limit and timeout defaults, the catalogue estimate and its "no estimate means run under the timeout" rule, the driver-level statement timeout, and the `source_sql` degraded entry shape and wording. Not matched, deliberately:

- Python also reads the Delta log for an estimate; the brief rules out a Delta/OneLake reader, so only the catalogue is used.
- Python's planner falls back to one program-less item per client when the footprint cannot be read, and a state filter then matches nothing. The brief asks for a typed refusal, so .NET refuses, but only when the plan needed the footprint.
- Python remembers a guard decision for an hour. .NET remembers the estimate and a timeout for `PORTFOLIO_FOOTPRINT_CACHE_SECONDS` (default 300).

## Evidence

Tests added (existing projects only): `FootprintBoundTests` (Infrastructure.Sources.Tests, 14 cases incl. theory rows), `PortfolioFootprintTests` and `BatchFootprintTests` (Api.Tests, 11 cases), one assertion pair in `CertifiedSourceTests` for the CSV overloads.

- More than 900 accounts (1,502): two batches of 900 and 602 bound ids; the merged result equals the expected per-account states and the parameterless read.
- Portfolio `limit=10` over a 25-client book asks for exactly those 10 ids; `offset=10` the next 10; an empty page asks nothing; the parameterless read is never called.
- SQL text for a batch contains `IN (@p0,@p1)` and none of the id digits.
- Every mode and the limit boundary (50,000,000 runs, 50,000,001 refuses), the timeout reaching the statement, estimate caching with an injected clock, the timeout mapping, the degraded shape, and the planner refusals.
- Mutation checks (each broken once, seen red, restored): footprint read for all rows instead of the page; planner reading when an explicit program is given; limit comparison `<=` to `<`; no batching; `-2` mapping broken; degrade catch removed; remembered timeout and estimate cache disabled. Two in-test self-tests also fail their own check on deliberately wrong guard decisions and wrong page reads.
- Gates: see `scale-s1-log.md` for the final build, format and test results.

## Still open

- The footprint is still a scan when it runs. Above the limit it is refused, not served; a pre-aggregated summary read is the real fix.
- `Footprint()` over a very large book issues one statement per 900 accounts, each under the timeout.
- Without the catalogue view there is no estimate, so `auto` cannot protect that endpoint; the timeout still does.
- The per-client row cap, per-account dataset cache and Silver path gaps in `LOCAL-RUNBOOK.md` section 7 are untouched.
