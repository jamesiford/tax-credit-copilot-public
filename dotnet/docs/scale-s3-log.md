# Scale S3 log: per-client projection cache (off by default)

Running log for branch `scale/s3-cache` (worktree `tcc-scale-s3`, from `main` @ 9bc7d41). Local commits only; nothing is pushed.

## Baseline (main @ 9bc7d41, before any change)

From `dotnet\`, `TCC_PYTHON=C:\Projects\py312-oracle\.venv\Scripts\python.exe`:

- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors (39 s).
- `dotnet format TaxCredit.slnx --verify-no-changes`: exit 0.
- `dotnet test TaxCredit.slnx`: see "Baseline tests" below.

## S3.1 Design (written before any code)

### What I read

`ClientSource.cs`, `Sql/SourceQueries.cs` (`SourceFingerprintReader`), `Projection/PayrollProjector*.cs`, `Projection/SourceDataset.cs`,
`Lookups/LookupResolver.cs`, `Mapping/SourceMapping.cs`, `RuntimeSourceRegistration`, `RunItemExecution`, `ObservedGoldWriter`, and every
caller of `LoadPayPeriods` / `LoadProjection` (Domain `ClientCalculation`, `ClientRunResolver`, `PayrollRows`, `StateCreditCalculator`;
Application `RunItemExecution`, `AssessClient`, `ListFindings`, `ReadsPortfolioService`, `ReadsUnitTrendService`; `SqlClientSource.LoadPortfolioPayPeriods`).

### Facts that shape the design

1. **`LoadProjection` depends on more than the Payroll table.** The projection reads Account, Entity, Location, PayCode, Address, StateCountyZip,
   Employment, EntityFiscalYearRules and PayFrequency, and resolves pay codes through `LookupResolver` (operator-edited lookup entries plus
   a seed file, under `PAY_CODE_POLICY` and `DATA_CLASSIFICATION`). The fingerprint observes only `COUNT_BIG(*)` and `MAX(modify_date)` of
   **Payroll** for the account and a hash of the discovered Payroll column names. So a dimension edit is invisible to it (stated as a
   limitation); a **lookup** edit is not a source change at all, so I add a cheap lookup digest (below).
2. **Inputs that change the projection but are constant for a process**: `SourceMapping.WorksiteMode`, `NullPayDateMode`,
   `CaseInsensitive`, and the lookup policy (`EffectivePayCodePolicy`, `CustomerClassified`, the seed version/inferred/hash).
3. **Everything calculation-shaped reaches rows through `IPayrollSource.LoadPayPeriods`** (a Domain port I may not change). The only run
   seam I can touch without editing Domain is: `IClientCalculationRunner.Run` (the sync `POST .../calculate` and the worker both end there),
   plus `RunItemExecution.Resolve/Assess/Calculate` which load rows themselves before the runner, plus `AssessClient` (writes claims).
4. `ObservedGoldWriter` already takes an **uncached** `SourceFingerprintReader.Fingerprint` at Gold-write time and records it in the manifest.
   That marker is unchanged. The cache never supplies a fingerprint to the manifest.
5. The scoped `SqlClientSource` is rebuilt per request, so state must live in a **singleton**. `SqlClientSource.ClearCache()` is called by
   reset paths on the scoped instance and must clear the singleton.

### Cache key

`(accountId, projectionIdentity)` where `projectionIdentity` is a string built once per process from: worksite mode, null-pay-date mode,
case-insensitivity, pay-code policy, customer-classified flag and the pay-code seed (version, inferred, SHA-256 of its entries). A changed
setting therefore cannot be served an entry built under another (only relevant if the singleton outlived a reconfiguration, which
`ClearCache()` also covers; the key makes it structural, not procedural).

### What is cached

The finished `PayrollProjection` (rows, controls, missing tables, provenance) for one account, plus its **stamp**:
`SourceFingerprint.Sha256` (which covers row count, maximum modified, modified status and the Payroll mapping hash) and a **lookup digest**
(SHA-256 of the pay-code lookup entries that are active today for the account and global client 0, read through the existing
`ISourceLookupReader`, a small operator table). Not cached: the raw dataset (dropped after projection), aggregates, scope, accounts, fiscal rules.

### Freshness

- Entry lifetime of a *trust* decision is `SOURCE_VERSION_CHECK_SECONDS` (default 300, min 1) counted from the last time the stamp was
  **taken and matched**. Inside it a page read returns the entry with no source query at all.
- Past it, the next read takes a fresh fingerprint (one aggregate) and the lookup digest, compares both with the entry's stamp and either
  re-arms the window (match) or reloads (mismatch). The stamp is always taken **before** the rows are read, so a change racing the load
  leaves the entry with an older stamp and the next check reloads once: the failure direction is an extra read, never a missed one.
- A **run** (below) ignores the window every time.
- `ClearCache()` empties the whole cache.

### Callers

- **May use the cache within the window (page reads):** `ReadsPortfolioService`, `ReadsUnitTrendService`, `ListFindings`, `StateCreditCalculator`
  (what-if), scope/eligibility/trend reads, `LoadPortfolioPayPeriods` (per account), and every other `IPayrollSource` consumer that is not on
  the list below.
- **Must revalidate every time (run path):** `IClientCalculationRunner.Run` (decorated so the whole run, including the Domain's own
  `LoadPayPeriods` calls inside `ClientCalculation`, runs under a *require fresh* scope), `RunItemExecution.Resolve/Assess/Calculate`
  (same scope), and the claims-writing `AssessClient`. The scope is a new Application port `IPayrollFreshness.RequireFresh()` implemented by the scoped
  `SqlClientSource`; while it is open every `LoadProjection` takes a fresh fingerprint and lookup digest and ignores the window.
  Revalidating reuses the cached rows only when both match, so a repeat run on unchanged data costs two cheap queries, not the read.
  With the cache off the scope is a shared no-op instance (no allocation).

### Single flight, LRU, bounds

One in-flight load per key. A concurrent window-eligible caller joins it and takes its result (or its exception: an outage is shared, not
retried by every waiter). A concurrent *run* caller never joins a flight that started before it arrived (its fingerprint might predate
the run); it waits for it and then does its own check. LRU order is a linked list under one lock; the load itself runs outside the lock.
Eviction removes least-recently-used entries until both `SOURCE_CACHE_ACCOUNTS` and `SOURCE_CACHE_MB` hold. An entry larger than the whole
byte budget is returned but not stored. Byte size is an **estimate** (sampled structural estimate of the row dictionaries times the row count).

### Failures and refusals

A load that throws (including `SourceTooLarge`, schema/outage failures) caches nothing and leaves any previous entry alone only if that entry was
still valid; if the revalidation fingerprint itself fails the exception propagates and the old entry is **not** served (no "stale on error"). An
unknown account (null projection) is not cached.

### Off mode

`SOURCE_CACHE_MODE=off` (default): no cache object is constructed, `SqlClientSource` takes the same code path as today (one null check),
no fingerprint or lookup query is issued, `RequireFresh()` returns a static no-op disposable.

### Staleness statement (what the operator accepts by turning it on)

With `SOURCE_CACHE_MODE=on` a page read can be up to `SOURCE_VERSION_CHECK_SECONDS` behind the source. Beyond that window a change is picked
up **only if** it changes the Payroll row count, or the maximum `modify_date` (when that column is populated), or the Payroll column mapping,
or the active pay-code lookup entries. **Not detected**: count/max-preserving updates (including any update when `modify_date` is entirely null
and the count is unchanged), changes to non-Payroll tables (Entity, Location, Address, StateCountyZip, PayCode, Employment, fiscal rules, pay
frequency), SQL endpoint synchronization lag, and the non-atomic gap between the fingerprint and the rows. `SourceFingerprint.Limitations`
lists the same. Calculation runs are never served inside the window, but they carry the same undetected classes. `ClearCache()` or a restart
is the remedy.

### Mutation review (hard stop check)

`PayrollProjection`, `ProjectionControls` and `PayRow` are records; `PayRow.Dict` is a mutable `PyDict`, so I read every use. A repo-wide
search of `src` for `.Dict.Set/.Add/.Remove/.Clear`, `.Dict[...] =`, casts of the row list to `List<PayRow>` and `CollectionsMarshal` found
**none**. Every use of `.Dict` reads (`Select`, `Get`, `TryGetValue`, `PortfolioValues.Text`), or copies first
(`EmployeeRestOfYear` builds `new PyDict()` copies before changing a value; `RunFingerprint`, `GoldProjection`, `QcDetector` only read).
Callers filter with LINQ into new lists. No caller mutates a projection, so sharing one instance across requests is safe. The projection
is published once and never written after, so concurrent readers need no locking.

### Observability

A `System.Diagnostics.Metrics.Meter` named `TaxCredit.SourceCache` (counters `tcc.source_cache.hits`, `.misses`, `.evictions`, `.revalidations`,
`.reloads`; observable gauges `.entries`, `.estimated_bytes`), added with `AddMeter` to the existing OpenTelemetry `WithMetrics` in
`ServiceDefaults/Extensions.cs`. No label carries an account id. `/api/ready` reports only `accounts` for the source today, nothing cache-like,
so it is **not** touched.

## Baseline tests (main @ 9bc7d41)

Architecture 16, Ai 167, Domain 18, Shadow 8, Auth 147, Orchestrator 431, Gateway 103, Sources 144 (+4 skipped), Persistence 141, Parity 152,
Api 419 passed / **4 failed**. The 4 Api failures were `TaskCanceledException ... Error while copying content to a stream` (the test HttpClient's
100 s timeout) on the slow staged-source tests, in a run where assemblies executed in parallel. They are not caused by this work (no
source file had changed yet) and are recorded as an existing, load-dependent flake.

## S3.2 The cache (as built)

- `Application/Ports/Sources/SourceCacheSettings.cs`: setting names/defaults, `IPayrollFreshness` (`RequireFresh()`), `NoPayrollFreshness`.
- `Infrastructure.Sources/Cache/`: `ProjectionCacheOptions` (parse + validate at startup, even when off), `ClientProjectionCache`
  (singleton LRU, byte + count bounds, single flight, stamp compare, run bypass), `ProjectionSizeEstimator` (sampled structural estimate,
  ~2.6 KB/row, which matches the 2.6 KB dictionary row measured in S2), `ProjectionCacheMetrics`.
- `PayrollProjector.CacheIdentity` / `LookupDigest`, `LookupResolver.PayCodeDigest` / `SeedIdentity`.
- `SqlClientSource`: optional cache; `LoadProjection` goes through it; `RequireFresh()`; `ClearCache()` clears it.
- Run path: `FreshSourceRunner` decorates `IClientCalculationRunner` (only registered when the cache is on); `RunItemExecution.Resolve/Assess/Calculate`
  and `AssessClientHandler` open `RequireFresh()`. `RuntimeContractWork.EnvironmentChanged` clears the cache.
- Decision recorded: an `IClientCalculationRunner` decorator, not an edit to the Domain's `ClientCalculation`, is how every payroll read
  inside a run (including the Domain's own `LoadPayPeriods` calls) falls under the fresh scope.
- A joined waiter counts as a hit; a miss is a read of the source's rows; `revalidations` counts stamp comparisons against a held entry.

## S3.3 Observability

Meter `TaxCredit.SourceCache` registered via `AddMeter` in `ServiceDefaults/Extensions.cs`: counters `tcc.source_cache.hits|misses|evictions|revalidations|reloads`,
gauges `.entries`, `.estimated_bytes`. `/api/ready` carries only an `accounts` count for the source, nothing cache-like: **not touched**.

## Mutation evidence (every new test can fail)

Each mutation was applied, built, the cache tests run, and the file restored:

| Mutation | Killed by |
|---|---|
| window ignored (never trusted) | 8 tests (hit, window bound, rearm, run scope, new-row, ...) |
| run does not bypass the window | 5 tests (run bypass x3, page-vs-run, run-not-joining) |
| stamp compare always true | 8 tests incl. the invalidation self-test |
| no single flight | concurrent, shared-failure, run-join |
| count bound not enforced | LRU count eviction, meter |
| byte bound not enforced | byte eviction |
| lookup digest dropped from stamp | operator lookup edit |
| `RequireFresh` does nothing | 2 run-scope tests |
| unknown client cached | unknown-client test |
| `AssessClient` scope removed | host test (claim assessment) |
| `RunItemExecution.Assess` scope removed | host test (queued steps) |
| `FreshSourceRunner` scope removed | host test (synchronous run) |

The invalidation rule also has an in-code self-test (`The_invalidation_scenario_can_fail_when_the_rule_is_broken`) that runs one scenario under
the real rule and two broken rules and requires the broken ones to be noticed.

## S3.4 Gates

- Build `-warnaserror`: 0 warnings, 0 errors. `dotnet format --verify-no-changes`: exit 0.
- Full `dotnet test TaxCredit.slnx --no-build -m:1`, run three times on the final code:
  every non-Api assembly green each time (Architecture 16, Ai 167, Domain 18, Shadow 8, Auth 147, Orchestrator 431, Gateway 103, Sources 189 + 4 skipped,
  Persistence 141, Parity 152). Api: run A 429/429; run B 424/429 and run C 428/429, the failures being the same
  100 s HTTP-timeout flake on the slow staged-source tests (a different test each time; Python Shadow `PythonBoundaryTests` also timed out
  once at 20 s under load and passed on rerun). Parity and Shadow replay are unmodified and green.
- In-process heap calibration of the estimator is a benchmark (`TCC_RUN_BENCH=1`), because a heap reading is meaningless while other tests allocate. Passed.
