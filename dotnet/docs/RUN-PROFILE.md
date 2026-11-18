# Run profile: where one client calculation spends its time

Branch `scale/s4-profile`. Method, harness and raw numbers: `scale-s4-log.md`, `SCALE-S4-REPORT.md`. Raw tables: `dotnet\artifacts\bench\bench-*.txt`
(local, not committed; regenerate with `.\dotnet\bench-run.ps1`).

## How to read the numbers

- One queued `Calculate` item, the real `RunWorkExecutor` > `RunPublication` > `PersistedClientCalculation` > Domain `ClientCalculation`, SQLite
  operational store, a synthetic client (three tax years of bi-weekly payroll, 100 locations, staff hired across the years) served by a fake
  `IAnalyticsTransport` in the real source shape. **No live lakehouse was used**: `TEST_LIVE_PROFILE` is not set. Live attribution below is derived.
- Times are **exclusive** (a span's own time minus its children), so the stage rows add up to the item's wall clock. "Engine + gold projection +
  replay" is `run.calculation` minus its instrumented children; nothing was added inside the Domain, so it cannot be split further here.
- The workstation was shared with other sessions' builds and tests. Wall times move by up to 2x between identical runs (the 400k "before" ran
  272 s, 208 s on the old generator, and 326 s under load). Row counts, statement counts, scan counts and the Gold hash are exact; seconds are not.
  The 100k comparison is three alternating pairs, the median pair is shown.

## Stage table (seconds, exclusive)

| Stage | 100k before | 100k after | 400k before | 400k after | 1M before | 1M after |
|---|---:|---:|---:|---:|---:|---:|
| resolve and authorize | 0.2 | 0.2 | 0.9 | 0.9 | 1.9 | 2.8 |
| fingerprint | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 | 0.0 |
| source read (SQL stream), all loads | 2.6 | 0.6 | 8.7 | 2.1 | 125.0 | 7.4 |
| projection (source rows to pay rows), all loads | 8.3 | 1.4 | 30.6 | 6.5 | 265.4 | 30.0 |
| engine + gold projection + replay (Domain, derived) | 14.5 | 13.5 | 66.3 | 65.4 | 273.4 | 419.8 (loaded box) |
| gold prepare (value conversion) | 1.2 | 0.8 | 7.0 | 4.7 | 12.9 | 12.4 |
| persistence writes (inserts) | 24.8 | 2.1 | 157.7 | 12.6 | 631.8 | 53.2 |
| persistence other statements | 0.1 | 0.0 | 0.0 | 0.0 | 0.1 | 0.1 |
| persistence reads and validation | 0.1 | 0.1 | 0.3 | 0.4 | 25.3 | 0.7 |
| publication and queue | 0.1 | 0.1 | 0.5 | 0.5 | 1.3 | 1.1 |
| commit | 0.0 | 0.1 | 0.1 | 0.6 | 0.2 | 6.6 |
| **item wall clock** | **51.9** | **19.1** | **272.1** | **93.5** | **1,337** | **533.8** |
| payroll scans of the source | 4 | 1 | 4 | 1 | 4 | 1 |
| peak working set (MB) | 1,545 | 718 | 6,872 | 2,786 | 14,110 | 6,123 |
| Gold dump hash | `d6637279...` | same | `9286b1ed...` | same | `124eb811...` | same |

Rows written per run (identical before and after): 100k: 98,073 period facts, 47,360 matrix, 7,692 eligibility; 400k: 392,292 / 189,651 / 30,768;
1M: 980,730 / 474,340 / 76,920 (plus 480 unit-year, 480 unit-month, 400 installment, 6 summary rows at every size).

Reading it: before the change, **persistence writes were 47 to 58 percent of the item** and **four source reads plus projections 14 to 29 percent**.
After it the Domain run is 70 to 79 percent of the item at 100k and 400k and is now the cost that scales worst (66 s at 400k, 270 s or more at 1M).

## Attribution of the unexplained 108 s

The live item, 3 min 35 s on 384,433 rows, divides at `run_started_at` and `run_completed_at`. In `ClientCalculation.Run` the completion
timestamp is taken **after** the engine and gold projection and **before** `Writer.WriteRun`; everything that happens afterwards is the 108 s:

| After `run_completed_at` | Harness at 400k (before) | Share |
|---|---:|---:|
| Gold inserts into SQLite (`persist.insert`, 392,292 + 189,651 + 30,768 + small tables) | 158 s | most of it |
| Source load number four, for `AssessAfterRun` (the claim); a load is about 10 s here (`source.load` 39 s / 4) | about 10 s | |
| Section 9 validation, twice (inside `Publish` and again by `Validate()`), claim write, supersede, observation, commit | under 1 s | |

Scaling the harness to the live shape (384k period facts; the reference client has few matrix rows, so most of the live Gold volume is the period
fact table, about 0.18 ms per row before the fix) gives **about 70 s of inserts** (384,600 rows x 0.18 ms) plus **a fourth source read of the order of
the first** (the 28 s before `run_started_at` holds read number one, from resolve), which together make up the 108 s. The 79 s inside the run holds source
reads two and three (`ResolveClientRun`, then `ReplayUnitSeries`) and the engine. Source reads are then roughly 100 s of the 215 s and SQLite inserts
roughly 70 s: about four fifths of the item is two application-side causes. The guess in the brief (persistence into SQLite) was right and incomplete.
This is a derivation from the harness, **not a live measurement**; a live run with the same spans (`TEST_LIVE_PROFILE=yes`, `az login`) is the way to confirm
the split.
## The six checks, with numbers

| Check | Verdict | Evidence |
|---|---|---|
| One statement per row instead of batched inserts | **Ruled out as stated; the batching itself was the cause.** Inserts were already multi-row (110 to 500 rows, up to 2,090 parameters per statement). | 5,900 insert statements at 400k, 26 ms each, 152 to 158 s in all. `InsertCostProbe`: a 20,000-row insert took 3.64 s with the real CHECKs and index, 3.70 s with neither: the cost is in sending the statement, not in the table. Microsoft.Data.Sqlite resolves each named parameter by a linear scan of the collection, so a 2,090-parameter statement is quadratic (about 20 ms). |
| A transaction per row, or none (fsync per statement) | **Ruled out.** | One serializable transaction for the whole calculation: 11 `db.begin` and 11 `db.commit` spans per item, 0.04 to 0.09 s of commit at 100k and 400k (6.6 s at 1M). |
| Repeated full-table reads, missing indexes on operational tables | **Source reads: confirmed. Operational tables: ruled out at 400k and below.** | The payroll table was scanned 4 times per item (399,984 rows x 4 = 1,599,936 rows read and projected). The 124 to 132 reads of the Gold and ops tables total 0.1 to 0.4 s at 100k and 400k; the validation scans cost 0.7 to 25 s at 1M across runs (up to about 2 percent). The employee tables already have `(client_id, run_id, tax_year)` indexes. Also 32 tiny reads each of `Entity` and `EntityFiscalYearRules` per item (one per fiscal-window lookup): free locally, one round trip each against a real endpoint. |
| The Gold projection rebuilding strings per row | **Ruled out as a major cost.** | `gold.prepare` (value conversion into storage types) is 0.8 to 1.3 s per 100k rows, 3 to 7 percent of the item. The Domain's own `GoldProjection` is inside `run.calculation` and cannot be separated without touching the Domain. |
| Manifest or artifact generation re-reading source data | **Ruled out.** | The manifest is written from the in-memory run (`persist.manifest` under 0.01 s). `persist.observation` (the source-observation row) is 0.003 to 0.05 s and re-reads nothing. Claim-package artifact generation is an HTTP-request path (`application/claim_package`), not part of a queued item. |
| The fingerprint taken more than once | **Ruled out.** | One `fingerprint` span per item, 0.00 to 0.03 s. `RunFingerprint.Identity` hashes rows already in memory and is part of the Domain run. (`unchanged-check` is only reached when a batch is not forced.) |

## Ranked causes

| # | Cause | Where | Size at 400k (before) | Fixed? |
|---|---|---|---:|---|
| 1 | Quadratic parameter binding in multi-row SQLite inserts | `SqlSession.InsertRows` | 158 s of 272 s | Yes: single-row prepared statement, same rows and order. 12.6 s after. |
| 2 | The same client's payroll read and projected four times per item (resolve, run, unit replay, assessment) | `RunItemExecution`, Domain run, `AssessAfterRun` | 39 s of 272 s (and 4x the memory) | Yes: `ScopedPayrollMemo`, one read per scope. 8.6 s after. |
| 3 | Domain run (engine, gold projection, replay) scales worse than linearly | `TaxCredit.Domain` | 66 s; 270 to 420 s at 1M | No: Domain is out of scope. Recommendation. |
| 4 | Whole payroll materialised as `List<Dictionary>` then `PyDict` rows; 2.8 GB at 400k, 6.1 GB at 1M after the fix (14 GB before) | `SourceScanner.Scan`, `PayrollProjector` | memory, plus GC time at 1M | No: restructuring. Recommendation. |
| 5 | CHECK functions and index on SQLite Gold tables | `tcc_decimal_valid`, schema | about 17 of the remaining 30 microseconds per row (`InsertCostProbe` 612 ms vs 338 ms per 20,000) | No: small after fix 1. |
| 6 | Validation scans (section 9) run twice per item | `GoldWriter.Publish`, `ClientCalculation.Run` | under 1 s at 400k; up to 25 s at 1M | No: it is a defence in depth; not worth the risk. |
| 7 | Lease of 600 s | `RunExecutionOptions` | a 1M-row item took 1,337 s before the fix and 534 s after on a loaded machine | No: the harness extends it to 7,200 s. Recommendation. |
