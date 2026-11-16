# ReadsCalc application and route handoff

**HALTED under hard-stop 1.** All 29 owned operations have implementations, but
the whole fast-test and replay gates are not green. Shared mediator lifetime,
feature-composition tests and duplicate framework probe routes require work
outside this session's ownership. No shared source was changed to conceal those
failures. See [HALT-routes_reads.md](HALT-routes_reads.md).

## Scope and composition

The feature owns exactly the 29 operations below. `ReadsCalcEndpoints` is
discovered by the ordinary API host and replaces only its exact inherited stubs.
`ReadsCalcModule` registers inward services before the provider is built;
requests enter the existing mediator. No central host, certified Domain, Python,
infrastructure, or sibling-feature source is modified.

The W1/W1b runtime already supplied `PayrollRows`, `ProgramDefaults`,
`ClientRunResolver`, `UnitTrendQueryHelpers`, all 25 `IGoldReadPort` members,
source selection/catalogue/fingerprints, operational persistence, authentication,
scenario reset and calculation execution. They are collaborators, not new ports.
Accepted-result handlers never replay payroll to produce a stored figure.
Explicit simulations and forecasts compute only their requested new reading.

## Operation / evidence / handler inventory

All paths have the `/api` prefix. `p1_reads` supplies ordinary success and binding
edges; `p1_query_edges` supplies specialized filters, unknown selections and
repeated scalars. `p2_reads_writes` supplies staged analytics and cross-client
coverage. The exact route registry remains `route-groups.json`.

| Method and path | Application entry point | Additional evidence/dependencies |
|---|---|---|
| GET `/me` | `IdentityReadHandler` | `p1_auth`, shared verified principal |
| GET `/eligibility/{tax_year}` | `StoredEligibility.Read` | `eligibility.status-both`, `eligibility.near-floor`; both methods, unpaged counts |
| GET `/progress/{tax_year}` | `ProximityViews.Progress` | negative within; recorded headcount denominator; `test_forecast.py` |
| GET `/forecast/{tax_year}` | `ReadsCalculationViews.Execute` | source forecast; `test_forecast.py` |
| GET `/alerts/monthly/{tax_year}` | `ReadsCalculationViews.Execute` | monthly canonical series |
| GET `/triggers` | `ReadsCalculationViews.Execute` | deterministic trigger catalogue |
| GET `/performance/{tax_year}` | `ReadsCalculationViews.Execute` | source performance, no accepted-result substitution |
| GET `/onezero/matrix/{tax_year}` | `StoredMatrix.Read` | `test_api_onezero_matrix.py`; recorded verdicts and resolved cells |
| GET `/onezero/{tax_year}` | `ReadsCalculationViews.Execute` | legacy calendar snapshot |
| GET `/onezero/{tax_year}/employee/{employee_id}` | `ReadsCalculationViews.Execute` | legacy employee detail, review annotations |
| POST `/onezero/employee/{employee_id}/review` | `ReviewOneZeroEmployeeHandler` | `p1_writes`, consistent writer authorization |
| GET `/designations/{state}` | `ReadsCalculationViews.Execute` | synthetic designation history; `test_designations.py` |
| GET `/reconcile/{tax_year}` | `ReadsCalculationViews.Execute` | source reconciliation |
| GET `/qc/{tax_year}` | `ReadsCalculationViews.Execute` | certified QC detection |
| GET `/onezero/retroactive/scan` | `ReadsCalculationViews.Execute` | retroactive source years |
| GET `/simulate/portfolio/{tax_year}` | `ReadsCalculationViews.Execute` | zero/negative inputs; host magnitude bound |
| POST `/simulate/unit` | `ReadsCalculationViews.Execute` | `test_simulate_unit.py`; year-resolved pricing |
| POST `/simulate/employee` | `ReadsCalculationViews.Execute` | source employee lever, no per-person dollar attribution |
| POST `/simulate/onezero` | `ReadsCalculationViews.Execute` | certified One/Zero simulation |
| GET `/ingestion/{tax_year}` | `IngestionViews.Overview` | `test_ingestion.py`; fiscal source selection and persisted annotations |
| POST `/ingestion/{tax_year}/exceptions/{exception_id}/resolve` | `ResolveIngestionExceptionHandler` | `p1_writes`; annotation, not Claims finding lifecycle |
| GET `/ingestion/{tax_year}/rows` | `IngestionViews.Rows` | source search/sort before paging; honest matching total |
| GET `/proximity/{tax_year}` | `ProximityViews.Cohort` | `test_rest_of_year.py`; necessary hours bound and unbounded counts |
| GET `/scope` | `ScopeViews.Options` | source client book plus materialized program/year catalogue |
| GET `/scope/client/{account_id}` | `ScopeViews.Client` | fiscal-window coverage, unknown versus empty versus outage |
| GET `/v2/clients/{client_id}/units` | `StoredUnits.Page` | `units.year-none`, `units.method-pp`; stored totals |
| GET `/v2/clients/{client_id}/units/{unit_id}` | `StoredUnits.Detail` | `unit.filter-good/bad`, `unit.month-0/13`, `unit.near-min-hours`; `client2001.unit-detail/unit-other-client/year-uncalculated` |
| GET `/v2/employees/{record_token}` | `StoredEmployees.Detail` | `unknown.employee-unknown-token`; tenant/run-bound lookup |
| POST `/employee/drill` | `StoredEmployees.Drill` | `test_api_employee_drill.py`; stored periods, verdicts and resolved segments |

### Setup and capture dependencies

P1 resets seed the real accepted run and source CSV. `boot.unit` obtains the
employee token used later by employee/drill operations; it must execute before
those exchanges. `boot.findings` belongs to Claims and remains a dependency
where later exchanges substitute finding handles. `p1_artifacts_ai` also
bootstraps these captures and cannot be omitted merely because its name is AI.
P2 resets use the existing SQL-analytics staging/projector path. Subsequent
sibling claim/run/base-year/rebase writes are not implemented or simulated here.
Missing captures and 501s from those operations are setup/sibling failures, not
permission to add their routes or manufacture accepted data.

## Application seams

### Portfolio, discovery and full trend assembly

The public namespace is
`TaxCredit.Application.Features.ReadsCalc.Portfolio`. The feature module calls
`AddReadsCalcPortfolio()`. Exact signatures, collaborator contracts, Python
examples and tests are in
[routes_reads-portfolio-handoff.md](routes_reads-portfolio-handoff.md).

- `ReadsPortfolioService.BuildPortfolio`, `LatestTaxYear` and `StateCredit`
  complete the legacy statutory portfolio scan without importing Claims or AI.
- `ReadsDiscoveryService.DiscoverCredits` and `FromTiles` preserve filtering,
  order, exclusions, trail steps and totals.
- `ReadsUnitTrendService.Execute(UnitTrendRequest)` completes the deferred
  source-backed series assembly and base override. It is an explicit compute
  seam for Drafts/Runs, not the accepted-result page load.
- `ReadsStoredPortfolioBriefs.ClientContext`, `ClientTrend` and `JobsAtRisk`
  give AI the accepted Gold values without another payroll replay.

The remaining outer adapter is `IPortfolioReferenceData`, with
`CountFederalNewHires(long)` and `Worksite(string)`. W1 payroll ports carry pay
periods, not hire dates; Python's separate committed synthetic annual-payroll
reference supplies that count. No invented zero or first-paycheck surrogate is
bound. AI's discovery/eligibility consumers and any genuine legacy Claims scan
must arrange that adapter; Drafts' explicit trend consumer has no dependency on
the future sibling classes. Missing hire-date access is not permission to copy
an engine or call an HTTP loopback.

### Calculation views

`ReadsCalculationViews.Execute` accepts either a method/template plus parameters
and optional JSON body, or its internal operation alias plus `ReadArguments`.
All 15 source-calculation/review operations and their certified collaborators
are listed in
[routes_reads-calculations-handoff.md](routes_reads-calculations-handoff.md).
The entry point has no dependency on unfinished sibling features.

### Durable annotations

`QcAnnotations.Resolutions(client)` hydrates a fresh certified
`QcResolutionStore` from versioned `ILookupStore` entries. The lookup is named
`qc_exception_annotation`, key kind `exception`, and is client-bound. Reopening
closes the live lookup version while retaining its action audit. Source-backed
calculation reads can consume this input; the certified writer is unchanged.
Claims' pending `application/qc_resolutions.py` equivalent should bind to this
same lookup contract rather than introducing a second process-global store.
The historical resolve URL carries no client: the explicit client query wins,
otherwise only the configured fixture account is eligible; a multi-client
source without a selected client receives 422 instead of a cross-client write.

`SiteLabels` is the display-only legacy synthetic site catalogue. Unknown
source-schema units retain their actual unit key; labels never affect math.
`IngestedPayCodes` exposes captured ingestion classification through
`IIngestedConfigSource` using the existing `IIngestedConfigFiles` boundary.
It performs no web retrieval.

## Limitations and owner decisions

- M-01: captured ingestion can override wage basis, measuring date and pay
  codes even on year-resolved packs. Preserve the certified calculation;
  ADR-005's stronger precedence rule needs an owner decision.
- Multi-program `credit_math` still prices its first program. Selection
  refusals remain in the certified run resolver; changing the arithmetic is
  not a route-layer improvement.
- FS-01/FS-11, CQ-02/CQ-05 and CAP-10 retain their certified boundaries:
  current/prior state-filter asymmetry, calendar legacy One/Zero, cash-basis
  canonical trimming, first-row collapse, and QC read drops versus writer.
- The strict leap-shift bridge for 2024-02-29 through 2025-02-28 is partial.
  No Domain repair or claim of universal strict fiscal parity is made.
- Source row-count/max-modified fingerprints are not Delta snapshots and
  cannot detect count/max-preserving edits.
- Live Warehouse metadata, native monetary AVG, external source freshness
  and private-reference certification are not verified. Only synthetic
  hermetic fixtures are used; there are no live customer calls.

## Verification log

Oracle: CPython **3.12.13**, using the approved interpreter and this checkout.
Target: .NET **10.0**, SDK **10.0.404**. No packages, live calls, private extracts,
central registration changes or new infrastructure were used.

| Check | Observed result |
|---|---|
| Whole strict build, final implementation | Passed, 0 warnings / 0 errors |
| Whole `dotnet format --verify-no-changes --no-restore` | Passed |
| Owned fast cases, final checkpoint | 28 passed in 15 seconds; the additional annotation/reset case passed before being moved to `heavy` |
| Whole non-heavy suite | 723 passed, 13 failed; all 13 in API framework/contract tests |
| Portfolio/discovery/trend tests including heavy P2 | 15 passed |
| Isolated P2 forecast recording comparisons | All four client cases passed; the enclosing heavy run was stopped at HALT, not claimed complete |
| Complete ordinary-host replay, six scenarios | 1,245 exchanges; raw ReadsCalc **241/514 (46.89%)**, gate failed |

The full-suite count is from `reads-fast01`, before the final test-category
metadata adjustment. The final strict build, formatter and 28-case selection
cover implementation commit `ef6a3fe`, including the transport/reviewer changes
and test-category adjustment. Slow/heavy recording cases not reported by the
runner remain unclaimed.

### Ordinary-host replay evidence

The normal API was started with no test-assembly feature registrations. Real
endpoint discovery, seed reset and auth/environment setup were exercised through
the existing contract hooks; no Worker poller was started. Complete scenarios:
`p1_artifacts_ai`, `p1_auth`, `p1_query_edges`, `p1_reads`, `p1_writes`,
`p2_reads_writes`. The raw board is
`dotnet/artifacts/reads-02.json`; per-scenario reports are under
`dotnet/artifacts/reads-02-raw/` (local, ignored artifacts).

| Scenario | Exchanges | Raw differences across all groups |
|---|---:|---:|
| p1_artifacts_ai | 36 | 150 |
| p1_auth | 114 | 416 |
| p1_query_edges | 71 | 534 |
| p1_reads | 584 | 1,257 |
| p1_writes | 366 | 1,049 |
| p2_reads_writes | 74 | 641 |

These are raw, unchanged-comparer observations, not waived or adjusted scores.
The wrapper includes exact validation text, framework variants and sibling
business routes. The improvements register describes limited non-figure
differences; **no passing adjusted replay percentage is claimed**.

All P1 `ok.*` source-calculation reads matched. Stored unit responses differ in
the page-independent population metadata described below. The replay also found
two local reviewer-attribution discrepancies: Python accepted the supplied
synthetic reviewer, whereas the first endpoint implementation defaulted it to
`system`. The endpoint now reads the body before attribution, preserving that
local fallback while the verified principal still overrides spoofed attribution.
That final fix compiled and the owned fast suite passed; the full replay was not
repeated after the mandatory shared-boundary HALT.

### Owned-handler differences, not waived as numbers

Stage 2 explicitly requires unfiltered population counts independent of page
size. W1 `GoldReader.PeopleTotal` instead returns `displayed` when no grid filter
is present, after applying `Limit`; the Python recordings pin the same defect.
The application uses existing unbounded Gold ports for these counts:

- `p1_query_edges:unit.limit-1`: recorded **1 / 1**, actual **21 / 10**.
- `p2_reads_writes:client2001.unit-detail`: recorded **3 / 3**, actual **26 / 13**.

The focused host case proves independent employee/near filters, paging and
month validation. Neither the recorded numbers nor the comparer was edited.
No numeric waiver exists. The owner must reconcile the conflicting count
requirement and numerical recording policy before a 100% gate is attainable.

### Shared composition failures and setup dependencies

`DependencyInjection.AddApplication` registers `IMediator` as a singleton.
`Mediator` resolves handlers through its captured provider, not the current
request scope. Scoped ReadsCalc services can consequently retain the first
CSV/fiscal source across P1-to-P2 resets. Ordinary replay then reports the
fixture client rather than the four P2 clients and emits assumed-calendar
fiscal metadata. Fresh isolated P2 hosts pass complete forecast comparisons for
all four clients and full trend comparisons for both methods. Those isolated
passes do not establish multi-reset correctness.

Framework tests `RegistryTests`, `DiscoveryTests`, `PagingTests` and
`RuntimeTrustTests` deliberately add their own `GET /api/scope` probes.
`EndpointRegistration` maps all real groups without resolving duplicate real
method/templates. The new real scope route therefore raises
`AmbiguousMatchException`; setting endpoint order would still fail their
`Assert.Single` contract and would hide, not solve, the collision.

`ProviderSelectionTests` separately validates `AddApplication` plus infrastructure
without feature registration. It now reports
`Unable to resolve service for type ...ReadsCalculationViews` and the other
feature services while validating the automatically discovered handlers.
Updating those tests to use actual feature composition, or settling a shared
Application registration contract, lies outside this ownership.

Missing sibling handlers cause additional, separate discrepancies: Claims'
finding/portfolio/situation operations and Drafts' run/base-year/rebase writes
remain 501. Later owned reads cannot reproduce the run identity, override
provenance and recalculated values those absent writes would have produced.
No sibling route is mapped here and no accepted run is fabricated to compensate.
W1b's existing readiness mismatch remains outside this feature.

### Persistence and remaining validation

Owned tests passed for accepted-run identity/value preservation after reopening
the same operational store, method-specific whole-population counts, independent
unit filters, source sorting before paging, typed dictionary/null/number
transport, durable exception/review annotations and a second annotation reset.
The annotation reset case exceeded 20 seconds under contention and is now
tagged `heavy`. Parent P2 token/year coverage and the unreported remainder of
the heavy calculation-recording run are deferred at HALT; they are not reported
as passes.

The code is a preserved implementation checkpoint, **not an integration-ready or
certified complete route slice**. The precise upstream decisions and restart
steps are in the HALT report and machine-readable status.
