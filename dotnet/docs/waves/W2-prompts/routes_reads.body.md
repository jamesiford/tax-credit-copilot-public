## Your role

Implement the `reads_calc` application features and HTTP surface on the integrated W1b runtime. This is the certified-figure read/calculation path, not another engine port. The Domain calculation, numeric compatibility, Gold projection and payload builder are already certified; the missing work is application orchestration, transport shaping and the deferred view builders.

Work in `dotnet\src\TaxCredit.Application\Features\ReadsCalc`, `dotnet\src\TaxCredit.Api\Endpoints\ReadsCalc` and `dotnet\tests\TaxCredit.Api.Tests\ReadsCalc`. The authoritative operation list is `dotnet\docs\route-groups.json`: this group has 29 operations. Despite the brief's prose, `GET /api/v2/portfolio` belongs to ClaimsArtifactsRules; client run, latest-run, base-year and rebase endpoints belong to DraftsRuns. Implement the portfolio/discovery application work assigned here, but do not map those other groups' endpoints. Claims, draft/batch lifecycle, AI, gateway, shared host files and certified Domain sources are not this session's implementation scope.

## Preflight

Read `dotnet\docs\COMPOSITION-REPORT.md`, `dotnet\docs\HOST-ARCHITECTURE.md`, `dotnet\docs\PERSISTENCE-REPORT.md`, `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`, `dotnet\docs\DOMAIN-SLICE-REPORT.md`, `dotnet\docs\port-map.md` and the relevant families in `dotnet\docs\findings.md`. Then read `contract\CONTRACT-REPORT.md` sections 4-5, `contract\FINDINGS.md`, `contract\COVERAGE.md`, the P1/P2 recordings and the captured route schemas in `dotnet\src\TaxCredit.Api\Contract\routes.generated.json`.

Use the W1b state rather than the older skeleton account: real persistence, source selection, trust, reset and execution are already composed. Trace `IEndpointGroup`, `IFeatureModule`, the in-house mediator, `RequestValidator.Body`, the wire DTO/converters and existing error helpers. Feature services are discovered before host construction; an exact real method/template replaces its own 501 stub without a shared registration edit.

First establish a compact route-to-recording-to-handler inventory for all 29 operations. Include setup/capture dependencies, not just success responses. P1 uses committed CSV; P2 uses staged analytics and the existing projector. Existing ports provide the source catalogue and fingerprint reader, all 25 `IGoldReadPort` members, lookups, findings, claims and transactional calculation. Verify these through ordinary API composition, not a second hand-wired application graph.

The port map is a generated DS1 snapshot, not proof that its pending ports are still absent. Reconcile each assigned module with current W1/W1b code before writing it. In particular, `PayrollRows`, `ProgramDefaults`, `ClientRunResolver` and `UnitTrendQueryHelpers` already contain certified helpers. Preserve their implementation and finish only the surrounding application work.

## Stage 1: settle the data/view boundary and missing application work

Inspect `backend\tools\portfolio.py`, `backend\tools\discovery.py`, `backend\application\queries\get_unit_trend.py`, `backend\application\queries\_client_run.py`, `backend\application\payroll_rows.py` and `backend\application\program_defaults.py`. Implement remaining needed behavior in ReadsCalc using existing ports and certified helpers. Distinguish stored Gold reads from source-backed calculations: a read of accepted results must not silently run payroll again, and an unavailable source must not become an empty successful result.

Cover portfolio aggregation, discovery ordering/filtering, unit trend assembly, program selection, missing payroll and unauthored-year behavior using the existing Python specifications: `test_discovery.py`, `test_capabilities_equivalence.py`, `test_api_trend.py`, `test_designations.py`, `test_multiple_programs_per_state.py`, `test_run_state_derivation.py` and `test_routers_through_the_mediator.py`. Exercise the production Python functions from the session's checkout for any missing differential examples; new C# tests belong in the owned test folder.

Publish a narrowly named application entry point for the portfolio/discovery views inside ReadsCalc, with its input/output and W1 collaborator requirements documented. Claims' HTTP portfolio and AI's capability consumers are parallel sessions, so their new code is not available on this base. Do not make this group's compilation depend on their future classes. Identify any missing cross-feature consumption seam explicitly in the report, with the exact caller and proposed integration binding; an HTTP loopback or copied engine is not a substitute.

Checkable result: focused application cases produce the recorded P1/P2 view values and failure distinctions through W1 ports, and the deferred-module ledger names exactly what was already supplied versus completed here. Update `dotnet\docs\port-map.md` with a clearly delimited ReadsCalc completion addendum linking C# symbols/tests; retain the generated DS1 inventory and its historical percentages as historical, rather than relabeling all partial modules as complete.

## Stage 2: implement stored reads, scope and employee drill

Map `GET /api/me`, `/api/scope`, `/api/scope/client/{account_id}`, `/api/v2/clients/{client_id}/units`, `/api/v2/clients/{client_id}/units/{unit_id}`, `/api/v2/employees/{record_token}` and `POST /api/employee/drill`. Match each operation's fields, null/presence distinctions, selected method, current-run envelope, filters, totals and paging. Keep unfiltered population counts independent from page size and near-threshold filters. Resolve employee tokens against the stored tenant/run, not by exposing raw rows from another account.

Use `contract\recordings\p1_query_edges.jsonl` cases `units.year-none`, `units.method-pp`, `unit.filter-good`, `unit.filter-bad`, `unit.month-0`, `unit.month-13`, `unit.near-min-hours`, `unknown.client-huge` and `unknown.employee-unknown-token`. Include `contract\recordings\p2_reads_writes.jsonl` cases `client2001.unit-detail`, `client2001.unit-other-client`, `client2001.year-uncalculated` and both methods for clients 2001-2004. The smaller unknown client and an invalid storage identity are different cases.

Checkable result: seeded reads work on the ordinary host, cross-client reads refuse appropriately, and sorting/filtering precedes paging with honest totals. Reopening the same store retains the run envelope and values. The huge storage identifier reaches a deliberate binding refusal rather than a SQL overflow.

## Stage 3: implement calculation views, simulations and ingestion

Complete the remaining operation families from the registry:

- Eligibility, progress, forecast, monthly alerts, triggers, performance, one-zero matrix, one-zero overview and employee detail.
- One-zero employee review; designations; reconciliation and QC; retroactive scan; proximity.
- Portfolio simulation plus unit, employee and one-zero simulation POSTs.
- Ingestion summary, exception resolution and rows.

Compose existing `Proximity`, `ForecastProjection`, simulation, performance, reconciliation, trigger, canonical/QC and rule-library entry points rather than duplicating their arithmetic. Finish the full trend query assembly even though the base-year/rebase HTTP routes are elsewhere. Keep selected year/program, fiscal convention, source tenant, state filtering and rule provenance attached throughout.

For ingestion resolution use the existing persistence lookup/finding boundaries and certified `QcResolutions` behavior; trace the distinction between an ingestion exception annotation and Claims' finding-resolution lifecycle. The sibling Claims session owns the remaining `application\qc_resolutions.py` application integration; consume existing W1/Domain contracts here and describe any still-missing shared binding instead of introducing a conflicting private global store.

Cases to include are `p1_query_edges:eligibility.status-both`, `eligibility.near-floor`, repeated scalar and empty-limit cases, and `p1_reads:get-api-progress-tax-year.query-within-negative`. Exercise simulation zero/negative/invalid magnitudes and the host's existing operational bound. Use `test_api_employee_drill.py`, `test_api_onezero_matrix.py`, `test_rest_of_year.py`, `test_simulate_unit.py`, `test_ingestion.py`, `test_forecast.py` and the route-specific recordings for deferred application behavior.

Checkable result: every owned method/template has a real handler, recorded 4xx cases reach the correct error family, and successful calculations agree in all values with their recordings. Review/resolution changes can be observed through their intended reads without secretly changing the certified run pipeline.

## Stage 4: prove ordinary-host behavior and document the handoff

Run focused tests for the new features through real seed-backed composition, then replay complete scenarios needed by this group's cases. `replay_board.py --group` selects display, not which scenario exchanges execute. `p1_artifacts_ai` also bootstraps employee/finding captures, and P2 scenarios include other groups' writes; distinguish a setup dependency from an owned-handler mismatch.

Use fresh absolute replay output paths and the existing profile reset/auth setup. Keep independent Worker pollers out of the replay world: the existing work gate is process-local. Confirm a second scenario reset removes feature state and that normal API startup, not only a test assembly, discovers the new handlers.

Write `dotnet\docs\ROUTES-READS-REPORT.md` with the 29-operation mapping, completed application modules, entry points for sibling consumers, recorded case results, unresolved shared seams and source/fiscal limitations. Separate raw replay observations from registered differences and from failures caused by unavailable sibling handlers. W1b's framework readiness mismatch is existing evidence, not work to repair from this folder.

Checkable result: a reader can trace each implemented route and deferred-module completion to a C# symbol, a recorded case or Python test, and fresh ordinary-host evidence.

## Traps to expect

- `CONTRACT-REPORT` sections 4-5 describe several wire families. Reuse transport DTOs, scale-preserving money conversion and existing 422/error helpers. `PyDict` is canonical Domain data, not a direct HTTP serializer. Mixed date representations and present-null fields remain field-specific.
- F-3 is a storage-ID range failure, not the draft paging problem: W1b deliberately permits arbitrarily large nonnegative draft offsets while `ClientIdentity.Parse` refuses invalid Int64 identities. Do not introduce a global integer clamp.
- The source adapters' strict leap-window bridge is explicitly partial for 2024-02-29 through 2025-02-28 shifted to begins TY2025 or ends TY2024. Verify the reached boundary first; do not claim strict fiscal parity or repair Domain from this route slice.
- `findings.md` M-01, FS-01/FS-11, CQ-02/CQ-05 and CAP-10 matter here: ingestion precedence, state/current versus prior filtering, calendar one-zero snapshots, pay-date year trimming, first-row collapse and the distinction between QC read drops and the certified writer's path.
- Gold `unreachable_months` contains zero-based positions (GP-03); missing average rows differ from present rows with null fields (GP-07). The stored seed's TY2025 population is not the public TY2023 certification.
- Source count/max-modified observations are neither Delta snapshots nor proof that count/max-preserving edits are detected. Live Warehouse metadata, native monetary AVG, source freshness and private-reference certification remain unverified.

## Evidence this plan is based on

- `dotnet\docs\DOMAIN-SLICE-REPORT.md`: certified numerical/payload entry points; portfolio/discovery and full trend/application work deferred.
- `dotnet\docs\port-map.md` and `dotnet\docs\findings.md`: module/test inventory and the M-01, GP, FS, CQ and CAP boundaries above.
- `dotnet\docs\PERSISTENCE-REPORT.md`: 25 real Gold-read members, exact stored values, tenant binding and transactional runner; no engine on ordinary Gold reads.
- `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`: source ports, strict leap-shift limitation, unknown versus empty clients and unchanged zero-worksite discrepancy.
- `dotnet\docs\COMPOSITION-REPORT.md` and `dotnet\docs\HOST-ARCHITECTURE.md`: pre-build feature registration, real P1/P2 reset, shared runtime and remaining 501 business handlers.
- `dotnet\docs\route-groups.json`: 29 ReadsCalc operations; portfolio HTTP belongs to claims, run/latest/base-year/rebase HTTP belongs to drafts.
- `contract\CONTRACT-REPORT.md`, `contract\FINDINGS.md`, `contract\COVERAGE.md` and the named P1/P2 recordings: wire families, binding edges and concrete route/case evidence.
- `parity\export_gold_payload.py` and `parity\goldens`: existing certified payload evidence to rely on, not a new domain-port assignment.
