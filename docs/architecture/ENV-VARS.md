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
| `CHANNEL_STORE` | `backend/application/deployment.py` (`store_choice`, used by `backend/application/wiring.py`) | The Microsoft 365 channel's audit trail (`tcc_ops.channel_audit`), writer allow-list (`channel_user`), confirmation tokens (`channel_confirmation`) and the narrator-agent trail (`agent_action_audit`). Default `sqlite` locally and `warehouse` once `ENVIRONMENT` is not `local`; a deployed process refuses an explicit `sqlite` or `memory`. Needs migrations `0001` and `0002` applied | unset (defaults to `warehouse` when deployed) | — | — | Enforced |
| `CHANNEL_WRITER_SOURCE` | `backend/application/deployment.py` (`writer_source`, used by `wiring.get_writer_entitlement`) | Who may make changes through the channel: `allowlist` (`tcc_ops.channel_user`, the default), `entra_group` (membership of `CHANNEL_WRITER_GROUP_ID`, via Graph `checkMemberGroups`) or `either`. An unknown value raises. Every source fails closed | unset (`allowlist`) | — | — | Enforced |
| `CHANNEL_WRITER_GROUP_ID` | `backend/application/deployment.py` | Object id of the Entra group whose members are writers. Needed for `entra_group` / `either`; the API's identity needs Graph `GroupMember.Read.All` (application) | unset | — | — | Enforced |
| `CHANNEL_ENFORCE_WRITER_FOR_USERS` | `backend/application/deployment.py` | `true` makes signed-in people (`TCC.User`) subject to the writer check too. Default off: the channel gateway is always checked, portal users keep writing as before | unset (off) | — | — | Enforced |
| `CHANNEL_CONFIRM_TTL_SECONDS` | `backend/application/deployment.py` | Lifetime of a prepare/commit confirmation token, 30–3600. Default 600 | unset (600) | — | — | Enforced |
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
| `FOUNDRY_PROJECT_ENDPOINT` | `backend/application/ai/settings.py`, `backend/infrastructure/ai/foundry_prompt_agents.py` | Foundry project endpoint. Unset: no agents are published and chat falls back to the scripted stream | TF api: `module.foundry.project_endpoint` | `FOUNDRY_PROJECT_ENDPOINT` | Same name, setting and output | No (chat degrades) |
| `FOUNDRY_MODEL` | `backend/application/ai/settings.py` | Model deployment name the `foundry` provider publishes agents with. Code default `gpt-5.4-mini` | TF api: `module.foundry.model` = variable `foundry_model` from azd `FOUNDRY_MODEL` (default `gpt-4.1-mini`). The deployment is named after the model | — | Setting from param `foundryModel` (default `gpt-5.4-mini`) | No |
| `AI_PROVIDER_CHAIN` | `settings.py` | Ordered providers; the first that answers wins, a failure before output falls to the next. `foundry` (default), `foundry_connection` (Foundry prompt agents on a BYOM connection), `gateway` (direct OpenAI-compatible calls). E.g. `foundry,gateway` or `gateway,foundry` | TF api: `ai_provider_chain` when set | — | new | No |
| `AI_PROVIDER_CHAIN__ROUTER`, `AI_PROVIDER_CHAIN__NARRATOR`, `AI_PROVIDER_CHAIN__ANALYSIS` | `settings.py` | Per-role override of the chain, e.g. narrator on the gateway and router on Foundry | not set | — | new | No |
| `AI_MODEL_ROUTER`, `AI_MODEL_NARRATOR`, `AI_MODEL_ANALYSIS` | `settings.py` | Model for a role on every provider. A provider-specific form wins: `AI_MODEL_NARRATOR__GATEWAY`, `__FOUNDRY`, `__FOUNDRY_CONNECTION`. Foundry falls back to `FOUNDRY_MODEL`; the gateway has no default and a missing name is an error | TF api: `ai_model_*` when set | — | new | Gateway: yes |
| `AI_FOUNDRY_CONNECTION_NAME` | `settings.py` | The Foundry model connection for `foundry_connection`; agents' models become `<connection>/<model>`. Prompt agents only — no Responses API, not with the Copilot harness | TF api: `ai_foundry_connection_name` when set | — | new | With that provider |
| `AI_EGRESS_POLICY` | `application/ai/egress.py` | `allow_all` (default) · `aggregates_only` · `block`, applied to providers outside Microsoft's boundary. An employee identifier or record token never enters a prompt, under any policy | TF api: `ai_egress_policy` | — | new | No |
| `AI_AGENT_VERSION_PINS` | `foundry_prompt_agents.py` | `AgentName=version,…` runs a published version instead of the latest: rollback is a setting | not set | — | new | No |
| `AI_TOKEN_BUDGET_DAILY`, `AI_TOKEN_BUDGET_PER_PRINCIPAL_DAILY` | `settings.py` | Daily token ceilings (global, per person). Unset = none. A call that would cross one is refused, not run | not set | — | new | No |
| `AI_INJECTION_GUARD`, `AI_OUTPUT_POLICY` | `safety/settings.py` | `on` (default) or `off`. The guard refuses to send a prompt carrying an instruction-override attempt; the policy withholds prose that links, gives addresses or identifier shapes, opens a code block or claims to be counsel. Both default ON and an `off` is logged at startup | `on` | — | new | No |
| `AI_OUTPUT_ALLOWED_HOSTS` | `safety/settings.py` | Comma-separated host suffixes the model's prose may link to (default none: the engine's blocks carry every link) | not set | — | new | No |
| `AI_CALL_TIMEOUT_SECONDS`, `AI_RETRY_MAX_ATTEMPTS`, `AI_RETRY_BASE_SECONDS`, `AI_RETRY_MAX_SECONDS`, `AI_TOTAL_DEADLINE_SECONDS`, `AI_BREAKER_FAILURE_THRESHOLD`, `AI_BREAKER_RESET_SECONDS`, `AI_BULKHEAD_MAX_CONCURRENT` | `settings.py` | Resilience: per-call timeout (30), attempts (3), backoff base/cap (0.5/8 s), total deadline across retries (45 s), breaker threshold (5) and reset (30 s), concurrent calls per provider (8) | not set | — | new | No |
| `AI_GATEWAY_ENDPOINT` | `gateway_settings.py` | The customer's model gateway, an `https://` base URL **without a path**. It needs the OpenAI-compatible chat-completions API with streaming and tool calling — **not** the Foundry Agents protocol | TF api, only when variable `ai_gateway_endpoint` is non-empty | — | new in v2 | With the `gateway` provider |
| `AI_GATEWAY_AUTH` | `gateway_settings.py` | `none` (mock/local only) · `api_key` · `oauth_client_credentials` · `entra_token`. **No default**: a gateway in the chain without it stops startup | TF api: `ai_gateway_auth` | — | new | With the `gateway` provider |
| `AI_GATEWAY_API_STYLE`, `AI_GATEWAY_API_VERSION` | `gateway_settings.py` | `openai_v1` (default; `/v1/chat/completions`, model in the body) or `azure_deployments` (`/openai/deployments/{model}/chat/completions?api-version=`) | TF api: `ai_gateway_api_style` | — | new | No |
| `AI_GATEWAY_API_KEY`, `AI_GATEWAY_API_KEY_HEADER`, `AI_GATEWAY_API_KEY_PREFIX` | `gateway_settings.py` | For `api_key`. The key is a **Key Vault reference only**; header default `Authorization`, prefix default `Bearer ` | key: TF api, only with `enable_key_vault` and `ai_gateway_api_key_secret_name` | — | new | Yes (secret) |
| `AI_GATEWAY_OAUTH_TOKEN_URL`, `AI_GATEWAY_OAUTH_CLIENT_ID`, `AI_GATEWAY_OAUTH_CLIENT_SECRET`, `AI_GATEWAY_OAUTH_SCOPE` | `gateway_settings.py` | For `oauth_client_credentials`. The secret is a **Key Vault reference only** | secret: only with `enable_key_vault` and `ai_gateway_oauth_secret_name` | — | new | Yes (secret) |
| `AI_GATEWAY_ENTRA_AUDIENCE` | `gateway_settings.py` | For `entra_token`: the audience the app's managed identity requests a token for. The preferred scheme — no secret anywhere | TF api: `ai_gateway_entra_audience` | — | new | With that scheme |
| `AI_GATEWAY_EXTRA_HEADERS` | `gateway_settings.py` | Non-secret headers as a JSON object | not set | — | new | No |
| `AI_GATEWAY_TIMEOUT_SECONDS`, `AI_GATEWAY_CONNECT_TIMEOUT_SECONDS` | `gateway_settings.py` | Read and connect timeouts (30 s, 5 s) | not set | — | new | No |
| `AI_GATEWAY_TLS_VERIFY` | `gateway_settings.py`, `deployment_check.py` | Default `true`. **`false` is refused when `ENVIRONMENT` is not `local`** | not set | — | new | No |
| `AI_GATEWAY_STREAMING`, `AI_GATEWAY_SUPPORTS_TOOLS` | `gateway_settings.py` | Default `true`. Streaming off reads one JSON body; tools off makes a planner use JSON-plan mode | not set | — | new | No |
| `WEBIQ_API_KEY`, `WEBIQ_BEARER_TOKEN`, `WEBIQ_BASE_URL` *(local)* | `backend/tools/webiq.py` | Live rule retrieval for the rules-ingestion agent. Base URL default `https://api.microsoft.ai/v3`. Without a key or token, live retrieval is unavailable | not set (a key is a secret and does not belong in app settings) | — | not set | No |

## 9. API host process

| Variable | Read by | Purpose / default | Deployed value | TF output | v1 Bicep | Required (deployed) |
|---|---|---|---|---|---|---|
| `WEB_CONCURRENCY` | `backend/startup.sh` | Gunicorn workers. Default `2` | TF api: variable `api_worker_count` (default `2`) | — | new in v2 | No |
| `PORT` | `backend/startup.sh` | Bind port. Default `8000` | App Service platform | — | n/a (container) | Set by platform |
| `TCC_WARM_ON_START` | `backend/application/warmup.py` | `0`/`false`/`no` disables the startup warm-up and Warehouse keepalive. Default `1`; skipped unless `DATA_SOURCE=lakehouse` | not set | — | not set | No |
| `TCC_KEEPALIVE_SECONDS` | `backend/application/warmup.py` | Warehouse pool keepalive interval. Default `30`, minimum `5` | not set | — | not set | No |
| `CAPABILITY_TIMEOUT_SECONDS` | `backend/application/capabilities/invoke.py` | How long one `POST /api/capabilities/{tool}` call may run before the caller gets a structured `504 timeout`. Default `25`; a bad value raises. The gateway's own `CHANNEL_REQUEST_TIMEOUT_SECONDS` (default 30) sits just above it | not set | — | new | No |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | App Service build (platform) | Build on deploy | TF platform: `true`, both apps | — | n/a (container images) | Platform |
| `WEBSITES_CONTAINER_START_TIME_LIMIT` | App Service (platform) | Start-up time limit, seconds | TF platform: `1800`, API | — | n/a | Platform |

## 9a. Channel gateway (`backend/channel`, only when `enable_m365_channel`)

The gateway is a third App Service app on the API's plan (`channel.main:app`, started by
`backend/startup-channel.sh`). `channel/config.py` reads these at startup and raises
`GatewayConfigurationError` naming every problem at once. It has **no unauthenticated
mode**: `AUTH_MODE` is not a gateway setting, and one set to anything but `entra` is
refused. Nothing below is a secret.

| Variable | Read by | Purpose / default | Deployed value | TF output | Required (deployed) |
|---|---|---|---|---|---|
| `TENANT_ID` | `backend/channel/config.py` | The Entra tenant every caller and every acting user must belong to. A GUID. No default | TF channel: variable `tenant_id` | — | Enforced |
| `GATEWAY_AUDIENCE` | `backend/channel/config.py` | The gateway's app registration: `api://<id>` or the bare client id (both accepted, like the API). Tokens for any other audience are a 401 | TF channel: variable `channel_gateway_audience` | `CHANNEL_GATEWAY_AUDIENCE` | Enforced |
| `API_BASE_URL` | `backend/channel/config.py` | Where the gateway reaches the API. Same variable name the web app uses | TF channel: `https://<API default hostname>` | `API_BASE_URL` | Enforced |
| `API_AUDIENCE` | `backend/channel/config.py` | The API registration the gateway's managed identity requests a token for (`<audience>/.default`) | TF channel: the API's own `API_AUDIENCE` | — | Enforced |
| `CHANNEL_STORE` | `backend/application/deployment.py` | The audit trail's store, as for the API. A deployed gateway refuses anything but `warehouse` | TF channel: `warehouse` (literal) | — | Enforced |
| `CHANNEL_ALLOWED_CALLER_APP_IDS` | `backend/channel/auth.py` | Comma-separated app ids that may call as the orchestrator **without** holding the `Channel.Invoke` role (a sandbox where the role cannot be assigned). Empty (default) is role-only. The path that authorised each call is logged | TF channel: variable `channel_allowed_caller_app_ids` | — | No |
| `CHANNEL_WRITER_SOURCE` | `backend/application/deployment.py` | As for the API: `allowlist` (default), `entra_group` or `either`. The gateway checks it on every `*_commit` and the API checks again | TF channel: variable `channel_writer_source` | — | Enforced |
| `CHANNEL_WRITER_GROUP_ID` | `backend/application/deployment.py` | The Entra group for `entra_group` / `either`; the gateway identity needs Graph `GroupMember.Read.All` | TF channel: variable `channel_writer_group_id` | — | Enforced when the source needs it |
| `CHANNEL_RATE_LIMIT_PER_MINUTE` | `backend/channel/config.py` | Calls per minute per user (token bucket, `1`–`6000`). Default `60`. Per process | not set | — | No |
| `CHANNEL_REQUEST_TIMEOUT_SECONDS` | `backend/channel/config.py` | How long the gateway waits for the API, `1`–`600`. Default `30`, above the API's own `CAPABILITY_TIMEOUT_SECONDS` | not set | — | No |
| `CHANNEL_DEBUG_WHOAMI` | `backend/channel/config.py` | `true` offers the `channel_ping` diagnostic (who the platform believes is calling, by which rule, whether the API answers). Never returns a token. Default off | not set | — | No |
| `WEB_CONCURRENCY` | `backend/startup-channel.sh` | Gunicorn workers. Default **`1`**: the fact ledger (`verify_figures`) and the rate limiter are per process | not set | — | No |
| `ENVIRONMENT`, `DATA_CLASSIFICATION` | `backend/application/deployment.py` | As for the API (a non-`local` environment switches the durable-store checks on) | TF channel: `azure`, from the profile | — | Enforced |
| `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE`, `FABRIC_WORKSPACE` | `backend/infrastructure/persistence/` | The Warehouse the audit trail is written to (the gateway holds `INSERT`/`SELECT` on `tcc_ops.channel_audit` only) | TF channel: the API's values | — | Enforced |
| `APPLICATIONINSIGHTS_CONNECTION_STRING`, `AZURE_CLIENT_ID` | `backend/telemetry.py` | Telemetry over the gateway's own managed identity (`Monitoring Metrics Publisher`); no key | TF channel | — | No |

The gateway authenticates to the API as itself: a managed-identity token (no secret) for
`API_AUDIENCE`, holding the app role `TCC.Agent`, plus `X-TCC-Acting-User` naming the
person it acts for.

## 9b. Channel orchestrator (`channel_orchestrator/`, a Foundry hosted agent)

A separate deployable: it is NOT an App Service app and Terraform does not set its variables.
They are supplied at deploy time (`azd env set`, or the `environment_variables` of the hosted-agent
version). The model-access settings are the **same `AI_*` variables as the API** (section 8), read by
the same `load_ai_settings`. The platform injects the reserved `FOUNDRY_*` names; never set those.

| Variable | Read by | Purpose / default | Deployed value | TF output | Required (deployed) |
|---|---|---|---|---|---|
| `CHANNEL_GATEWAY_URL` | `app/core/settings.py` | The gateway's `https://` base URL. The orchestrator calls `/channel/v1/tools/{tool}` and `/channel/v1/audit/narration` there. No default | `CHANNEL_BASE_URL` output | `CHANNEL_BASE_URL` | Enforced |
| `CHANNEL_GATEWAY_AUDIENCE` | `app/core/settings.py` | The gateway's app registration (`api://<id>`); the orchestrator's managed identity requests `<audience>/.default` and must hold `Channel.Invoke`. No default | same value as the gateway's `GATEWAY_AUDIENCE` | `CHANNEL_GATEWAY_AUDIENCE` | Enforced |
| `TENANT_ID` | `app/core/settings.py` | The Entra tenant (a GUID). A person from another tenant is refused before any call. No default | same as the gateway's | — | Enforced |
| `CHANNEL_NAME` | `app/core/settings.py` | `teams` (default) or `m365-copilot`: the `X-Channel` the gateway records | not set | — | No |
| `CHANNEL_MAX_TOOL_CALLS` | `app/core/settings.py` | Tools one turn may run, `1`–`20`. Default `6`. Eligibility under both methods counts as two | not set | — | No |
| `CHANNEL_CONFIRM_TTL_SECONDS` | `app/core/settings.py` | How long a prepared change waits for its owner's `confirm`, `30`–`3600`. Default `300` | not set | — | No |
| `CHANNEL_STATE_TTL_SECONDS` | `app/core/settings.py` | Idle time before a conversation's state (last client and year, pending change) is forgotten, `60`–`86400`. Default `3600`. In memory, per replica | not set | — | No |
| `CHANNEL_REQUEST_TIMEOUT_SECONDS` | `app/core/settings.py` | How long one gateway call may take, `5`–`300`. Default `40`, above the gateway's own `30` | not set | — | No |
| `CHANNEL_TURN_TIMEOUT_SECONDS` | `app/core/settings.py` | The deadline for a whole turn (tools, model, composition, audit), `10`–`600`. Default `90`. On expiry the person is told it took too long and nothing was changed; a confirm that times out is reported as unknown, never retried | not set | — | No |
| `CHANNEL_IDENTITY_SOURCES` | `app/core/settings.py` | Where the acting person's Entra object id may come from: `original-subject` (the platform's `x-ms-original-subject`), `platform` (`x-ms-user-identity`), `client-headers` (caller-supplied `x-client-*`; **opt-in**). Default `original-subject,platform`. With none resolvable the turn runs nothing | not set | — | No |
| `CHANNEL_DEBUG_WHOAMI` | `app/core/settings.py`, `app/host.py` | `true` answers the message `/whoami` with the identity signals received (header names, and values only for the identity fields) and what was resolved. Never a credential. Default off | not set | — | No |
| `AI_PROVIDER_CHAIN`, `AI_GATEWAY_*`, `AI_EGRESS_POLICY`, `AI_MODEL_*`, … | `application/ai/settings.py` (vendored) | Section 8, unchanged. `foundry` calls the agent's own Foundry account over its Azure OpenAI v1 surface with the agent's identity; `gateway` calls the customer's gateway. `foundry_connection` is refused (prompt agents only) | per customer | — | Per provider |
| `FOUNDRY_MODEL` | `app/wiring.py` | The `foundry` provider's model. Defaults to the platform-injected `AZURE_AI_MODEL_DEPLOYMENT_NAME` when unset | not set | — | No |
| `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_AGENT_NAME`, `FOUNDRY_AGENT_VERSION`, `AZURE_AI_MODEL_DEPLOYMENT_NAME`, `APPLICATIONINSIGHTS_CONNECTION_STRING` | platform | **Injected by the Foundry runtime; reserved.** The orchestrator reads the endpoint (to derive the account's model URL), the agent name and version (recorded on every narration audit row) and the model name | platform | — | Platform |
| `PYTHONNOUSERSITE` | the runtime | `1`. Dependencies are installed in the runtime environment, never with `pip install --user` | `1` in `azure.yaml` and the Dockerfile | — | Yes |
| `LOG_LEVEL` | `app/main.py` | Default `INFO`. Nothing logged carries a token, a header value or a message | not set | — | No |

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
| `TCC_ENABLE_M365_CHANNEL` | `enable_m365_channel` | `false` | public | The channel gateway app, its identity, telemetry role and diagnostic setting; outputs `CHANNEL_APP_NAME`, `CHANNEL_BASE_URL`, `GATEWAY_IDENTITY_NAME`. Needs `auth_mode = "entra"` and `api_client_id` |
| `TCC_CHANNEL_GATEWAY_AUDIENCE` | `channel_gateway_audience` | none | public (required with the toggle) | `GATEWAY_AUDIENCE` |
| `TCC_CHANNEL_WRITER_SOURCE` | `channel_writer_source` | `allowlist` | public | `CHANNEL_WRITER_SOURCE` |
| `TCC_CHANNEL_WRITER_GROUP_ID` | `channel_writer_group_id` | none | public (required unless `allowlist`) | `CHANNEL_WRITER_GROUP_ID` |
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
| `TCC_FOUNDRY_PUBLIC_NETWORK_ACCESS` | `foundry_public_network_access` | `false` | public | **Demo only.** Not an app setting: it changes two properties of the Foundry account (`publicNetworkAccess`, `networkAcls`). `true` enables the account's public endpoint (Entra-only, local auth off, private endpoint kept). Refused with the enterprise profile and customer data. Output `network_posture` |
| `TCC_FOUNDRY_ALLOWED_IP_RANGES` | `foundry_allowed_ip_ranges` | empty | public | **Demo only.** Comma-separated IPv4 CIDRs allowed through the account firewall when the toggle is on; empty allows any address |

Terraform variables with no azd mapping, settable only through a tfvars
overlay (`*.auto.tfvars`, `infra/profiles/*.tfvars`, or `TF_VARS_JSON` in
`deploy.yml`): `auth_mode`, `data_classification`, `create_fabric`,
`manage_fabric_access`, `create_network`, `web_inbound`, `web_allowed_ip_ranges`,
`enable_key_vault`, `api_worker_count`, `vnet_address_space`,
`private_dns_zone_ids`, `fabric_capacity_sku`, `fabric_workspace_role`,
`foundry_deployment_sku`, `foundry_capacity`, `ai_gateway_endpoint`,
`channel_allowed_caller_app_ids`, `channel_allowed_ip_ranges`, `channel_debug_whoami`,
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
