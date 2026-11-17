# ReadsCalc portfolio/discovery/trend handoff

Scope: application assembly only. No HTTP, Domain, shared registration, packages,
live systems, private data, commits, or files outside the assigned folders were
changed.

## Public consumption seam

Namespace: `TaxCredit.Application.Features.ReadsCalc.Portfolio`.

Call `services.AddReadsCalcPortfolio()` from the parent's ReadsCalc feature
module. All four services are scoped; registration is idempotent.

```csharp
IReadOnlyList<PyDict> ReadsPortfolioService.BuildPortfolio(
    long taxYear, long fyEndMonth = 12, long? accountId = null);
long ReadsPortfolioService.LatestTaxYear(
    long fyEndMonth = 12, long? accountId = null);
PyDict ReadsPortfolioService.StateCredit(
    string state, long taxYear, long? accountId = null,
    double? currentAverage = null, double? priorAverage = null,
    string? programCode = null, long fyEndMonth = 12);

PyDict ReadsDiscoveryService.DiscoverCredits(
    IReadOnlyList<string>? excludeCodes = null,
    long? accountId = null, long? taxYear = null);
static PyDict ReadsDiscoveryService.FromTiles(
    IReadOnlyList<PyDict> tiles, IReadOnlyList<string>? excludeCodes = null);

PyDict ReadsUnitTrendService.Execute(UnitTrendRequest query);
record UnitTrendRequest(
    string State, long? AccountId = null, string Method = "min_max",
    long? BaseYear = null, string? ProgramCode = null);

PyDict ReadsStoredPortfolioBriefs.ClientContext(
    long accountId, int taxYear, string method = "pay_period",
    string? programCode = null,
    Action<IReadOnlyDictionary<string, object?>>? onRun = null);
PyDict ReadsStoredPortfolioBriefs.ClientTrend(
    long accountId, string method = "pay_period", string? programCode = null,
    Action<IReadOnlyDictionary<string, object?>>? onRun = null);
PyDict ReadsStoredPortfolioBriefs.JobsAtRisk(
    ClientRunResolver resolver, long accountId, string state, int taxYear,
    string method = "min_max", string? programCode = null,
    Action<IReadOnlyDictionary<string, object?>>? onRun = null);
```

These are canonical application trees, not a serializer. The parent's existing
`ReadValues.Transport` normalizes them. Money remains exact integer/BigInteger
credit from Domain or scale-bearing stored values; no float summation of money.
`FromTiles` allows a caller to reuse a portfolio it already holds.

### Required outer reference-data binding

`IPortfolioReferenceData` is a new, narrow application port:

```csharp
long CountFederalNewHires(long taxYear);
PortfolioWorksite? Worksite(string unitId);
record PortfolioWorksite(string Name, string County = "", string City = "");
```

W1 source ports contain pay periods but **no hire dates**. The production Python
function `_federal_new_hires` reads the committed, synthetic `backend/data/payroll.csv`
independently of the selected pay-period client. An outer adapter must supply that
same reference count and propagate unreadable-source failures. Do not derive hires
from an employee's first pay period or silently bind zero. There is deliberately
no default fake binding. Worksite metadata may return null for unknown sites.
The parent's existing `SiteLabels` data can supply the four known GA display
dimensions. `PortfolioTestData` supplies public-fixture hire counts and metadata
only in tests.

Exact callers needing the seam:

- AI client discovery capability -> `ReadsDiscoveryService.DiscoverCredits`.
- AI client eligibility -> `ReadsStoredPortfolioBriefs.ClientContext`, then
  `ReadsPortfolioService.StateCredit` **with both stored averages**.
- AI client trend / jobs-at-risk -> the corresponding stored briefs, preserving
  the callback that identifies the accepted run.
- Claims portfolio/discovery consumers -> `BuildPortfolio` or `FromTiles` when
  they genuinely need the legacy source-backed statutory scan. The book's
  `/api/v2/portfolio` remains Claims-owned and should not call a payroll replay
  to display accepted claims.
- Draft/base-year/rebase callers -> `ReadsUnitTrendService.Execute` only when
  explicitly requesting a compute/rebase series, never for a Gold page load.

## Existing versus completed

Already certified and unchanged: `PayrollRows`, `ProgramDefaults`,
`ClientRunResolver`, `FiscalSource`, `RuleLibrary`, both One/Zero runners,
`OneZeroResultTrees`, `Rollups`, `UnitTrendQueryHelpers`, `UnitTrendTools`,
`BaseYearEngine`, `DesignationRegistry`, `Proximity.FragileCohort`.

Completed here:

- Portfolio source loading, substantial latest-year selection, pay-date fiscal
  bucketing, current/prior state calculations, one tile per priced program,
  federal hire tile, no-pack distinct employee counts, all display/audit fields.
- Discovery positive-lifetime filtering, stable descending ordering, exclusions
  independent of considered packs, exact totals, and active trail scan/hit steps.
- Full trend replay/assembly: load once, strict year/program/window resolution,
  named declines, six-reachable-month guard, matrix-to-unit/FEIN aggregation,
  reachable-month base inference, optional base override, designation provenance,
  staircase and tranche columns, exact totals, metadata and disclosures.
- Gold-only context, across-year trend and eligible-population risk briefs.
  Null future verdicts, uncalculated current years, missing prior years, fractional
  jobs, stored tokens and unfiltered denominators are retained.
- W1's missing legacy designation entries are filled read-only for **null/default
  client scope only**, using the four existing synthetic timelines. A real
  client-keyed designation is never guessed or replaced.

Parent should link this completion ledger from its port-map addendum; this
subtask was expressly prohibited from editing `port-map.md`.

## Verification

Oracle: `C:\Projects\py312-oracle\.venv\Scripts\python.exe`, CPython 3.12,
production functions from this checkout and public synthetic input only.
The small-fixture oracle uses `DATA_SOURCE=csv`. The P2 oracle builds account
2001 with `build_synthetic_dataset`, projects it through `source_to_bcs_rows`,
and calls the production `handle_get_unit_trend` for both methods. Only payroll
loading and fiscal-rule retrieval are rebound to that in-memory dataset; the
production fiscal-window resolver, strict year packs and engines run unchanged.
`contract.harness.hermetic.apply` disables dotenv/live configuration, blocks
outbound sockets, freezes the clock and places operational state in an explicitly
specified project-owned scratch folder, removed after generation. No temporary
directory or live adapter is used. Full output snapshots are under the owned test
`Fixtures` folder.
Only declined-year **error wording** is normalized; all successful values,
metadata, calculations, tiers, disclosures, rows and totals are compared.

- `PortfolioAssemblyTests`: full portfolio/discovery snapshot comparison;
  discovery trail; unknown client/missing payroll; unauthored year; invalid
  method; source failures; stored-average pricing without payroll; program/state
  conflict.
- `UnitTrendAssemblyTests`: full Min-Max and Pay Period snapshot comparison,
  repeated-call decline retention, base override, explicit program, fresh source
  reads rather than replay-cache substitution.
- `PortfolioPortBoundaryTests`: second program in one state with a distinct
  rate, explicit trend program, strict fiscal failure propagation, thin-tail
  latest-year selection and empty-source clock fallback.
- `StoredPortfolioBriefTests`: no payroll access; legitimate stored zero versus
  absent result; null post-base verdict; eligible/evaluated population and
  fractional risk jobs; stored record token.
- `PortfolioP2Tests`, explicitly **heavy**: ordinary TestHost reset/composition,
  complete account 2001 source/fiscal trend against direct Python legacy-query
  snapshots for both methods, then stored client context against accepted Gold.

Latest completed command:

```powershell
cd dotnet
dotnet test tests\TaxCredit.Api.Tests\TaxCredit.Api.Tests.csproj `
  --no-restore -m:1 `
  --filter "FullyQualifiedName~ReadsCalc.Portfolio" `
  -v minimal
```

**15 passed, 0 failed, 0 skipped, 2 minutes 45 seconds.** This includes the heavy
P2 test; the other 14 cases previously completed in 20 seconds. The command built
Application, API, adapters and test projects with ordinary analyzers enabled and
reported no warnings or errors. Owned whitespace formatting was run.
Both `dotnet format whitespace` and `dotnet format style`, restricted to the
owned application/test folders with `--verify-no-changes`, completed successfully.

The initial P2 test compared trend lifetime directly to Gold writer totals.
That assertion was invalid: the newer writer excludes the open year from closed
tranches and projects installments separately; this legacy query includes every
accepted year in its series. Direct production Python confirmed the C# values:
`GA_GA-001` Min-Max lifetime is **126,385** for the legacy query, versus
**128,730** in Gold. The replacement compares full direct-query snapshots rather
than changing the calculation to satisfy a different engine path.

Observed public fixture values:

| Answer | Value |
|---|---:|
| Latest substantial year | 2025 |
| Portfolio GA annual / lifetime | 66,500 / 332,500 |
| Discovery annual / lifetime, no exclusions | 185,825 / 500,395 |
| Discovery hits, no exclusions | 4 |
| GA trend years / units | 2024–2025 / 4 |
| GA trend annual / tranche lifetime | 83,125 / 415,625 |
| P2 account 2001 Min-Max annual / tranche lifetime | 546,980 / 668,080 |
| P2 account 2001 Pay Period annual / tranche lifetime | 545,860 / 667,520 |

These are public fixture values, **not private reference certification**.

## Deliberate differences / inherited limitations

- An entirely empty client payroll declines `BuildPortfolio` instead of returning
  a successful unrelated federal-reference tile. Unknown client and outage must
  not look like a completed client assessment. Source transport and strict fiscal
  failures propagate unchanged; they are not caught as ordinary year declines.
- No process-global replay cache: Python's key omits source content and its cached
  tuple drops declined-year explanations on subsequent calls. Fresh calls retain
  errors and all declines; successful figures are unchanged.
- `StateCredit` checks a known explicit program/state conflict using the existing
  certified defaults helper. Parent still owns HTTP error-family/status mapping.
- Portfolio uses the Python pay-date fiscal convention and flat benefit helper,
  **not** the newer client-window assessment path. Trend preserves Python's
  latest scalar threshold/rate pricing and emits `STATUTE-DRIFT`; it does not
  silently switch to per-year benefits or change calculated values. Source/fiscal
  bridge limitations, including strict leap-window shifts, remain W1 limitations.
- Source data is not a historical snapshot; no freshness guarantees or private
  reference certification are claimed. No live system was contacted.

Any required improvements-register entries and the final full-build/replay
evidence belong to the parent-owned report/register, not this restricted slice.
