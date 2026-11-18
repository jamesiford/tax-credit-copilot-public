# .NET configuration contract (Stage D2)

This is a **consumer-verified, offline contract**, not release approval. The Python
inventory is a reference, not a compatible `.NET` environment file. Do not copy
`backend/.env`, private payroll, customer identifiers, keys or tokens into packages,
examples, logs or CI artifacts.

## Machine-readable inventory and validator

[`configuration/inventory.json`](configuration/inventory.json) explicitly enumerates
every literal setting/input/output name in `docs/architecture/ENV-VARS.md`, including
removed names and grouped AI controls. It adds actual .NET settings and expands the
role/provider model family. `contract.py` resolves compact group inheritance into one
record per variable: classification, target mapping, consumer or absent **for each
executable**, service scope, required/default/unset/empty semantics, and non-secret
source. Shared metadata is inherited, not omitted. Classifications are `unchanged`,
`translated`, `Python-ops-only`, `platform-injected`, `unsupported`, `irrelevant`.
`unchanged` describes a name with a functioning consumer; it does not promise every
Python fallback or every executable is the same.

From the repository root, using the fixed oracle:

```powershell
$python = 'C:\Projects\py312-oracle\.venv\Scripts\python.exe'
$env:PYTHONDONTWRITEBYTECODE = '1'
& $python dotnet\deploy\configuration\validate.py --inventory
& $python dotnet\deploy\configuration\validate.py --service api --file dotnet\deploy\configuration\examples\api.json
& $python -m unittest discover -s dotnet\deploy\configuration -p test_*.py -v
```

The scripts use only Python 3.12 stdlib; they never connect, acquire credentials,
read `.env`, or enumerate the process environment. Input is an **explicit JSON object
of emitted setting names to strings**, not `os.environ`. Exit 0 means syntax/policy
valid; exit 1 means refused. Diagnostics contain setting **names only**, never values,
file paths from failed reads, exception messages or JSON excerpts. Example output:
`{"valid":false,"settings":["API_AUDIENCE"]}`. Invalid JSON/files produce only
`configuration`. `--local` relaxes deployment posture for synthetic lint, not release
approval. `--check-resources` additionally checks the manifest's resource paths.

Examples use reserved `.invalid` hosts, synthetic registrations and a synthetic
client identifier; they make no native availability claim. Valid Worker settings do
not make Worker deployable on App Service. A valid orchestrator manifest does not
authenticate its incoming subject.

The validator is deliberately stricter than some hosts: explicit deployed posture,
client binding, writer enforcement, canonical audience shape, HTTPS origins, no
ambient feature assembly loading, and secretless model-gateway auth. It refuses
unsupported/irrelevant/legacy-name emissions rather than claiming they work.
Platform settings are inventoried separately from application consumers.

## Exact deployed API / Worker / gateway inputs

These three share `AddTaxCreditRuntime`; even the non-HTTP Worker constructs the
auth, rule, source and artifact graph.

| Settings | Contract and actual consumer |
|---|---|
| `ENVIRONMENT` | Explicit non-`local`. Unset defaults **local** in `RuntimeConfiguration`; empty is nonlocal in runtime validation. |
| `DATA_CLASSIFICATION` | Explicit `synthetic` or `customer`. Runtime defaults synthetic and does not validate the enum; deployment lint closes that gap. |
| `AUTH_MODE` | Explicit `entra`. Gateway forcibly sets it. `ALLOW_ANONYMOUS_SYNTHETIC` is **not wired** by `RuntimeTrustRegistration`; no deployed anonymous demo exemption. |
| `PERSISTENCE_PROVIDER` | Exact `warehouse`; unset defaults sqlite. One destination for every Gold/ops repository, not one database per legacy store selector. |
| `FABRIC_SQL_SERVER`, `FABRIC_SQL_DATABASE` | Required Warehouse host/database. Explicit translation from Python `WAREHOUSE_SERVER` / `WAREHOUSE_DATABASE`; old names are **not aliases**. |
| `DATA_SOURCE` | Exact `lakehouse` deployed, meaning SQL analytics. Unset defaults **csv**; empty/unknown rejected, unlike Python. `flex` is accepted only outside deployed validation. |
| `SOURCE_SQL_SERVER`, `SOURCE_SQL_DATABASE` | Lakehouse SQL analytics endpoint and database. Resolve explicitly from verified endpoint metadata; translate `LAKEHOUSE_SQL_*` manually. No Warehouse-host or item-name fallback. |
| `SOURCE_SCHEMA` | **Unset → `tcc_source`; empty/whitespace → SQL `dbo`**. `SourceScanner.TableName` quotes `[dbo].[physical]` for the blank case and sets `HasBlankSchemaWarning`; it never emits Python's empty SQL qualification. Nonblank identifier regex: `[A-Za-z0-9_][A-Za-z0-9_-]{0,127}`. Old azd default `flex` is not a .NET default. |
| `SOURCE_MAX_ACCOUNT_ROWS` | Unset/blank → 1,000,000. Whole number ≥ 1000; anything else is a startup `InvalidOperationException`. Most payroll rows one client may have; over it the read stops one row past the limit and the API answers 422 `account_too_large` whose remedy names this setting and the limit. About 3.5 KB of peak memory per row (`docs/SCALE-S2-REPORT.md`). |
| `SOURCE_PORTFOLIO_MAX_ACCOUNTS` | Unset/blank → 25. Whole number ≥ 1. A portfolio-wide payroll load (entity portfolio simulation) over this many clients is refused before reading (422 `portfolio_too_large`). |
| `SOURCE_PORTFOLIO_MAX_ROWS` | Unset/blank → 5,000,000. Whole number ≥ 1000. The same load is refused before reading any client whose rows would take the running total (from the SQL scope aggregate) over this. |
| `ARTIFACT_STORE`, `ARTIFACT_BLOB_ACCOUNT_URL` | Exact `blob` and explicit HTTPS account origin. Identity-only `DefaultAzureCredential`; no SAS/key/connection string. Local bytes are forbidden deployed. |
| `AUTH_TENANT_ID`, `API_AUDIENCE` | Required shared Entra trust settings. **No `AZURE_TENANT_ID` fallback** in composition. Audience supports comma-separated accepted API registration forms; deployment lint requires bare GUID or `api://GUID` per entry. |
| `CLIENT_ALLOWLIST` | Nonempty JSON object, effective person OID → client-ID arrays. Missing/empty denies signed client access; it does not grant portfolio-wide access. Keep operational values out of retained proof artifacts. |
| `CHANNEL_WRITER_SOURCE`, `CHANNEL_WRITER_GROUP_ID` | Explicit `allowlist`, `entra_group`, `either`; non-allowlist needs group GUID and Graph application permission `GroupMember.Read.All`. Database grants/allowlists remain operator work. |
| `CHANNEL_ENFORCE_WRITER_FOR_USERS` | Explicit `true` deployed; actual shared parser accepts `true/1/yes`, `false/0/no` and blank, **not `on/off`**. Gateway always enforces the acting-person writer check. |
| `AZURE_CLIENT_ID` | Attached per-service user-assigned managed identity client id. Azure SDK consumes it; selecting an ID does not attach or grant the identity. |
| `GIT_COMMIT` | Immutable build revision. Unset becomes `working-tree`; no git discovery subprocess. Empty is retained by runtime and rejected by deployment lint. |
| `CONTRACT_HOOKS` | Off (`0` recommended). **Only exact `1` activates** token mint/reset/environment/drain controls; deployed runtime rejects enabled hooks. Ordinary `dotnet DLL` never invokes the project replay-launch MSBuild target. |
| `REPOSITORY_ROOT` | Explicit staged product root: `/app/resources` in Linux images; `/home/site/wwwroot/resources` for App Service packages. **`RESOURCE_ROOT` does not exist.** |

`AZURE_TENANT_ID` / `AZURE_TOKEN_CREDENTIALS` are SDK-chain inputs, not replacements
for API trust. Existing SDK `DefaultAzureCredential` owns their behavior. A separate
Worker needs its own `AZURE_CLIENT_ID`; `RUN_WORKER_IDENTITY_CLIENT_ID` is not read.
Gateway needs full application permissions because it runs application services
**in process**. `API_BASE_URL` is not consumed by gateway and cannot make it a proxy.

Gateway additionally requires explicit `TENANT_ID` and `GATEWAY_AUDIENCE`.
Its tenant runtime fallback to `AUTH_TENANT_ID` is not relied on by deployment lint.
`API_AUDIENCE` remains the shared API trust audience, not the gateway audience.
`CHANNEL_GATEWAY_AUDIENCE` belongs to orchestrator and must match gateway's
`GATEWAY_AUDIENCE`; no setting automatically merges these three audiences.

Gateway controls with real consumers: `CHANNEL_ALLOWED_CALLER_APP_IDS` (optional
role bypass allowlist), `CHANNEL_CALLER_CHANNELS` (`appGUID=teams|m365-copilot`),
`CHANNEL_RATE_LIMIT_PER_MINUTE` (1–6000, default 60), exact
`CHANNEL_MCP_ALLOWED_ORIGINS` (default none), `CHANNEL_DEBUG_WHOAMI` (off).
The gateway does not read `CHANNEL_RESOLVE_DISPLAY_NAMES` or
`CHANNEL_REQUEST_TIMEOUT_SECONDS`; it makes no HTTP business call to another API.

API `/api/ready` returns **HTTP 200 with `ready=false`** in the parent's measured
ordinary-published process smoke with missing synthetic CSV. Its body carries
settled startup observations, not continuous probing. An HTTP status-only
platform probe cannot express API dependency readiness either: inspect the
`ready` body or add the missing host mapping to a non-success unavailable status.

Gateway `/channel/ready` is only a **static liveness/config assertion**:
`ChannelEndpoints` hardcodes `ready=true`, echoes a store selector and never reads
`RuntimeStatus.Readiness`. `GatewayHost` maps `/api/health` but no `/api/ready`.
An unavailable source can therefore coexist with HTTP 200/`ready=true`; this must
not be used as dependency readiness. The missing host seam is a dependency-result
route using the shared readiness observation/query and a non-success unavailable
status. That application-owned change and its negative proof are release
prerequisites, not configuration fixes.

## Resources: preserve paths and Linux case

API, Worker and gateway packages must retain this **allowlisted** resource tree,
read-only, rooted at `REPOSITORY_ROOT`. The `resources` directory belongs under
the published package root (`/app/resources` in the image,
`/home/site/wwwroot/resources` on App Service), not an external checkout.
Parent deployment tooling stages locked-restore inputs without changing
application projects or central package files:

| Relative resource | Actual reason |
|---|---|
| `backend/rules/**` | Exact authored program/year packs, registry, lookups, methodology and `schema/rule-pack.schema.json`; `RuntimeCalculationRegistration`, `RuleLibrary`, `AssumptionFiles`, `JsonSchemaPackValidator`, `LookupResolver`. Do not flatten, rename, regenerate or omit authored subtrees. |
| `docs/data/schema/tcc-schema.sqlserver.sql` | `PersistenceSchema.Read` supplies typed Gold write bindings, including on Warehouse; this is not permission to run bootstrap. |
| `docs/data/schema/migrations/*.sql` | All authored SQL migrations, ordinal filename order, read with schema metadata. `tcc-schema.fabric.sql` is **not** read by .NET; it may be retained as authored operator material but is not a runtime dependency. |
| `backend/data/payroll.csv` | Committed synthetic annual wage/reference data: `ProgramWageSource` and `PortfolioReferenceData`. Missing file can silently yield no rows; retain it. This is not client payroll. |
| `backend/data/payroll_pay_periods.csv` | Committed synthetic **draft preview** sample: `SyntheticPreviewSample.Load`, independent of `DATA_SOURCE`; also local CSV smoke. Excluding it breaks deployed previews even with lakehouse SQL. |
| `backend/data/rules_ingested/ga_jtc.json`, `tn_jtc.json` | Tracked captured inputs, wired via `JsonIngestedConfigFiles`. Absence silently yields no ingestion overlay; preserve current inputs, including unresolved M-01 precedence. |

If `RULES_DIR` is overridden, previews seek `data/payroll_pay_periods.csv` beside
that rules directory's parent. Null-coalescing paths preserve **empty strings**;
do not set resource path variables to empty. `SEED_ROOT` may point at an absent
`contract/seed` in production: seeds load only through local contract controls.
No private extract, `backend/data/payroll/`, `.env`, SQLite database, token cache,
generated log, contract seed directory or blanket `backend` copy belongs in production.
The source mapping is the **embedded** `Sources.DefaultMapping.json`, not an
external JSON runtime dependency.

## Unsupported controls are not successful configuration

`RuntimeSourceRegistration` calls `SourceMapping.Load()` **without a patch**.
`SOURCE_MAPPING_FILE`, `SOURCE_TABLE_PREFIX`, `SOURCE_TABLE_CASE`,
`SOURCE_TABLE_MAP`, `WORKSITE_LOCATION_SOURCE` and `NULL_PAY_DATE_POLICY` have no
environment wiring, despite typed mapping support in the library. Source cache,
Silver, Delta version, OneLake transport, schema-validation mode and Python
footprint guards likewise have no runtime setting consumer.

Shared persistence ignores Python individual store selectors. Gold/ops schemas are
fixed; `GOLD_SCHEMA` / `OPS_SCHEMA` cannot rebind .NET SQL. Governed data privacy has
typed defaults (including `CapabilityOptions.MinimumGroupSize=5`) but
`DATA_MIN_GROUP_SIZE` and other `DATA_QUERY_*` flags are not wired. Their presence
must never be reported as a raised privacy floor or enabled raw source queries.
The unresolved person-lane/privacy behavior in W3 reports remains a release gate.

Run settings are not inherited: `RunExecutionOptions` fixes **lease 600 seconds,
attempts 3**; Worker processes one item at a time and waits **1 second** between
polls. There is an initial heartbeat but **no periodic extension during synchronous
calculation**. Python lease/concurrency/heartbeat/poll/backoff flags do nothing.
`RUN_WORKER_STALE_SECONDS` translates to actual `RUN_STALE_WORKER_SECONDS`
(default **60**, health reporting only, not Python's 300). `--once` or exact
`WORKER_ONCE=1` drains finitely; ordinary daemon deployment keeps it off.

## Orchestrator model and trust contract

The installed preview AgentHost SDK binds **`http://[::]:8088`** using
`ListenAnyIP`, overriding `--urls` and `ASPNETCORE_URLS` even when they request
loopback and another port. Parent measured the SDK's address-override diagnostic
and actual binding. `ASPNETCORE_URLS` is therefore **unsupported as an
orchestrator address/confinement control** in the inventory and validator.
API/gateway listener configuration is unaffected. SDK `/readiness` remains the
orchestrator probe. Orchestrator has no repository, payroll or SQL role. It requires
`TENANT_ID`, HTTPS `CHANNEL_GATEWAY_URL`, `CHANNEL_GATEWAY_AUDIENCE`; bounds and
defaults for every turn/session/AI/model-gateway control are in the inventory.

Only its `ProviderClients` builds real model clients. Role model resolution is
provider-specific `AI_MODEL_<ROLE>__<PROVIDER>` → `AI_MODEL_<ROLE>` →
`FOUNDRY_MODEL` → platform `AZURE_AI_MODEL_DEPLOYMENT_NAME` → `gpt-5.4-mini`
for Foundry; **gateway has no model fallback**. Shared/per-role provider chains
accept `foundry` and `gateway` only; `foundry_connection` and version pins absent.
`AI_GATEWAY_*` controls include explicit auth/dialect/version, headers, optional
key/OAuth fields, Entra audience, timeouts, streaming, tools and TLS. The deployed
contract supports **`entra_token` only**, never emits keys or OAuth secrets, keeps
TLS verification on, and rejects ambiguous non-origin model gateway URLs.
The actual .NET endpoint constructor allows a path; the deployment contract is
intentionally narrower. The API runtime **does not consume these model controls**:
it registers only an `OfflineRuntime`; even a configured Foundry endpoint remains
`Unavailable` with no invocation factory.

Deployment keeps `AI_INJECTION_GUARD=on`, `AI_OUTPUT_POLICY=on`, explicit
`AI_EGRESS_POLICY=aggregates_only` or `block`, nonnegative daily and per-principal
token budgets, `CHANNEL_DEBUG_WHOAMI=false`, `KNOWLEDGE_ENABLED=false` and provider
`none`. Knowledge `foundry-iq` is unimplemented; only synthetic fake exists.
Foundry-reserved endpoint/name/version/model variables remain platform-injected;
do not author their deployment values in customer settings.

**External orchestrator ingress stays disabled/private.** Current SDK hosting
copies HTTP headers into `IdentityResolver`; it does not authenticate an original
person. A GUID or opaque SDK user key is not proof of identity. Before external
enablement, a trusted ingress must authenticate upstream, validate issuer,
audience and tenant, remove all incoming `x-ms-original-subject-*`,
`x-ms-user-identity`, `x-agent-user-id`, and opt-in `x-client-*` signals, replace
only from an authenticated subject, and prevent direct-origin bypass. Do not
enable `client-headers` as a workaround. A network-private endpoint alone is not
the missing subject binding. Parent guard defaults to exit **78** and allows a
local synthetic proof only with explicit synthetic/local/proof flags **and**
`/sys/class/net` containing only **`lo`**. Proof flags on Docker bridge networking
still exit **78**. Docker `--network none` proof measured SDK readiness **200**
and SIGTERM exit **0**; ordinary published-artifact proof uses the same isolated
namespace. A requested loopback URL is not the safety boundary: the kernel
network namespace is. This enables no externally deployable orchestrator.
Initial gateway count is one and orchestrator external count is zero; restart
loses host-local ledgers, limiters, sessions/checkpoints and budgets.

## Built-in telemetry versus the optional deployment hook

`ServiceDefaults/Extensions.cs` registers ASP.NET/HTTP/runtime instrumentation,
but **no exporter**, and does not subscribe custom `TaxCredit.Ai` Activity/Meter.
`APPLICATIONINSIGHTS_CONNECTION_STRING` merely changes a health boolean in the
ordinary runtime. Neither it nor `TELEMETRY_ENABLED`, authentication-string or
arbitrary OTEL settings demonstrate receipt. The orchestrator's direct
`LoggerFactory.AddSimpleConsole` is not configured by ordinary host logging
environment switches. Do not claim those switches suppress its messages.

The separate optional deployment-owned startup hook is now locally measured;
see [`telemetry/README.md`](telemetry/README.md) for its exact integration,
receipt, collector-failure, privacy and shutdown evidence. Its explicit settings
are `DOTNET_STARTUP_HOOKS`, `TELEMETRY_ENABLED`, `OTEL_SERVICE_NAME`,
`TELEMETRY_VERSION` and `TELEMETRY_ENDPOINT`. The hook subscribes
allowlisted sources/meters, including custom AI signals when emitted, and exports
a newly constructed minimal OTLP/HTTP JSON envelope. This does **not** change
ServiceDefaults, install an application exporter, or make an unavailable model
provider run successfully. Terraform does not install or activate this hook.
Use its own validation/receipt procedure separately from the D2 application-setting
manifest validator; the latter does not claim to validate optional hook inputs.

The optional hook captures no logs and does not export runtime meters or invent
queue/lease/readiness/uncertain-write business signals. Product/platform logging,
native collector/backend configuration and actual application telemetry coverage
remain separate prerequisites. Retain the private/disabled posture and safe host
logging suppression until those boundaries are approved; never export headers,
queries, bodies, model prose, person/client identifiers, credentials or exception
detail. Its local synthetic receipt proof is not native service certification.

Evidence and measurements: [`configuration/config-proof.md`](configuration/config-proof.md).
Host topology: [`DEPLOYMENT-MATRIX.md`](DEPLOYMENT-MATRIX.md).
