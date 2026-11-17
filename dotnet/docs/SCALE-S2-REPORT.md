# Scale S2 report: a row-cap setting, the measured cost of a row, a bounded portfolio load

Branch `scale/s2-row-cap`. Application code and docs under `dotnet/` only. No Python, calculation engine, Domain, rule pack, package or
customer data touched. Numeric results and every healthy-path response are unchanged.

## Settings

| Setting | Default | Minimum | What it does |
|---|---|---|---|
| `SOURCE_MAX_ACCOUNT_ROWS` | 1,000,000 | 1,000 | Most payroll rows one client may have. The scan stops one row past it; the API answers 422 `account_too_large` and the remedy names the setting and the limit. Python's equivalent defaults to 50M; see the cap below for why this default is not copied. |
| `SOURCE_PORTFOLIO_MAX_ACCOUNTS` | 25 | 1 | Most clients a portfolio-wide payroll load will read. |
| `SOURCE_PORTFOLIO_MAX_ROWS` | 5,000,000 | 1,000 | Running payroll-row total that load may not pass. |

All three are read once at startup through `IRuntimeConfiguration`. Unset or blank keeps the default; a non-integer, a negative or a value
below the minimum stops the host with `InvalidOperationException("<NAME> must be a whole number of at least N.")`.

The portfolio-wide load (`LoadPortfolioPayPeriods`, used only by entity portfolio simulation) now refuses with `SourcePortfolioTooLarge`
(HTTP 422, code `portfolio_too_large`) **before reading**: first on the client count, then per client from the cheap SQL scope aggregate
(`PayrollScope`), before that client's payroll is read. The remedy is "Select fewer clients, or raise `SOURCE_PORTFOLIO_MAX_ACCOUNTS` /
`SOURCE_PORTFOLIO_MAX_ROWS` if the host has the memory." Small books load exactly as before. Python has no such bound (only the per-account cap).

## What a row costs

Synthetic client in the real source shape: 13 engine columns per Payroll row (ids as `long`, dates as `DateTime`, hours and wages as
`decimal`), 40 pay periods per employee, a dictionary per row exactly as the SQL transport builds it. Release build, .NET 10,
workstation GC, one fresh process per size, Snapdragon X Elite 12-core, 31 GB. `SourceDatasetReader.Load` then `PayrollProjector.Project`.
Heap figures are `GC.GetTotalMemory` after a forced full collection; working set is sampled every 10 ms.

| Rows | Scan B/row | Projection B/row | Retained B/row once the scan is dropped | Scan heap | Projected heap | Peak working set | Scan time | Project time |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 100,000 | 931 | 2,571 | 2,574 | 89 MiB | 245 MiB | 433 MiB | 0.4-0.6 s | 1.4-2.8 s |
| 400,000 | 929 | 2,570 | 2,571 | 354 MiB | 981 MiB | 1,440-1,492 MiB | 1.4-3.2 s | 5-13 s |
| 1,000,000 | 926 | 2,568 | 2,569 | 883 MiB | 2,450 MiB | 3,462-3,503 MiB | 3-10 s | 14-58 s |
| 400,000, compact row (prototype) | 480 | 2,570 | 2,571 | 183 MiB | 981 MiB | 1,259 MiB | 0.8-1.1 s | 6.7-10.9 s |

Reading it:

- **About 3.5 KB of peak memory per row** (marginal, after the roughly 70-80 MiB runtime baseline): 0.9 KB for the scanned dictionary plus 2.6 KB for
  the projected engine row. The two coexist while projecting, so peak is their sum; once projection returns, the scan is freed and 2.6 KB/row
  stays for the length of the run.
- **The projection is the bigger half, and it is the Domain's contract.** `PayRow` is a 21-key `PyDict` plus an 11-field `PayrollRow`, with
  boxed values and per-row date and ID strings. Shrinking it means changing the projector's output type or the Domain, which this stage
  must not do.
- Times are CPU-only (no network) and moved 2-4x between runs on this shared machine; the memory figures reproduce within 1%. The real run
  of 3 min 35 s on a 384k client is therefore overwhelmingly SQL transfer, not .NET: this stage's levers are memory and the cap, not that time.
- The real SQL value types are not known here. If the endpoint returns money as strings, rows are larger; re-run the benchmark against the
  real column types before raising the cap.

Reproduce (each size in its own process):

```pwsh
$env:TCC_RUN_BENCH = '1'
dotnet test tests\TaxCredit.Infrastructure.Sources.Tests -c Release --filter "FullyQualifiedName=TaxCredit.Infrastructure.Sources.Tests.RowCostBenchmark.Rows_1M"
```

`Rows_100k`, `Rows_400k` and `Rows_400k_CompactRow` likewise; `TCC_BENCH_OUT=<file>` appends the table row. Without `TCC_RUN_BENCH=1` the tests are skipped.

## Recommended cap

Peak memory is roughly `0.1 GB + 3.5 KB x rows` for one run in one process.

| Host memory for a run | Largest cap that fits (about 10% headroom) |
|---|---|
| 2 GB | 500,000 |
| 4 GB | 1,000,000 |
| 8 GB | 2,000,000 |
| 16 GB | 4,000,000 |

- **Keep the default at 1,000,000.** It is the largest round number that fits a 4 GB budget (3.5 GB peak measured). It stays below
  Python's 50M on purpose: 50M rows is about 175 GB in one process, so that default would be a promise the host cannot keep.
  The measured evidence supports a higher default only on a host sized for it; set `SOURCE_MAX_ACCOUNT_ROWS` per deployment.
- Budget per **concurrent** run: the cap bounds one client, not the host. Two simultaneous 1M-row runs need about 7 GB.
- **A 10x larger client (10M rows) needs about 35 GB in this design**, per run. That is not a cap to raise; it needs a different read:
  project and run one tax year at a time (a year-scoped read instead of the whole history), serve a pre-aggregated per-client summary,
  partition or cluster Payroll by `account_id`, or slim the engine row (Domain). Do these before raising the cap past a few million.
- `SOURCE_PORTFOLIO_MAX_ROWS` at the requested 5,000,000 would hold about 13 GB of projected rows (2.57 KB each; each client's scan is freed
  as the next begins). It matches the brief, but a host under 16 GB should lower it, for example to 1,000,000 for 4 GB.

## Optional scan compaction: measured, not adopted

Replacing the per-row `Dictionary<string, object?>` with a row that shares one column-name array (`CompactRow` in the benchmark) cut the scan
from 929 to 480 B/row and peak working set at 400k by about 16% (1,259 vs 1,440-1,492 MiB). It was left out of production because:
the saving is small against the projection's 2.6 KB; the change belongs in `SqlAnalyticsTransport.Materialize`, the one path this environment
cannot run against a real SQL endpoint; and row iteration order is relied on by the fingerprint, so it needs its own parity proof.
It is a safe, contained follow-up once there is a live endpoint to test against.

## Behaviour changes

| Case | Before | After |
|---|---|---|
| Client over the row cap | 422, remedy "Review the account row limit before retrying." | 422, same shape; remedy names `SOURCE_MAX_ACCOUNT_ROWS` and the limit |
| Portfolio load over its bounds | Loaded everything into memory | 422 `portfolio_too_large`, nothing read past the trip |
| Healthy requests | | Byte-identical |
| Offline fixture byte ceiling | Reused the row-cap remedy | Its own remedy (bytes) |

## Gates

See the end of `scale-s2-log.md` for the final build, format and test record.

## Still open

- No live-endpoint measurement: real column types and SQL transfer time are unmeasured.
- The projection's per-row cost (2.6 KB) is the dominant term and sits in the Domain contract; reducing it is a Domain decision.
- No year-scoped or streamed read, no pre-aggregated summary, no per-client dataset cache, no Silver path (see `LOCAL-RUNBOOK.md` section 7).
- `SOURCE_PORTFOLIO_MAX_ROWS` default (5M) is memory-heavy; consider tying defaults to host memory.
- The scope aggregate is one `GROUP BY` per client in the portfolio guard; for a book near the 25-client bound that is 25 cheap queries, but it
  has not been timed against a large table.
