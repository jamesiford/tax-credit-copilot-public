# R1 mapping: `TCC_*` environment variables to generic names

Generated from the inventory before any code change. Convention: no prefix where the name is already specific; a category prefix
(`TEST_`, `BENCH_`, `FUZZ_`, `MUTATION_`, `ORACLE_`, `EXISTING_`, `SPIKE_`, `DEPLOY_`, `AI_GATEWAY_`) where it groups a family or the bare name collides.
Classes: **runtime** (read by a running host), **deploy** (Terraform, azd, provisioning, scripts), **test/developer**, **frontend**.

| Old name | New name | Class | Read or set by | Files | Note |
| --- | --- | --- | --- | ---: | --- |
| `TCC_PERSISTENCE_PROVIDER` | `PERSISTENCE_PROVIDER` | runtime | .NET, Python, Terraform/azd/contract, scripts/CI, tests | 32 |  |
| `TCC_REPOSITORY_ROOT` | `REPOSITORY_ROOT` | runtime | .NET, Python, Terraform/azd/contract, tests | 31 |  |
| `TCC_REPO_ROOT` | `REPOSITORY_ROOT` | runtime | Python, Terraform/azd/contract | 4 | Python fixture-root override; merged into REPOSITORY_ROOT as directed (same meaning: the repository root) |
| `TCC_SEED_ROOT` | `SEED_ROOT` | runtime | .NET, Python, Terraform/azd/contract | 8 |  |
| `TCC_RESOURCE_ROOT` | `RESOURCE_ROOT` | deploy | Python, Terraform/azd/contract, tests | 6 | Terraform/deploy input for the packaged resources root |
| `TCC_WORKER_ONCE` | `WORKER_ONCE` | runtime | .NET, Python, Terraform/azd/contract | 6 |  |
| `TCC_ENABLE_RUN_WORKER` | `ENABLE_RUN_WORKER` | deploy | docs only | 1 | documented azd value only |
| `TCC_CONTRACT_HOOKS` | `CONTRACT_HOOKS` | runtime | .NET, Python, Terraform/azd/contract, tests | 56 |  |
| `TCC_CONTRACT_PROFILE` | `CONTRACT_PROFILE` | runtime | .NET, Terraform/azd/contract | 3 |  |
| `TCC_CONTRACT_DIR` | `CONTRACT_DIR` | test/developer | .NET, Python, Terraform/azd/contract | 16 | MSBuild/dev launch property and contract replays |
| `TCC_FEATURE_ASSEMBLIES` | `FEATURE_ASSEMBLIES` | runtime | .NET, Python, Terraform/azd/contract, tests | 9 |  |
| `TCC_WARM_CLIENTS` | `WARM_CLIENTS` | runtime | Python, Terraform/azd/contract, tests | 8 |  |
| `TCC_WARM_ON_START` | `WARM_ON_START` | runtime | Python, Terraform/azd/contract, tests | 15 |  |
| `TCC_KEEPALIVE_SECONDS` | `KEEPALIVE_SECONDS` | runtime | Python, Terraform/azd/contract, tests | 5 |  |
| `TCC_STRANDED_RUN_MINUTES` | `STRANDED_RUN_MINUTES` | runtime | Python, Terraform/azd/contract, tests | 5 |  |
| `TCC_ALLOW_SEED` | `ALLOW_SEED` | runtime | Python, Terraform/azd/contract, scripts/CI, tests | 10 |  |
| `TCC_TELEMETRY_ENABLED` | `TELEMETRY_ENABLED` | runtime | .NET, Python | 5 | the Python backend already reads TELEMETRY_ENABLED with the same meaning (telemetry on/off) |
| `TCC_TELEMETRY_ENDPOINT` | `TELEMETRY_ENDPOINT` | runtime | .NET, Python | 5 |  |
| `TCC_TELEMETRY_VERSION` | `TELEMETRY_VERSION` | runtime | .NET, Python | 5 |  |
| `TCC_RECEIPT_ENDPOINT` | `TELEMETRY_RECEIPT_ENDPOINT` | deploy | Python, scripts/CI | 3 | telemetry collector verification; category prefix because RECEIPT_ENDPOINT alone is vague |
| `TCC_BULK_LOAD` | `BULK_LOAD` | runtime | .NET, tests | 6 | added by S5 |
| `TCC_BULK_LOAD_MIN_ROWS` | `BULK_LOAD_MIN_ROWS` | runtime | .NET, tests | 5 | added by S5 |
| `TCC_BULK_TIMEOUT_SECONDS` | `BULK_TIMEOUT_SECONDS` | runtime | .NET, tests | 5 | added by S5 |
| `TCC_RETAIN_SUPERSEDED_RUNS` | `RETAIN_SUPERSEDED_RUNS` | runtime | .NET | 6 | added by S5 |
| `TCC_GATEWAY_SECRET` | `AI_GATEWAY_SECRET` | deploy | scripts/CI, tests | 2 | name of the variable the model-connection script reads; joins the AI_GATEWAY_ family |
| `TCC_COWORK_` | `COWORK_` | runtime | Python | 2 | prefix of per-key Cowork plugin overrides (COWORK_<KEY>) |
| `TCC_COWORK_GATEWAY_MCP_URL` | `COWORK_GATEWAY_MCP_URL` | runtime | tests | 1 | instance of the COWORK_ prefix |
| `TCC_BACKEND` | `BACKEND_DIR` | test/developer | Python | 2 | portable-rules crosscheck: path of the backend directory |
| `TCC_ORCHESTRATOR_LOCAL_PROOF` | `ORCHESTRATOR_LOCAL_PROOF` | deploy | Python, scripts/CI | 2 | container smoke switch |
| `TCC_PROFILE` | `DEPLOY_PROFILE` | deploy | Terraform/azd/contract, scripts/CI, tests | 13 | PROFILE alone is ambiguous (PowerShell's $PROFILE, .NET run profiles); category prefix |
| `TCC_TENANT_ID` | `TENANT_ID` | deploy | Terraform/azd/contract | 5 | same meaning as the channel gateway's TENANT_ID (the Entra tenant) |
| `TCC_API_CLIENT_ID` | `API_CLIENT_ID` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_WEB_CLIENT_ID` | `WEB_CLIENT_ID` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_API_AUDIENCE` | `API_AUDIENCE` | deploy | Terraform/azd/contract | 5 | same meaning as the API's runtime API_AUDIENCE app setting |
| `TCC_APP_SERVICE_SKU` | `APP_SERVICE_SKU` | deploy | Terraform/azd/contract | 6 |  |
| `TCC_APP_SUBNET_ID` | `APP_SUBNET_ID` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_PRIVATE_ENDPOINT_SUBNET_ID` | `PRIVATE_ENDPOINT_SUBNET_ID` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_FABRIC_WORKSPACE_ID` | `EXISTING_FABRIC_WORKSPACE_ID` | deploy | Terraform/azd/contract | 5 | COLLISION: infra/outputs.tf emits FABRIC_WORKSPACE_ID into the azd environment, so an input of the same name would be overwritten by the output and flip the next apply from 'use existing' to 'create'. Category prefix EXISTING_ |
| `TCC_FABRIC_WAREHOUSE_ID` | `EXISTING_FABRIC_WAREHOUSE_ID` | deploy | Terraform/azd/contract | 5 | COLLISION with output FABRIC_WAREHOUSE_ID; see above |
| `TCC_WAREHOUSE_SERVER` | `EXISTING_WAREHOUSE_SERVER` | deploy | Terraform/azd/contract | 5 | COLLISION with output WAREHOUSE_SERVER (and the API app setting); see above |
| `TCC_WAREHOUSE_DATABASE` | `EXISTING_WAREHOUSE_DATABASE` | deploy | Terraform/azd/contract | 5 | COLLISION with output WAREHOUSE_DATABASE (and the API app setting); see above |
| `TCC_WAREHOUSE_PLATFORM` | `WAREHOUSE_PLATFORM` | deploy | Terraform/azd/contract | 6 | the output WAREHOUSE_PLATFORM echoes this input unchanged, so the shared name carries one meaning |
| `TCC_FABRIC_WORKSPACE_NAME` | `FABRIC_WORKSPACE_NAME` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_FABRIC_LAKEHOUSE_NAME` | `FABRIC_LAKEHOUSE_NAME` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_FABRIC_CREATED` | `FABRIC_CREATED` | deploy | Python, Terraform/azd/contract, scripts/CI, tests | 17 | azd output consumed by provisioning scripts |
| `TCC_SQL_CREATED` | `SQL_CREATED` | deploy | Python, Terraform/azd/contract, scripts/CI, tests | 14 | azd output consumed by provisioning scripts |
| `TCC_SQL_ADMIN_GROUP_NAME` | `SQL_ADMIN_GROUP_NAME` | deploy | Terraform/azd/contract | 6 |  |
| `TCC_SQL_ADMIN_GROUP_OBJECT_ID` | `SQL_ADMIN_GROUP_OBJECT_ID` | deploy | Terraform/azd/contract | 6 |  |
| `TCC_LAKEHOUSE_SQL_` | `LAKEHOUSE_SQL_` | deploy | docs only | 2 | prefix fragment in prose |
| `TCC_LAKEHOUSE_SQL_SERVER` | `LAKEHOUSE_SQL_SERVER` | deploy | Terraform/azd/contract | 6 | same meaning as the API app setting of that name |
| `TCC_LAKEHOUSE_SQL_DATABASE` | `LAKEHOUSE_SQL_DATABASE` | deploy | Terraform/azd/contract | 6 | same meaning as the API app setting of that name |
| `TCC_DATA_QUERY_` | `DATA_QUERY_` | deploy | docs only | 2 | prefix fragment in prose |
| `TCC_DATA_QUERY_SOURCE_ENABLED` | `DATA_QUERY_SOURCE_ENABLED` | deploy | Python, Terraform/azd/contract, scripts/CI, tests | 15 | same meaning as the API app setting of that name |
| `TCC_DATA_QUERY_TIMEOUT_SECONDS` | `DATA_QUERY_TIMEOUT_SECONDS` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_DATA_QUERY_MAX_ROWS` | `DATA_QUERY_MAX_ROWS` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_DATA_QUERY_RATE_PER_MINUTE` | `DATA_QUERY_RATE_PER_MINUTE` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_DATA_QUERY_MAX_CONCURRENCY` | `DATA_QUERY_MAX_CONCURRENCY` | deploy | Terraform/azd/contract | 5 |  |
| `TCC_FOUNDRY_ALLOWED_IP_RANGES` | `FOUNDRY_ALLOWED_IP_RANGES` | deploy | Terraform/azd/contract | 12 |  |
| `TCC_FOUNDRY_PUBLIC_NETWORK_ACCESS` | `FOUNDRY_PUBLIC_NETWORK_ACCESS` | deploy | Terraform/azd/contract | 12 |  |
| `TCC_ENABLE_M365_CHANNEL` | `M365_CHANNEL_ENABLED` | deploy | Terraform/azd/contract, scripts/CI, tests | 14 |  |
| `TCC_CHANNEL_GATEWAY_AUDIENCE` | `CHANNEL_GATEWAY_AUDIENCE` | deploy | Terraform/azd/contract, scripts/CI | 6 |  |
| `TCC_CHANNEL_WRITER_SOURCE` | `CHANNEL_WRITER_SOURCE` | deploy | Terraform/azd/contract, tests | 9 | same meaning as the API app setting of that name |
| `TCC_CHANNEL_WRITER_GROUP_ID` | `CHANNEL_WRITER_GROUP_ID` | deploy | Terraform/azd/contract | 7 | same meaning as the API app setting of that name |
| `TCC_CHANNEL_RESOLVE_DISPLAY_NAMES` | `CHANNEL_RESOLVE_DISPLAY_NAMES` | deploy | Terraform/azd/contract, tests | 10 | same meaning as the gateway setting of that name |
| `TCC_CHANNEL_HEALTH_CHECK` | `CHANNEL_HEALTH_CHECK` | deploy | scripts/CI, tests | 3 | deploy-hook switch |
| `TCC_DEPLOY_PYTHON` | `DEPLOY_PYTHON` | deploy | scripts/CI | 2 | interpreter used by publish.ps1 |
| `TCC_DOTNET_ACTIVATE` | `DEPLOY_DOTNET_ACTIVATE` | deploy | Python, scripts/CI | 3 | a DOTNET_ prefix is reserved by the .NET runtime |
| `TCC_FABRIC_TESTS` | `TEST_FABRIC` | test/developer | Terraform/azd/contract, tests | 29 |  |
| `TCC_SQL_TESTS` | `TEST_SQL` | test/developer | Terraform/azd/contract, tests | 6 |  |
| `TCC_AZURE_TESTS` | `TEST_AZURE` | test/developer | Terraform/azd/contract, tests | 5 |  |
| `TCC_REQUIRE_PARITY` | `TEST_REQUIRE_PARITY` | test/developer | Terraform/azd/contract, scripts/CI, tests | 16 |  |
| `TCC_TEST_SETTINGS_PROBE` | `TEST_SETTINGS_PROBE` | test/developer | tests | 1 |  |
| `TCC_TEST_SCHEMA` | `TEST_SCHEMA` | test/developer | tests | 1 |  |
| `TCC_AI_EVALS_LIVE` | `TEST_AI_EVALS_LIVE` | test/developer | tests | 5 |  |
| `TCC_SQLSERVER_TEST` | `TEST_SQLSERVER` | test/developer | tests | 4 | added by S5 |
| `TCC_LIVE_PROFILE` | `TEST_LIVE_PROFILE` | test/developer | tests | 6 | added by S5 |
| `TCC_LIVE_SQL_SERVER` | `TEST_LIVE_SQL_SERVER` | test/developer | tests | 1 |  |
| `TCC_LIVE_SQL_DATABASE` | `TEST_LIVE_SQL_DATABASE` | test/developer | tests | 1 |  |
| `TCC_ENV_FILE` | `TEST_ENV_FILE` | test/developer | tests | 1 |  |
| `TCC_UPDATE_DEVIATIONS` | `TEST_UPDATE_DEVIATIONS` | test/developer | tests | 4 |  |
| `TCC_PYTHON` | `ORACLE_PYTHON` | test/developer | .NET, Python, Terraform/azd/contract, tests | 30 |  |
| `TCC_ALLOW_OTHER_PYTHON` | `ORACLE_ALLOW_OTHER_PYTHON` | test/developer | tests | 3 |  |
| `TCC_RUN_BENCH` | `BENCH_RUN` | test/developer | scripts/CI, tests | 16 |  |
| `TCC_BENCH_SIZES` | `BENCH_SIZES` | test/developer | scripts/CI, tests | 4 | added by S5 |
| `TCC_BENCH_LABEL` | `BENCH_LABEL` | test/developer | scripts/CI, tests | 3 |  |
| `TCC_BENCH_DUMP` | `BENCH_DUMP` | test/developer | scripts/CI, tests | 2 |  |
| `TCC_BENCH_OUT` | `BENCH_OUT` | test/developer | tests | 2 |  |
| `TCC_FUZZ_N` | `FUZZ_N` | test/developer | tests | 6 |  |
| `TCC_FUZZ_SEED` | `FUZZ_SEED` | test/developer | tests | 6 |  |
| `TCC_FUZZ_PARALLEL` | `FUZZ_PARALLEL` | test/developer | tests | 4 |  |
| `TCC_FUZZ_BATCH` | `FUZZ_BATCH` | test/developer | tests | 2 |  |
| `TCC_RUN_MUTATION_TESTS` | `MUTATION_RUN` | test/developer | tests | 5 |  |
| `TCC_MUTATION_FILTER` | `MUTATION_FILTER` | test/developer | tests | 3 |  |
| `TCC_MUTATION_TEST_FILTER` | `MUTATION_TEST_FILTER` | test/developer | tests | 3 |  |
| `TCC_PLATFORM_SPIKE_APPROVED` | `SPIKE_PLATFORM_APPROVED` | test/developer | .NET | 2 |  |
| `TCC_SHADOW_APPROVED` | `SPIKE_SHADOW_APPROVED` | test/developer | Python | 5 |  |
| `TCC_REPO` | `SPIKE_REPO` | test/developer | Python | 1 | shadow spike admission passes the repository path to a child process |
| `TCC_THEME` | `UI_THEME` | frontend | docs only | 1 | documented dev-tool switch; VITE_THEME is the build-time theme and does not cover the sweep tools |
| `TCC_API_TARGET` | `API_TARGET` | frontend | docs only | 3 |  |
| `TCC_WEB_BASE` | `WEB_BASE` | frontend | docs only | 2 |  |
| `TCC_STRICT_CLASSIC` | `STRICT_CLASSIC` | frontend | docs only | 1 |  |

## Not environment variables (left unchanged)

| Token | What it is |
| --- | --- |
| `TCC_COLUMNS` | a Python constant (the column list of the reference payroll extract) |
| `TCC_DECIMAL` | the SQLite collation name (a database object, R2) |
| `TCC_TELEMETRY_INVALID_CONFIGURATION` | a stderr diagnostic code, not a setting |
| `TCC_TELEMETRY_EXPORT_FAILED` | a stderr diagnostic code, not a setting |
| `TCC_TELEMETRY_` | prose fragment for the TCC_TELEMETRY_* diagnostic codes |
| `TCC_GOLD_SCHEMA` | docstring slip: the real variable is GOLD_SCHEMA (database object, R2) |

## Collisions checked

Every unprefixed new name was grepped against the repository. Names that already exist with the **same** meaning (the deployed app setting
that the azd value feeds) keep the bare name. Four azd inputs collide with a Terraform **output** of the same name that means the value in
use rather than the value to use (`FABRIC_WORKSPACE_ID`, `FABRIC_WAREHOUSE_ID`, `WAREHOUSE_SERVER`, `WAREHOUSE_DATABASE`); azd writes outputs
back into the environment, so a shared name would flip the next apply from "use existing" to "create". They take the `EXISTING_` prefix.
`PROFILE` is ambiguous and became `DEPLOY_PROFILE`; `DOTNET_ACTIVATE` became `DEPLOY_DOTNET_ACTIVATE` because `DOTNET_` is reserved by the runtime.
`REPOSITORY_ROOT` is the one deliberate merge (two old names, same meaning), as directed.
