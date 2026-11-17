# API, gateway and Worker composition

The ordinary .NET 10 API and Worker share real W1 adapters through
`TaxCredit.ServiceDefaults.Hosting.AddTaxCreditRuntime`. Framework probes,
documentation, contract controls and the missing-reference workspace share
that composition with implemented business feature groups. The standalone
gateway reuses application services in-process; it requires no API listener.
The API retains all **110 captured method/template pairs**, including the
gateway placeholders; channel clients use the gateway executable instead.

## W3 standalone gateway and repeatable dual-host replay

`TaxCredit.Gateway` references the API composition library, Application and
ServiceDefaults. `GatewayHost.Build` calls `AddSkeletonHost` before provider
construction and `UseSkeletonHost` afterwards. It maps only channel/MCP,
download, process-health and opt-in contract-control endpoints; it does not
map portal endpoints, `/docs` or `/openapi.json`. The API and Worker do not
reference the gateway. No loopback HTTP client or separate API is needed by
gateway tools. The orchestrator is a separate Responses host that calls the
gateway REST surface with verified acting-person assertions.

Build first, then run both contract replays unattended from the worktree root:

```powershell
dotnet build .\dotnet\TaxCredit.slnx -warnaserror
& C:\Projects\py312-oracle\.venv\Scripts\python.exe .\dotnet\docs\run_wave_replays.py --out .\dotnet\artifacts\w3-replay
```

The runner starts each ordinary executable with `dotnet run --no-build
--no-launch-profile`, the conductor's `TCC_CONTRACT_DIR` marker, an isolated
SQLite database/artifact directory and a free loopback port. It verifies
CPython 3.12 and health, invokes the unchanged public `contract.replay` from
`backend` with root `PYTHONPATH`, semantic mode and the reset URL, and always
stops its own child host. Scenario setup/reset/mint/drain is automatic.
Nine API scenarios run against the API; the three `g1_` scenarios run against
the gateway. `--scenario g1_rest` selects a complete individual scenario.
Reports distinguish raw differences from policy scoring: runner exit success
means both replays completed, not that every field matched.

## Ownership and registration

`Contract/routes.generated.json` records each method/template, name, Python
endpoint, typed flag, declared parameters and request schema. HEAD operations
and the nine deferred gateway operations are included. Parameters are enriched
with the bounds/enums in the captured OpenAPI schema. `route-groups.json`
partitions every operation exactly once. Generate/check these files from the
existing inventory, never from Python imports:

```powershell
& C:\Projects\py312-oracle\.venv\Scripts\python.exe dotnet\src\TaxCredit.Api\Contract\generate_registry.py --check
```

The group ownership is:

| Registry group | API / Application / test folder | Scope |
| --- | --- | --- |
| framework | Framework | Probes and schema documentation |
| reads_calc | ReadsCalc | Scope, calculation reads, simulations, ingestion and current user |
| claims_artifacts_rules | ClaimsArtifactsRules | Claims/v2 claims, findings, artifacts, rules and audit |
| drafts_runs | DraftsRuns | Drafts/programs/batches and trend run/base-year/rebase routes |
| ai | Ai | Chat, summary and capabilities |
| workspace_sealed | WorkspaceSealed | All eleven captured workspace routes |
| gateway | Separate `TaxCredit.Gateway` executable | Channel, MCP and downloads |

Folders are relative to `src/TaxCredit.Api/Endpoints/`,
`src/TaxCredit.Application/Features/` and `tests/TaxCredit.Api.Tests/`.
Shared transport code stays in API `Wire/`, host composition in `Hosting/`,
and the framework-independent control ports in Application `Ports/Contract/`.
No speculative business handlers or empty infrastructure adapters were added.

Before `Build`, `FeatureDiscovery` scans the API and Application assemblies plus
the semicolon-separated `TCC_FEATURE_ASSEMBLIES` setting (assembly names or
absolute assembly paths). Assemblies/types are ordinally sorted and deduplicated.
Public, concrete, parameterless `IFeatureModule` implementations configure
services once; the same discovered types supply endpoint groups after `Build`.
This is trusted startup configuration, never request input.

To replace a stub, add a concrete `IEndpointGroup` with
`Map(IEndpointRouteBuilder)` under the group's API folder. Map the exact
method/template and dispatch an Application command/query through the existing
in-house mediator. Put its handler and tests in that group's folders. Discovery
maps all real groups first, then generates 501 endpoints only for unclaimed
method/template pairs. No shared registration file or stub needs editing.
The discovery test loads its test assembly through that production setting,
resolves a module-registered service at its real endpoint and leaves unrelated
stubs in place. No temporary provider or service mutation occurs during mapping.
Inventory drift and a duplicate/missing group assignment fail
tests; update captured inventory through its owner, not within this session.

Endpoint groups import Application, not infrastructure. Outward adapter wiring
lives in ServiceDefaults; inward execution lives in Application Hosting/Ports.
The API and Worker do not reference one another. Domain and the W1 Sources/Auth/AI
implementations are unchanged. `AddSkeletonHost` / `MapSkeletonHost` retain
their compatibility names but now use the real composition.

Minimal copyable discovery example (place in the group's API folder; replace
the illustrative `/api/scope` implementation when that feature is installed):

```csharp
using TaxCredit.Api.Endpoints;
using TaxCredit.Api.Hosting;
using TaxCredit.Application.Ports.Contract;

public sealed record ScopeCaption(string Value);

public sealed class ScopeModule : IFeatureModule
{
    public void ConfigureServices(IServiceCollection services, IConfiguration configuration) =>
        services.AddSingleton(new ScopeCaption(configuration["SCOPE_CAPTION"] ?? "scope"));
}

public sealed class ScopeEndpoints : IEndpointGroup
{
    public void Map(IEndpointRouteBuilder endpoints) =>
        endpoints.MapGet("/api/scope", (ScopeCaption caption, IClock clock) =>
            new { caption = caption.Value, observed_at = clock.UtcNow });
}
```

Real business routes dispatch the in-house mediator to handlers under their
Application feature folder; they do not calculate in the endpoint. The four
next-wave feature folders (`ReadsCalc`, `ClaimsArtifactsRules`, `DraftsRuns`,
`Ai`) need no Program, HostComposition or central route-list edit.

## Wire and errors

HTTP uses standard System.Text.Json: snake_case POCO fields, explicit nulls,
UTF-8, compact output and `application/json`. Native number lexemes and object
ordering are not parity requirements. Converters render `decimal` and
`PyDecimal` money as invariant decimal strings with their scale intact.
IDs/dates remain typed values or the explicit wire strings supplied by handlers.

`PyJson`/`PyDict` are **not the HTTP writer**. The existing Domain uses them for
canonical evidence such as calculation trails, fingerprints, program-draft
hashes and other certified ordered calculations. Future handlers should shape
transport DTOs rather than expose an ordered domain mapping as an HTTP array.
No money, headcount or certified result is recomputed by this host layer.

`ApiErrors` supplies the client-readable families: string `detail`, object
`detail` with code/reason/remedy, nested run-batch detail/code, and the
top-level dependency-unavailable response. `RequestValidator` checks captured
path/query/header/cookie parameters and body schemas before dispatch, including
required values, primitive types, bounds, enums, references and nullable unions.
Failures are 422 with `detail[]`, `type`, `loc`, `msg` and input where available.
English, Pydantic `ctx` and parser offsets are intentionally not reproduced.
The buffered request body is rewound and accessible via `RequestValidator.Body`.

The access port runs before a validation response is released for a protected
operation. Handled mediator refusals/validation failures remain 403/422.
Unhandled exceptions become JSON 500 with no exception text or stack in the
response; the boundary logs only the exception type. Request-start/finish
diagnostic logging is suppressed so URLs/query values are not written by it.
401 challenges use `WWW-Authenticate: Bearer`; 405 keeps native `Allow`.

`EventStream` writes and flushes `event: name\ndata: JSON\n\n`, disables
buffering and sets `Cache-Control: no-cache` / `X-Accel-Buffering: no`.
This is a transport helper, not an implemented chat/summary capability.

## Framework-default checklist

This follows CONTRACT-REPORT section 5, but the task's semantic policy takes
precedence over that report's older raw-byte recommendations.

| Area | Override or retained default |
| --- | --- |
| Names/nulls/order | Snake_case and `Never` ignore nulls; native ordering retained |
| Numbers | Scale-preserving money strings; native ordinary JSON numbers retained |
| Escaping | Standard relaxed UTF-8 encoder; no Python-compatible custom writer |
| Automatic validation | Inventory validator and 422 detail family; no controllers/automatic 400s |
| Binding | Explicit schema/type/bound checks, body rewind; unknown fields follow schema |
| ProblemDetails/status pages | Not installed; middleware supplies JSON 404/405/500 |
| Developer errors | Developer exception page is never installed |
| HEAD/trailing slash/OPTIONS | Native routing/CORS; no Python 307/HEAD/preflight emulation |
| Query repetition | Scalar validation takes the last value; undeclared query keys are ignored |
| Header casing/content type | Native header casing; JSON charset removed, HTML declares UTF-8 |
| Vary | `Vary: Origin` on transport responses for safe caching |
| Culture/time | Invariant money/ID formatting; clock port instead of ambient test time |
| Authentication | Real W1 trust pipeline; explicit request-principal push/restore after awaited validation |
| Streaming | Explicit SSE framing, per-frame flush and buffering disabled |
| Background ordering | Shared work gate, durable executor and real contract-work reset/drain |

Standard CORS accepts explicit `CORS_ORIGINS` (comma-separated), defaulting to
the local Vite origin `http://localhost:5173`; methods and headers are explicit,
not reflected or wildcard credentials. Deployed browser traffic uses the
same-origin BFF. Rejected preflights and trailing/case path behavior remain
ASP.NET defaults, not reproduced FastAPI artifacts.

Public documentation is small, self-contained HTML linking the captured schema;
there is no external CDN or configured browser OAuth client. The OpenAPI body
is an inventory snapshot, **not a claim that stubbed business handlers work**.

## Hermetic controls and adapter seams

Only startup `TCC_CONTRACT_HOOKS=1` maps `/__contract__/drain`, `/env`, `/mint`
and `/reset`; otherwise these paths are 404. `/env` cannot enable hooks.
Environment overrides are host-local, never process-global mutations.
One hermetic gate serializes control and product requests.

The conductor's actual launcher sets `TCC_CONTRACT_DIR`, but omits the hook
flag and disables launch profiles. The API project therefore bridges that
explicit inventory-directory marker to the startup argument
`--TCC_CONTRACT_HOOKS=1` in `ComputeRunArguments`. This applies only to
`dotnet run`, requires `inventory/routes.json` in the supplied directory, and
never overrides an explicitly set `TCC_CONTRACT_HOOKS` (including `0`).
Ordinary launches and direct DLL/deployed execution gain no hook default.
`Contract/test_contract_launch.py` verifies all three launch conditions.

Reset accepts a body profile, a `?profile=` query, or the startup
`TCC_CONTRACT_PROFILE`, with P1 as the default. P1/P2/G1/G1L are supported.
The public replay sends the scenario's declared profile to reset and applies
its authentication/writer/rate-limit setup before minting.
`RuntimeContractWork` loads real Gold/operational/source
seeds, restores caches and snapshots, and drains the shared durable executor.
G1/G1L use P1, matching the harness; P2 selects staged materialized analytics
using the existing SQL source projector/fiscal adapters. P1 selects CSV.

`IClock`, `IIdSource` and `ISecretSource` use the normalisation protocol:
frozen UTC, sequential UUID-shaped IDs and deterministic secret bytes in the
hermetic host, real sources otherwise. Minting uses a startup-generated,
in-memory RSA key, validated cryptographically by the real RS256 validator
through a hook-only key bridge. No token, key or token-lookup digest is retained.
Seed loading consumes no UUID calls, so reset resumes the independent UUID
counter after the seed and four real startup trace allocations (P1: seven;
P2: thirty) while restarting
the independent secret counter. Normal hosts use real time/randomness.

Framework health/readiness dispatch Application queries. Startup and control
changes settle actual queue/store and source-account observations. Probes read
that snapshot; they do not replay calculations or fabricate scan counters.
Workspace endpoints are loopback-only
and never load a private reference extract: summary/refresh report unavailable,
details report dependency-unavailable, including the F-6 JSON 503 correction.

## Configuration and ordinary launches

Run from `dotnet` to select SDK **10.0.404**, not the repository-root SDK.
ASP.NET/Generic Host configuration supplies normal command-line/environment/
configuration-file precedence. The host-local contract overlay wins until reset;
unset means absent, not a process environment mutation. Startup-only settings
cannot change through `/env`. Invalid consumer configuration is rolled back.

| Settings | Local default / requirement |
| --- | --- |
| `ENVIRONMENT`, `AUTH_MODE` | `local`, `none`; nonlocal defaults to `entra` |
| `TCC_PERSISTENCE_PROVIDER`, `OPERATIONAL_DB` | `sqlite`, `dotnet\artifacts\local\operations.db` |
| Native operational provider | Explicit `sqlserver` or `warehouse`; require `FABRIC_SQL_SERVER`, `FABRIC_SQL_DATABASE` |
| `DATA_SOURCE`, `DATA_CLASSIFICATION` | `csv`, `synthetic`; SQL uses `lakehouse` (`flex` alias) |
| SQL source | `SOURCE_SQL_SERVER`, `SOURCE_SQL_DATABASE`, `SOURCE_SCHEMA` (default `tcc_source`) |
| Resources | `TCC_REPOSITORY_ROOT` or upward discovery from cwd/executable; `RULES_DIR`, `TCC_SEED_ROOT`, `PAYROLL_PATH` override paths |
| Default resources | Existing `backend\rules`, `contract\seed`, `backend\data\payroll_pay_periods.csv`; wage adapter reads committed `backend\data\payroll.csv` |
| Source policies | `FISCAL_RULES_POLICY=assume`, optional `PAY_CODE_POLICY`; strict behavior stays in W1 adapters |
| `ARTIFACT_STORE`, `ARTIFACT_LOCAL_ROOT` | Explicit effective `local`, `dotnet\artifacts\local\bytes`; `blob` requires `ARTIFACT_BLOB_ACCOUNT_URL` |
| Trust | Entra requires `AUTH_TENANT_ID`, `API_AUDIENCE`; `CLIENT_ALLOWLIST` is a JSON object mapping signed object IDs to client-ID arrays, absent denies |
| Writer policy | `CHANNEL_WRITER_SOURCE=allowlist` (persisted); `entra_group` / `either` require `CHANNEL_WRITER_GROUP_ID` |
| Writer enforcement / limiter | `CHANNEL_ENFORCE_WRITER_FOR_USERS=false`, `RATE_LIMIT_PER_MINUTE=60`; real W1 snapshots rebuild on `/env` |
| AI | Endpoint absent: disabled offline provider; configured `FOUNDRY_PROJECT_ENDPOINT` without an invocation factory: explicit unavailable |
| Run provenance | `GIT_COMMIT`, default `working-tree` outside hooks |

Nonlocal startup requires `warehouse`, `lakehouse`, Blob and hooks off. There is
no SQLite/CSV fallback after native configuration fails. Credentials use
`DefaultAzureCredential`; no keys are settings. Publish product resources with
the executable or point at an explicit resource root. Startup does not auto-seed.

```powershell
Set-Location C:\Projects\GitHub\tcc-dotnet-w1b-composition\dotnet
dotnet run --project src\TaxCredit.Api --no-launch-profile -- --urls http://127.0.0.1:51773
```

In another terminal, use the same explicit database/source/resource settings:

```powershell
Set-Location C:\Projects\GitHub\tcc-dotnet-w1b-composition\dotnet
dotnet run --project src\TaxCredit.Worker --no-launch-profile
# Finite bounded pass (also TCC_WORKER_ONCE=1):
dotnet run --project src\TaxCredit.Worker --no-launch-profile -- --once
```

## Trust, execution and lifetime handoff

`IApiAccess` calls `IApiTrustService`; middleware pushes its validated principal
after the await and restores it in `finally`. `IApiPrincipalAccessor` is request
context, not a singleton caller value. The original signed caller determines
client authorization and rate bucket; the effective person determines writer
entitlement. Acting headers cannot elevate delegated users. Policy-protected
mediator commands use `RuntimeAuthorizer`; its synchronous bridge reflects the
existing synchronous `IAuthorizer` contract. Missing principals deny.

HTTP writer classification is shared for deferred features, including mutating
GET refresh; draft lists/read-only POSTs are not commands. Protected valid-request
F-14 exceptions remain `reader.assess`, `reader.run`, `reader.rules-verify`,
`reader.batch-dry-run`; agent and acting-header precedence still applies.
Dependency failures stay JSON 503, not bearer 401. Feature handlers must preserve
existence-before-visibility for batches/artifacts.

Singletons: database, shared sources/clock, work gate/executor, runtime overlay,
seed generations, limiter/writer snapshots, AI router/budget, auth events/key
cache and artifact generation owner. Scoped: source projector/catalogue/fiscal/
lookup readers, rules/defaults/resolver, trust/client/writer policy, calculation
and artifact-byte leases. The wage state resolver uses a separate plain library
to avoid a wage-enabled RuleLibrary dependency cycle.

API drain and Worker call the same inward `RunWorkExecutor`. It reaps/claims,
heartbeats, persists an item/run identity, reconciles accepted manifests before
compute, and publishes through `IClientCalculationRunner`. Gold, manifest,
assessment claims and queue finish/refresh share one database transaction.
Known aborted conflicts/source outages retry with backoff; cancellation releases
and refunds the claim. Future `not_before` work remains pending.

The synchronous certified calculation has no mid-calculation periodic heartbeat.
The default 600-second lease is renewed before publication, and checked before
commit; expiry refuses/rolls back rather than accepting stale ownership. Long
runs need lease sizing or a separately designed renewal boundary. Local process
durability and fake native SQL are proved, not live cross-replica execution.

The gate serializes product requests, drain and reset. Reset restores stores,
lookup/source generations, leases, clock/UUID/secret state, limiter/writer/Graph/
JWKS snapshots and cooldowns, AI budgets/router and auth events. Local bytes use
a new exclusively owned generation; reset waits for scoped users (bounded five
seconds) before targeted cleanup, never deletes the configured production root,
and does not report cleanup failure as success.
The gate is process-local: stop independent Workers before hermetic reset, and
do not run a separate poller during replay. It is not a distributed reset lock.

## Local replay and evidence

Use the ordinary API command with `TCC_CONTRACT_DIR` pointing at this worktree's
`contract` directory and the hook flag absent to exercise the conductor bridge.
Then run from the worktree root:

```powershell
& C:\Projects\py312-oracle\.venv\Scripts\python.exe dotnet\src\TaxCredit.Api\Contract\replay_board.py --base-url http://127.0.0.1:51773 --out C:\Projects\GitHub\tcc-dotnet-w1b-composition\dotnet\artifacts\local-board.json --raw-dir C:\Projects\GitHub\tcc-dotnet-w1b-composition\dotnet\artifacts\local-replay
```

The wrapper performs each profile reset and auth setup before the unchanged
semantic replay; it does not reset a second time and erase that setup.
`--scenario` selects complete scenarios; `--group` only selects board display.
The fresh twelve-scenario / **1,769-exchange** results are
`replay-composition-board.json` and `replay-composition-framework.json`.
Wrapper framework is **26/39 (66.67%)**, versus baseline 29/39; exact
method/template framework is **8/19 (42.11%)**, versus baseline 11/19.
The three additional raw failures are truthful P1 readiness observations,
not calculation changes. This wave is **board-only**; no waiver was applied and
no claim is made that the earlier conductor 50% framework threshold passes.
See `COMPOSITION-REPORT.md` for limits and remaining red business groups.
