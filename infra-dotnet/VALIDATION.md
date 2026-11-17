# D3 validation — 17 November 2026 UTC

## Measured local outcome

Final clean copy:
`C:\Projects\GitHub\tcc-dotnet-w4-deploy\infra-dotnet\.validation\clean-20261117T051845392Z`

Created by `pwsh -File .\infra-dotnet\validate.ps1`, not validated against a
preinitialized source directory. `.validation` is ignored. Only source
configuration, tests, bundled lint configuration and the provider lock were
copied; no local backend/var/state files. Final full run: **28.90 seconds**.

| Command (inside that copy) | Outcome |
|---|---|
| `python guard_offline.py` | Exit 0: only approved resource/provider types, all fixtures mocked, no aliases/adoption/provisioners |
| `python -m unittest discover -s tests -p test_*.py -q` | Exit 0: **3 tests passed**, including real-provider, missing-mock, alias/remapping and external-ownership refusals |
| `terraform init -backend=false -input=false -no-color` | Exit 0: signed locked AzureRM package installed; **backend not initialized** |
| `terraform fmt -check -recursive` | Exit 0 |
| `terraform validate -no-color` | Exit 0 |
| `terraform test -no-color` | Exit 0: **14 runs passed, 0 failed** |
| `tflint --recursive --no-color` | Exit 0, no findings; existing repository's bundled recommended Terraform ruleset pattern |
| `git diff --check -- infra-dotnet` | Exit 0 |
| Explicit source trailing-whitespace scan | Exit 0 across **24 files** (also covers untracked files) |

Tools already available; no tool installation or global configuration changes:
Terraform **1.17.1**, Windows AMD64; TFLint **0.65.0** with bundled Terraform
ruleset **0.15.0**. The stdlib-only guard used local Python **3.14** (not the
calculation oracle; no Python product tests/calculation were run).

Provider: **hashicorp/azurerm = 4.81.0**, pinned in both modules and committed
lock, registry signature verified by init. Registry metadata also exposed
AzureRM 5.14.0; this stack intentionally keeps the available compatible **4.x**
schema rather than silently adopting a major version. No AzAPI, Fabric, Entra,
random or aliased provider is required/configured. Every test file declares
`mock_provider "azurerm"`; the guard rejects live-provider blocks and aliases.
`command=apply`/`plan` occur **only inside mocked terraform test runs**.

Loaded resource schema versions were measured with
`terraform providers schema -json` from an independently initialized
backend-free `modules\http_service` inside the earlier clean copy:
Linux web app **1**, service plan **1**, user-assigned identity **1**;
resource group, role assignment, private endpoint and diagnostic setting **0**.
The installed schema accepts `dotnet_version="10.0"` and both DLL startups.
This does not prove regional runtime availability.

## Assertions exercised

- Independent `rg/asp/app/id-tcc-dotnet-*` naming, reserved tags and distinct
  `dotnet-api`/`dotnet-gateway` azd tags; .NET-only backend key/output interface.
- Both actual app resources: .NET **10.0**, correct `dotnet …dll` entry point,
  no remote build/container/Python startup; listener port 8080, package mount.
- HTTPS, minimum TLS 1.2 including SCM, FTP/basic publishing off; app/SCM
  deny defaults with no allow exceptions, public networking off, VNet route-all,
  actual private endpoint targets and existing sites DNS zone bindings.
- Separate service identities, identity client settings and each actual Blob
  grant's service principal, container scope and pinned role GUID.
- Actual app settings: Warehouse and lakehouse SQL translations, Blob,
  case-sensitive resource root, explicit Entra/classification/person writer
  controls, revision, hooks/debug off and no unsupported Python/AI/port flags.
  An explicitly empty source schema remains empty.
- Actual diagnostics: metrics only; no request/application/error tracing logs.
- Gateway off removes its complete footprint and returns empty target outputs.
  Default inventory is 1 RG + 1 plan + 2 identities + 4 container grants +
  2 apps + 2 private endpoints + 3 metric diagnostic settings (**15 resources**).
  API-only inventory is **9**; no external storage/network/Fabric ownership.
- Negative configuration runs refuse Worker enablement, orchestrator enablement,
  conflated audiences, unbound group writer policy, empty client binding,
  missing source SQL endpoint, SAS-bearing Blob URL, wrong DLL, Python app name,
  deployed local stores/replay controls and unsupported runtime flags.

## Corrected during validation

Initial init refused Terraform's reserved variable name `source`; renamed it
to **`payroll_source`** throughout. First lint found unavailable topology toggles
unused; outputs now consume their validated-false values, without disabling a
lint rule. A provider-schema probe from the backend-declared root correctly
required backend initialization; no backend was initialized to satisfy it.
Schema measurement moved to the backend-free clean child module. Final required
gates above are all green.

## Native blockers / deliberately not claimed

No Azure/Fabric/Foundry/Entra/customer requests, standalone plan/apply, deployment,
Python hooks, import, state migration or git commit were performed.
Registry/package downloads are the only required network access for cold init.

- Referenced subnet delegation/capacity, private endpoint approval, DNS links,
  outbound firewall paths, regional .NET 10 availability and private SCM/OIDC
  package deployment still need approved native verification.
- No Fabric membership/T-SQL grant, schema migration or publication/lease
  transaction proof. Gateway needs full in-process application/source/Blob access,
  not the Python forwarding gateway's audit-only grant. Operator additions and
  grant handoff are in `README.md`; no external Fabric object enters this state.
- Worker Generic Host has **no HTTP listener**. Its App Service topology refuses
  enablement; the DLL is named only in unavailable metadata, never a fake probe.
- Orchestrator has no resource/identity/ingress; true enablement is refused until
  verified upstream/person assertions, employer binding and bypass protection
  exist. No external channel trust/Foundry readiness is asserted.
- Gateway `/channel/ready` returns constant metadata; `/api/health` is liveness,
  not live native readiness or queue progress. Native gateway release readiness
  must not be inferred from these endpoints.
- Runtime exporter/custom-meter coverage is absent; only platform metrics are
  configured. Safe telemetry integration remains a release prerequisite.
- One gateway instance limits host-local concurrency risk, not restart/session/
  idempotency durability. The process-local 600-second lease lacks periodic
  heartbeat during synchronous computation; no unsupported knob is emitted.
- A dedicated .NET backend must still be configured by the operator/integrating
  manifest. The documented output is the default key, not proof of backend
  selection. Package/resource staging and azd manifest activation are parent-owned.
