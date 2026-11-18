# R1 report: environment variables without the product prefix

Branch `rename/r1-env-vars` (worktree `..\tcc-rename-r1`). Not pushed. Names only: no default, value, calculation, route, response or database object changed.

## Result

Every `TCC_*` environment variable was renamed to a generic name. The complete old-to-new table, with the class, readers and reason for each, is
[`rename-r1-mapping.md`](rename-r1-mapping.md); the same table is in `CHANGELOG.md` and `architecture/ENV-VARS.md`. Everything the repository emits (Terraform app
settings and outputs, azd values, `configure-local.ps1`, `run-*.ps1`, `.env.example`, workflows, docs, examples) uses only the new names. The deployed contract
(`dotnet/deploy/configuration/inventory.json` and its examples, `infra-dotnet`, `contract/inventory/env-inventory.json`) lists only new names.

Decisions worth knowing:

- Four azd inputs took an `EXISTING_` prefix (`EXISTING_FABRIC_WORKSPACE_ID`, `EXISTING_FABRIC_WAREHOUSE_ID`, `EXISTING_WAREHOUSE_SERVER`, `EXISTING_WAREHOUSE_DATABASE`):
  `infra/outputs.tf` already emits the bare names into the azd environment with a different meaning (the value in use, not the value to use), so a shared name would
  have turned the next apply from "use existing" into "create".
- `TCC_PROFILE` became `DEPLOY_PROFILE` (`PROFILE` is ambiguous) and `TCC_DOTNET_ACTIVATE` became `DEPLOY_DOTNET_ACTIVATE` (`DOTNET_` is reserved by the runtime).
- `REPOSITORY_ROOT` is the one deliberate merge (the Python `TCC_REPO_ROOT` and the .NET `TCC_REPOSITORY_ROOT`), as directed.
- Where the bare new name already existed with the same meaning (the deployed app setting the azd value feeds: `CHANNEL_*`, `DATA_QUERY_*`, `LAKEHOUSE_SQL_*`,
  `API_AUDIENCE`, `TENANT_ID`, `WAREHOUSE_PLATFORM`, `TELEMETRY_ENABLED`), the two collapsed into one name. The .NET configuration inventory listed each of these twice
  (once as a runtime setting, once as azd metadata); the azd duplicate was removed.

## Still read through an alias (remove next release)

| Host | Where the old names live | How the new name wins | Test |
| --- | --- | --- | --- |
| .NET API, Worker, Gateway | `dotnet/src/TaxCredit.ServiceDefaults/Hosting/LegacySettingAliases.cs` (`RuntimeConfiguration.Get`, `IConfiguration.Setting`) | the old name is read only when the new name is unset | `LegacySettingAliasTests` (Api.Tests), `LegacySettingAliasGatewayTests` (Gateway.Tests) |
| .NET tests | `dotnet/tests/Shared/LegacyTestEnvironment.cs` (module initializer linked into every `.Tests` project by `Directory.Build.props`), plus `Directory.Packages.props` conditions | same | `LegacyTestEnvironmentTests` |
| .NET telemetry startup hook | `dotnet/deploy/telemetry/Hook/Settings.cs` (`Variable`) | same | covered by the deploy telemetry probes |
| Python backend, tests, scripts | `backend/config_aliases.py`, applied in `config.load_settings`, `backend/tests/conftest.py`, `scripts/sql_common.py` | same | `backend/tests/test_config_aliases.py` |
| Standalone Python scripts | `scripts/cowork_plugin/settings.py` (`TCC_COWORK_` prefix), `scripts/portable-rules/crosscheck.py` (`TCC_BACKEND`), `backend/tools/verify_reference_independent.py` (`TCC_REPO_ROOT`) | same | `test_cowork_package.py` |
| PowerShell scripts and azd | `scripts/legacy-env.ps1`, dot-sourced by `postprovision`, `deploy-channel`, `create-model-connection`, `publish`, `guard-target`; run as the azd `preprovision` hook with `-AzdEnv`, which also writes the new names into the azd environment | same | parse check; run by hand |
| MSBuild launch properties | `TaxCredit.Api.csproj`, `TaxCredit.Gateway.csproj` (`TCC_CONTRACT_DIR`, `TCC_CONTRACT_HOOKS`) | the old name is ignored when the new one is set | none (developer launch) |

Every alias warns once per name and never prints a value.

No alias, on purpose: `ORCHESTRATOR_LOCAL_PROOF` (a container safety switch that must fail closed) and `TELEMETRY_RECEIPT_ENDPOINT` (read by the OpenTelemetry collector
configuration, which cannot fall back).

### How to remove the aliases

Delete `LegacySettingAliases.cs` and its calls (`RuntimeConfiguration`, `RuntimeRegistration`, the seven `Setting(...)` sites); delete `LegacyTestEnvironment.cs` and the
`Directory.Build.props` item; delete `backend/config_aliases.py` and its call in `config.load_settings` and the conftest; delete `scripts/legacy-env.ps1`, its
dot-sourcing lines and the `preprovision` hook in `azure.yaml`; remove the three standalone fallbacks listed above, the `Variable` helper in `Settings.cs`, and the
`TCC_` conditions in `Directory.Packages.props` and the two csproj files. Then `git grep -n "TCC_"` must return only `CHANGELOG.md`, `rename-r1-mapping.md` and the historical reports.

## Still hardcoded (not environment variables)

- Database objects, handled by R2: the schemas `tcc_gold`, `tcc_ops`, `tcc_source`, `tcc_shared`, `tcc_scratch_dotnet`, tables, the SQLite collation `TCC_DECIMAL` and the
  function `tcc_decimal_valid`, `docs/data/schema/tcc-schema.*.sql`.
- Python constant `TCC_COLUMNS` and class `TccPayrollAdapter` (code names, not settings).
- Two stderr diagnostic codes of the telemetry hook, `TCC_TELEMETRY_INVALID_CONFIGURATION` and `TCC_TELEMETRY_EXPORT_FAILED` (codes, not variables; changing them would change what operators grep for).
- Azure resource names and the `tcc-dotnet` validation (`app-tcc-dotnet-...`, `guard-target.ps1`, `infra-dotnet/validate.ps1`).
- `TaxCredit.*` namespaces, assemblies and telemetry source names; `tcc_shared` (the orchestrator's vendored package); the Entra role `TCC.User`.
- Documentation and sample values that say `tcc` as a name (for example `/tmp/tcc/ops.db`, `tcc-channel.cowork-plugin`).

## Remaining `TCC_` tokens in `git grep` and why

1. The alias tables and their tests (listed above), `scripts/legacy-env.ps1`, the standalone fallbacks.
2. `CHANGELOG.md`, `dotnet/CHANGELOG.md` (earlier entries are history), `docs/rename-r1-mapping.md`, this report and `rename-r1-log.md`.
3. Historical reports and logs that describe past results, left untouched: `docs/archive/**`, `docs/m365-channel/MASTER-STATUS.md`, `docs/m365-channel/FINAL-STATE.md` (one runnable command updated),
   `dotnet/docs/*-log.md`, `dotnet/docs/*-REPORT.md`, `dotnet/docs/parity-report.md`, `dotnet/docs/findings.md`, `dotnet/docs/waves/**`, `dotnet/docs/status/*.json`.
4. The non-environment tokens above (`TCC_COLUMNS`, `TCC_DECIMAL`, the two diagnostic codes).

## Outside the repository

The `GHCP-Prompts-DotNet\Scale-Reads` folder (the S1 to S5 prompts) does not exist on this machine, so nothing there was edited or checked. `C:\Projects\tcc-prompts\SPIKE-A-client-enrichment-and-gold.md`
and `SPIKE-B-second-tax-credit.md` still say `TCC_FABRIC_TESTS` (now `TEST_FABRIC`). `actionlint` is not installed here, so the workflows were checked by reading the diff only.
