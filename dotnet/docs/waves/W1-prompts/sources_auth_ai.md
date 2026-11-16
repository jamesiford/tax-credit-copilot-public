# Payroll sources, Entra auth, rate limits, AI providers, telemetry, blob artifacts

Session `sources_auth_ai` of wave `W1`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-w1-sources` (branch `dotnet/w1-sources_auth_ai`, created from `dotnet/integration`).

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

Build payroll/source/fiscal adapters, API Entra trust/authorization, rate limits, AI providers/safety/resilience/telemetry and local/blob artifact bytes. Use owned `dotnet/src/TaxCredit.Infrastructure.Sources/`, `TaxCredit.Infrastructure.Auth/`, `TaxCredit.Infrastructure.Ai/`, their matching tests and Application `Ports/Sources/`, `Ports/Auth/`, `Ports/Ai/`.

Bridge existing Domain `Pipeline.IPayrollSource`/`IFiscalRuleSource`, pure `FiscalSource` and program-wage seams to the richer `backend/application/source_ports.py` surface. Do not strand the certified pipeline behind duplicate interfaces. Existing Infrastructure Payroll/Rules adapters are reuse/reference candidates, not files to move/edit.

Persistence owns lookup storage, artifact metadata/audit, Gold and queues; you own source resolution and bytes. Skeleton owns middleware/hooks/wiring; W2 owns endpoints/handlers/prompt agents. Provide services/registration, not routes. Gateway/orchestrator trust belongs to later waves, not alternative API claims.

## Preflight

Read `dotnet/docs/DOMAIN-SLICE-REPORT.md`, `dotnet/docs/slice-domain-log.md` DS7, IN and CAP, `dotnet/docs/port-map.md`, `dotnet/docs/findings.md`, `dotnet/docs/PLATFORM-RISKS.md`, `contract/CONTRACT-REPORT.md` sections 3-5 and 8, `contract/docs/AUTH-CONTRACT.md`, `contract/docs/normalisation.md` and `contract/FINDINGS.md`.

Inspect prepared references, Domain pipeline/fiscal/program interfaces and `Infrastructure/Payroll/CsvPayrollSource.cs`. Read Python source binding/ports, `data/source/from_fabric.py`, `sql_scan.py`, `to_bcs.py`, mapping, payroll fiscal I/O, `api/auth.py`, `application/identity.py` and AI service/safety modules. Inventory Application behavior too, placing its adapter contracts within owned folders.

Establish worktree-local CPython 3.12 imports and isolated fake transports. W0 approval does not transfer: its guarded token `SELECT 1` proves no source metadata/parity, throughput, sync lag or version choice. This task has no live-service experiment.

Settle fiscal projection, trust and egress before provider plumbing. Domain's capstone used CSV/calendar windows and supplied fiscal helper rules, not SQL/fallback/overrides/strict I/O.

## Stage S1: source and fiscal contracts without another engine

Implement all source-port capabilities: fixture ID, client/portfolio payroll, provenance-bearing fiscal windows, configuration/book/footprint, scope aggregates and shared scope. Preserve unconfigured/unknown/empty/unavailable distinctions, never outage-as-empty payroll.

Reuse the certified parser/typed conversion for `backend/data/payroll_pay_periods.csv` (9,477 rows) and `parity/goldens/canonical.jsonl.gz` cases. Another account gets none of the fixture tenant's rows. Reuse through an owned-project reference/bridge without moving code or creating cycles; do not duplicate the CSV state machine.

Port SQL reads/mapping/projection from `sql_scan.py`/`to_bcs.py` and Python persistence source aggregates into Sources. Keep Warehouse/source endpoints and pools separate. Test mapped quoted identifiers, explicit columns, parameterized tenant/key filters, bounded ID batches, streaming/row limits and config/tenant cache isolation. CSV mode must not open unused SQL connections.

Provide a `Microsoft.Data.SqlClient` analytics connection factory with injected Entra token acquisition for `https://database.windows.net/.default`; test authentication configuration, scope/refresh and cancellation without acquiring a live token. Reconcile shared driver/credential package versions at integration.

Represent local lakehouse tests with P2 `contract/seed/P2/source/*.jsonl.gz` and a fake/SQLite analytics endpoint. Python may read offline Delta as oracle evidence; .NET materialized fixtures are not runtime Delta readers. Preserve source schema/missing-table metadata and label the substitution.

Fiscal I/O order: SQL rules; opt-in bounded fixture fallback on classified failure; overrides if source rules are absent/unreadable, client before global. Source wins. Unreadable and empty have distinct diagnostics; strict missing-rule errors propagate, assume returns flagged calendar provenance through the pure resolver. Bugs do not trigger outage fallback.

Inject a narrow lookup reader, test with an in-memory double, and document its Persistence bridge. SQL-served logical lakehouse sets `HoldsClientRules=true`; CSV remains false. Requested fallback without a configured local provider is explicit unavailability, not runtime Delta installation or successful emptiness.

Port `test_app_owned_lookups.py` fiscal cases: source-before-override, client-before-global, flagged missing rules and `test_strict_fiscal_policy_blocks_instead_of_assuming`/`test_a_typed_dependency_failure_is_not_swallowed_by_the_window_resolver`. Add SQL failure/fallback off/on, malformed rules, two clients, both conventions and leap-day shifts using `FiscalSource.WindowFromRule`.

Resolve code/category and client/global pay codes with seed provenance/strictness. Test customer-classified settings using synthetic rows: seeds are not authored mappings. Count/flag unmapped/defaulted codes and imputed/excluded dates. The certified engine, not source projection, trims fiscal windows, filters short periods and collapses rows.

Checkable result: source port coverage is explicit, CSV and materialized P2 rows feed the certified pipeline, fiscal provenance and strict failures survive the bridge, and source outages/tenant mistakes cannot silently change the input.

## Stage S2: settle projection parity and the version stand-in

Port focused scenarios from `backend/tests/test_source_mapping.py`, `test_sql_read_path.py`, `test_source_sql_scope.py`, `test_source_multiyear.py`, `test_source_synthetic.py`, `test_source_schema_blank_and_probe.py` and the source fallback tests. The brief's broad `test_data_source*` pattern does not describe the full behavior. Use small source-shaped cases in fast tests and the committed materialized P2 data for volume coverage.

Cover renamed/cased/unsafe mapping, required versus optional schema, coercible/junk/null numbers, PayDate impute/exclude, dangling IDs, WorksiteLocation/Location, state prefixes and span-derived frequency. Emit Domain-supported IDs/dates; report FZ-04 non-finite payroll limits without changing Numerics. Real Fabric type metadata remains unmeasured.

Port `test_sql_read_path.py` projected-row and certified-method equivalence, parameter/streaming limits and `test_a_tenant_read_is_one_projected_filtered_statement_and_never_select_star`. Preserve deterministic fixture order and exercise order sensitivity: live SQL without ordering has no such guarantee.

No platform version recommendation exists. Expose an account count/maximum-modified-date fingerprint with mapped metadata/deterministic encoding, provenance and explicit missing/null behavior. Test empty/repeated reads, changed count/date and other-client changes. Supply it for later run recording without editing manifests/handlers or calling it a Delta ID.

Document undetected count/max-preserving updates, endpoint lag and non-atomic observations. The spike did not verify Silver markers or OneLake/REST alternatives.

Implement deferred `IProgramWageSource` from `tools/payroll.py`/`program_credit.py` and configured committed payroll. M-19 records NY_EXCELSIOR wage 101,528.17/per-job 6,599; test its RuleLibrary result without reimplementing credit math.

Checkable result: fake SQL and materialized source projections agree on recorded rows/controls and selected certified results, aggregates match row projections, and a deterministic, clearly limited version marker is available to later run recording.

## Stage S3: API token trust and authorization as services

Build injectable JWKS/signing-key validation and configured production retrieval with ephemeral RSA tests. Follow AUTH-CONTRACT API names/shapes/order; separate validation, extraction, selections and writer policy for host composition without web references in Application.

Test RS256/signature, algorithm refusal, v2 issuer, both audiences, required `exp/iat/iss/aud`, 60-second expiry/not-before edges, malformed claims/tenant, rotation and bounded refresh failure. Preserve `oid/roles/scp` names. Key/credential outages are typed failures, not anonymous success.

Delegated: `user_impersonation`/`TCC.User`, no Agent role. App-only: documented shape/`TCC.Agent`, no scope/User role. Agent caller `oid` selects client permissions; bound acting-user `oid` attributes writes. App IDs/display names are not substitutes.

Validate `X-TCC-Acting-User`: base64url object, bounds, GUIDs/tenant, allowed channel/assurance and optional context. Users cannot promote header identity. Agent header validation precedes forbidden commands: `p1_auth:agent.forbidden-checked-before-header` versus `agent.forbidden-assess` gives 400 versus 403.

Use fake allow-list/group providers. Normalize path/query/body IDs, ID lists and nested scope for host authorization. Batch/artifact existence precedes visibility (`p1_auth:client-authz.unknown-batch-is-404`); document the Persistence lookup order, not repository code.

Port `test_writer_sources.py`: failed sources deny/log, another successful independent source can grant, failed groups are not cached and truthy non-bools are controlled. Preserve actor/acting-user equality. Expose writer/agent-forbidden metadata including F-14 gaps for handlers, not route guards.

F-14-F-16 need case-specific policy handoff: expose consistent writer support without silently changing protected valid-request outcomes. Give W2 affected cases/review items. F-15 read denial cannot be solved by agent author impersonation.

Port `test_auth.py`, `test_auth_default.py`, `test_agent_principal.py`, writer/visibility cases using direct services and `contract/harness/auth.py` mint templates. Gateway scopes/audiences/`X-Acting-*` are not accepted API alternatives.

Checkable result: an ephemeral-token matrix demonstrates authentication versus authorization distinctions, acting-user validation order, fail-closed writer checks and normalized client selection; the report gives the skeleton exact service/error contracts and later route-policy obligations.

## Stage S4: per-caller rate limits

Port API/p1_auth token buckets with monotonic clock, `(kind, caller oid)` key, signed-in callers only, continuous refill and `floor((1-tokens)/rate)+1` retry. Expose code/reason/remedy/seconds; host writes the header.

Test depletion/refill edges, identities, concurrency/reset and abandoned-bucket lifecycle. Validate settings and expose host reset; G1L's 6/minute gateway limit is not the API default.

Checkable result: deterministic concurrent calls cannot overspend a bucket, retry values match recorded arithmetic, and the host can map refusals into the documented structured 429.

## Stage S5: AI contracts, guards and provider runtimes

Define owned contracts from Python domain/application/infrastructure AI: roles/readiness, requests/events/usage/hops, errors/token access/telemetry. AI models were deferred; place contracts in owned Application ports, not Domain. Inject definitions without W2 prompt agents/roster/publishing.

Run egress/injection guards before providers. Use `backend/tests/ai_evals/datasets/injection.jsonl`, `test_ai_egress.py`/`test_ai_safety_injection.py`: identifiers always refused; aggregates-only excludes external row briefs; block excludes external providers; trail hashes are not IDs. Emit rule codes, not text. Prevent forged fences/`JSON:` replacing trusted figures.

Implement role/readiness chains/hops and fake-tested gateway/Foundry seams. OpenAI v1 model is in body, Azure deployment in URL. Stream deltas/usage/tool chunks without executing tools. API-key/OAuth/Entra auth needs audience checks, cache/expiry/coalesced refresh, 401 invalidation and auth-header precedence.

Use `test_ai_gateway.py` for dialect/auth/errors, tools and Retry-After seconds/date. Fake clients prove the wire. Upstream bodies/prompts/headers/secrets never reach errors/reprs.

Resilience order: bulkhead/breaker/retry/event-gap timeout. Port `test_ai_resilience.py`/`test_ai_chain.py`: transient-before-output retries, provider delays within deadline, no client/policy retries, one half-open probe, no shedding health penalty, one breaker failure per request. After text, no provider switch/restart. Record/propagate cancellation.

Port `test_ai_budget.py`: concurrent-safe user/overall UTC-day budgets, 4-char/token estimates versus reported usage, rollover/no-limit, pre-call refusal and error/cancellation/retry accounting without double charges.

Port scripted degradation from `test_ai_degraded.py`/`test_ai_fallthrough.py`: unchanged trusted figures, once/request unavailability, partial-output marker, caller fallback and explicit truncation. This is not agent/calculation code; gateway numeric-guard integration follows later.

Use existing OpenTelemetry with injected collectors and `test_ai_telemetry.py` provider/role/outcome/hops/timing/usage/degraded/cancel fields, no prompts/sensitive dimensions. Exporters remain skeleton-owned. Return events W2 can frame like `contract/recordings/p1_artifacts_ai.jsonl`, not SSE endpoints.

Checkable result: guards demonstrably block provider calls, fake-wire tests cover dialect/auth/streaming behavior, chain/resilience/budget tests settle failure and cancellation semantics, and scripted fallback preserves trusted figures with safe telemetry.

## Stage S6: artifact bytes and integration evidence

Port byte-store halves of `local_store.py`/`blob_store.py` and `backend/tests/contracts/test_contract_artifacts.py`. Place contract in owned `Ports/Ai/Artifacts/`, adapter/tests in Ai/Artifacts and its test project; there is no owned Storage project.

Local writes are atomically create-only, even concurrently. Test duplicate preservation, empty/binary bytes, absent/nested paths and traversal/absolute/drive/UNC/backslash escapes. Expose honest local durability/deployed refusal. Fake Blob tests cover create-only/content type/credentials; only not-found is absence, auth/network errors propagate.

F-5 (`p1_artifacts_ai:package.create-again`) needs a typed duplicate conflict for W2, not blob overwrite. Persistence owns metadata/prefix/access checks. E-6 container portability does not permit changed stored bytes/hashes/member content.

Write `dotnet/docs/SOURCES-AUTH-AI-REPORT.md`: ports/registration, source/fiscal/lookup/fingerprint behavior, fake versus fixture evidence, auth/policy handoff, limiter arithmetic/reset, AI wire/resilience/budget/cancel tests, bytes/telemetry and live metadata/model/blob/JWKS limits.

Document host clocks/keys/extraction, lookup bridge, source/bucket/budget/provider/byte reset and error mapping; hooks stay skeleton-owned. Report package versions/ownership overlaps for integration reconciliation.

## Traps to expect

- `contract/CONTRACT-REPORT.md` sections 4-5: status and error-shape family must be available to the host; validation text that names a Python exception is not the JWT algorithm. A bare framework challenge or ProblemDetails is not this adapter's application error contract.
- `dotnet/docs/findings.md` T-18, CQ-02/CQ-05/CQ-13 and CAP-05: null versus absent, PayDate versus Tax_Year, collapse ordering and CSV parser details affect input. Source projection must not repeat certified filtering or fiscal arithmetic.
- M-01/M-19: existing ingestion behavior is already in RuleLibrary, while percentage-of-wages payroll access still needs an adapter. Preserve the existing numeric paths rather than replacing them.
- `contract/FINDINGS.md` F-14-F-16: writer enforcement, agent read denial and acting-user precedence require an explicit host/route handoff, not an adapter that quietly grants more access.
- `contract/docs/normalisation.md`: the replay freezes time, UUIDs, limiter clocks and background work at their sources. Avoid static process-global state that prevents reset or leaks a prior scenario.
- `PLATFORM-RISKS.md`: token connectivity is not proof of pooling, endpoint freshness, read metadata or Delta-version equivalence. Materialized P2 tables are offline fixtures only.
- `dotnet/docs/findings.md` V-01: an existing package pin may embody a licensing decision; selecting the newest package is not a substitute for checking the actual dependency/license surface.

## Evidence this plan is based on

- `C:\Projects\tcc-conductor-runtime\reports\W0.md`: both earlier sessions passed their listed checks; the detailed reports bound what their results establish.
- `dotnet/docs/DOMAIN-SLICE-REPORT.md`, `slice-domain-log.md` CAP/DS7/IN and `port-map.md`: certified source/fiscal/domain seams already exist; SQL fiscal I/O, strict policy, AI models and the program-wage adapter were deferred.
- `dotnet/docs/PLATFORM-RISKS.md` and `platform-risks-log.md`: only Warehouse token connectivity and scratch cleanup were proven; no source read, version-marker or direct-Delta design was validated.
- `dotnet/docs/findings.md` M-01/M-19, CQ-02/CQ-13, CAP-05 and FZ-04: numeric paths, CSV limits, assumed windows and unsupported non-finite payroll shapes constrain adapter work.
- `contract/docs/AUTH-CONTRACT.md` and `contract/recordings/p1_auth.jsonl`: claim names/shapes, acting-header validation order, client existence/visibility distinction and token-bucket retry arithmetic.
- `contract/CONTRACT-REPORT.md` sections 3-5 and 8 and `contract/FINDINGS.md` F-5/F-14-F-16/E-6: HTTP framing is later work, duplicate package paths are immutable-store conflicts, authorization oddities need case-specific handoff, and container bytes are not portable.
- `contract/seed/README.md` and `contract/seed/P2/manifest.json`: P2 contains materialized logical source tables, 197,094 Payroll rows and four fiscal rules, usable without a .NET Delta runtime.
- `contract/docs/normalisation.md`, `contract/harness/auth.py` and `contract/harness/control.py`: ephemeral token minting and source-level determinism/reset semantics are the host-facing test basis.
- `contract/docs/replay-spawn-312.md`, `replay-inprocess-312.md` and `replay-spawn-314-crosscheck.md`: the Python reference passes all 1,769 exchanges; the 3.14 cross-check does not change the 3.12 oracle.
- `contract/docs/ORCHESTRATOR-SPEC.md`: model-dependent output is specified using fake models, not recorded as deterministic truth; hosted-agent execution is outside W1.

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
- report required: `dotnet/docs/SOURCES-AUTH-AI-REPORT.md`

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-w1-sources`** (branch `dotnet/w1-sources_auth_ai`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/src/TaxCredit.Infrastructure.Sources/**`, `dotnet/src/TaxCredit.Infrastructure.Auth/**`, `dotnet/src/TaxCredit.Infrastructure.Ai/**`, `dotnet/tests/TaxCredit.Infrastructure.Sources.Tests/**`, `dotnet/tests/TaxCredit.Infrastructure.Auth.Tests/**`, `dotnet/tests/TaxCredit.Infrastructure.Ai.Tests/**`, `dotnet/src/TaxCredit.Application/Ports/Sources/**`, `dotnet/src/TaxCredit.Application/Ports/Auth/**`, `dotnet/src/TaxCredit.Application/Ports/Ai/**`, `dotnet/Directory.Packages.props`. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/sources_auth_ai.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/sources_auth_ai-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-sources_auth_ai.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/sources_auth_ai.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "sources_auth_ai",
  "branch": "dotnet/w1-sources_auth_ai",
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
