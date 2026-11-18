# Scale S4 report: where one client calculation spends its time, and what was fixed

Branch `scale/s4-profile`. Application code in `dotnet/` only. No Python, Domain, rule pack, calculation arithmetic, package or customer data was touched.
Nothing is pushed. Companion documents: `RUN-PROFILE.md` (stage table, attribution, ranked causes), `scale-s4-log.md` (running log).

## Method

1. **Spans.** `RunSpans` (`TaxCredit.Application/Hosting`) wraps an `ActivitySource` named `TaxCredit.Run`. With no listener `Start` returns `null`, so telemetry off costs one
   volatile read per span. `ServiceDefaults` subscribes OpenTelemetry to the source, so the same spans reach a collector without a new package. Spans cover
   resolve, fingerprint, source read per table, projection, the Domain run as a whole, Gold value conversion, every persistence write and read, commit, publication.
2. **Harness.** `bench-run.ps1` runs an opt-in test (`TCC_RUN_BENCH=1`) in `TaxCredit.Api.Tests`: the real host, worker executor, mediator pipeline and SQLite
   store, with a fake `IAnalyticsTransport` serving a synthetic client of 100k, 400k or 1M payroll rows (three tax years, 100 locations, staff hired across the years).
   It prints a per-stage table of exclusive time and a content hash of every stored Gold row (run id and `*_at` columns excluded: a fresh identity and the clock).
3. **Comparison.** "Before" is commit `b54538b` (spans and harness only, behaviour unchanged); "after" is the working tree. 100k was run as three alternating
   before/after pairs; 400k and 1M once each. A probe (`InsertCostProbe`, opt-in) separated the cost of CHECK constraints and the index from the cost of the statement.
4. **Not done.** The live-lakehouse run: `TCC_LIVE_PROFILE` was not set, so the live split is derived from the harness, not measured.

## Results

Seconds, wall clock of the item. The machine was shared with other sessions, so treat them as +/- 2x; counts and hashes are exact.

| Payroll rows | Before | After | Payroll scans | Peak memory (before / after) | Gold dump |
|---:|---:|---:|---:|---|---|
| 100,000 | 58.1, 46.3, 51.9 (median 51.9) | 17.4, 19.1, 29.3 (median 19.1) | 4 / 1 | 1.5 GB / 0.7 GB | `d6637279...` identical in all 6 runs |
| 400,000 | 272.1 (326.5 under load) | 93.5 | 4 / 1 | 6.9 GB / 2.8 GB | `9286b1ed...` identical |
| 1,000,000 | 1,337 | 533.8 | 4 / 1 | 14.1 GB / 6.1 GB | `124eb811...` identical |

At 400k, persistence writes fell from 157.7 s to 12.6 s and the four source reads plus projections from 39.2 s to 8.6 s. The 1M "before" is also the run that exceeds the
default 600 s worker lease (see recommendations); the harness raises the lease to 7,200 s so every size can be timed.

The unexplained 108 s is the Gold inserts (about 70 s at the live row count) plus the fourth payroll read for the claim assessment (see `RUN-PROFILE.md`; derived, not live).

## Fixes made

| # | Change | Where | Result |
|---|---|---|---|
| 1 | On SQLite, a Gold insert prepares one single-row statement and re-binds it per row, in the same transaction, in the same order. Microsoft.Data.Sqlite resolves named parameters by a linear scan, so the previous 110 to 500 rows (up to 2,090 parameters) per statement cost about 20 to 26 ms each. SQL Server and Warehouse keep the existing multi-row path, unchanged. | `SqlSession.InsertPrepared` | 400k: inserts 157.7 s to 12.6 s. Probe: 3.64 s to 0.61 s per 20,000 rows. |
| 2 | `ScopedPayrollMemo`: within one scope (an HTTP request or a queued item) the latest client's payroll is read and projected once instead of four times (resolve, run, unit replay, assessment). One client only, dropped with the scope, never shared across requests, a failed read is not remembered. Registered around `IPayrollSource` in `RuntimeSourceRegistration`. | `ScopedPayrollMemo` | 400k: reads plus projections 39.2 s to 8.6 s; peak memory 6.9 GB to 2.8 GB. |

Safety evidence for both: the stored Gold dump is hash-identical at all three sizes and in all six 100k runs; Parity 152/152 passed unmodified; Domain, Architecture,
Ai, Auth, Gateway, Orchestrator, Sources and Persistence suites green; `TaxCredit.Api.Tests` and `Shadow.Tests` green when run in isolation (see "Gates").
No Domain file, rule pack or Python file changed, so no calculation figure and no healthy-path response can differ; the hash comparison covers the Gold side, and the
Api and Shadow suites cover the responses.

Regression tests (run in every normal test run, no opt-in): `SqliteInsertTests` (statement size, row order, nulls and typed values with a reused statement, mismatched row writes
nothing), `QueuedRunCostTests` (a queued calculation reads the payroll once; no insert statement carries more than 128 parameters), `ScopedPayrollMemoTests`.

`-Persistence warehouse`: unchanged. Fix 2 also applies there (it is in the source path, not the store); fix 1 does not. No Warehouse run was possible here, so the memo is
covered only by the offline suites on that path.

## Recommendations (not done; larger than a contained fix)

| Recommendation | Why | Estimate |
|---|---|---|
| **Domain run scaling**: engine, gold projection and unit replay are now 70 to 79 percent of an item and grow faster than linearly (66 s at 400k, 270 to 420 s at 1M). Profile inside `ClientCalculation.Run` with spans, then the replay across years and `GoldProjection`. Needs owner sign-off and the Parity gate. | Largest remaining cost | Profiling: 2 to 3 days. Gains unknown until profiled. |
| **Stream the source into the projector** instead of `List<Dictionary>` then `PyDict` rows (`SourceScanner.Scan`, `PayrollProjector`). Today about 7 KB per payroll row. | 400k needs 2.8 GB and 1M 6.1 GB after the fix (14 GB before); GC time shows at 1M | 1 to 2 weeks; halves the memory; 5 to 10 percent of time. |
| **Lease for long items**: `RunExecutionOptions.LeaseSeconds` is 600 s and nothing heartbeats during `run.calculation`. A 1M-row item takes 534 to 1,337 s here and loses its lease (`RunLeaseLost`). Heartbeat per stage or size the lease from the row count. | An item above roughly 500k rows fails with no result | 2 to 3 days with a test. |
| **Warehouse writes**: measure `-Persistence warehouse` with the same spans. The multi-row path is unchanged and unprofiled; a bulk path (SqlBulkCopy) for the employee-grain tables is the likely win. | Not covered by this profile | 1 week including a live Warehouse. |
| **Cache per-scope fiscal rule lookups**: 32 reads each of `Entity` and `EntityFiscalYearRules` per item. Free locally, a round trip each live. | Latency, not volume | 1 day. |
| **Optional**: a fast path in `tcc_decimal_valid` (about 17 of the remaining 30 microseconds per Gold row on SQLite); skip nothing in section 9. | Small after fix 1 | 1 day. |

### For the data owner (for the customer email)

The application now reads a client's payroll once per calculation (it was four times) and writes its results about 12 times faster locally. What remains on the
source side, and what would help:

1. **Throughput of one filtered scan.** A calculation reads every row of the client's payroll from the SQL analytics endpoint once (about 400,000 rows today, with
   about a dozen columns), plus a handful of small dimension tables. Please tell us the sustained read time for `SELECT <columns> FROM Payroll WHERE account_id = <one client>`
   over about 400,000 rows. Our target is tens of seconds.
2. **Layout of the payroll table.** Partitioning or clustering by account (and tax year) keeps that scan from reading other clients' data.
3. **Endpoint freshness.** Confirm the SQL endpoint's metadata synchronisation lag after new payroll lands, because a calculation records a count and a latest-modified
   marker of the rows it read as its source fingerprint.
4. **Capacity.** The Fabric capacity SKU in use, and whether it throttles under a single 400,000-row read. The earlier slow-open of the small `Account` table suggests it may.
5. **Row growth.** Expected maximum payroll rows per client. About 500,000 rows is where the current 600 s worker lease starts to matter, and about 1,000,000 is the
   application's per-read row cap (`maximumRows`).

## Gates

From `dotnet\` with `TCC_PYTHON=C:\Projects\py312-oracle\.venv\Scripts\python.exe`:

- `dotnet build TaxCredit.slnx -warnaserror`: 0 warnings, 0 errors.
- `dotnet format TaxCredit.slnx --verify-no-changes`: exit 0.
- `dotnet test TaxCredit.slnx`: see `scale-s4-log.md` "Final gates" for the last full run.
- Test-suite noise: on this shared machine the whole-solution run produced timing-bound failures that passed in isolation. Baseline: `GoldQueryTimeoutTests...`,
  `Forecast_preserves_staged_source_values(2004)`, `P2_uses_staged_source_catalogue...`. After: `PythonBoundaryTests...` (Shadow), `Forecast_preserves_staged_source_values` (2003 and 2004),
  `Staged_P2_source_fiscal_assembly...`, `P2_uses_staged_source_catalogue...`, `Rebase_reads_gold...`. Each of those passed when run alone.

## What is still open

- A live-lakehouse profile with the same spans (needs `TCC_LIVE_PROFILE=yes` and `az login`). The 108 s attribution is a derivation until then.
- The Domain run (above), memory, the lease, the Warehouse path.
- `bench-run.ps1` is a SQLite-and-fake-source harness; it says nothing about source latency.
