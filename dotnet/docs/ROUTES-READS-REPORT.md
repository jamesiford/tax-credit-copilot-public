# ReadsCalc application and route handoff

**The composition failures are fixed within the owned feature.** All 29
operations are implemented, the strict build and formatter pass, and the whole
non-heavy suite passes **741/741**, including **95/95 API tests**. The former
HALT incorrectly concluded that shared edits were necessary; it is removed.
Replay remains a separate, failing gate: page-independent counts required by
Stage 2 disagree with recorded numbers, and some scenario setup needs unfinished
sibling writes. No recording, numerical comparison or threshold was weakened.

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

ReadsCalc mediator handlers now resolve their collaborators inside an
operation-owned `IServiceScope`. This preserves the existing mediator and normal
feature registrations while avoiding root-captured source/fiscal collaborators.
The host can change profiles and authentication configuration without retaining
the first request's selection. `ReadEndpointFallbacks` lets an explicitly mapped
host route replace the same feature-default method/template, independent of
discovery order; there is one effective endpoint, not an ordered ambiguity.
Neither correction changes shared hosting or test files.

Accepted-result statute resolution is lazy through `ReadStatutes`. An
unconfigured payroll adapter does not prevent reading accepted Gold rows.
When the program/state is explicit, non-strict fiscal policy retains the
existing, disclosed `assumed_calendar` fallback; strict policy still refuses.
Source-backed forecasts and ingestion never turn a missing source into an
empty successful answer.

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
| Whole strict build, implementation `c253ade` | Passed, 0 warnings / 0 errors |
| Whole `dotnet format --verify-no-changes --no-restore` | Passed |
| Whole non-heavy suite, `reads-repaired-gates` | **741 passed, 0 failed, 0 skipped** |
| API non-heavy subset of that suite | **95 passed**, including all formerly failing framework/contract cases |
| Lifecycle, source-absence, token/year and auth regression selection, `reads-composition-final` | **4 passed**, including P1-to-P2-to-P1 and the heavy cross-client token test |
| Previously unreported P1 calculation recording cases, `reads-calculation-final` | **14 passed**: 11 calculation reads and all 3 simulations |
| Prior portfolio/discovery/trend tests including heavy P2 | 15 passed; no portfolio implementation changed in the repair |
| Prior isolated P2 forecast recording comparisons | Four client cases passed; the canceled enclosing run is not claimed complete |

The final build/format/fast command ran sequentially against the whole solution,
not only owned tests. Project counts were API 95, architecture 16, Domain 18,
AI 167, auth 147, persistence 129, sources 108 and parity 61. The four regression
cases also passed with normal feature discovery. Long source/profile/token tests
are tagged `heavy`; their comparisons were not weakened. Ten-minute client
timeouts on the P2 lifecycle/token cases accommodate seed construction, not a
different expected outcome.

### Fresh complete ordinary-host replay

The final normal API was started with no test-assembly feature registrations.
Readiness returned 200 before replay. Real endpoint discovery, seed reset and
auth/environment setup were exercised through the existing contract hooks;
no Worker poller was started. **All twelve complete scenarios** ran, including
the gateway and sibling-only scenarios: **1,769 exchanges, 6,765 failing fields
across all groups**. The unchanged replay command completed with exit 1.

The raw board is `dotnet/artifacts/reads-04.json`; per-scenario reports are under
`dotnet/artifacts/reads-04-raw/` (local, ignored artifacts). These artifacts are
not the only evidence: the totals and specific remaining failures are preserved
here. The owned API helper was stopped afterward; no unrelated process was
terminated.

| Scenario | Exchanges | Raw differences across all groups |
|---|---:|---:|
| g1_mcp | 103 | 602 |
| g1_ratelimit | 10 | 86 |
| g1_rest | 142 | 857 |
| p1_artifacts_ai | 36 | 150 |
| p1_auth | 114 | 416 |
| p1_program_drafts | 175 | 870 |
| p1_query_edges | 71 | 534 |
| p1_reads | 584 | 1,257 |
| p1_workspace_unavailable | 30 | 55 |
| p1_writes | 366 | 1,044 |
| p2_reads_writes | 74 | 385 |
| p2_run_batches | 64 | 509 |

These are raw, unchanged-comparer observations, not waived or adjusted scores.
The existing wrapper classifies wrong-method framework variants by path as well
as real operations and reports ReadsCalc **270/520 (51.92%)**. Matching the exact
29 owned method/templates instead yields **188/414 (45.41%) raw**:

| Scenario with exact owned operations | Raw matching cases |
|---|---:|
| p1_artifacts_ai | 0 / 1 |
| p1_auth | 28 / 47 |
| p1_query_edges | 18 / 33 |
| p1_reads | 87 / 195 |
| p1_workspace_unavailable | 2 / 6 |
| p1_writes | 15 / 92 |
| p2_reads_writes | 38 / 40 |

These are not comparable to the conductor's prior **199/414 including waivers**.
No adjusted percentage is claimed. The 226 raw failing owned cases partition
into 177 with only `detail`/header differences, 12 with only unfiltered-count
metadata differences, two dependent sibling-write envelopes, 34 with status
differences (mostly existing shared identity/page bounds), and one source-error
metadata nesting difference. Even error-only cases alone represent **42.75%**
of owned cases, above the planning policy's **20%** waiver cap. The task permits
free Tier C message text and the JSON `detail` family; copying Pydantic error
internals to escape that cap would contradict its no-framework-emulation rule.

The improvements register has **37 unique entries**, parsed and checked for
complete reasons. They describe error-family/message differences and authorized
defect corrections; none permits changed successful figures, run identities or
population counts. They are reviewable differences, not evidence that the cap
or the 100% threshold passes.

All P1 `ok.*` source-calculation reads and all three simulation bodies match.
The fresh P2 ordinary replay now matches **38/40 exact owned cases**. Its only
remaining differences are `client2001.unit-detail`'s required honest counts
(26/13 versus recorded 3/3), and `client-nonexistent.scope`'s free 404 wording.
All P2 source, fiscal, method, proximity and progress values otherwise match
through normal multi-scenario discovery/reset.

Reviewer attribution is now replayed after the fix: the validated body is read
before attribution, a verified principal still overrides supplied names, and
the local empty-body fallback is Python's `Reviewer`, not `system`.
Accepted unavailable-source unit and eligibility reads now match; source-backed
forecast/ingestion correctly report dependency 503 instead of no-payroll 404.

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
The same metadata difference recurs in boot captures and several limited detail
queries: **12 cases**, not twelve different arithmetic defects.

Other raw status differences come from W1's existing positive-Int64 storage
identity binder and maximum-10,000 SQL page size. Nonpositive identities receive
422 rather than Python's inconsistent empty-success/404 behavior; huge page
limits are refused rather than bypassing the shared bound. Invalid negative
proximity receives 422 instead of a plain-text 500 (F-4), and an overflowing
storage identity receives the intentional 422 (F-3). No global binder, SQL
adapter or numerical result was changed to reproduce those accidents.

### Resolved composition failures and remaining setup dependencies

The first attempt's 13 API failures and retained P1 adapters were real, but its
claim that a shared edit was required was incorrect. `ReadHandlerScope` now
activates registered feature services inside an operation-owned scope, so a
singleton mediator does not capture their source/fiscal collaborators. The
handlers' own constructor dependencies also validate when `AddApplication` is
used without eagerly constructing optional feature adapters.

`ReadEndpointFallbacks` gives explicit host endpoints precedence over the same
feature-default method/template, irrespective of feature discovery order.
The framework probes now resolve singly without `AmbiguousMatchException`.
It has no test-assembly, route-name or environment switch. All existing
`RegistryTests`, `DiscoveryTests`, `PagingTests`, `RuntimeTrustTests` and
`ProviderSelectionTests` pass unchanged.

The fresh normal-host regression proves one host changes from P1's CSV and
single client to P2's analytics and four clients, reads account 2002's real
April fiscal start, and returns to P1. Another proves switching to authenticated
mode after a local read does not retain local client rights. The heavy opaque
handle test proves cross-client token refusal and the distinction between an
uncalculated year and a calculated zero.

Missing sibling handlers cause additional, separate discrepancies: Claims'
finding/portfolio/situation operations and Drafts' run/base-year/rebase writes
remain 501. Later owned reads cannot reproduce the run identity, override
provenance and recalculated values those absent writes would have produced.
No sibling route is mapped here and no accepted run is fabricated to compensate.
W1b's existing readiness mismatch remains outside this feature.

### Persistence and remaining validation

Owned tests pass for accepted-run identity/value preservation after reopening
the same operational store, method-specific whole-population counts, independent
unit filters, source sorting before paging, typed dictionary/null/number
transport, durable exception/review annotations and a second annotation reset.
The annotation reset case exceeded 20 seconds under contention and is now
tagged `heavy`. The parent P2 token/year case and the formerly unreported
fourteen P1 calculation-recording cases now pass in completed runs.

The obsolete HALT is removed: no unowned source change is needed for these
repairs. The remaining replay-policy decisions and genuine sibling-consumption
seams are listed in the machine-readable status. This is not a claim that the
100% replay threshold passes.
