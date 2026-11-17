# Independent .NET App Service infrastructure

Stage D3 only. This tree does not invoke Python hooks, deploy code, create
Fabric/Blob/network resources, import state or change the existing `infra` stack.
The deployment manifest is owned separately at `dotnet\deploy\azure.yaml`.

## Integration contract for azd

The manifest's Terraform `infra.path` must resolve to this directory (from
`dotnet\deploy`, `../../infra-dotnet`). Resolve paths from the manifest, not CWD.
Use **only** `dotnet-api` and, when enabled, `dotnet-gateway` service selection.
The proposed `dotnet-worker` service has **no provisioned target**: do not run
unqualified `azd up`/`azd deploy` across all three services.

| Executable | App/tag | Outputs |
|---|---|---|
| API | `app-tcc-dotnet-<environment>-api` / `dotnet-api` | `DOTNET_API_APP_NAME`, `DOTNET_API_APP_ID`, `DOTNET_API_URL` |
| Gateway | `app-tcc-dotnet-<environment>-gateway` / `dotnet-gateway` | `DOTNET_GATEWAY_APP_NAME`, `DOTNET_GATEWAY_APP_ID`, `DOTNET_GATEWAY_URL` (empty when disabled) |
| Worker | unavailable; `enable_worker=true` fails validation | `DOTNET_WORKER_TOPOLOGY` |
| Orchestrator | unavailable; `enable_orchestrator=true` fails validation | `DOTNET_ORCHESTRATOR_TOPOLOGY` |

Other outputs: `DOTNET_RESOURCE_GROUP_NAME`, `DOTNET_SERVICE_PLAN_ID`,
`DOTNET_IDENTITIES` (`api`/`gateway` -> `resource_id`, `client_id`, `principal_id`),
`DOTNET_PRIVATE_ENDPOINT_IDS` and `DOTNET_STATE_KEY`. No generic Python-compatible
`API_APP_NAME`/`AZURE_RESOURCE_GROUP` outputs are emitted. The integrating manifest
must map `DOTNET_RESOURCE_GROUP_NAME` explicitly to its own azd environment.

### Input interface

Pass these as Terraform input variables, for example JSON-encoded `TF_VAR_network`
and `TF_VAR_payroll_source` from the integrating manifest's environment. There
is deliberately no implicit mapping from the Python azd environment. Do not
serialize actual allowlists into checked-in tfvars or package artifacts.

| Variable | Type / semantics |
|---|---|
| `subscription_id`, `environment_name`, `location` | Required explicit target; names always include `tcc-dotnet`. Environment suffix 3–20 lowercase characters. |
| `tenant_id` | Required Entra tenant GUID; used for `AUTH_TENANT_ID` and gateway `TENANT_ID`, not inferred from subscription. |
| `api_audience`, `gateway_audience` | Required **distinct** app registration GUIDs or `api://GUID`; API audience remains separate even in gateway's shared composition. |
| `git_commit` | Required full lowercase 40-character revision. |
| `warehouse` | Required `{server, database}` existing Fabric Warehouse SQL endpoint; no connection-string credentials. |
| `payroll_source` | Required `{server, database, schema?}` existing lakehouse SQL analytics endpoint. Schema default `tcc_source`; explicit `""` preserved. |
| `blob` | Required `{account_url, artifacts_container_resource_id, outputs_container_resource_id}`; HTTPS account URL with no SAS; two matching existing container ARM IDs. |
| `network` | Required object below; references only. |
| `log_analytics_workspace_id` | Required existing workspace ARM ID; platform metrics only. |
| `client_allowlist` | Required nonempty sensitive `map(list(number))`, principal -> positive client IDs. No all-clients fallback. |
| `writer_source`, `writer_group_id` | `allowlist` (default), `entra_group`, `either`; GUID required only for group modes. Stored writer decisions/Graph grants are operator-owned. |
| `channel_callers` | `map(set(string))`, default `{}`; app GUID -> `teams` and/or `m365-copilot`. Empty creates no service allowlist. |
| `enable_gateway` | Default `true`; false removes gateway app, identity, endpoints and Blob grants. |
| `enable_worker`, `enable_orchestrator` | Must remain false. |
| `data_classification` | `customer` (default) or `synthetic`; anonymous mode is never enabled. |
| `app_service_sku`, `tags` | `P1v3` default (`P2v3`/`P3v3` accepted); reserved ownership/service tags cannot be overridden. |
| `resource_root` | Fixed `/home/site/wwwroot/resources` staging contract. |

`network` members:

```text
integration_subnet_id         existing Microsoft.Web/serverFarms-delegated subnet
private_endpoint_subnet_id    distinct existing private endpoint subnet
sites_private_dns_zone_id     existing privatelink.azurewebsites.net zone
blob_private_endpoint_id      existing approved Blob private endpoint
blob_private_dns_zone_id      existing privatelink.blob.core.windows.net zone
fabric_private_endpoint_id    existing approved Fabric private endpoint
fabric_private_dns_zone_ids   nonempty existing Fabric private DNS zone ARM IDs
```

Only the app/SCM private endpoints and their DNS zone groups are new. No external
private endpoint, VNet, subnet, DNS zone/link, storage account/container, workspace,
lakehouse or Warehouse is in this stack's state. Reference shape validation does
**not** prove existence, approval, DNS links, routing or Fabric regional support.
Operators must pre-establish those dependencies and restricted VNet egress to
Fabric SQL, Blob and Entra/JWKS (plus Graph only for group writer modes).

### State and deployment isolation

Backend is partial `azurerm`, Entra-only, key
`tax-credit-copilot-dotnet.tfstate`. Configure an already-existing **dedicated
.NET state container/account per environment**, or an explicitly .NET-prefixed
environment key. `backend.config.example` is value-free/synthetic guidance.
Never reuse the Python backend's account/container/key/workspace tuple, run
state migration/import, or rename Python resources. Terraform outputs cannot
prove which backend an operator supplied. Protect the backend with RBAC and
network controls: state includes configuration/client bindings.

No backend initialization or provisioning is approved by this delivery.
The only commands executed here use `init -backend=false` and mocked tests.
There are no pre/postprovision hooks and no automatic schema/grant/seed scripts.

## Runtime and configuration evidence

Both apps are Linux **.NET 10 code deployments**, not containers, with
`dotnet TaxCredit.Api.dll` / `dotnet TaxCredit.Gateway.dll`. Packages must place
the DLL at the zip root and authored resources under `resources`; runtime uses
`TCC_REPOSITORY_ROOT=/home/site/wwwroot/resources`. `RuntimePaths` expects
`backend/rules` and `docs/data/schema`; staging must include the verified runtime
resources described by `dotnet\deploy` (including consumed public wage/preview
samples). Terraform does not assemble or certify the package.

`RuntimeRegistration`, `RuntimeSourceRegistration`, `RuntimeTrustRegistration`,
`RuntimeArtifacts`, `RuntimePaths`, `RuntimeWriters`, `ChannelConfiguration` and
`ChannelAuthenticator` are the configuration source, not the Python environment
inventory. `settings.tf` emits their real names:

- Warehouse -> `FABRIC_SQL_SERVER`/`FABRIC_SQL_DATABASE`,
  `TCC_PERSISTENCE_PROVIDER=warehouse`; no individual Python store selectors.
- Source -> `SOURCE_SQL_SERVER`/`SOURCE_SQL_DATABASE`/`SOURCE_SCHEMA`,
  `DATA_SOURCE=lakehouse`; no OneLake/Delta/mapping-override controls.
- Bytes -> `ARTIFACT_STORE=blob`, `ARTIFACT_BLOB_ACCOUNT_URL`; identity selected
  by per-service `AZURE_CLIENT_ID`. SQL clients enforce encryption/certificate
  validation in source code; there is no invented TLS environment switch.
- `ENVIRONMENT=azure`, explicit classification/Entra/client allowlist, person
  writer enforcement, strict pay-code/fiscal policies, `TCC_CONTRACT_HOOKS=0`.
- Gateway additionally gets its own tenant/audience, explicit caller/channel
  binding, rate 60/minute and `CHANNEL_DEBUG_WHOAMI=false`. It makes business
  calls **in-process**, so no `API_BASE_URL` is emitted.
- `GIT_COMMIT` is retained. API/gateway Foundry invocation is unavailable in
  `RuntimeAiRegistration`; no model/provider/egress/budget settings are advertised
  as functioning. No Python lease, heartbeat, polling or concurrency settings.

ASPNETCORE Production/URLs are framework settings, not application flags.
The listener is port 8080. Built-in .NET App Service uses the code-stack port;
container-only `WEBSITES_PORT` is deliberately not emitted. Remote build is
disabled and `WEBSITE_RUN_FROM_PACKAGE=1` expects a ready-to-run zip.

## Network, privilege and proof boundary

Public app and SCM access are off; both access-restriction defaults deny, no
allow exceptions; sites private endpoints provide private app/SCM access.
Deployment needs a VNet-reachable agent and Entra-authenticated Kudu/OneDeploy,
not basic-auth publishing or a public allowlist workaround. TLS >=1.2, HTTPS,
FTP/basic publishing off; all app outbound traffic routes through the supplied
integration subnet. This stack does not create firewall rules or allow public
orchestrator/Copilot ingress.

One new plan instance, one worker per app, no autoscale/sticky-session durability
claim. Gateway confirmation-key exclusivity, ledgers/rate limits and sessions are
host-local. Restart loses volatile state; one replica is not crash durability.
Worker's Generic Host has no HTTP listener: no Worker app/health probe is created.
The orchestrator has no resource/identity/ingress here. External work must
authenticate issuer/audience/tenant, strip and replace `x-ms-original-subject-*`,
`x-ms-user-identity`, `x-agent-user-id`, opt-in `x-client-*` from a verified subject,
bind employer access, and prevent direct-origin bypass before enablement exists.

### Actual identity footprint

| Identity | Granted by **this** stack | Required operator-owned native access |
|---|---|---|
| API UAMI | Storage Blob Data Contributor on **only** existing `artifacts` and `outputs` containers | Fabric workspace/item access plus source-table SELECT, SELECT/INSERT/UPDATE/DELETE on application `tcc_gold`/`tcc_ops` objects and new tables below; no DDL/admin/key access |
| Gateway UAMI | Same two container-scoped grants, distinct principal | Same real application/source/Gold/ops access as API, including channel audit/confirmations/artifact metadata; **not** Python's audit-only gateway grant |
| Worker/orchestrator | No identities or assignments | Unavailable; future Worker needs shared application access, orchestrator must have no payroll/DB/Blob role |

The built-in Blob role GUID is pinned. It includes read/write/**delete**, even
though immutable-byte adapter operations do not delete; this is a documented
privilege surplus, not an immutability policy. No account keys, Owner,
Contributor, subscription-wide role or Graph application grant is assigned.
Do not grant service principals client/person writer rights as a shortcut.
Group writer modes need separately approved Graph membership access; allowlist
mode uses persisted writer decisions with no Graph app permission.

Keep the established Python operations manual. Approve/verify native additions
`write_sequence`, `manual_override.write_order`, `run_work_identity`,
`run_source_observation`, `finding_audit`; apply forward migration with writers
stopped, then operator Fabric membership/T-SQL grants, then resume after native
transaction/publication checks. Existing Python migration tooling is not proof
that these new additions are deployed. NOT ENFORCED uniqueness is not evidence.
Use `DOTNET_IDENTITIES` to target both app principals explicitly; the old
gateway audit-only grant is insufficient. No live grants were attempted here.

Diagnostics export **AllMetrics only** for apps/plan; no allLogs, HTTP logs,
request tracing, detailed errors, app logs or App Insights connection string.
Framework console logging is suppressed to avoid request/path/exception PII.
ServiceDefaults has no exporter and does not subscribe custom `TaxCredit.Ai`
meters: do not claim application traces, custom signals or readiness alerts
are exported. A reviewed safe telemetry integration remains a release prerequisite.
`/api/health` is liveness. API `/api/ready` checks application dependencies.
Gateway `/channel/ready` is **constant metadata** (`ready=true`/store label), not
dependency readiness; GatewayHost does not map `/api/ready`. Neither a liveness
200 nor that gateway metadata certifies native permissions or queue progress.

## Reproducible local validation

From any directory: `pwsh -File <worktree>\infra-dotnet\validate.ps1`.
It creates an explicitly printed clean copy under the ignored
`infra-dotnet\.validation\clean-<UTC>` directory, copies no local backend/var
files and runs the guard/negative tests before initializing Terraform. Then:
`init -backend=false -input=false`, `fmt -check -recursive`, `validate`, `test`,
and `tflint --recursive` using the existing bundled Terraform ruleset pattern.
Provider download requires registry access on a cold machine; execution is
cloud-free. Every provider is mocked, aliases/remapping/adoption/hooks are
rejected. No standalone plan/apply runs. See `VALIDATION.md` for measured results.
