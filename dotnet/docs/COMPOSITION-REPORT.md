# W1b composition report

## Result

The ordinary .NET 10 API and Worker now use one real W1 adapter graph.
Feature-owned services register before Build; contract reset/drain, trust,
source observations and durable execution no longer depend on a separately
composed test host. Business HTTP handlers and gateway/orchestration remain
deferred. Domain and the Sources/Auth/AI adapter implementations were not edited.

Implementation commits: `f81d2ef` (persistence/paging), `81a6ef4` (composition).
The following documentation commit contains this report, status and fresh replay
evidence. Nothing was pushed; no remote or live service was changed.

## Shared graph and configuration

| Area | Real composition / lifetime |
| --- | --- |
| Persistence | One singleton `PersistenceDatabase`, `AddPersistence` once, real Gold/operational/seed/queue ports and transactional `IClientCalculationRunner` |
| Provider selection | Local SQLite by default; explicit SQL Server/Warehouse uses Entra SQL connections, never fallback |
| Rules/calculation | Existing Application rule registration, real pack/wage adapters and scoped wage-enabled library/defaults/fiscal/resolver/calculation/assessment |
| Payroll | Existing CSV/SQL source registrations, mapping/scanner/projector, persisted lookup bridge and scoped source/fiscal snapshots |
| Replay source | P1 committed CSV; P2 staged `ISeedData` through cached materialized analytics and existing projector/fiscal logic; G1/G1L map to P1 |
| Trust | Real RS256 validator/trust service, explicit request principal, caller client allowlist, person writer policy, W1 limiter and Graph membership provider |
| AI | `AddTaxCreditAi` router/resilience/guards/budget with explicit offline provider; configured Foundry without invocation factory is unavailable, never fabricated success |
| Bytes | Existing explicit local/Blob adapters; persistent metadata/audit, hook-only scoped generation leases and owned reset cleanup |
| Execution | Singleton gate/executor; scoped inward operation and real transactional publisher; no API/Worker reference cycle |
| Observations | Shared `IHostStatus` settles real queue/store and source-account reads before probes; provider status reflects disabled/unavailable honestly |

`HOST-ARCHITECTURE.md` documents exact settings, precedence/defaults, resource
discovery, commands and lifetimes. Important defaults are local/none auth,
SQLite, synthetic CSV and local bytes; native deployed configuration requires
Warehouse, lakehouse SQL and Blob with controls disabled. Explicit
`CLIENT_ALLOWLIST` is required for signed production client access; no configured
production all-clients or deny-all-writers convenience policy is substituted.
Writer sources are persisted allowlist, Entra group or either. No package was
added; existing stable central pins and persistent CPython settings remain.

The wage adapter's state resolver uses a plain separate rule library to avoid
the wage-enabled library cycle. Scoped source/lookup/fiscal consumers see host
overlay changes on the next scope, not stale immutable singletons.

## Stages and proofs

**C1:** Deterministic API/Application plus explicit-assembly discovery invokes
`IFeatureModule.ConfigureServices` before provider construction. A test assembly
loaded through the production setting registers its own service; its endpoint
resolves it, exactly replaces one stub and leaves another 501. No temporary
provider or mapping-time DI mutation. The four next-wave feature folders need
no shared startup edit.

**C2:** Nonempty selected years now serialize as supported boxed lists, survive
SQLite reopen and retain order; empty years retain the previous representation.
Override save/change/clear/later-save at identical timestamps uses a persisted,
transactionally updated counter. Reverse IDs, reopen, independent/concurrent
connections, tenant isolation and local upgrade idempotence pass. Native SQL and
bindings are hermetically checked. Historical equal-time intent cannot be
recovered from old IDs. Draft offsets use BigInteger validation/count-first
paging; Int64 maximum/larger offsets yield empty pages with honest totals.
Malformed/negative offsets and invalid storage IDs remain 422; ordinary unknown
IDs retain the handler-independent empty/not-found behavior.

**C3:** Both executables call the same outward ServiceDefaults registration.
Provider-validation tests construct real native SQL/Blob adapters without
opening connections, exercise a fake group provider and explicit unavailable
Foundry status. Ordinary startup discovers resources without live credentials.
This proves selection and DI construction, not deployment connectivity.

**C4:** Real reset restores Gold/ops/source state, invalidates work/source/
configuration snapshots, restarts deterministic sources and rotates owned local
bytes. P2 checks actual accounts/footprint/fiscal rules, then restores CSV.
Writer enforcement and limiter changes/restoration affect behavior, not merely
an echo. Ephemeral minted RSA tokens go through real validation, including
negative signature/issuer/audience/tenant/lifetime tests. No token/key lookup or
persistence. Reset resumes after seed UUID high-water marks (P1 three, P2
twenty-six) independently of secret counters. Drain executes real work and
leaves future `not_before` items pending. Marker-only `dotnet run` works; direct
DLL and explicit-off controls remain absent.

**C5:** Principal push occurs after awaited access validation and is restored in
`finally`; await survival and concurrent isolation pass. Authenticated reads
reach seeded repositories through default startup, with refusals before store
access. Public bypass, actor binding, mixed roles, acting-header-before-agent
refusal, caller client permissions, writer changes, rate/reset behavior and
unknown-batch 404 are exercised. W1 intentionally returns 400 for missing/
malformed acting headers and 403 for mixed roles; those outcomes are preserved.
The four named F-14 valid-request exceptions are tested and retained, not
silently "fixed." F-15 lists require no invented actor. Auth dependency outages
map to JSON 503 without a misleading bearer challenge.

**C6:** Worker polls at bounded one-second intervals; `--once` and contract drain
use the same executor. Claim/heartbeat/reap, cancellation/refund, classified
source backoff and assessment-only work pass. Publication tests cover accepted
manifest recovery without recompute, cancellation rollback, competing
publishers, expired/wrong leases and injected lost-commit acknowledgement.
Gold, manifest, assessed claims and queue completion share one transaction.
A real finite Worker process consumes an API-composed persisted item and exits;
reopened storage proves terminal item, accepted manifest, source observation,
Gold and claims. P1 expected **107/77/72** comes from its unchanged TY2025 seed
manifest, not the unrelated TY2023 synthetic certification.

**C7:** Actual API socket startup, control-off behavior, architecture/purity
assertions and complete semantic replay all ran. Handoff and deployed schema
provisioning are separate documents. No live Fabric/Foundry/Entra/customer
request, private extract certification or cross-replica deployment is claimed.

## Verification

From `dotnet`, SDK **10.0.404**: whole solution `dotnet build -warnaserror`
passes with zero warnings/errors; full `dotnet format --verify-no-changes`
passes. Fast tests (`Category!=heavy`) have zero failures/skips:

| Assembly | Passed |
| --- | ---: |
| Domain | 18 |
| Architecture | 16 |
| API | 66 |
| Parity | 61 |
| Sources | 108 |
| Auth | 147 |
| AI | 167 |
| Persistence | 129 |
| **Total** | **712** |

All **seven API heavy tests** also pass (91 seconds combined), including P2
source restoration, bytes/counter reset, real drain and actual API/Worker
processes. The original CPython 3.12 conductor launch-bridge tests pass **3/3**.
The existing long Domain/Persistence heavy suites are wave-end work, not claimed
as run here. The parity assembly uses the persistent approved CPython oracle.

The integration log's "781" baseline conflicts with its own listed assembly
counts, which sum to **681**. None of those tests was deleted. Relative to that
enumerated baseline the measured fast gate adds 20 API and 11 Persistence cases;
heavy scheduling is reported separately. An intermediate retry test failure was
an unintended explicit-interface stub in its fake, not a bypassed production
retry failure; the diagnostic and stub were removed before the final green run.

## Replay: board only, no waivers

The ordinary executable was launched with `dotnet run --no-launch-profile`,
`TCC_CONTRACT_DIR`, **no explicit hook flag**, and no test feature assembly.
It served all twelve scenarios / **1,769 exchanges** with complete setup,
captures and profile resets. The wrapper sets scenario auth metadata after reset
and does not ask the child replay to reset again. The unchanged replay ran in
semantic mode. Absolute fresh diagnostic reports were generated at
`C:\Projects\GitHub\tcc-dotnet-w1b-composition\dotnet\artifacts\composition-replay-final\raw`.
The helper stopped its own process in `finally`. Committed reports retain
aggregate/category/case-path evidence, not payloads or credentials.

| Group | Current raw passed/cases | Baseline raw passed/cases |
| --- | ---: | ---: |
| Framework, wrapper membership | 26/39 (66.67%) | 29/39 (74.36%) |
| Framework, exact method/template membership | 8/19 (42.11%) | 11/19 (57.9%) |
| Control | 4/4 | 4/4 |
| Reads/calculation | 103/520 | 82/520 |
| Claims/artifacts/rules | 70/397 | 58/397 |
| Drafts/runs | 64/398 | 54/398 |
| AI | 3/31 | 3/31 |
| Workspace sealed | 57/125 | 56/125 |
| Gateway | 0/255 | 0/255 |

The new exact-membership result is computed over the fresh complete reports;
the external conductor itself was **not rerun**. The baseline conductor result
is authoritative historical evidence, not interchangeable with wrapper scoring.
The three additional raw failures are P1 readiness cases: actual source status/
account/problem observations replace recorded skipped/read-counter placeholders.
P2's old readiness difference likewise now reflects real loaded source facts.
Other framework misses remain documentation presentation/native path/CORS
differences. **The earlier 50% exact-framework threshold does not pass raw.**
This wave explicitly requires a board, not a green business/framework threshold.
No thresholds, recordings, goldens, seeds, certified constants or comparison
logic were changed; **zero waivers** were applied. Improvements are documented
without using them to conceal the regression. Business groups stay red because
their handlers remain deferred, even when shared auth now correctly refuses an
invalid request before the 501.

## Limits and owner decisions

`COMPOSITION-SCHEMA-PROVISIONING.md` details required `write_order`, sequence,
work identity, source observation and finding-audit provisioning. SQLite
upgrades/reopen are verified; deployed native DDL, grants, managed-identity
pooling/refresh and cross-replica transactions remain unverified. An injected
ambiguous acknowledgement test is not a real Warehouse commit experiment.

The synchronous certified calculation has no periodic heartbeat during compute.
The 600-second lease is renewed before publication and rechecked before commit;
expiry rolls back/refuses. Size leases for measured runs or design an approved
renewal boundary before long production work. The gate is process-local:
independent Workers must be stopped before hermetic reset/replay; it is not a
distributed reset lock. Fingerprints are row-count/max-
modified markers (CSV count/file-mtime), not historical snapshots; edits that
preserve both can evade freshness detection.

Figure-sensitive owner questions remain unchanged: M-01 ingestion overriding
year-resolved values despite the design, first-program multi-program credit math,
strict leap-window contextual fiscal behavior, zero-worksite SQL/projector
differences, native monetary AVG, and the historical equal-time override order.
The owner must also decide whether to standardize truthful readiness observation
fields before reinstating the old framework threshold. No changed calculated
figure is proposed as an improvement. Live-service/private-reference approval
and a production Foundry invocation factory remain outside this task.
