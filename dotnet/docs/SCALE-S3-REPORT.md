# Scale S3 report: an opt-in per-client projection cache

Branch `scale/s3-cache`. Application code and docs under `dotnet/` only. No Python, Domain, rule pack, calculation engine, package or customer
data touched. With the default (`SOURCE_CACHE_MODE=off`) behaviour is unchanged. Working log: `docs/scale-s3-log.md` (design first, then build, mutation and gate evidence).

## Design in brief

- **What is cached:** the finished `PayrollProjection` of one client, in a singleton `ClientProjectionCache` (the scoped `SqlClientSource` is rebuilt per request).
- **Key:** account id plus a projection identity (worksite mode, null-pay-date mode, case-insensitivity, pay-code policy, customer-classified flag, pay-code seed hash).
- **Stamp:** the existing source fingerprint hash (Payroll row count, maximum `modify_date`, modified status, Payroll column mapping) plus a digest of the active pay-code lookup entries. The lookup digest is there because an operator's lookup edit changes a projection without touching the source.
- **Freshness:** a matching stamp is trusted for `SOURCE_VERSION_CHECK_SECONDS`. After that the next read takes the stamp again (one aggregate and a small lookup read), keeps the entry on a match and reloads on a mismatch. The stamp is taken before the rows, so a racing change costs an extra read, never a missed one. A failed stamp serves nothing.
- **Runs always revalidate:** every calculation run (sync `IClientCalculationRunner` via `FreshSourceRunner`, queued `RunItemExecution.Resolve/Assess/Calculate`) and claim assessment (`AssessClient`) read under `IPayrollFreshness.RequireFresh()`, which ignores the window and takes a fresh stamp on each read. The manifest's own source observation is still the uncached fingerprint taken at Gold-write time.
- **Bounds:** LRU by estimated bytes and by client count; an entry larger than the whole budget is returned, not stored. Single-flight per client; waiters share a failure instead of retrying it; a run never takes a load that began before it asked.
- **Never cached:** failed loads, `SourceTooLarge`, unknown clients.
- **Mutation review:** nothing in `src` mutates `PayrollProjection`, `PayRow` or its `PyDict` (searched `.Dict.Set/Add/Remove/Clear`, indexer assignment, list casts); the one copier (`EmployeeRestOfYear`) copies first. Sharing one instance is safe.

## Settings

| Setting | Default | Minimum | Meaning |
|---|---|---|---|
| `SOURCE_CACHE_MODE` | `off` | | `off` or `on`; `off` constructs nothing and issues no extra query |
| `SOURCE_CACHE_MB` | 512 | 16 | estimated bytes (about 2.6 KB per projected row) |
| `SOURCE_CACHE_ACCOUNTS` | 64 | 1 | clients held |
| `SOURCE_VERSION_CHECK_SECONDS` | 300 | 1 | trust window for page reads |

All are validated at startup even when the cache is off; a bad value stops the host naming the setting.

## Staleness statement

With the cache on, a page read can be up to `SOURCE_VERSION_CHECK_SECONDS` behind the source. Beyond that, a change is seen only if it changes the Payroll row count, the maximum `modify_date` (when `modify_date` is entirely null only the count can detect a change), the Payroll column mapping or the active pay-code lookups. **Not detected** until restart or `ClearCache()`: updates that preserve count and maximum modified (including any in-place edit when `modify_date` is all null), changes to non-Payroll tables (Entity, Location, Address, StateCountyZip, PayCode, Employment, fiscal rules, pay frequency), SQL endpoint sync lag, and the gap between stamp and rows. These are the fingerprint's `Limitations`; a run carries the same undetected classes, it only refuses to be served on the clock. This is why the cache is off by default: turning it on is an operator decision.

## Observability

Meter `TaxCredit.SourceCache` (registered with the existing OpenTelemetry pipeline, no package added): `tcc.source_cache.hits`, `.misses`, `.evictions`, `.revalidations`, `.reloads`, gauges `.entries`, `.estimated_bytes`. No client id is a label. `/api/ready` reports no similar source facts, so it is untouched.

## Test evidence

New tests: 44 cache tests in `TaxCredit.Infrastructure.Sources.Tests` (hit, miss, per-client and per-identity separation, window and its strict bound, fingerprint-change and modified-date invalidation, the documented undetected change, lookup edit, run bypass, byte and count eviction, oversize entry, failure not cached, shared failure, single flight under concurrency, run not joining an older load, off-mode no-op, `SourceTooLarge` and unknown client not cached, `ClearCache`, settings parsing, meter, estimator) and 6 host tests in `TaxCredit.Api.Tests` (off by default, on registers the shared cache and the fresh runner, invalid setting stops startup, sync run / queued steps / claim assessment read under the fresh scope, a plain page read does not).
Twelve mutations of the invalidation, run-bypass, bound, single-flight and scope code were each killed (table in the log), plus an in-code mutation self-test of the stamp rule.
Gates: build `-warnaserror` clean, `dotnet format --verify-no-changes` clean, Parity (152) and Shadow (8) green and unmodified, every non-Api assembly green on three full runs. `TaxCredit.Api.Tests` passed 429/429 once; on two other runs 1 to 5 of the slow staged-source tests hit the test HttpClient's 100 s timeout (a different test each time, the same failure class as 4 failures on unmodified `main`). The estimator's heap calibration is a `TCC_RUN_BENCH=1` benchmark.

## Still open

- No measured wall-clock gain on a real 384k-row client is claimed: no lakehouse is reachable here. The mechanism removes the whole row read for repeat reads inside the window and replaces it with two cheap queries on a run.
- Dimension-table and in-place edits are undetected (above). A per-table fingerprint or a Delta version would close that; neither is available through the SQL endpoint today.
- Per-process cache: each host/worker keeps its own; no shared tier.
- The byte figure is an estimate; a hard memory limit needs a measured one.
- Entry memory is the full projection (about 2.6 KB per row): one 1M-row client is about 2.6 GB. Choose `SOURCE_CACHE_MB` against `SOURCE_MAX_ACCOUNT_ROWS`.
- The slow staged-source Api tests' 100 s client timeout is flaky on this machine independent of this work.

## Merge with S4 (ScopedPayrollMemo, RunSpans)

- Both kept. S4's ScopedPayrollMemo still reads a client's payroll once per request or queued item; S3's cache sits underneath it, in SqlClientSource.LoadProjection (the source.load/read/project spans wrap the uncached read only).
- The memo is now also the scope's IPayrollFreshness: rows it remembered from a read made outside a require-fresh scope are never handed to code inside one, so a run cannot be served rows the source's freshness check did not vouch for; rows read inside a fresh scope are reused by the rest of that item (still one read per item). With SOURCE_CACHE_MODE=off the memo gets no source freshness scope and RequireFresh() is a no-op, so behaviour is identical to S4.
- New tests: a queued item scans the payroll exactly once with the cache off and on (QueuedRunCostTests), a cache-on revalidation takes a fingerprint without rescanning, and two memo tests (non-fresh rows not served inside a fresh scope; no change without a freshness scope).
- Gates after the merge: build -warnaserror clean, format clean, full dotnet test TaxCredit.slnx -m:1 green (Api 438, Persistence 145, Sources 189 + 4 skipped, Parity 152, Shadow 8, others unchanged), nothing flaky this run.
