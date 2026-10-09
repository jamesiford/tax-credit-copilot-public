# Support runbook

Requirement **OBS-2**. Health checks, how to read the logs, KQL for the
failures seen in practice, the common operator actions, and what to capture
before escalating.

Related: [ENV-VARS.md](ENV-VARS.md) (every setting named below),
[DEPLOYMENT-HANDOVER.md](DEPLOYMENT-HANDOVER.md) (deploy, verify, teardown in
full), [CONNECTIVITY-MATRIX.md](CONNECTIVITY-MATRIX.md) (network paths and what
is and is not authenticated), [ADR-007](ADR-007-warehouse-operational-store.md)
(the Warehouse is the only operational store).

All KQL below targets the Log Analytics workspace (`log-tcc-<suffix>`) that
`infra/modules/monitoring/main.tf` creates and both apps' diagnostic settings
and Application Insights feed. Run it from that workspace's **Logs** blade, or
`az monitor log-analytics query`.

## 1. Health checks

| Check | Call | What it proves | What it does not prove |
|---|---|---|---|
| Web app | `GET https://<web host>/healthz` | The Express BFF process is up. Body is `{"status":"ok","api_configured":<bool>}`; `api_configured` is `false` only if `API_BASE_URL` is unset (`frontend/server/app.js`) | Nothing about the API or Fabric |
| API, through the web app | `GET https://<web host>/api/health` | The web app's proxy reaches the API. Body includes `status`, `foundry_configured`, `agents_registered`, `telemetry_configured`, `warm` (`backend/main.py`) | Fabric reachability — see §4 |
| API readiness | `GET https://<web host>/api/ready` | Startup finished and the warm-up (`backend/application/warmup.py`) is not still `running`. A warm-up that failed still reports `ready: true` — warm-up is an optimisation, not a gate | Whether the warm-up actually succeeded; read `warm.status` for that |
| API, direct | `GET https://<api host>/api/health` | **Returns 403 by design.** The API's access restriction allows only the web app's VNet integration subnet (`web-app-subnet`); there is no API private endpoint. A 403 here is the network working, not a fault (`CONNECTIVITY-MATRIX.md` R2) | — |

`/api/health` and `/api/ready` are the only two API routes exempt from bearer
validation under `AUTH_MODE=entra`, so both answer from inside the subnet
without a token.

A deployed process can also fail to **start** before any of these answer —
see §8.

## 2. Reading the logs

### 2.1 Tables actually produced

Both apps' diagnostic settings (`infra/modules/app_service/main.tf`) enable
`category_group = "allLogs"` plus `AllMetrics`, and the plan gets `AllMetrics`.
Application Insights is workspace-based (`infra/modules/monitoring/main.tf`),
so its tables land in the same workspace. In practice, for this app, these are
the tables with data:

| Table | Source | Holds |
|---|---|---|
| `AppRequests` | App Insights (OpenTelemetry via `configure_azure_monitor`, `backend/telemetry.py`) | One row per API request: `Url`, `ResultCode`, `DurationMs`, `OperationId`, `Success` |
| `AppDependencies` | App Insights | Outbound calls the instrumented libraries see (ODBC/Warehouse, outbound HTTPS) |
| `AppTraces` | App Insights | `logging` records emitted anywhere in `backend/` once telemetry is configured — this is where `tenant_sql.py`'s retry warnings and any `log.exception` land |
| `AppExceptions` | App Insights | Unhandled exceptions, with `OuterMessage` and the stack |
| `AppServiceHTTPLogs` | App Service platform (`AllLogs`) | Every HTTP request at the platform (IIS/Kudu) layer, both apps: `CsMethod`, `CsUriStem`, `ScStatus`, `TimeTaken` |
| `AppServiceConsoleLogs` | App Service platform | stdout/stderr of the process — gunicorn/uvicorn boot lines on the API, `node` on the web app |
| `AppServiceAppLogs` | App Service platform | Only populated if the platform's own app-logging feature is on in addition to the diagnostic setting; usually empty here since the app emits through `logging` → App Insights instead |

`AppTraces` is only populated when `APPLICATIONINSIGHTS_CONNECTION_STRING` is
set (it is, on both apps, by Terraform) **and** `telemetry_configured` in
`/api/health` reads `true`. If it reads `false`, check §7 first: nothing below
that depends on `AppTraces` will show anything.

### 2.2 Correlating one request

`AppRequests.OperationId` is the trace id OpenTelemetry assigns per request;
the same value appears on the `AppDependencies`, `AppTraces` and
`AppExceptions` rows that request produced. Start from the failing
`AppRequests` row, then pivot:

```kql
AppRequests
| where TimeGenerated > ago(1h)
| where Url has "/api/v2/clients" and Success == false
| order by TimeGenerated desc
| take 20
```

```kql
let op = "<OperationId from the row above>";
union AppDependencies, AppTraces, AppExceptions
| where OperationId == op
| order by TimeGenerated asc
```

## 3. Paused or expired Fabric capacity

Every data path (payroll read, Gold read, Warehouse write) fails while
`/api/health` still reports `status: ok` — health does not check Fabric.
Symptoms: `ArtifactNotFound` on OneLake reads, or a connection error from the
Warehouse ODBC driver. Capacity state is an Azure Resource Graph fact (Fabric
capacity `state` = `Paused`), not a log; check it before reading logs further.

```kql
AppExceptions
| where TimeGenerated > ago(2h)
| where OuterMessage has "ArtifactNotFound" or OuterMessage has "artifact not found"
| project TimeGenerated, OperationId, OuterMessage, ProblemId
| order by TimeGenerated desc
```

```kql
AppTraces
| where TimeGenerated > ago(2h)
| where Message has_any ("Connect() timed out", "client error (Connect)", "operation timed out")
| project TimeGenerated, OperationId, Message, SeverityLevel
| order by TimeGenerated desc
```

The connect-timeout text is what `backend/data/source/from_fabric.py`'s
`_TRANSPORT_OPTIONS` is built to absorb (a 5 s connect timeout against a slow
but live capacity); the same text appearing in a burst with `health: ok` is
the "Active but unreachable" shape of a capacity problem, not a code defect.

## 4. Cold start and slow readiness

`/api/ready` answering `ready: false` for longer than a few tens of seconds
after a restart, or `warm.status` staying `"running"`:

```kql
AppServiceConsoleLogs
| where TimeGenerated > ago(30m)
| where _ResourceId has "app-tcc-api"
| order by TimeGenerated asc
```

```kql
AppTraces
| where TimeGenerated > ago(30m)
| where Message has_any ("warmup", "warm-up", "reap_stranded_runs")
| order by TimeGenerated asc
```

`backend/application/warmup.py` times each startup step; the OneLake open
alone is documented at 13–38 s against an Active capacity (the unauthenticated
equivalent answers in under a second, so the latency is the storage path, not
DNS or network). `TCC_WARM_ON_START=0` disables the background warm-up thread
if you need to measure a genuinely cold first request instead.

## 5. Warehouse write conflicts

`backend/infrastructure/persistence/tenant_sql.py` retries snapshot-isolation
conflicts (native errors 24556, 3960) and deadlocks (1205) up to 5 attempts
with 0.2 s doubling capped at 3.2 s, and logs each retry as a `warning` through
the `tcc.tenant_sql` logger — this is the exact text to search for:

```kql
AppTraces
| where TimeGenerated > ago(6h)
| where Message startswith "write conflict (attempt"
| project TimeGenerated, OperationId, Message, SeverityLevel
| order by TimeGenerated desc
```

A handful of these per large run is expected (concurrent Gold writes for the
same client-year). A row where `attempt 5/5` appears and the request still
failed means the retry budget was exhausted — check whether another run for
the same client is writing concurrently, which `tcc_ops.run_manifest` can
confirm (§7's query, filtered to `run_status = 'running'`).

## 6. 401/403 spikes (authentication)

Only meaningful under `AUTH_MODE=entra`. `backend/api/auth.py` raises 401 when
the bearer token does not verify (`WWW-Authenticate: Bearer` header) and 403
when it verifies but lacks the `user_impersonation` scope, the `TCC.User` app
role, or is not authorized for the requested client.

```kql
AppRequests
| where TimeGenerated > ago(1h)
| where ResultCode in ("401", "403")
| summarize count() by ResultCode, Url, bin(TimeGenerated, 5m)
| order by TimeGenerated desc
```

```kql
AppTraces
| where TimeGenerated > ago(1h)
| where SeverityLevel >= 3  // Warning and above
| where Message has_any ("401", "403", "not authorized for client")
| order by TimeGenerated desc
```

A 403 burst on one `client_id` with everything else healthy is
`AllClientsAuthorizer`-adjacent (D24: any authenticated caller with `TCC.User`
sees every client today, so a 403 here means the role/scope itself is missing,
not a per-client rule) — see `DEPLOYMENT-HANDOVER.md`'s known limitations.

## 7. 5xx and slow requests by route

```kql
AppRequests
| where TimeGenerated > ago(1h)
| where ResultCode startswith "5"
| summarize count() by Url, ResultCode
| order by count_ desc
```

```kql
AppRequests
| where TimeGenerated > ago(1h)
| where Success == true
| summarize avg(DurationMs), percentile(DurationMs, 95), count() by Url
| order by percentile_DurationMs_95 desc
| take 20
```

### The synchronous run and its front-end timeout

`POST /api/v2/clients/{id}/runs` is synchronous: the API computes the whole
run (`gunicorn --timeout 600`) before it answers. A caller going through the
web app can still hit App Service's front-end timeout (about 230 s) while the
run keeps going server-side. A `5xx`/timeout on this route in `AppRequests`
does **not** by itself mean the run failed — confirm it:

```
GET /api/v2/clients/{id}/runs/latest
```

`backend/api/trend.py`'s `latest_client_run` reads `tcc_ops.run_manifest` and
returns `run_status` (`running` / `success` / `failed` / `superseded`),
`run_id`, `run_started_at`, `run_completed_at`. A 404 means "not yet
calculated", which is a real state, not an error. If `run_status` is `success`
with a `run_completed_at`, the timeout was front-end only and the data is
correct; poll again if it is still `running`.

## 8. Artifact download denials

Every claim-package download is recorded in `tcc_ops.artifact_access`
(`outcome` is `served`, `denied` or `missing`) by
`backend/application/artifacts.py` / `backend/api/artifacts.py`, whether or
not it succeeded.

```sql
SELECT TOP 100 access_id, artifact_id, client_id, user_upn, accessed_at, outcome
FROM tcc_ops.artifact_access
WHERE outcome = 'denied'
ORDER BY accessed_at DESC;
```

```sql
-- Same artifact, every outcome, to see a retry sequence
SELECT access_id, user_upn, accessed_at, outcome
FROM tcc_ops.artifact_access
WHERE artifact_id = '<artifact_id>'
ORDER BY accessed_at;
```

Run this with `python scripts/run-sql.py --target deployed` (or any `pyodbc`
client against `WAREHOUSE_SERVER` / `WAREHOUSE_DATABASE`) — it is a durable
audit table, not a log.

## 9. Migrations state

```pwsh
python scripts/apply-migrations.py --target deployed --dry-run
```

Reports pending migrations against `tcc_ops.schema_migration` without applying
anything. `0 pending` is the expected steady state (confirmed after
provisioning). A non-zero count after a deploy that was supposed to migrate
means the post-provision hook did not run to completion — check
`scripts/postprovision.ps1`'s exit code from the `azd up` output, or re-run the
command above without `--dry-run`.

## 10. Deployment configuration refused at startup

`backend/application/deployment.py`'s `check_deployment_configuration()` raises
`DeploymentConfigurationError` before the API serves a single request if the
deployed settings are unsafe. The process will not start at all — there is no
`/api/health` to call. Read the exception text (it lists every problem found,
one per line) from `AppServiceConsoleLogs` or the Kudu log stream:

```kql
AppServiceConsoleLogs
| where TimeGenerated > ago(1h)
| where ResultDescription has "refusing to start"
| order by TimeGenerated desc
```

The messages it can raise, verbatim fragments to search for:

- `"refusing to start (ENVIRONMENT="` — the header line; everything after
  `- ` on the following lines is one specific problem.
- `"DATA_CLASSIFICATION is required when ENVIRONMENT is not 'local'"` —
  `DATA_CLASSIFICATION` app setting missing or blank.
- `"is not durable; a deployed environment must use 'warehouse'"` — one of
  `CLAIM_STORE` / `FINDING_STORE` / `RUN_MANIFEST_STORE` / `OVERRIDE_STORE` is
  not `warehouse` (or its `fabric` alias) outside a local environment.
- `"is not durable; a deployed environment must use 'blob'"` /
  `"...must use 'warehouse'"` — `ARTIFACT_STORE` / `ARTIFACT_REPOSITORY`.
- `"AUTH_MODE=entra needs AUTH_TENANT_ID"` / `"...needs API_AUDIENCE"` —
  enterprise profile misconfigured.
- `"AUTH_MODE=none is refused with DATA_CLASSIFICATION=customer"` — D26: the
  public profile's defaults (`AUTH_MODE=none`) must never be paired with real
  payroll.

Every one of these is a Terraform app-setting defect, not a code defect (see
[ENV-VARS.md](ENV-VARS.md) §1 for what sets each value) — fix the Terraform
variable or profile override and redeploy (§11), it is not safe to patch the
running app setting by hand and leave Terraform disagreeing with it.

## 11. Common operations

Full provisioning, verification and teardown steps are in
[DEPLOYMENT-HANDOVER.md](DEPLOYMENT-HANDOVER.md); this is the short form for a
support action once an environment already exists. Load the azd environment
into the shell first where a command needs its outputs:

```pwsh
azd env get-values | ForEach-Object { if ($_ -match '^([^=]+)="?(.*?)"?$') { Set-Item "env:$($Matches[1])" $Matches[2] } }
```

| Operation | Command | Notes |
|---|---|---|
| Redeploy code only (no infra change) | `azd deploy` (local azd environment) or dispatch `.github/workflows/deploy.yml` (`workflow_dispatch` only — there is no push trigger, D23) | `azd deploy` packages and zip-deploys both apps without re-running `terraform apply`; the postprovision hooks do not re-run |
| Full provision + deploy | `azd up --no-prompt` | Idempotent: a second `azd provision --preview` reports no changes |
| Run pending migrations | `python scripts/apply-migrations.py --target deployed` | Never pass `--bootstrap` against a Warehouse that already has `tcc_ops.schema_migration` — bootstrap is destructive and is gated to run only once, on a Warehouse Terraform just created (D22) |
| Re-grant Warehouse SQL | `python scripts/grant-warehouse-sql.py --target deployed` | `GRANT` is idempotent; re-run after rotating or recreating the API identity |
| Seed the operational store | `pwsh scripts/seed-operational-store.ps1` (add `-WhatIf` to preview) | Idempotent: writes nothing new once a client-year has an assertion seeded |
| Tear down a deployment | `azd down --purge --force --no-prompt`, then confirm `az group exists --name <rg>` reports `false` | `--purge` also purges the Foundry account (an explicit `azapi_resource_action.purge_on_destroy`, since azurerm's own purge flag does not reach an `azapi` resource) so nothing is left in Fabric/Foundry soft-delete. Observed teardown time was approximately 6–12 minutes |
| Rotate a credential | **Nothing to rotate.** The stack is keyless: `DefaultAzureCredential` and managed identity everywhere, Key Vault only exists behind `enable_key_vault` (default off) because there is no secret to hold | — |

## 12. Escalation facts

Capture all of the following before escalating; each identifies the same
event from a different table and none alone is enough to reproduce it:

| Fact | Where to get it |
|---|---|
| `run_id` / `run_status` | `GET /api/v2/clients/{id}/runs/latest`, or `tcc_ops.run_manifest` directly |
| `calculation_id` | Same response/table — the deterministic hash of the inputs and config that produced the figures |
| `code_commit` | Same table (`run_manifest.code_commit`); `"working-tree"` means `GIT_COMMIT` was not set in the azd/CI environment for that deploy (see [ENV-VARS.md](ENV-VARS.md) §1) |
| `OperationId` | The failing row in `AppRequests` (§2.2) — the key to pull every other telemetry row for that one request |
| Request path and `ResultCode` | `AppRequests.Url`, `AppRequests.ResultCode` |
| `artifact_id` / `access_id` | `tcc_ops.artifact_access`, for a download issue (§8) |
| Time window (UTC) and approximate `client_id` | Needed to bound every query above |
