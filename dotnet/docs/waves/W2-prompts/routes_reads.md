# Read and calculation routes (certified-figure path)

Session `routes_reads` of wave `W2`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-w2-reads` (branch `dotnet/w2-routes_reads`, created from `dotnet/integration`).

---

## Pre-approved decisions (policy)

The owner decided these in advance. Follow them without asking. If something needs a decision that is not covered here, choose the reading closest to the documented design and the Python behaviour, record it in STATUS.json under `needs_human`, and continue.

- **parity**: Equivalent behaviour, not bug-for-bug. The target is the designed functionality and the contract a client depends on: the same routes and methods, authentication and authorisation, request and response fields and their types, the meaning of each status code, money as a decimal string with its scale, and the same calculated figures for the same valid input. Do not reproduce defects, accidents of Python, FastAPI or Pydantic, or artefacts of the recording harness (plain-text error bodies, key order, number lexemes such as 5.0 versus 5, byte-level headers and wording, HEAD and trailing-slash quirks, reflected CORS headers). Never write code whose only purpose is to reproduce a defect or a framework artefact. Where the Python behaviour is a bug or an accident, implement what the design, the ADRs, the docs or sound engineering intend, and record it in dotnet/docs/improvements/<session>.json (see improvements_register). If the same issue turns up naturally in the .NET code, that is acceptable; note it as a finding.
- **parity_tiers**: The replay runs in semantic mode (values equal; key order and number lexeme free). Tier A (certified-figure routes and every gateway tool result): the values must be equal, and a changed figure is never an improvement. Tier B (everything else with a JSON body): values equal. Tier C (error responses): keep the error shape family (a JSON body with `detail`, as the clients read it) and the right status; the message text is free. Tier D (zip and xlsx container bytes, timing, model output): out of scope. Anything else that differs from a recording for a good reason goes in the improvements register, not into reproduction code.
- **python_oddities**: Fix defects instead of reproducing them. F-2 to F-6 (plain-text 500s): return the JSON error family with the correct status, a 4xx where the cause is a client error, and never a stack trace. F-8 (duplicate claims): handle duplicates as the claims design intends (idempotent or a 409), and record which. F-14 to F-16 (inconsistent writer checks): apply the writer check consistently to every route that writes. F-1 (a GET that never returns because magnitude is unbounded): bound it and refuse out-of-range values with a 422. F-17 and every other entry in contract/FINDINGS.md: apply the same principle; read the finding first. Exception: if fixing something would change a calculated figure, a stored value or an authorisation outcome for a valid request, keep the Python result, and list it under needs_human as a fix candidate for the owner.
- **oracle**: CPython 3.12 is the only oracle interpreter. The recordings, goldens and seeds were made on it.
- **target**: net10.0 only. Do not use .NET 11 features or preview packages unless a decision below names them.
- **delta_read**: No Delta library at runtime. Payroll is read over the lakehouse SQL analytics endpoint behind an IPayrollSource port. For the data-version stand-in use the design recommended in dotnet/docs/PLATFORM-RISKS.md if that file exists; otherwise use a per-account fingerprint of row count plus the maximum modified date, record it with each run, and list the limitation.
- **warehouse_writes**: Use multi-row parameterised INSERT batches (the Python adapter's method) unless dotnet/docs/PLATFORM-RISKS.md proves a faster supported bulk path on Fabric Warehouse. Retry on SQL errors 24556, 3960 and 1205. Never use EF Core migrations against Fabric Warehouse.
- **mediator**: Use the in-house mediator (ADR 0003). No MediatR, and no libraries with commercial licences. Check a package's licence before adding it and record it in the session log.
- **scope_cuts**: Out of scope: the 10 sealed /api/workspace routes (answer exactly what the recordings show when the reference extract is absent), tools/reference_*, web retrieval inside tools/rules_ingestion beyond its HTTP surface, the mock AI gateway, and the ops scripts (migrations, grants, seeding, smoke checks), which stay in Python for now.
- **external_systems**: Never contact live Fabric, Foundry, Entra or any customer system unless the session's task names it and its approval variable is set. The hermetic seeds under contract/seed are the data source for development and replay.
- **numeric_guard**: Agents narrate and tools calculate (ADR-008). The numeric guard ports as is, with the same refusals.
- **heavy_tests**: Tag every test that runs longer than about 20 seconds or loads more than 20 MB as [Trait("Category", "heavy")]. A session's own gate is build, format, fast tests and its replay groups; heavy suites run at wave end and at the final gate.
- **route_ownership**: Each route group lives in its own folders: src/TaxCredit.Application/Features/<Group>/ and src/TaxCredit.Api/Endpoints/<Group>/ plus tests under tests/TaxCredit.Api.Tests/<Group>/. A group registers itself through an endpoint-group class discovered by the host; no shared file is edited to add or retire a route.
- **schema_messages**: Pack and draft validation (domain slice, finding on JsonSchema.Net): verdicts, keywords and paths must be correct; the English wording of messages is free. Record any case where a verdict differs from Python's jsonschema in dotnet/docs/pack-validation-deviations.md, with the reason.
- **ingestion_override**: Captured ingestion overrides a year-resolved pack's wage_basis, measuring_date and pay codes (domain finding M-01). This changes calculated figures, so keep it as ported and list it under needs_human as a fix candidate for the owner. Read the finding and the ADRs first: if the design clearly says otherwise, say so in the report, but still do not change it without the owner's decision.
- **multi_program_credit_math**: In credit_math a state with several programs prices its first program, as Python does; the typed refusals live in the run-resolution code (_client_run, program_defaults), which is ported. Do not add a refusal to credit_math. List this under needs_human as a fix candidate for the owner, since it affects figures.
- **improvements_register**: Each deliberate difference from the recorded Python behaviour is an entry in dotnet/docs/improvements/<your session>.json: {"improvements": [{"id": "IMP-<session>-1", "kind": one of defect_fix, error_text, wire_incidental, framework_default, "route": "METHOD /path/template", "case": optional text matching a recorded case id, "categories": optional list of replay categories, "path_prefix": optional JSON path, "finding": "F-n or empty", "reason": what was wrong and what the .NET host does instead (at least 20 characters)}]}. The replay gate treats failures covered by an entry as waived and shows them on the board and in the wave report for the owner to review; a changed number is never waived, and a group that relies on the register for more than the policy limit of its cases fails.
- **domain_slice**: The domain slice is certified (dotnet/docs/DOMAIN-SLICE-REPORT.md): build the application layer on top of it and do not re-port or re-verify its modules. Anything marked partial or pending in dotnet/docs/port-map.md and needed by your routes is yours to finish.

---

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

---

## Gates (checked by the conductor after you finish, mechanically)

- `no_halt`: no HALT.md in the worktree
- `commits_present`: at least one commit on your branch
- `clean_tree`: everything committed
- `not_pushed`: the branch is not on any remote
- `owned_paths`: every changed file is inside your owned paths
- `status_json`: the STATUS.json finish file exists and parses
- `report_present`: the report files named below exist
- `dotnet_build`: `dotnet build -warnaserror` passes on the whole solution
- `dotnet_format`: `dotnet format --verify-no-changes` passes
- `tests_fast`: all tests not tagged `heavy` pass
- `replay`: the contract replay (semantic mode) meets the thresholds for your route groups; failures covered by your improvements register entries are shown separately and are capped
- report required: `dotnet/docs/ROUTES-READS-REPORT.md`
- replay thresholds: reads_calc >= 100%

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-w2-reads`** (branch `dotnet/w2-routes_reads`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/src/TaxCredit.Application/Features/ReadsCalc/**`, `dotnet/src/TaxCredit.Api/Endpoints/ReadsCalc/**`, `dotnet/tests/TaxCredit.Api.Tests/ReadsCalc/**`, `dotnet/docs/**`. The last entry, `dotnet/docs/**`, is always yours for reports, logs, status files and the improvements register; it never needs an exception. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/routes_reads.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/routes_reads-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-routes_reads.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/routes_reads.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "routes_reads",
  "branch": "dotnet/w2-routes_reads",
  "head": "<short commit>",
  "summary": "<at most ten lines: what was built, what the gates say, what surprised you>",
  "stages": {"<stage id>": "done | partial | skipped"},
  "gates_claimed": {"<gate>": true},
  "deviations": [{"id": "DEV-1", "what": "...", "why": "...", "decision_needed": false}],
  "findings": ["Python behaviour that looks wrong, or traps found"],
  "open_questions": ["..."],
  "needs_human": [{"item": "...", "why": "..."}],
  "reports": ["relative path of each report you wrote"]
}
```

Then print a short summary. The conductor reads your reports and `STATUS.json` to plan the next wave, so write them for a reader who has not seen your session: numbers, evidence, exact error messages, and what the next session can now rely on.
