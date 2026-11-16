## Your role

Make the ordinary API executable and Worker use the real W1 adapters; adding a route group must require changes only in that group's folders. A separately composed test host is not the deliverable: the conductor-launched executable must use those registrations.

Integration contains the certified Domain, W1 adapter libraries, skeleton API and minimal Worker Main. Archived W2 features/executor are diagnostic evidence, not installed dependencies. Implement shared prerequisites in the owned host, Application Hosting/Ports and persistence surfaces. Business handlers, gateway/orchestrator and live-service experiments remain outside this task.

## Preflight

Read `dotnet\docs\HOST-ARCHITECTURE.md`, `PERSISTENCE-REPORT.md`, `SOURCES-AUTH-AI-REPORT.md`, `DOMAIN-SLICE-REPORT.md`, `PLATFORM-RISKS.md`, `findings.md`, `integrate-W1-log.md` and `waves\W1.md`. Read `contract\CONTRACT-REPORT.md` sections 4-5, `contract\FINDINGS.md`, `contract\docs\AUTH-CONTRACT.md`, `contract\docs\normalisation.md`, `contract\harness\control.py`, `freeze.py`, `auth.py`, and the seed manifests. Resolve report-relative paths within the current worktree.

Inspect these precise startup seams before changing them:

- `dotnet\src\TaxCredit.Api\Program.cs`, `Hosting\HostComposition.cs`, `HostMiddleware.cs`, `SkeletonAccess.cs`, `SkeletonHostStatus.cs`, `RuntimeConfiguration.cs`, `RuntimeSources.cs`, `ContractTokenMinter.cs`, and `Endpoints\Contract\ContractEndpoints.cs`.
- `Endpoints\EndpointRegistration.cs` and `IEndpointGroup.cs`; `TaxCredit.Application` registration and mediator discovery; `Application\Ports\Contract`; the persistence registration and operational repositories; the concrete W1 adapter registration extensions.
- `dotnet\src\TaxCredit.Worker\Program.cs` and its project references, plus the architecture assertions that constrain Application, Domain and host dependencies.

Use read-only `git show` for `dotnet\docs\ROUTES-DRAFTS-RUNS-REPORT.md` and `HALT-routes_drafts_runs.md` on `archive/w2-attempt1-routes_drafts_runs`, `ROUTES-CLAIMS-REPORT.md` on `archive/w2-attempt1-routes_claims`, and `ROUTES-AI-REPORT.md` on `archive/w2-attempt1-routes_ai_agents`; do not merge them. The reads archive is preparation commit `bf5d638`, with no reads implementation/report.

Establish the integrated baseline: the integration log records 781 non-heavy tests across eight assemblies. Select SDK 10.0.404 from `dotnet`; root invocation previously selected SDK 11. Preserve persistent CPython 3.12 testhost configuration and explicit-setting precedence.

**Result:** inventory adapters/collaborators/lifetimes, skeleton registrations and existing queue components. Choose shared composition usable by API/Worker without inter-host references: owned ServiceDefaults can carry outward wiring; Application Hosting/Ports carry inward contracts/orchestration, not storage SDKs. Source/Auth/AI implementations and Domain remain read-only dependencies.

## Stage C1: settle pre-build feature registration and the shared runtime boundary

Introduce discovered `IFeatureModule.ConfigureServices(IServiceCollection, IConfiguration)` or a documented equivalent. Preserve `IEndpointGroup.Map(IEndpointRouteBuilder)`. Discover deterministically from intended assemblies; invoke service modules once before `Build`, then map real groups before filling unclaimed operations with 501s.

Startup order: settings/adapters, feature services, provider construction, middleware, real groups, remaining stubs. No temporary provider or DI mutation during endpoint mapping. Features depend on Application ports; host composition names concrete adapters.

Add a test-only feature in `TaxCredit.Api.Tests`: its callback registers a service its endpoint consumes. Include that assembly through the documented discovery mechanism in production startup. Prove service resolution, exact stub replacement and unrelated-stub preservation, without manually registering the test feature/service.

**Result:** a feature folder suffices without edits to Program, HostComposition or a central list. Define the shared executor seam for contract drain and Worker now; draft/batch HTTP orchestration remains deferred.

## Stage C2: reproduce and repair the persistence blockers

Repair `dotnet\src\TaxCredit.Infrastructure.Persistence\Operational\RunBatchRows.cs`, `BatchValues`: nonempty `TaxYears` passes unsupported `long[]` to `PyJson`. Use `batch.TaxYears.Select(y => (object?)y).ToList()`, preserving years/order and the empty representation. Test real round-trip/reopen with selected years. The archived create expected 202 but returned JSON 500; do not discard years to evade it.

`Operational\ManualOverrideRepository.cs` orders by `created_at, override_id`; `BaseYears` folds history, so clearing can lose to an earlier choice at the same timestamp. Repair this and directly coupled selectors with a persisted, transactionally allocated monotonic tie-breaker. Random GUIDs, process counters, SQLite-only rowid, inflated timestamps and unprotected MAX+1 do not solve cross-provider ordering.

Test save -> changed save -> clear -> later save at identical timestamps, reverse-ordered IDs, reopen, tenant isolation and independent connections. Preserve timestamps/public IDs; cover real SQLite and hermetic native-provider SQL/bindings. Document necessary deployed schema provisioning separately from verified local upgrades; operator scripts remain outside ownership.

Inspect `TaxCredit.Api\Wire\RequestValidator.cs` and draft paging: blanket Int64 checks reject BigInteger offsets before dispatch. Separate storage-ID bounds from paging semantics; huge valid draft offsets should yield an honest total/empty page without overflow/allocation. Retain 422 for invalid storage IDs and constrained years/limits. Test Int64 maximum, larger/malformed/negative offsets, huge client ID and ordinary unknown client through handler-independent API probes, not new business handlers.

**Result:** real queue rows retain nonempty years, latest choices follow durable write order at DATETIME2(3) precision, and HTTP validation no longer imposes storage-ID limits on unrelated integer parameters.

## Stage C3: compose the real adapter graph in both executables

Replace skeleton registration with shared configuration-driven composition. Document actual setting names, precedence, defaults and requirements; reuse existing vocabulary.

1. Persistence: call `AddPersistence(database, repositoryRoot, seedRoot, ...)` once for real Gold/operational/queue/seed ports and transactional `IClientCalculationRunner`. Default local/replay to SQLite; explicitly select SQL Server/Fabric Warehouse native adapters by configuration, without fallback to SQLite. Separate local schema initialization from deployed provisioning.
2. Rules/payroll: use `AddRuleLibrary` and existing adapters against configured `backend\rules`, not copies. Compose `AddTaxCreditCsvSources`, `AddTaxCreditSqlSources`, `AddTaxCreditProgramWages`, mapping, analytics transport, lookups, fiscal rules and fingerprints. Bridge persistence lookup/seed ports to source interfaces as needed. Avoid wage-enabled RuleLibrary/state-resolver cycles.
3. Replay sources: loading Gold does not switch payroll/catalogue/fiscal readers. Compose P2's staged `ISeedData` through an explicitly identified offline analytics/materialized path using existing projector/fiscal logic; P1 uses committed CSV. Derive G1/G1L mapping from harness/scenarios, not unsupported SeedImporter profile names. Read account/footprint/readiness facts from loaded data.
4. Trust/limits: compose `AddTaxCreditAuth`, real client authorizer, writer sources, W1 limiter, clocks and signing keys. Convenience defaults `AllClientsAuthorizer`/deny-writers are not configured production policy. Isolate synthetic local policy.
5. AI/bytes: compose `AddTaxCreditAi` providers/router/guards/budgets with scripted/offline defaults. `AddLocalArtifactBytes` requires explicit `local`; deployed Blob uses `AddBlobArtifactBytes`. Metadata/audit stays in persistence. Remote failures are explicit, not empty bytes or fabricated model success.

Supply certified `ClientCalculation` dependencies and publish through `IClientCalculationRunner`: Gold, manifests and claim assessment share one transaction/database and claim sink.

Replace `SkeletonHostStatus` with real store/source/provider observations; settle startup checks before replay. Normal local API launch needs no live credentials or test-only registrations.

**Result:** default startup and tests resolve the same graph. Verify provider-selection branches with fake transports, offline defaults and resource/root discovery for ordinary API/Worker launches.

## Stage C4: connect the contract protocol to real state

Replace `NoContractWork` with real seed/queue/reset coordination. Preserve startup-only exposure and `Contract\test_contract_launch.py`: conductor supplies `TCC_CONTRACT_DIR`, disables profiles and omits the hook flag; the project bridges a valid inventory marker only for `dotnet run`, respecting explicit `TCC_CONTRACT_HOOKS=0`. Ordinary/direct-DLL launches remain hook-off.

Follow the harness/control and normalisation protocol. Empty `{}` reset uses query/startup profile/default P1. Restore real Gold/source/operational state; invalidate leases and source/config caches; reset limiter/budget/token/deterministic state. Serialize control/product work and suspend scheduling across reset/drain.

Byte stores have no destructive reset. Use a fresh exclusively owned local artifact generation, disposing old users before targeted cleanup; never clean production roots. Metadata-only reset is incomplete; reset failures cannot answer success.

`/__contract__/env` changes host-local configuration, not process/machine environment. Rebuild/reset immutable consumer snapshots as needed. Test changing/restoring writer enforcement, limits, source selection and another scenario setting; an echo of ignored settings is insufficient.

Share injected clock/ID/secret sources across auth, persistence, calculation, worker, limiter/budget. Freeze recorded time/counters/order at source; inspect UUID/secret counter relationships rather than assuming skeleton counters match. Reset restarts sequences. Env cannot enable hooks or fixture trust in production.

`/__contract__/mint` issues ephemeral RSA tokens accepted by real RS256 validation via an in-memory key bridge, including negative signature/issuer/audience/lifetime cases. Minted-token lookup is not validation; persist neither tokens nor keys.

`/__contract__/drain` uses Worker's executor synchronously and returns the actual count. Future `not_before` work remains pending. Coordinate deferred recalculation with response/next-request ordering.

**Result:** reset -> authenticated store observation -> durable work -> drain -> reopened terminal-state observation uses real stores. A repeated reset reproduces the initial state, counters and token-policy behavior; hooks absent/explicitly off remain 404.

## Stage C5: replace skeleton access with the W1 trust pipeline

Bridge `IApiAccess` to `IApiTrustService` with explicit request-principal storage/cleanup and concurrency isolation. The archive found AsyncLocal assigned inside an awaited access call did not reliably reach endpoints.

Exercise `AUTH-CONTRACT.md` through default startup: public bypass, bearer/RS256/lifetime/issuer/audience, delegated/app-only shapes, acting-user before agent refusal, client authorization, writer/actor binding, signed-caller limiter. Map abstract typed auth/source failures to the right JSON families and challenge/retry headers.

Use `p1_auth`: expired-on-public-health, wrong tenant/audience, mixed roles, missing/valid acting header on forbidden writes, unknown batch 404. Original agent principal selects clients/limiter; delegated acting headers cannot elevate. Preserve existence-before-visibility seams for batch/artifact handlers.

Expose consistent writer policy for every write route and future feature. F-14 exceptions are `reader.assess`, `reader.run`, `reader.rules-verify`, `reader.batch-dry-run`: the W1 auth/archive reports flag valid-request outcomes protected by supplied policy. Test enforcement; identify preserved exceptions by case/rationale rather than claiming exact parity for changed authorization. F-15 draft-list reads need no invented command actor; retain F-16 precedence.

**Result:** an authenticated read reaches a real seeded-store collaborator through default startup; malformed/unauthorized calls cannot reach it. Genuine dependency/configuration failures remain distinguishable from 401/403. No `SkeletonAccess` behavior is the default production authentication path.

## Stage C6: run the durable queue from the Worker host

Replace empty host startup with a real queue loop. Archived `Execution\RunWorker.cs`, `ExecuteRunItem.cs`, `RunWorkCoordinator.cs`, `OwnedReplayHost` illustrate collaborators, not installed APIs. Implement non-HTTP orchestration in owned Hosting/Ports/Worker, reusing repositories, certified state/retry helpers and transactional runner, not copied engine/selection logic.

Cover claim/heartbeat/reap, bounded polling, cancellation/release, classified retry, atomic finish/refresh and shutdown. Reconcile publication identity after process death or ambiguous commit instead of calculating twice. Preserve lease owner/expiry/client checks.

Share explicit API database/source settings. Disable racing inline pollers for replay; drain and any finite one-pass Worker mode use the same executor.

**Result:** a real Worker process consumes a synthetic item persisted by the API composition, exits or stops cleanly, and reopened storage shows its terminal item, accepted manifest and expected Gold/claim effects. Competing connections cannot both publish the same lease. This proves local durability, not cross-replica live Fabric behavior.

## Stage C7: composition evidence and feature-author handoff

Cover discovery, real auth/seed/reset/drain/env, hook-off launches, persistence/paging regressions and Worker sharing in owned tests. A test-only endpoint may observe real stores while business routes remain 501; authenticated 501 alone proves no store access. Include an actual API executable socket launch and Domain-purity assertions.

Run existing solution build/format/non-heavy checks from `dotnet`, then semantic replay against default startup with complete setup/captures/profile resets and fresh absolute reports. W1b is board-only. Compare conductor framework baseline 11/19 (57.9%, zero waivers), separately from wrapper 29/39 (74.36%). Explain real readiness changes and remaining stubs.

Update `dotnet\docs\HOST-ARCHITECTURE.md`: startup/config/defaults, ordinary API and Worker commands, discovery and copyable minimal module/endpoint example, feature locations, principal/writer/limiter seams, transaction runner and reset lifetimes. Four next-wave groups must need no shared-startup edits.

Write `dotnet\docs\COMPOSITION-REPORT.md`: adapter/config matrix, test/process evidence, persistence/schema repairs, framework comparison, remaining stubs and unresolved assumptions. Separate local/fake-transport proof from deployed behavior.

## Traps to expect

- `CONTRACT-REPORT.md` sections 4-5 contain older byte-level guidance. Preserve client-visible value types, null-versus-absent, money scale, validation/error families and required headers using the established wire helpers; incidental key order, number lexemes, English parser wording, HEAD/redirect/CORS quirks are not a reason to build a Python HTTP emulator.
- `PyJson`/`PyDict` belong on certified canonical/hash paths, not as the generic HTTP writer. `findings.md` T-14 and FZ-09 show conditional numeric promotion can silently change boxed types; the year-array failure is another representation boundary, not a reason to alter the encoder.
- `PERSISTENCE-REPORT.md` corrects the contract report's money shorthand: deployed DDL is DECIMAL(19,4). Keep exact decimal bindings and transaction boundaries. SQLite numeric rendering is not live Warehouse metadata certification.
- `contract\FINDINGS.md` E-3/E-4 explain worker/recalculation races; E-9 distinguishes shipped gzip hash from decompressed content hash. A reset response returning 200 with no real reset was precisely the previous false confidence.
- `SOURCES-AUTH-AI-REPORT.md` leaves the strict leap-window bridge partial: 2024-02-29..2025-02-28 shifted to begins TY2025/ends TY2024 can be calendar-assumed by the contextless certified Domain port. Composition cannot certify that away. M-01 ingestion precedence, first-program credit math, zero-worksite SQL/projector differences and native monetary AVG remain figure-sensitive boundaries.
- `PLATFORM-RISKS.md` proves only token-authenticated SELECT 1 and zero-object cleanup. SQL read/write parity, version freshness, live pooling/refresh, EF scope and bulk-copy support remain unmeasured. Use the existing count/max fingerprint with its limitations, not a claimed Delta snapshot.
- The merged central props already deduplicate SqlClient and persist oracle launch settings. Compatible stable Azure packages were chosen around DI 10.0.0; avoid reintroducing duplicate pins or treating a package upgrade as a composition repair.

## Evidence this plan is based on

- `C:\Projects\tcc-conductor-runtime\reports\W0.md` and `W1.md`: prerequisite sessions passed, but W1 left real default-host seeding/auth/business integration deferred.
- `dotnet\docs\waves\W1.md`, `integrate-W1-log.md`, `replay-integrate-W1-board.json`: merged 781-test baseline, 1,769 replay exchanges, authoritative versus wrapper framework denominators and honest red business groups.
- `dotnet\docs\HOST-ARCHITECTURE.md`: 110 captured method/template pairs, eleven workspace operations, post-build endpoint discovery, no-op work seam and inventory-marker hook launch bridge.
- `dotnet\docs\PERSISTENCE-REPORT.md`: real registration/seed interfaces, 18,111 P1 and 390,660 P2 rows, atomic publication/assessment, byte cleanup handoff and deployed finding-audit provisioning gap.
- `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`: real adapter registration/reset contracts, auth precedence and writer-review cases, explicit local-byte environment, per-process limiter/budgets and partial fiscal bridge.
- `dotnet\docs\ROUTES-DRAFTS-RUNS-REPORT.md` and `HALT-routes_drafts_runs.md` on the drafts archive: nonempty-year encoder failure, random-GUID timestamp ties, oversized draft-offset rejection and explicit-host/default-host divergence. Claims and AI archived reports independently confirm missing pre-build composition and historical Worker CS5001; the current integration minimal Main supersedes that historical build symptom.
- `contract\CONTRACT-REPORT.md`, `contract\docs\AUTH-CONTRACT.md`, `contract\docs\normalisation.md`, `contract\FINDINGS.md` and harness sources: error and money families, deterministic-source protocol, auth case identities and control ordering.
- `dotnet\docs\DOMAIN-SLICE-REPORT.md`, `findings.md` and `PLATFORM-RISKS.md`: certified entry points to reuse, representation traps and the limits of fiscal/live-platform evidence.
