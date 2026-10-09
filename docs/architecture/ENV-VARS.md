# Environment variables: v1 Bicep to v2 Terraform parity

Requirement **TF-6**. Every environment variable the application, its scripts and
its tests read, where a deployed environment gets it, and what carried it before
Terraform replaced Bicep.

Sources:

- Runtime reads: `backend/` (`os.getenv`, `os.environ`), `backend/startup.sh`,
  `frontend/server/` (`process.env`), `frontend/src/api.js` (`import.meta.env`).
- Deployed values: [`infra/main.tf`](../../infra/main.tf) (`api_app_settings`),
  [`infra/modules/app_service/main.tf`](../../infra/modules/app_service/main.tf)
  (platform settings, web settings), [`infra/outputs.tf`](../../infra/outputs.tf),
  [`infra/main.tfvars.json`](../../infra/main.tfvars.json),
  [`azure.yaml`](../../azure.yaml), [`scripts/postprovision.ps1`](../../scripts/postprovision.ps1),
  [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml).
- v1: `infra/main.bicep` and `infra/main.parameters.json`, deleted during the
  infrastructure rewrite. Read them with `git show 7083a1d^:infra/main.bicep`. Cosmos settings
  were removed one commit range earlier (A05, `git show a0cddef^:infra/main.bicep`).

Related: [RUNBOOK.md](RUNBOOK.md) (support), [DEPLOYMENT-HANDOVER.md](DEPLOYMENT-HANDOVER.md)
(operator inputs), [ADR-007](ADR-007-warehouse-operational-store.md) (Warehouse
replaces Cosmos).

## How to read the tables

| Column | Meaning |
|---|---|
| Read by | File that reads the variable. Paths are relative to the repo root |
| Default | Value the code uses when the variable is unset |
| Deployed value | Where a deployed environment gets it. "TF api" = an API app setting in `infra/main.tf`; "TF platform" = a setting in `infra/modules/app_service/main.tf` |
| TF output | The `infra/outputs.tf` output carrying the same value into the azd environment, or `—` |
| v1 Bicep | What `infra/main.bicep` did with it. "not set" = Bicep never set it; "new in v2" = Terraform sets it and Bicep did not; "removed in v2" = Bicep set it and Terraform does not |
| Required (deployed) | **Enforced**: `backend/application/deployment.py` refuses to start without a valid value. **Functional**: the app starts but the named feature fails. **No**: optional |

Local-only variables are marked *(local)*. Nothing below is a secret: every
deployed setting is non-secret by design (HOST-5), and the stack holds no key to
rotate.

## 1. Deployment posture and safety

Checked at startup by `check_deployment_configuration()` before the API serves a
request. A failure raises `DeploymentConfigurationError` ("refusing to start");
see [RUNBOOK.md §8](RUNBOOK.md#8-deployment-configuration-refused-at-startup).

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `ENVIRONMENT` | `backend/application/deployment.py` | `local` (default) or anything else, which means deployed and switches on the durable-store, classification and auth checks | TF api: `azure` | — | new in v2 | Enforced (its value turns enforcement on) |
| `DATA_CLASSIFICATION` | `backend/application/deployment.py` | `synthetic` or `customer`. No default; never inferred | TF api: profile matrix in `infra/locals.tf` (public `synthetic`, enterprise `customer`); override with Terraform variable `data_classification` | `DATA_CLASSIFICATION` | new in v2 | Enforced |
| `AUTH_MODE` | `backend/application/deployment.py`, `backend/api/auth.py` | `none` (default) or `entra`. `none` with `customer` is refused when deployed | TF api: profile matrix (public `none`, enterprise `entra`); override with `auth_mode` | `AUTH_MODE` | new in v2 | Enforced |
| `GIT_COMMIT` | `backend/application/commands/run_client_calculation.py`, `backend/tools/reference_runner.py` | Commit stamped on every run (`run_manifest.code_commit`). Unset: `git rev-parse HEAD`, else `working-tree` | TF api: variable `git_commit` from azd `GIT_COMMIT`; `deploy.yml` sets `TF_VAR_git_commit` to the workflow commit | — | Same: param `gitCommit` from azd `GIT_COMMIT` | No (runs record `working-tree`) |
| `LOG_LEVEL` | `backend/main.py` | Python root log level. Default `INFO` | not set | — | not set | No |
| `TCC_STRANDED_RUN_MINUTES` | `backend/infrastructure/persistence/fabric_warehouse.py` | Minutes a run may stay `running` before the startup reaper marks it failed. Default `60` | not set | — | not set | No |

## 2. Payroll source (Fabric Lakehouse over OneLake)

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `DATA_SOURCE` | `backend/tools/fabric_source.py`, `backend/tools/reference_workspace.py`, `backend/application/warmup.py` (via `active_data_source`) | `lakehouse` (default), `fabric` (flattened slice) or `csv` (test fixture, not deployable). `flex` is a deprecated alias for `lakehouse`; unknown values resolve to `lakehouse` | TF api: `lakehouse` | — | v1: param `dataSource` (azd `DATA_SOURCE`, default `flex`) | Functional |
| `FABRIC_WORKSPACE` | `backend/data/source/from_fabric.py`, `backend/tools/fabric_source.py`, `backend/data/source/load_fabric.py`, `backend/data/source/to_delta.py` | Workspace name or id in OneLake paths. No default | TF api: `module.fabric.workspace_name` (created workspace, or azd `TCC_FABRIC_WORKSPACE_NAME`) | `FABRIC_WORKSPACE` | Setting from param `fabricWorkspace` (azd `FABRIC_WORKSPACE`); not an output | Functional (every payroll read) |
| `FABRIC_LAKEHOUSE` | as above, plus `backend/infrastructure/persistence/source_sql.py` | Lakehouse name. No default | TF api: `module.fabric.lakehouse_name` (created, or azd `TCC_FABRIC_LAKEHOUSE_NAME`) | `FABRIC_LAKEHOUSE` | Setting from param `fabricLakehouse` (azd `FABRIC_LAKEHOUSE`); not an output | Functional |
| `SOURCE_SCHEMA` | `backend/config.py`, `backend/data/source/from_fabric.py`, `backend/data/source/to_delta.py`, `backend/infrastructure/persistence/source_sql.py`, `scripts/postprovision.ps1` | Lakehouse schema holding source payroll. Default `tcc_source`; a customer overlay can select an existing schema such as `flex` | TF api: variable `source_schema` from azd `SOURCE_SCHEMA` | `SOURCE_SCHEMA` | new in v2 | Functional (every source-table read) |
| `FABRIC_EMPLOYEES_TABLE` | `backend/tools/fabric_source.py` | Table for `DATA_SOURCE=fabric` only. Default `dbo/employees` | not set | — | removed in v2 (was param `fabricEmployeesTable`) | No |
| `FLEX_ACCOUNT_ID` | `backend/infrastructure/payroll/pay_period_source.py` | Account the configured reference client is read under (warm-up, single-client paths). Default `1001` | not set (code default applies) | — | removed in v2 (was param `flexAccountId`, azd `FLEX_ACCOUNT_ID`) | No |
| `REFERENCE_ACCESS_OUTPUT_PATH` *(local)* | `backend/tools/reference_workspace.py` | Path to the partner's Access output for the sealed comparison | not set | — | not set | No |

## 3. Fabric Warehouse (`tcc_gold`, `tcc_ops`)

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `WAREHOUSE_SERVER` | `backend/infrastructure/persistence/fabric_warehouse.py`, `scripts/sql_common.py`, `scripts/seed-operational-store.ps1`, `scripts/postprovision.ps1` | Warehouse SQL endpoint host. No default | TF api: `module.fabric.warehouse_server` (created Warehouse's connection string, or azd `TCC_WAREHOUSE_SERVER`) | `WAREHOUSE_SERVER` | Setting from param `warehouseServer` (azd `WAREHOUSE_SERVER`); not an output | Functional (every Gold read and every `warehouse` store) |
| `WAREHOUSE_DATABASE` | same as above | Warehouse database (item display name). No default | TF api: `module.fabric.warehouse_database` (created, or azd `TCC_WAREHOUSE_DATABASE`) | `WAREHOUSE_DATABASE` | Setting from param `warehouseDatabase`; not an output | Functional |
| `WAREHOUSE_ODBC_DRIVER` | `backend/infrastructure/persistence/fabric_warehouse.py` | ODBC driver name. Default `ODBC Driver 18 for SQL Server` | not set | — | not set | No |
| `WAREHOUSE_CONNECT_TIMEOUT` | `backend/infrastructure/persistence/fabric_warehouse.py` | Connect timeout, seconds. Default `90` | not set | — | not set | No |
| `GOLD_SCHEMA` | `backend/config.py` (also every SQL script through it) | Read schema. Default `tcc_gold`. A non-identifier is refused at import | not set | — | not set (v1 schemas were `flex_*`) | No. If set, set it identically for the API and the scripts |
| `OPS_SCHEMA` | `backend/config.py` | Operational schema. Default `tcc_ops`. Same rule | not set | — | not set | No. Same rule |

## 4. Operational stores

Accepted values: `warehouse` (durable; `fabric` is the v1 alias), `sqlite`,
`memory`. A deployed process refuses anything but `warehouse`.

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `CLAIM_STORE` | `backend/application/deployment.py` (`store_choice`, used by `backend/application/wiring.py`), `backend/tools/purge_test_claims.py`; set by `scripts/seed-operational-store.ps1` | Claims and engagements. Default `sqlite` | TF api: `warehouse` | — | `cosmos` until A05, then `warehouse` | Enforced |
| `FINDING_STORE` | `backend/application/deployment.py`; set by `scripts/seed-operational-store.ps1` | Finding resolutions. Default `sqlite` | TF api: `warehouse` | — | `cosmos` until A05, then `warehouse` | Enforced |
| `RUN_MANIFEST_STORE` | `backend/application/deployment.py` | Run manifests. Default `memory` | TF api: `warehouse` | — | param `runManifestStore`, default `fabric` (the v1 alias) | Enforced |
| `OVERRIDE_STORE` | `backend/application/deployment.py` | Overrides. Default: follows `RUN_MANIFEST_STORE` | TF api: `warehouse` | — | not set (followed `RUN_MANIFEST_STORE`) | Enforced |
| `OPERATIONAL_DB` *(local)* | `backend/infrastructure/persistence/sqlite_claims.py`, `sqlite_findings.py`, `sqlite_artifacts.py`, `backend/tools/purge_test_claims.py` | SQLite file for the `sqlite` adapters. Default `backend/data/operational.db` | not set | — | not set | No |

## 5. Artifacts (Blob Storage)

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `ARTIFACT_STORE` | `backend/application/deployment.py` | Artifact bytes: `local` (default) or `blob` | TF api: `blob` | — | new in v2 | Enforced (`blob`) |
| `ARTIFACT_REPOSITORY` | `backend/application/deployment.py` | Artifact rows (`tcc_ops.artifact`, `artifact_access`): `sqlite` (default) or `warehouse` | TF api: `warehouse` | — | new in v2 | Enforced (`warehouse`) |
| `ARTIFACT_BLOB_ACCOUNT_URL` | `backend/infrastructure/storage/blob_store.py`; `backend/tests/contracts/conftest.py` | Blob endpoint. No default | TF api: `module.storage.blob_endpoint` | `ARTIFACT_BLOB_ACCOUNT_URL` | new in v2 | Functional (claim packages, downloads) |
| `OUTPUTS_RETENTION_DAYS` | `backend/application/wiring.py` | `retain_until` stamped on new artifacts. Default `2555` | TF api: variable `outputs_retention_days` (default `2555`; the same variable sets the `outputs` lifecycle policy) | — | new in v2 | No |
| `ARTIFACT_LOCAL_ROOT` *(local)* | `backend/infrastructure/storage/local_store.py` | Root for `local` artifact bytes. Default `backend/data/artifacts` | not set | — | not set | No |

## 6. Authentication (API) and Easy Auth (web)

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `AUTH_TENANT_ID` | `backend/application/deployment.py` (`auth_tenant_id`, used by the token validator in `backend/application/wiring.py`) | Tenant whose tokens the API accepts. Falls back to `AZURE_TENANT_ID` | TF api, only when `AUTH_MODE=entra`: azd `TCC_TENANT_ID`, else the deploying principal's tenant | — | new in v2 | Enforced when `AUTH_MODE=entra` |
| `AZURE_TENANT_ID` | `backend/application/deployment.py` | Fallback for `AUTH_TENANT_ID` only | not set on the apps | — | not set | No |
| `API_AUDIENCE` | `backend/application/deployment.py`, `backend/application/wiring.py` | Audience the API validates | TF api, only when `entra`: azd `TCC_API_AUDIENCE`, else `api://<TCC_API_CLIENT_ID>` | — | new in v2 | Enforced when `AUTH_MODE=entra` |
| `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID` | App Service Easy Auth (platform), web app | Web identity's client id; Easy Auth uses a managed-identity federated credential instead of a client secret | TF platform (web), only when Easy Auth is on (enterprise) | — | new in v2 | Functional when Easy Auth is on |

## 7. Identity and telemetry

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `AZURE_CLIENT_ID` | `backend/telemetry.py` (`managed_identity_client_id`); also honoured by `azure-identity`'s `DefaultAzureCredential` | Selects the app's user-assigned identity | TF platform: API identity client id on the API, web identity client id on the web | `API_IDENTITY_CLIENT_ID` (API only) | One shared identity's client id on the API | Functional (identity-based access to Warehouse, OneLake, Blob, Foundry, App Insights) |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | `backend/telemetry.py`, `backend/main.py` (`/api/health` `telemetry_configured`) | Enables Azure Monitor OpenTelemetry. Unset: telemetry off | TF platform: both apps, from `module.monitoring` (sensitive; not an output). On the web app no code in `frontend/server` reads it | — | API only | No (but the runbook's App* tables depend on it) |
| `APPLICATIONINSIGHTS_AUTHENTICATION_STRING` | not read by application code (the API passes a credential explicitly in `backend/telemetry.py`) | `Authorization=AAD;ClientId=<identity>` for Entra-authenticated ingestion | TF platform: both apps | — | new in v2 | No |

## 8. AI (Foundry)

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | `backend/main.py`, `backend/agents/factory.py` | Foundry project endpoint. Unset: agents are not registered and chat falls back to the scripted stream | TF api: `module.foundry.project_endpoint` | `FOUNDRY_PROJECT_ENDPOINT` | Same name, setting and output | No (chat degrades) |
| `FOUNDRY_MODEL` | `backend/main.py`, `backend/agents/factory.py` | Model deployment name. Code default `gpt-5.4-mini` | TF api: `module.foundry.model` = variable `foundry_model` from azd `FOUNDRY_MODEL` (default `gpt-4.1-mini`). The deployment is named after the model | — | Setting from param `foundryModel` (default `gpt-5.4-mini`) | No |
| `AI_GATEWAY_ENDPOINT` | not read by backend code | Optional AI gateway (AI-2); must carry the Foundry Agents protocol | TF api, only when variable `ai_gateway_endpoint` is non-empty (tfvars overlay only) | — | new in v2 | No |
| `WEBIQ_API_KEY`, `WEBIQ_BEARER_TOKEN`, `WEBIQ_BASE_URL` *(local)* | `backend/tools/webiq.py` | Live rule retrieval for the rules-ingestion agent. Base URL default `https://api.microsoft.ai/v3`. Without a key or token, live retrieval is unavailable | not set (a key is a secret and does not belong in app settings) | — | not set | No |

## 9. API host process

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `WEB_CONCURRENCY` | `backend/startup.sh` | Gunicorn workers. Default `2` | TF api: variable `api_worker_count` (default `2`) | — | new in v2 | No |
| `PORT` | `backend/startup.sh` | Bind port. Default `8000` | App Service platform | — | n/a (container) | Set by platform |
| `TCC_WARM_ON_START` | `backend/application/warmup.py` | `0`/`false`/`no` disables the startup warm-up and Warehouse keepalive. Default `1`; skipped unless `DATA_SOURCE=lakehouse` | not set | — | not set | No |
| `TCC_KEEPALIVE_SECONDS` | `backend/application/warmup.py` | Warehouse pool keepalive interval. Default `30`, minimum `5` | not set | — | not set | No |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | App Service build (platform) | Build on deploy | TF platform: `true`, both apps | — | n/a (container images) | Platform |
| `WEBSITES_CONTAINER_START_TIME_LIMIT` | App Service (platform) | Start-up time limit, seconds | TF platform: `1800`, API | — | n/a | Platform |

## 10. Web app (Express BFF) and SPA build

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `API_BASE_URL` | `frontend/server/app.js`, `frontend/server/index.js` | Proxy target for `/api`. Unset: `/api` answers 503 and `/healthz` reports `api_configured: false` | TF platform (web): `https://<API default hostname>` | `API_BASE_URL` (same value) | Bicep output `API_BASE_URL` existed (Container Apps FQDN); the web container used `API_BACKEND_URL` / `API_BACKEND_HOST` instead | Functional |
| `PORT`, `WEBSITES_PORT` | `frontend/server/index.js` | Listen port. Default `8080` | App Service platform | — | n/a | Set by platform |
| `VITE_API_BASE` *(build time)* | `frontend/src/api.js` | API base baked into the bundle. Default empty: same-origin `/api` | not set | — | not set | No |
| `API_BACKEND_URL`, `API_BACKEND_HOST` | `frontend/nginx.conf` (envsubst template) | v1 nginx proxy target | not set; `nginx.conf` and `Dockerfile` are excluded by `frontend/.webappignore` and not deployed | — | removed in v2 | No |

## 11. Removed with Cosmos (A05, before Terraform)

| Variable | v1 Bicep | v2 |
|---|---|---|
| `COSMOS_ENDPOINT` | API setting and output | removed; nothing in `backend/` reads it ([ADR-007](ADR-007-warehouse-operational-store.md)) |
| `COSMOS_DATABASE` | API setting and output | removed |
| `COSMOS_ACCOUNT_NAME` | output | removed |

## 12. Scripts, hooks and CI

Values the post-provision hooks and `deploy.yml` read. azd exports the
environment (including Terraform outputs) to hooks; `deploy.yml` copies the
outputs it needs into `$GITHUB_ENV` after `terraform apply`.

| Variable | Read by | Purpose | Source |
|---|---|---|---|
| `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE` | `scripts/sql_common.py`, `scripts/seed-operational-store.ps1`, `scripts/postprovision.ps1` | Connect, and check the resolved target | TF outputs |
| `FABRIC_WORKSPACE_ID`, `FABRIC_WAREHOUSE_ID` | `scripts/sql_common.py`, `scripts/postprovision.ps1` | Target `deployed`: the guard resolves these through the Fabric API before any SQL runs | TF outputs (new in v2) |
| `TCC_FABRIC_CREATED` | `scripts/sql_common.py`, `scripts/postprovision.ps1`, `deploy.yml` | `true` only when this apply created the Warehouse; the only case the destructive bootstrap may run (D22) | TF output (new in v2) |
| `API_IDENTITY_NAME` | `scripts/grant-warehouse-sql.py` | Principal for the T-SQL grants | TF output (new in v2) |
| `TCC_PROFILE` | `scripts/postprovision.ps1` | `public` runs the synthetic load | azd input, echoed as TF output |
| `SOURCE_SCHEMA`, `FABRIC_WORKSPACE`, `FABRIC_LAKEHOUSE` | `scripts/postprovision.ps1`, `backend/data/source/load_fabric.py` | Synthetic load target | TF outputs |
| `GOLD_SCHEMA`, `OPS_SCHEMA` | every SQL script via `backend/config.py` | Schema names | unset (defaults) |
| `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | `deploy.yml` | OIDC login; mapped to `ARM_*` and `FABRIC_CLIENT_ID` / `FABRIC_TENANT_ID` (with `ARM_USE_OIDC`, `FABRIC_USE_OIDC`) | GitHub repository or environment variables ([OIDC-SETUP.md](OIDC-SETUP.md)) |
| `AZURE_ENV_NAME`, `AZURE_LOCATION`, `AZURE_RESOURCE_GROUP` | `deploy.yml` | `TF_VAR_environment_name`, `TF_VAR_location`, `TF_VAR_resource_group_name`; target assertion | GitHub variables |
| `TF_BACKEND_RESOURCE_GROUP`, `TF_BACKEND_STORAGE_ACCOUNT`, `TF_BACKEND_CONTAINER` | `deploy.yml` | Remote state; the run fails without them (D23) | GitHub variables |
| `TF_VARS_JSON` | `deploy.yml` | Enterprise BYO inputs, written to `deploy.auto.tfvars.json` | GitHub variable (no secrets) |
| `TCC_REPO_ROOT` *(local)* | `backend/tools/verify_reference_independent.py` | Repo root override | unset |

## 13. Tests only

| Variable | Read by | Purpose |
|---|---|---|
| `TCC_REQUIRE_PARITY` | `backend/tests/test_engine_parity_reference.py`, `backend/tests/test_flex_roundtrip.py` | `1` turns a missing-fixture skip of the parity gate into a collection error |
| `TCC_FABRIC_TESTS` | live-Fabric tests under `backend/tests/` | `1` opts in to tests that read the Lakehouse and Warehouse |
| `TCC_AZURE_TESTS` | `backend/tests/contracts/conftest.py` | `1` (with `ARTIFACT_BLOB_ACCOUNT_URL`) runs the artifact store contract against Blob |
| `DATA_SOURCE` | `backend/tests/conftest.py` | Pinned to `csv` for the whole suite; never taken from `.env` |
| `FABRIC_WORKSPACE`, `FABRIC_LAKEHOUSE`, `FABRIC_EMPLOYEES_TABLE`, `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE` | `backend/tests/conftest.py` | Copied from `backend/.env` when unset, for the opt-in live tests |

## 14. azd environment values the operator sets

`azd env set NAME value`, then `azd up --no-prompt`.
[`infra/main.tfvars.json`](../../infra/main.tfvars.json) maps each into a
Terraform variable. These are inputs, not app settings: Terraform turns them
into the settings above. Full guidance is in [DEPLOYMENT-HANDOVER.md](DEPLOYMENT-HANDOVER.md).

| azd value | Terraform variable | Default | Profile | Becomes |
|---|---|---|---|---|
| `TCC_PROFILE` | `profile` | `public` | both | Every profile default in `infra/locals.tf`; output `TCC_PROFILE` |
| `AZURE_ENV_NAME` | `environment_name` | written by azd | both | Resource names, `azd-env-name` tag |
| `AZURE_LOCATION` | `location` | none | both | Region; output `AZURE_LOCATION` |
| `AZURE_RESOURCE_GROUP` | `resource_group_name` | `rg-<env>` | both | Output `AZURE_RESOURCE_GROUP` |
| `AZURE_SUBSCRIPTION_ID` | `subscription_id` | written by azd | both | Provider subscription |
| `TCC_TENANT_ID` | `tenant_id` | deploying principal's tenant | enterprise | `AUTH_TENANT_ID`, Easy Auth issuer |
| `GIT_COMMIT` | `git_commit` | empty | both | `GIT_COMMIT` |
| `FABRIC_CAPACITY_ADMIN` | `fabric_capacity_admin` | none | public (`create_fabric`) | Capacity administrator; required when Fabric is created |
| `TCC_WEB_CLIENT_ID` | `web_client_id` | none | enterprise (required) | Easy Auth client id |
| `TCC_API_CLIENT_ID` | `api_client_id` | none | enterprise (required) | `API_AUDIENCE` when `TCC_API_AUDIENCE` is empty |
| `TCC_API_AUDIENCE` | `api_audience` | `api://<api client id>` | enterprise | `API_AUDIENCE` |
| `TCC_APP_SUBNET_ID` | `app_integration_subnet_id` | none | enterprise (required) | VNet integration subnet |
| `TCC_PRIVATE_ENDPOINT_SUBNET_ID` | `private_endpoint_subnet_id` | none | enterprise (required) | Private endpoint subnet |
| `TCC_FABRIC_WORKSPACE_ID` | `fabric_workspace_id` | none | enterprise (required) | Output `FABRIC_WORKSPACE_ID` |
| `TCC_FABRIC_WORKSPACE_NAME` | `fabric_workspace_name` | created workspace | enterprise | `FABRIC_WORKSPACE` |
| `TCC_FABRIC_LAKEHOUSE_NAME` | `fabric_lakehouse_name` | created Lakehouse | enterprise | `FABRIC_LAKEHOUSE` |
| `TCC_FABRIC_WAREHOUSE_ID` | `fabric_warehouse_id` | none | enterprise (required) | Output `FABRIC_WAREHOUSE_ID` |
| `TCC_WAREHOUSE_SERVER` | `warehouse_server` | created Warehouse | enterprise (required) | `WAREHOUSE_SERVER` |
| `TCC_WAREHOUSE_DATABASE` | `warehouse_database` | created Warehouse | enterprise (required) | `WAREHOUSE_DATABASE` |
| `SOURCE_SCHEMA` | `source_schema` | `flex` | both | `SOURCE_SCHEMA` |
| `FOUNDRY_MODEL` | `foundry_model` | `gpt-4.1-mini` | both | `FOUNDRY_MODEL`, deployment name |
| `FOUNDRY_MODEL_VERSION` | `foundry_model_version` | `2025-04-14` | both | Model version (not an app setting) |
| `TCC_APP_SERVICE_SKU` | `app_service_sku` | `P1v3` | both | Plan SKU (not an app setting) |

Terraform variables with no azd mapping, settable only through a tfvars
overlay (`*.auto.tfvars`, `infra/profiles/*.tfvars`, or `TF_VARS_JSON` in
`deploy.yml`): `auth_mode`, `data_classification`, `create_fabric`,
`manage_fabric_access`, `create_network`, `web_inbound`, `web_allowed_ip_ranges`,
`enable_key_vault`, `api_worker_count`, `vnet_address_space`,
`private_dns_zone_ids`, `fabric_capacity_sku`, `fabric_workspace_role`,
`foundry_deployment_sku`, `foundry_capacity`, `ai_gateway_endpoint`,
`outputs_retention_days`, `tags`.

### v1 azd values that no longer exist

From the deleted `infra/main.parameters.json`: `CONTAINER_APPS_LOCATION`,
`FOUNDRY_MODEL_SKU` (now Terraform variable `foundry_deployment_sku`, overlay
only), `DATA_SOURCE`, `FLEX_ACCOUNT_ID`, `FABRIC_EMPLOYEES_TABLE`,
`RUN_MANIFEST_STORE`, `SERVICE_API_IMAGE_NAME`, `SERVICE_WEB_IMAGE_NAME`,
`AZURE_PRINCIPAL_ID`. `FABRIC_WORKSPACE`, `FABRIC_LAKEHOUSE`,
`WAREHOUSE_SERVER` and `WAREHOUSE_DATABASE` were inputs in v1; in v2 they are
Terraform **outputs**, and the enterprise inputs are the `TCC_`-prefixed names
above.

## 15. Output parity: Bicep to Terraform

| v1 Bicep output | v2 Terraform output | Note |
|---|---|---|
| `AZURE_LOCATION` | `AZURE_LOCATION` | unchanged |
| `AZURE_RESOURCE_GROUP` | `AZURE_RESOURCE_GROUP` | unchanged |
| `API_APP_NAME` | `API_APP_NAME` | Container App name, now App Service `app-tcc-api-<suffix>` |
| `WEB_APP_NAME` | `WEB_APP_NAME` | now `app-tcc-web-<suffix>` |
| `API_BASE_URL` | `API_BASE_URL` | now the API App Service hostname. Reachable only from the web app's integration subnet; a direct call returns 403 |
| `WEB_BASE_URL` | `WEB_BASE_URL` | now the web App Service hostname |
| `FOUNDRY_PROJECT_ENDPOINT` | `FOUNDRY_PROJECT_ENDPOINT` | unchanged |
| `AZURE_CONTAINER_REGISTRY_ENDPOINT` | — | removed in v2: code deploy, no registry |
| `AZURE_CONTAINER_REGISTRY_NAME` | — | removed in v2 |
| `AZURE_CONTAINER_APPS_ENVIRONMENT_NAME` | — | removed in v2: App Service plan |
| `COSMOS_ENDPOINT`, `COSMOS_ACCOUNT_NAME`, `COSMOS_DATABASE` | — | removed in A05 |
| — | `TCC_PROFILE`, `AUTH_MODE`, `DATA_CLASSIFICATION` | new: resolved profile |
| — | `API_IDENTITY_NAME`, `API_IDENTITY_CLIENT_ID`, `API_IDENTITY_PRINCIPAL_ID` | new: the API's own identity (v1 had one shared identity) |
| — | `ARTIFACT_BLOB_ACCOUNT_URL` | new |
| — | `FABRIC_WORKSPACE_ID`, `FABRIC_WORKSPACE`, `FABRIC_LAKEHOUSE`, `FABRIC_WAREHOUSE_ID`, `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE`, `SOURCE_SCHEMA`, `TCC_FABRIC_CREATED` | new: Fabric is in Terraform (created or brought) |
| — | `api_role_assignments`, `web_role_assignments`, `easy_auth_enabled` | new, lower case: for review, not used by hooks |
