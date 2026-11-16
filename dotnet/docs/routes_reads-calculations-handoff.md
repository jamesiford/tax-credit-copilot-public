# ReadsCalc source-calculation handoff

## Public application seam

`TaxCredit.Application.Features.ReadsCalc.Calculations.ReadsCalculationViews`
has these public overloads:

```csharp
object Execute(string operation, IReadOnlyDictionary<string, string?> parameters,
    JsonElement? body = null);
object Execute(string operation, ReadArguments args);
```

`operation` accepts the literal method/template below, or the internal alias in
the second column. Results are nested ordinary dictionaries/arrays, normalized
with `ReadValues.Transport`, not direct HTTP serialization of `PyDict`.
Operation refusals use shared `ReadRefusalException.StatusCode`. Source adapter
failures retain their existing typed distinctions rather than becoming an empty
successful report.

Constructor collaborators, all supplied by the existing composition plus the
parent ReadsCalc module:

- `RuleLibrary`, `ProgramDefaults`, `ClientRunResolver`;
- `IClientPayrollSource`, `ILookupStore`, `IGoldReadPort`;
- `ClientCalculationConfig` (the deterministic clock);
- shared `ReadsCalc.Ingestion.QcAnnotations`.

No dependency on the sibling Portfolio builders, an HTTP loopback, external
systems, an additional package, or a modified Domain helper was introduced.

## Covered operations

| Method/template | Alias | Implementation / authoritative Python |
|---|---|---|
| GET `/api/forecast/{tax_year}` | `forecast` | `ForecastViews.Forecast`; `api/forecast.py`, `ForecastProjection` |
| GET `/api/alerts/monthly/{tax_year}` | `monthly_alerts` | `ForecastViews.MonthlyAlerts`; `api/forecast.py`, `application/alert_levers.py` |
| GET `/api/triggers` | `triggers` | `ForecastViews.Triggers`; `api/forecast.py`, `TriggerDetector` |
| GET `/api/performance/{tax_year}` | `performance` | `ForecastViews.Performance`; `api/forecast.py`, `PerformanceDashboard` |
| GET `/api/onezero/{tax_year}` | `onezero` | `OneZeroViews`; `queries/get_one_zero.py`, `application/onezero_entry.py` |
| GET `/api/onezero/{tax_year}/employee/{employee_id}` | `onezero_employee` | `EmployeeViews.Employee`; `queries/get_employee_derivation.py`, engine-output slicing |
| POST `/api/onezero/employee/{employee_id}/review` | `review_employee` | `EmployeeViews.ReviewEmployee`; `commands/review_employee.py` |
| GET `/api/designations/{state}` | `designations` | `QualityViews.Designations`; `queries/get_designation_splits.py`, `DesignationRegistry` |
| GET `/api/reconcile/{tax_year}` | `reconcile` | `QualityViews.Reconcile`; `queries/get_reconciliation.py`, `BenchmarkReconciliation` |
| GET `/api/qc/{tax_year}` | `qc` | `QualityViews.Qc`; `queries/get_qc_exception_report.py`, `QcDetector` |
| GET `/api/onezero/retroactive/scan` | `retroactive` | `RetroactiveView`; `api/retroactive.py`, `BaseYearEngine` |
| GET `/api/simulate/portfolio/{tax_year}` | `simulate_portfolio` | `EntitySimulation`; `queries/simulate_portfolio.py` |
| POST `/api/simulate/unit` | `simulate_unit` | `UnitSimulation` + `LocationPricing`; `queries/simulate_unit.py` |
| POST `/api/simulate/employee` | `simulate_employee` | `EmployeeSimulation` + `EmployeeRestOfYear`; `queries/simulate_employee.py` |
| POST `/api/simulate/onezero` | `simulate_onezero` | `EntitySimulation`; `api/simulate.py` |

Every statutory result is obtained from certified Domain methods: Pay Period,
Min-Max, Headcount, forecast, performance, rollups, reconciliation, QC, triggers,
OneZeroLever, OneZeroSimulation, designation splits, and frozen-base-year trend.
`EmployeeRestOfYear` completes the deferred application-level scenario transform:
paid periods stay immutable, split pay-code lines share one future-period
target, and open-year periods are projected only while their pay date remains
inside the fiscal window. It does not decide eligibility or price credits.

Unit and employee what-ifs read the stored location series, reproduce the
baseline payroll average, and price the changed series with `UnitTrendTools`.
The unit what-if also reproduces the stored baseline qualified/credit verdict.
Open years retain zero claimable credit and expose explicitly named run-rate
estimates. Stacked employees are changed together before a single engine
evaluation, not priced as the sum of independent single-person scenarios.

## State and source boundaries

- Source reads use `PayrollRows.RequirePayPeriods` over `IClientPayrollSource`.
  Reads requiring QC drops hydrate fresh tenant decisions through
  `QcAnnotations.Resolutions`; no private/global resolution dictionary exists.
- Employee annotations are versioned `ILookupStore` rows:
  lookup `employee_reviews`, client `0`, kind `employee_id`. Clearing closes the
  current version. A fresh service scope reads the persisted decision.
  The legacy route has no tenant argument, so its annotation namespace remains
  global by employee key; adding tenant scope requires an API contract decision.
- The attributed reviewer supplied by the parent endpoint is preferred over
  request-body attribution; an extra `actor` body field is not consumed.
- Optional negotiated state overrides read lookup `negotiated_overrides`,
  client `0`, key equal to the state. No override authoring endpoint/binding
  exists in this slice. An absent row means no negotiated override, not invented
  statute.
- Designation reporting builds the existing **read-only legacy synthetic**
  timelines locally because W1's injected registry intentionally holds only
  source-schema stories. Those display facts are flagged by the Domain report.
- Reconciliation uses the authored synthetic benchmark from
  `backend/data/onezero_benchmark_synthetic.json`, including its full disclaimer,
  as application-owned immutable benchmark data. It is not a recorded response.
- Retroactive filing comparison preserves the separate illustrative
  `backend/data/claims.py` registry's state/year membership. It is not silently
  replaced by operational Claims decisions or presented as a verified filing.
- No source exception is caught into a successful empty portfolio. Per-client
  simulation arithmetic failures alone may produce an explicit declined row.

## Fiscal quirks intentionally preserved / owner candidates

These are figure-affecting Python behaviors, not fixes authorized by this task:

1. Forecast, legacy OneZero, employee derivation, reconciliation and retroactive
   scan use the legacy global fiscal convention. Python's
   `get_fiscal_year_end_month()` is a constant `12`, not a runtime setting.
   They are intentionally distinct from the client's resolved fiscal window.
2. Performance and monthly alerts select by the source `Tax_Year` column,
   whereas legacy OneZero and forecast select by pay date.
3. Entity and portfolio simulations select source rows/prior bases using the
   client's fiscal windows, but certified `OneZeroSimulation.OneZeroSnapshot`
   still measures the snapshot with a calendar start. Correcting that helper
   would change figures and requires the owner/Domain slice.
4. Legacy credit application still uses RuleLibrary's existing first-program
   selection and captured-ingestion precedence. No statutory values were
   independently copied or corrected.
5. Retroactive tranches preserve the scalar benefit sampled by Python rather
   than retrofitting a per-year rate map; the separate legacy illustrative
   filing membership also considers pending registry entries “already filed.”
   Neither is evidence about an actual filed return.
6. W1's documented strict leap-window bridge limitation remains unchanged.
   No private reference extract or live source was used to claim verification.

Deliberate non-figure improvements: employee reviews are durable instead of
process-global; finite simulation magnitude is bounded at 10,000 (F-1);
invalid date-backed tax years receive an application 422 rather than an
unhandled date construction failure. Designation-only year labels remain
unbounded integers because that operation constructs no calendar dates.
The parent consolidates any replay improvements register; none is authored here.

## Verification

Focused tests under `TaxCredit.Api.Tests/ReadsCalc/Calculations`:

- `EmployeeRestOfYearTests`: split pay-code allocation, immutable paid periods,
  open-year pay-date bound, and explicit unavailable/closed-year refusals.
  **3 passed**, isolated .NET 10 test execution.
- `CalculationBoundaryTests`: small, hermetic source replacement through normal
  host DI; legacy source-year versus pay-date selection; source-outage and
  unknown-client distinction; operational magnitude refusal; persisted reviews,
  reviewer attribution, and clearing across service scopes.
- `CalculationRecordingTests` (**heavy**): all 11 P1 successful calculation-read
  bodies, three P1 source/Gold simulation bodies, and four P2 client forecast
  bodies. Comparisons are recursive semantic values, not response fixtures used
  by the implementation. Seed reset/setup is intentionally included.

The parent reported an ordinary-host complete P1 reads replay with **all owned
successful calculation cases matching**, including forecast, alerts, triggers,
performance, legacy OneZero, employee detail, designations, reconciliation, QC,
retroactive scan and portfolio simulation. This is parent-reported replay
evidence, not a separately claimed run.

An application compile with analyzers disabled passed the owned calculation
files. Owned IDE0011 and formatting diagnostics were fixed using project-scoped
`dotnet format` includes; remaining owned CA1859/CA1861 findings were corrected.
A concurrent seed-backed full test attempt was stopped to avoid contending with
the parent's host/test verification, not reported as passing. Final current
whole-solution analyzer and P2 replay results belong to the parent report.

### Historical bounded verification before the initial parent HALT

- Updated all three owned parser calls to the final shared `WholeNumber` name.
- Current isolated .NET 10 compile and lightweight tests: **6 passed, 0 failed,
  0 skipped** (675 ms test duration; analyzers disabled). The tiny test source
  also implements `ISourceReader`, as required by runtime readiness binding.
- Heavy recording execution independently passed **all four P2 forecast
  comparisons**, for clients **2001, 2002, 2003, 2004**, with a fresh P2 host and
  reset per case. Complete JSON semantics matched authoritative recordings.
  Their individual elapsed times were 2m17s, 3m04s, 2m22s and 2m10s respectively.
- The heavy run was explicitly stopped at the parent's hard-stop instruction,
  after those four reported passes. It is **not a completed 18-case pass**;
  no additional P1 simulation/read result was reported before cancellation.
- Parent identified an integration defect outside this ownership: singleton
  Mediator resolves scoped handlers from the root, retaining source/fiscal
  adapters across ordinary-host P1-to-P2 resets. Fresh isolated P2 passes do not
  establish correctness of that reset lifecycle. Parent also reports framework
  stub/duplicate-endpoint and AddApplication-only validation blockers.
  No shared implementation was changed to repair these issues.

### Conductor retry correction

The initial conclusion that composition required unowned changes was wrong.
The parent fixed source/fiscal retention with operation-owned DI scopes and
resolved explicit host route overrides within ReadsCalc. Shared mediator,
hosting and framework tests remain unchanged. The whole strict build and
formatter now pass, and all **741 non-heavy solution tests** pass, including
**95 API tests**. Fresh lifecycle, source-absence and token/year tests pass.
The current complete replay and remaining heavy recording results are reported
in [ROUTES-READS-REPORT.md](ROUTES-READS-REPORT.md); the historical canceled run
above is not their evidence.
