# Infrastructure Component Specification

**Requirement** INF-1 / DOC-4 · **Audience** the customer's infrastructure
architect · **Source of truth** the Terraform in [`infra/`](../../infra/)

This document describes every Azure and Fabric resource the Terraform creates.
For each one it gives the SKU, runtime, settings, identity, roles, network,
diagnostics, tags, and the module and variables that control it. You can read
it without opening the Terraform. Every value comes from these files:

- [`infra/providers.tf`](../../infra/providers.tf)
- [`infra/variables.tf`](../../infra/variables.tf)
- [`infra/locals.tf`](../../infra/locals.tf)
- [`infra/main.tf`](../../infra/main.tf)
- [`infra/outputs.tf`](../../infra/outputs.tf)
- `infra/modules/*/main.tf` (each module declares its variables in the same file)

If a value isn't set in Terraform, this document says so. In that case the
Azure platform default applies, or it's the customer's decision.

[CONNECTIVITY-MATRIX.md](CONNECTIVITY-MATRIX.md) covers who talks to what, and
with which identity.

---

## 1. Profiles

`TCC_PROFILE` selects a profile through `azd env set TCC_PROFILE
public|enterprise`. [`infra/main.tfvars.json`](../../infra/main.tfvars.json)
maps it to the variable `profile`. `locals.tf` resolves the D25 matrix once,
and every module reads those locals. If a variable is `null`, it takes the
profile default.

| Setting (local) | `public` | `enterprise` | Override variable |
|---|---|---|---|
| `auth_mode` | `none` | `entra` | `auth_mode` |
| `easy_auth` | `false` | `true` (only when `auth_mode = entra`) | none. Derived: `auth_mode == "entra" && (profile default \|\| profile == "enterprise")` |
| `data_classification` | `synthetic` | `customer` | `data_classification` |
| `create_fabric` | `true` | `false` | `create_fabric` |
| `manage_fabric_access` | `true` | `false` | `manage_fabric_access` |
| `create_network` | `true` | `false` (BYO) | `create_network` |
| `web_inbound` | `public` | `private_endpoint` | `web_inbound` (`private_endpoint` \| `access_restriction` \| `public`) |
| Key Vault | off | off | `enable_key_vault` (default `false`, both profiles) |

Consequence of the `easy_auth` derivation: if you set `auth_mode = "entra"`
on the **public** profile, the API validates tokens but the web app doesn't
get Easy Auth.

**Providers** (`providers.tf`): Terraform `>= 1.9.0`, `hashicorp/azurerm ~>
4.81.0`, `Azure/azapi ~> 2.13.0` and `microsoft/fabric ~> 1.14.0` (with
`preview = true`). The azurerm provider settings are:

- `resource_provider_registrations = "none"`. Terraform never registers
  resource providers.
- `storage_use_azuread = true`.
- `storage.data_plane_available = false`.
- `resource_group.prevent_deletion_if_contains_resources = false`.
- `cognitive_account.purge_soft_delete_on_destroy = true`.
- `key_vault.purge_soft_delete_on_destroy = true`.

The `fabric` provider authenticates with the Azure CLI locally, and with OIDC
in CI (`FABRIC_USE_OIDC`).

**Resource counts.** These counts are managed resources at default
variables. They don't include the two data sources.

- `public`: **44** resources. This matches the live public-profile deployment.
- `enterprise`: **29** resources, or 33 with `enable_key_vault = true`.

---

## 2. Naming

The suffix `name_suffix` (local `token`) is:

```
substr(sha1("<subscription id>/<environment_name>/<location>"), 0, 8)
```

The subscription ID comes from `subscription_id`, or from the deploying
principal's context when that variable is empty. The suffix is stable for one
environment in one subscription and region, and it differs across them.

`environment_name` must match `^[a-z0-9][a-z0-9-]{1,40}$`.

| Resource | Name |
|---|---|
| Resource group | `resource_group_name`, else `rg-<environment_name>` |
| User-assigned identities | `id-tcc-api-<s>`, `id-tcc-web-<s>` |
| VNet / subnets | `vnet-tcc-<s>` / `snet-app`, `snet-pe` |
| DNS zone links | `link-<key>` (`blob`, `cognitiveservices`, `openai`, `aiservices`, `vault`, `sites`) |
| Log Analytics / App Insights | `log-tcc-<s>` / `appi-tcc-<s>` |
| App Service plan / apps | `asp-tcc-<s>` / `app-tcc-api-<s>`, `app-tcc-web-<s>` |
| Storage account | `sttcc<s>` (13 characters, lowercase alphanumeric) |
| Key Vault | `kv-tcc-<s>` |
| Foundry account / project / deployment | `aif-tcc-<s>` (also its custom subdomain) / `proj-tcc` / the model name (default `gpt-4.1-mini`) |
| Private endpoints | `pe-blob-<s>`, `pe-aif-<s>`, `pe-kv-<s>`, `pe-web-<s>` |
| Fabric capacity | `fctcc<s>` |
| Fabric workspace / Lakehouse / Warehouse | `tcc-<environment_name>` / `tcc_lakehouse` / `tcc_warehouse` |
| Diagnostic settings | `diag-api`, `diag-web`, `diag-plan`, `diag-blob`, `diag-kv`, `diag-aif` |

`<s>` is the suffix.

---

## 3. Tags

`local.tags` is `merge(var.tags, {...})`, so the three fixed tags win over any
key of the same name in `var.tags`:

| Tag | Value |
|---|---|
| `azd-env-name` | `environment_name` |
| `application` | `tax-credit-copilot` |
| `profile` | `public` or `enterprise` |
| *(any)* | extra tags from the variable `tags` (default `{}`) |

Both App Services also carry `azd-service-name`, with the value `api` or
`web`. azd uses this tag to find its deploy targets. `deploy.yml` reads
`azd-env-name` on an existing resource group and refuses to deploy into a
group tagged for another environment.

**Tagged:** the resource group, identities, VNet, private DNS zones and links,
Log Analytics, App Insights, the App Service plan and both apps, the storage
account, Key Vault, every private endpoint, the Foundry account and project,
and the Fabric capacity.

**Not tagged:** subnets, storage containers, the lifecycle policy, role
assignments, diagnostic settings, the Foundry model deployment, the Foundry
purge action, and the Fabric workspace, Lakehouse, Warehouse and workspace
role assignment. These resources take no `tags` argument here.

---

## 4. Resources

### 4.1 Resource group

| | |
|---|---|
| Resource | `azurerm_resource_group.this` |
| Profiles | both |
| Name / region | see §2 / `location` (every resource uses one region) |
| Settings | The provider deletes the group on destroy even if it holds resources Terraform didn't create, such as App Insights smart-detection rules |
| Tags | §3 |
| Module / variables | root `main.tf` · `resource_group_name`, `location`, `environment_name`, `tags` |

### 4.2 Network: VNet, subnets, NSGs, private DNS

Module [`modules/network`](../../infra/modules/network/main.tf), with
`create = local.create_network`.

**Public profile (`create_network = true`)** creates the following.

| Resource | Settings |
|---|---|
| `azurerm_virtual_network.this` | Address space `vnet_address_space` (default `10.40.0.0/16`) |
| `azurerm_subnet.app` (`snet-app`) | `cidrsubnet(space, 8, 1)` (default `10.40.1.0/24`). Delegated to `Microsoft.Web/serverFarms`, with service endpoint `Microsoft.Web`. Both apps integrate here, and the API's inbound rule allows this subnet (§4.7) |
| `azurerm_subnet.private_endpoints` (`snet-pe`) | `cidrsubnet(space, 8, 2)` (default `10.40.2.0/24`). `private_endpoint_network_policies = "Disabled"` |
| `azurerm_private_dns_zone.this` | One zone per required key (see below) |
| `azurerm_private_dns_zone_virtual_network_link.this` | One link per zone to the VNet, `registration_enabled = false` |

The private DNS zones are built from `local.dns_zone_names` in `main.tf`:

| Key | Zone | When |
|---|---|---|
| `blob` | `privatelink.blob.core.windows.net` | always |
| `cognitiveservices` | `privatelink.cognitiveservices.azure.com` | always |
| `openai` | `privatelink.openai.azure.com` | always |
| `aiservices` | `privatelink.services.ai.azure.com` | always |
| `vault` | `privatelink.vaultcore.azure.net` | `enable_key_vault = true` |
| `sites` | `privatelink.azurewebsites.net` | `web_inbound = "private_endpoint"` |

**NSGs, route tables, NAT gateway:** none is created in either profile. With
BYO subnets, they are the customer's decision. Both apps set
`vnet_route_all_enabled = true`, so all outbound traffic follows the
subnet's routing. That includes traffic to Fabric, Entra and Azure Monitor,
which have public endpoints.

**Enterprise profile (`create_network = false`)** creates nothing in this
module. It passes these through:

- `app_integration_subnet_id`: required. Per the variable description, it
  must be delegated to `Microsoft.Web/serverFarms` and carry the service
  endpoint `Microsoft.Web`.
- `private_endpoint_subnet_id`: required.
- `private_dns_zone_ids`: a map. The validation requires `blob`,
  `cognitiveservices`, `openai` and `aiservices`. It does **not** check
  `sites` or `vault`, but you must supply `sites` when `web_inbound =
  private_endpoint` (the enterprise default), and `vault` when
  `enable_key_vault = true`.

Linking the customer's zones to the customer's VNet is the customer's
responsibility.

| | |
|---|---|
| Identity / roles | none |
| Diagnostics | none |
| Tags | VNet, zones and links: §3. Subnets: none |
| Variables | `create_network`, `vnet_address_space`, `app_integration_subnet_id`, `private_endpoint_subnet_id`, `private_dns_zone_ids`, `enable_key_vault`, `web_inbound` |

### 4.3 User-assigned managed identities

Module [`modules/identity`](../../infra/modules/identity/main.tf). Both
profiles.

| Identity | Used by | Holds |
|---|---|---|
| `id-tcc-api-<s>` | API app (only identity on it; `AZURE_CLIENT_ID`; Key Vault reference identity) | Every data permission. See §4.13 |
| `id-tcc-web-<s>` | Web app (only identity on it; `AZURE_CLIENT_ID`; Easy Auth federated-credential client) | Monitoring Metrics Publisher on App Insights only |

The API identity's name, client ID and principal ID are outputs
(`API_IDENTITY_NAME`, `API_IDENTITY_CLIENT_ID`, `API_IDENTITY_PRINCIPAL_ID`).
`grant-warehouse-sql.py` grants T-SQL permissions to `API_IDENTITY_NAME`.

The web identity's principal ID isn't an output.

Tags: §3.

### 4.4 Log Analytics workspace

| | |
|---|---|
| Resource | `azurerm_log_analytics_workspace.this` (`log-tcc-<s>`) · module [`monitoring`](../../infra/modules/monitoring/main.tf) |
| Profiles | both |
| SKU | `PerGB2018` |
| Retention | 30 days (module variable `retention_in_days`. The root module doesn't expose it) |
| Network | public endpoints. No Azure Monitor Private Link Scope is created |
| Identity / roles | none assigned by Terraform. Reader access for operators is the customer's decision |
| Diagnostics | sink for every diagnostic setting (§4.14) |
| Tags | §3 |

### 4.5 Application Insights

| | |
|---|---|
| Resource | `azurerm_application_insights.this` (`appi-tcc-<s>`) · module `monitoring` |
| Profiles | both |
| Type | workspace-based on §4.4, `application_type = "web"` |
| Settings | `local_authentication_enabled = false`. Ingestion must be Entra-authenticated, so the connection string alone can't write telemetry |
| Roles | `Monitoring Metrics Publisher` at App Insights scope, granted to the API identity and the web identity (`azurerm_role_assignment.publisher`, `principal_type = ServicePrincipal`) |
| App wiring | Both apps get `APPLICATIONINSIGHTS_CONNECTION_STRING` (a sensitive output) and `APPLICATIONINSIGHTS_AUTHENTICATION_STRING = Authorization=AAD;ClientId=<own identity client id>`. The API configures Azure Monitor OpenTelemetry with its managed identity ([`backend/telemetry.py`](../../backend/telemetry.py)). The web server (`frontend/server`) includes no telemetry SDK |
| Network | public ingestion endpoint, reached through VNet-integrated outbound |
| Diagnostics | none |
| Tags | §3 |

### 4.6 App Service plan

| | |
|---|---|
| Resource | `azurerm_service_plan.this` (`asp-tcc-<s>`) · module [`app_service`](../../infra/modules/app_service/main.tf) |
| Profiles | both |
| OS / SKU | Linux · `app_service_sku`, default `P1v3` (azd: `TCC_APP_SERVICE_SKU`) |
| Shared by | API app and web app |
| Zone redundancy, worker count, autoscale | not set by Terraform (platform defaults) |
| Diagnostics | `diag-plan`: `AllMetrics` to Log Analytics |
| Tags | §3 |

### 4.7 API app

| | |
|---|---|
| Resource | `azurerm_linux_web_app.api` (`app-tcc-api-<s>`) · module `app_service` |
| Profiles | both |
| Runtime | Python `3.12`. Code (zip) deploy. Startup command `sh startup.sh`, which runs [`backend/startup.sh`](../../backend/startup.sh): `gunicorn -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY:-2} --timeout 600 main:app` |
| Health | `health_check_path = "/api/health"`, `health_check_eviction_time_in_min = 10`. `/api/health` and `/api/ready` are exempt from authentication |
| Always On / HTTP | `always_on = true`, `https_only = true`, `http2_enabled = true`, `minimum_tls_version = "1.2"` |
| FTP / SCM | `ftps_state = "Disabled"`. `ftp_publish_basic_authentication_enabled = false`. `webdeploy_publish_basic_authentication_enabled = false`, so deployment uses Entra only. `scm_ip_restriction_default_action = "Allow"`. SCM minimum TLS isn't set by Terraform |
| Identity | user-assigned `id-tcc-api-<s>` only. Also `key_vault_reference_identity_id` |
| Outbound network | VNet integration into the app subnet (`virtual_network_subnet_id`), `vnet_route_all_enabled = true` |
| Inbound network | `public_network_access_enabled = true`, `ip_restriction_default_action = "Deny"`. One allow rule, `web-app-subnet` (priority 100): `virtual_network_subnet_id = <app subnet>`. Only callers integrated into that subnet reach the API, through the `Microsoft.Web` service endpoint. **The API has no private endpoint** in either profile. Both live smoke tests confirmed that a direct call to the API hostname returns 403 |
| Easy Auth | none. The API validates bearer tokens itself when `AUTH_MODE = entra` ([`backend/infrastructure/auth/entra.py`](../../backend/infrastructure/auth/entra.py)) |
| Logs | `detailed_error_messages = true`, `failed_request_tracing = false`, HTTP logs to the file system (7 days, 35 MB) |
| Diagnostics | `diag-api`: category group `allLogs` and `AllMetrics` to Log Analytics |
| Tags | §3 + `azd-service-name = api` |

**App settings.** None is a secret (HOST-5). The platform settings come from
the module. The rest come from `api_app_settings` in `main.tf`, which are
merged last and win.

| Setting | Value |
|---|---|
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | App Insights connection string |
| `APPLICATIONINSIGHTS_AUTHENTICATION_STRING` | `Authorization=AAD;ClientId=<api identity client id>` |
| `AZURE_CLIENT_ID` | API identity client ID |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |
| `WEBSITES_CONTAINER_START_TIME_LIMIT` | `1800` |
| `ENVIRONMENT` | `azure` |
| `DATA_CLASSIFICATION` | profile (§1) |
| `AUTH_MODE` | profile (§1) |
| `CLAIM_STORE`, `FINDING_STORE`, `RUN_MANIFEST_STORE`, `OVERRIDE_STORE`, `ARTIFACT_REPOSITORY` | `warehouse` |
| `ARTIFACT_STORE` | `blob` |
| `ARTIFACT_BLOB_ACCOUNT_URL` | storage primary blob endpoint |
| `OUTPUTS_RETENTION_DAYS` | `outputs_retention_days` (default `2555`) |
| `DATA_SOURCE` | `flex` |
| `SOURCE_SCHEMA` | `source_schema` (default `flex`) |
| `FABRIC_WORKSPACE`, `FABRIC_LAKEHOUSE` | from the Fabric module (created names, or BYO inputs) |
| `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE` | from the Fabric module (created Warehouse connection string and name, or BYO inputs) |
| `FOUNDRY_PROJECT_ENDPOINT` | `https://aif-tcc-<s>.services.ai.azure.com/api/projects/proj-tcc` |
| `FOUNDRY_MODEL` | `foundry_model` (default `gpt-4.1-mini`) |
| `WEB_CONCURRENCY` | `api_worker_count` (default `2`) |
| `GIT_COMMIT` | `git_commit` (azd: `GIT_COMMIT`) |
| `AUTH_TENANT_ID`, `API_AUDIENCE` | only when `AUTH_MODE = entra`. `API_AUDIENCE` = `api_audience`, else `api://<api_client_id>` |
| `AI_GATEWAY_ENDPOINT` | only when `ai_gateway_endpoint` is non-empty. No backend module reads this setting yet |

At startup the API refuses a non-durable store, and it refuses `AUTH_MODE =
none` with `DATA_CLASSIFICATION = customer`, whenever `ENVIRONMENT` isn't
`local` ([`backend/application/deployment.py`](../../backend/application/deployment.py)).

Variables: `app_service_sku`, `api_worker_count`, `auth_mode`,
`data_classification`, `api_client_id`, `api_audience`, `tenant_id`,
`source_schema`, `foundry_model`, `ai_gateway_endpoint`,
`outputs_retention_days`, `git_commit`.

### 4.8 Web app

| | |
|---|---|
| Resource | `azurerm_linux_web_app.web` (`app-tcc-web-<s>`) · module `app_service` |
| Profiles | both |
| Runtime | Node `24-lts`. Startup command `npm start` (`node server/index.js`). An Express server serves `dist/` and proxies `/api` to `API_BASE_URL` ([`frontend/server/app.js`](../../frontend/server/app.js)) |
| Health | `health_check_path = "/healthz"`, eviction after 10 min |
| Always On / HTTP | `always_on = true`, `https_only = true`, `http2_enabled = true`, `minimum_tls_version = "1.2"` |
| FTP / SCM | as for the API: FTPS disabled, both basic-auth publishing flags `false`, `scm_ip_restriction_default_action = "Allow"` |
| Identity | user-assigned `id-tcc-web-<s>` only |
| Outbound network | VNet integration into the **same** app subnet as the API, `vnet_route_all_enabled = true` |
| Diagnostics | `diag-web`: `allLogs` and `AllMetrics` to Log Analytics |
| Tags | §3 + `azd-service-name = web` |

**Inbound network** follows `web_inbound`:

| `web_inbound` | `public_network_access_enabled` | Default action | Rules | Private endpoint |
|---|---|---|---|---|
| `public` (public default) | `true` | `Allow` | none | none |
| `access_restriction` | `true` | `Deny` | one `Allow` per CIDR in `web_allowed_ip_ranges`, named `allow-<n>`, priority `100 + n` | none |
| `private_endpoint` (enterprise default) | `false` | `Allow` | none | `pe-web-<s>`: subresource `sites`, in the PE subnet, DNS zone group `sites` |

App Service applies `public_network_access_enabled = false` to the SCM site
too. With the enterprise default, the zip deploy of the web app needs a
private path to it. Terraform doesn't provide one.

**App settings:**

| Setting | Value |
|---|---|
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | App Insights connection string |
| `APPLICATIONINSIGHTS_AUTHENTICATION_STRING` | `Authorization=AAD;ClientId=<web identity client id>` |
| `AZURE_CLIENT_ID` | web identity client ID |
| `SCM_DO_BUILD_DURING_DEPLOYMENT` | `true` |
| `API_BASE_URL` | `https://<API default hostname>` |
| `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID` | web identity client ID. Set only with Easy Auth |

`web_app_settings` is `{}`.

**Easy Auth** (`auth_settings_v2`) is present only when `local.easy_auth` is
true (§1):

| Setting | Value |
|---|---|
| `auth_enabled` / `require_authentication` | `true` / `true` |
| `unauthenticated_action` | `RedirectToLoginPage` |
| `default_provider` | `azureactivedirectory` |
| `excluded_paths` | `["/healthz"]` |
| `active_directory_v2.client_id` | `web_client_id` (the customer's web registration) |
| `tenant_auth_endpoint` | `https://login.microsoftonline.com/<tenant_id>/v2.0` |
| `client_secret_setting_name` | `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID`. The web identity acts as a federated credential, so there's no client secret |
| `login_parameters.scope` | `openid profile email offline_access <api_audience>/user_impersonation` |
| `login.token_store_enabled` | `true` |

The web server forwards `X-MS-TOKEN-AAD-ACCESS-TOKEN` to the API as
`Authorization: Bearer`. It drops any `Authorization` header the browser sent.

Variables: `app_service_sku`, `web_inbound`, `web_allowed_ip_ranges`,
`web_client_id`, `api_client_id`, `api_audience`, `tenant_id`, `auth_mode`.

### 4.9 Storage account (artifacts)

Module [`modules/storage`](../../infra/modules/storage/main.tf). Both
profiles.

| | |
|---|---|
| Resource | `azurerm_storage_account.this` (`sttcc<s>`) |
| SKU | `StorageV2`, `Standard`, `ZRS` |
| BLOB-1 settings | `public_network_access_enabled = false`. `shared_access_key_enabled = false`. `allow_nested_items_to_be_public = false` (no anonymous access). `min_tls_version = "TLS1_2"`. `https_traffic_only_enabled = true`. `default_to_oauth_authentication = true`. Private endpoint for `blob` |
| Blob properties | `versioning_enabled = true`, blob soft delete 30 days, container soft delete 30 days |
| Management plane only | Containers use `storage_account_id`, and the lifecycle is `azurerm_storage_management_policy`. With `storage_use_azuread = true` and `data_plane_available = false`, Terraform never needs data-plane reach |
| Containers | `artifacts` (source documents behind rule packs) and `outputs` (claim packages at `{client_id}/{run_id}/...`). Both `container_access_type = "private"` |
| Lifecycle | rule `outputs-retention` (enabled). Applies to `blockBlob` with prefix `outputs/`. Deletes base blobs after `outputs_retention_days` (default 2555, about 7 years) since creation, and deletes versions after the same number of days |
| Private endpoint | `pe-blob-<s>`, subresource `blob`, in the PE subnet, DNS zone group with the `blob` zone |
| Identity on the account | none |
| Roles | `Storage Blob Data Contributor` granted to the API identity, **once per container** (`artifacts`, `outputs`). There is no account-scope grant. The web identity has no storage role |
| Diagnostics | `diag-blob` on `<account>/blobServices/default`: `allLogs` and metric `Transaction`. There's no account-level diagnostic setting |
| Tags | account and PE: §3 |
| Variables | `outputs_retention_days`. The network inputs come from §4.2 |

No SAS is issued. The API streams blob bytes through its artifact service and
records every download in `tcc_ops.artifact_access`.

### 4.10 Key Vault (optional)

Module [`modules/keyvault`](../../infra/modules/keyvault/main.tf). It's
created only when `enable_key_vault = true` (default `false` in **both**
profiles). The stack holds no secrets, so the vault exists for customer
policy, or for a future third-party credential held as a Key Vault reference.

| | |
|---|---|
| Resource | `azurerm_key_vault.this` (`kv-tcc-<s>`) |
| SKU | `standard` |
| Settings | `rbac_authorization_enabled = true`. `purge_protection_enabled = true`. `soft_delete_retention_days = 7`. `public_network_access_enabled = false`. `network_acls`: `default_action = "Deny"`, `bypass = "None"` |
| Private endpoint | `pe-kv-<s>`, subresource `vault`, DNS zone `vault` |
| Roles | `Key Vault Secrets User` granted to the API identity at vault scope |
| Use | The API app's `key_vault_reference_identity_id` is the API identity. No application code calls Key Vault |
| Diagnostics | `diag-kv`: `allLogs` and `AllMetrics` |
| Tags | vault and PE: §3 |
| Teardown | The provider sets `purge_soft_delete_on_destroy = true`, but purge protection is on, so a destroyed vault stays soft-deleted for its 7-day retention |
| Variables | `enable_key_vault`, `tenant_id`, `private_dns_zone_ids["vault"]` (BYO) |

### 4.11 Microsoft Foundry

Module [`modules/foundry`](../../infra/modules/foundry/main.tf), using
`azapi` API version `2025-06-01`. Both profiles.

| Resource | Settings |
|---|---|
| `azapi_resource.account` (`aif-tcc-<s>`) | `Microsoft.CognitiveServices/accounts`, kind `AIServices`, SKU `S0`, system-assigned identity. `customSubDomainName = aif-tcc-<s>`. `allowProjectManagement = true`. `disableLocalAuth = true` (no keys). `publicNetworkAccess = "Disabled"`. `networkAcls.defaultAction = "Deny"` |
| `azapi_resource.project` (`proj-tcc`) | `accounts/projects`, system-assigned identity, no properties |
| `azapi_resource.deployment` | `accounts/deployments`, named after the model. SKU `foundry_deployment_sku` (default `GlobalStandard`) with capacity `foundry_capacity` (default `20`, in thousands of tokens per minute). Model format `OpenAI`, name `foundry_model` (default `gpt-4.1-mini`), version `foundry_model_version` (default `2025-04-14`). No tags |
| `azurerm_private_endpoint.account` (`pe-aif-<s>`) | subresource `account`, in the PE subnet. The DNS zone group `foundry` has three zones: `cognitiveservices`, `openai`, `aiservices` |
| `azurerm_role_assignment.ai_user` | Role definition ID `53ca6127-db72-4b80-b1b0-d745d6d5456d` (**"Foundry User"**, formerly "Azure AI User", so it's pinned by GUID). Granted to the API identity at **account** scope |
| `azurerm_monitor_diagnostic_setting.account` (`diag-aif`) | `allLogs` and `AllMetrics` |
| `azapi_resource_action.purge_on_destroy` | On destroy only, a `DELETE` on the subscription-level `deletedAccounts/aif-tcc-<s>` path for the region and resource group. This releases the subdomain from the 48-hour soft delete |

Writes to the account are serialized: project, then deployment, then private
endpoint, then diagnostic setting. The account accepts one write at a time,
and parallel writes produced 409 `RequestConflict` during live deployment.

The account's and the project's system-assigned identities get no role
assignments. The project endpoint output is
`https://aif-tcc-<s>.services.ai.azure.com/api/projects/proj-tcc`.

Tags: account, project and PE use §3. The deployment isn't tagged.

Variables: `foundry_model`, `foundry_model_version`, `foundry_deployment_sku`,
`foundry_capacity`, `ai_gateway_endpoint` (an app setting only, §4.7).

### 4.12 Fabric

Module [`modules/fabric`](../../infra/modules/fabric/main.tf).

**`create_fabric = true`** (public default) creates:

| Resource | Settings |
|---|---|
| `azurerm_fabric_capacity.this` (`fctcc<s>`) | SKU `fabric_capacity_sku` (default `F2`), tier `Fabric`. `administration_members = [fabric_capacity_admin]` (a UPN, required when creating; set with `azd env set FABRIC_CAPACITY_ADMIN`). Tags: §3 |
| `data.fabric_capacity.this` | Looks up the capacity's Fabric ID by display name after it exists |
| `fabric_workspace.this` (`tcc-<environment_name>`) | On the capacity, with description `Tax Credit Copilot (<environment_name>)`. The identity that runs Terraform creates it |
| `fabric_lakehouse.this` (`tcc_lakehouse`) | `enable_schemas = true`. Holds the source schema (`source_schema`) |
| `fabric_warehouse.this` (`tcc_warehouse`) | Holds schemas `tcc_gold` and `tcc_ops`, created by the DDL bootstrap in postprovision, not by Terraform |

**`create_fabric = false`** (enterprise default) creates nothing. These
inputs are passed through: `fabric_workspace_id`, `fabric_workspace_name`,
`fabric_lakehouse_name`, `fabric_warehouse_id`, `warehouse_server` and
`warehouse_database`. Validation requires the ID, server and database inputs.

**`manage_fabric_access = true`** (public default) creates
`fabric_workspace_role_assignment.api`. It grants the API identity
(`ServicePrincipal`) the workspace role `fabric_workspace_role`, default
**`Contributor`**. Per the variable description, Contributor covers OneLake
read and Warehouse writes, and the provider can't express item-level ReadAll.

With `manage_fabric_access = false` (enterprise default), the customer's
Fabric admin grants the role.

The schema-level T-SQL grants are never made by Terraform. See §5.

| | |
|---|---|
| Network | Fabric endpoints are public. Fabric private link isn't provisioned (NET-4: a customer prerequisite) |
| Diagnostics | none |
| Outputs | `FABRIC_WORKSPACE_ID`, `FABRIC_WORKSPACE`, `FABRIC_LAKEHOUSE`, `FABRIC_WAREHOUSE_ID`, `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE`, and `TCC_FABRIC_CREATED` (`"true"` only when this deployment created the Warehouse. That's the only case in which the destructive bootstrap may run, D22) |
| Variables | `create_fabric`, `manage_fabric_access`, `fabric_capacity_sku`, `fabric_capacity_admin`, `fabric_workspace_role`, the BYO inputs above, `source_schema` |

### 4.13 Role assignments (all)

| Principal | Role | Scope | Resource | Profiles |
|---|---|---|---|---|
| API identity | Storage Blob Data Contributor | container `artifacts` | `module.storage.azurerm_role_assignment.blob_data["artifacts"]` | both |
| API identity | Storage Blob Data Contributor | container `outputs` | `module.storage.azurerm_role_assignment.blob_data["outputs"]` | both |
| API identity | Foundry User (`53ca6127-…`) | Foundry account | `module.foundry.azurerm_role_assignment.ai_user` | both |
| API identity | Monitoring Metrics Publisher | App Insights | `module.monitoring.azurerm_role_assignment.publisher["api"]` | both |
| API identity | Key Vault Secrets User | Key Vault | `module.keyvault.azurerm_role_assignment.secrets_user[0]` | `enable_key_vault` |
| Web identity | Monitoring Metrics Publisher | App Insights | `module.monitoring.azurerm_role_assignment.publisher["web"]` | both |
| API identity | Fabric workspace role `fabric_workspace_role` (default Contributor) | Fabric workspace | `module.fabric.fabric_workspace_role_assignment.api[0]` | `manage_fabric_access` (public default) |

The outputs `api_role_assignments` and `web_role_assignments` list the Azure
role assignments for review. `infra/tests/enterprise.tftest.hcl` asserts
that the API's Azure roles are exactly the first four rows, and that the web
identity holds only Monitoring Metrics Publisher.

### 4.14 Diagnostic settings (all)

Every setting sends to the Log Analytics workspace (§4.4).

| Name | Target | Logs | Metrics |
|---|---|---|---|
| `diag-api` | API app | `allLogs` | `AllMetrics` |
| `diag-web` | web app | `allLogs` | `AllMetrics` |
| `diag-plan` | App Service plan | none | `AllMetrics` |
| `diag-blob` | storage `blobServices/default` | `allLogs` | `Transaction` |
| `diag-kv` | Key Vault (if enabled) | `allLogs` | `AllMetrics` |
| `diag-aif` | Foundry account | `allLogs` | `AllMetrics` |

Log Analytics, App Insights, the VNet, private endpoints and Fabric have no
diagnostic settings. Application telemetry reaches App Insights from the
API's OpenTelemetry exporter.

---

## 5. Prerequisites outside Terraform

| Prerequisite | Who | Notes |
|---|---|---|
| **Register resource providers** | customer subscription owner | Terraform sets `resource_provider_registrations = "none"`. Register `Microsoft.Web`, `Microsoft.Storage`, `Microsoft.CognitiveServices`, `Microsoft.Network`, `Microsoft.OperationalInsights`, `Microsoft.Insights` and `Microsoft.ManagedIdentity`. Add `Microsoft.Fabric` when `create_fabric = true` and `Microsoft.KeyVault` when `enable_key_vault = true` ([OIDC-SETUP](OIDC-SETUP.md) §2) |
| **Deploying principal's Azure rights** | customer | It must create the resources and the role assignments in §4.13. For CI: Contributor, plus Role Based Access Control Administrator constrained to those roles, at resource-group scope ([OIDC-SETUP](OIDC-SETUP.md)) |
| **Entra app registrations** (enterprise, D12 / AUTH-1) | customer Entra admin | Terraform takes the client IDs (`web_client_id`, `api_client_id`) and never creates the registrations. **API registration:** exposes delegated scope `user_impersonation` and app role `TCC.User`. Its audience is `api://<api_client_id>` unless you set `api_audience`. Assign `TCC.User` to the users or groups who may use the app. A token without the role gets 403. **Web registration:** the Easy Auth client, with redirect `/.auth/login/aad/callback` and permission to the API's `user_impersonation`. It needs a federated identity credential that trusts the web user-assigned identity, because Easy Auth uses `OVERRIDE_USE_MI_FIC_ASSERTION_CLIENTID` instead of a client secret |
| **BYO network** (enterprise) | customer network team | An integration subnet delegated to `Microsoft.Web/serverFarms` with service endpoint `Microsoft.Web`. A private-endpoint subnet. Private DNS zones (§4.2) linked to the VNets that must resolve them. Egress from the integration subnet to Fabric, Entra and Azure Monitor (their endpoints are public; §4.2) |
| **Fabric tenant setting** | Fabric administrator | "Service principals can use Fabric APIs" must allow the API identity, and also the CI application if one is used (FAB-3). Without it, the workspace role exists and data calls still fail, while `/api/health` stays 200 |
| **Fabric private link / DNS** | customer | Not provisioned (NET-4) |
| **Fabric workspace role** (enterprise, `manage_fabric_access = false`) | customer Fabric admin | Grant the API identity a workspace role that allows OneLake read and Warehouse writes (the Terraform default is Contributor). The deploying principal needs Admin or Member to run the T-SQL scripts. `scripts/grant-fabric-mi-access.ps1` predates v2: it was written for Container Apps and defaults to Viewer |
| **Fabric capacity admin** (`create_fabric = true`) | operator | `azd env set FABRIC_CAPACITY_ADMIN <UPN>`. The plan fails without it |
| **T-SQL grants** | `scripts/grant-warehouse-sql.py` (azd postprovision and `deploy.yml`) | `GRANT SELECT, INSERT, UPDATE, DELETE ON SCHEMA::tcc_gold` and the same on `tcc_ops`, `TO [<API_IDENTITY_NAME>]`. Idempotent |
| **Schema** | `scripts/apply-migrations.py` | Runs the DDL v2.0 bootstrap only when `TCC_FABRIC_CREATED = true` and the Warehouse has no `tcc_ops.schema_migration`. Otherwise it applies pending forward migrations (D22) |
| **Synthetic data and seed** | `scripts/postprovision.ps1` | load-synthetic (public profile only), then `seed-operational-store.ps1`. `deploy.yml` runs neither |
| **Terraform state** | customer | Local by default. [`infra/backend.azurerm.tf.example`](../../infra/backend.azurerm.tf.example) is the remote template. `deploy.yml` requires remote state (`TF_BACKEND_*`) |
| **GitHub OIDC** | customer | See [OIDC-SETUP](OIDC-SETUP.md) |

---

## 6. Profile matrix

Default variables; ✔ = created, — = not created, BYO = supplied by the customer.

| Resource | `public` | `enterprise` | Toggle |
|---|---|---|---|
| Resource group | ✔ | ✔ | — |
| User-assigned identities (api, web) | ✔ | ✔ | — |
| VNet, `snet-app`, `snet-pe` | ✔ | BYO | `create_network` |
| NSG / route table / NAT | — | customer's | none in Terraform |
| Private DNS zones + VNet links (blob, cognitiveservices, openai, aiservices) | ✔ | BYO | `create_network` |
| Private DNS zone `vault` | ✔ if Key Vault | BYO if Key Vault | `enable_key_vault` |
| Private DNS zone `sites` | — (`web_inbound = public`) | BYO | `web_inbound = private_endpoint` |
| Log Analytics workspace | ✔ | ✔ | — |
| Application Insights + 2 publisher roles | ✔ | ✔ | — |
| App Service plan | ✔ | ✔ | — |
| API app (+ subnet access restriction) | ✔ | ✔ | — |
| Web app | ✔ (public inbound) | ✔ (no public access) | `web_inbound` |
| Web app Easy Auth | — | ✔ | `auth_mode` (§1) |
| Web app private endpoint | — | ✔ | `web_inbound = private_endpoint` |
| Storage account, 2 containers, lifecycle policy, blob PE, 2 role assignments, diagnostic setting | ✔ | ✔ | — |
| Key Vault, PE, role assignment, diagnostic setting | — | — | `enable_key_vault` |
| Foundry account, project, deployment, PE, role assignment, diagnostic setting, purge action | ✔ | ✔ | — |
| Fabric capacity, workspace, Lakehouse, Warehouse | ✔ | BYO | `create_fabric` |
| Fabric workspace role for the API identity | ✔ | customer | `manage_fabric_access` |
| T-SQL schema grants | script | script | — |
| **Managed resources** | **44** | **29** (33 with Key Vault) | |
