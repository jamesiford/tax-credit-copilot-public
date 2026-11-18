# D2 configuration evidence and measurements

Scope: `dotnet/deploy/configuration/**`, `CONFIGURATION.md`,
`DEPLOYMENT-MATRIX.md` only. No application, ServiceDefaults, package, cloud,
private-data, CI, provisioning or commit changes were made by this slice.

## Preflight and decisions

Read the W4 deployment task and relevant rows from `PLATFORM-RISKS`,
`PERSISTENCE-REPORT`, `SOURCES-AUTH-AI-REPORT`, `COMPOSITION-REPORT`,
`COMPOSITION-SCHEMA-PROVISIONING`, `HOST-ARCHITECTURE`,
`ROUTES-CONVERGENCE-REPORT`, `GATEWAY-REPORT`, `GATEWAY-CONVERGENCE-REPORT`,
the W3 policy stop (now `INHERITED-W3-RELEASE-BLOCKERS`), `ORCHESTRATOR-REPORT`, all three orchestrator traceability
indexes, contract sections 4–5/findings and the findings/improvement indexes.
Reports distinguish local composition/connectivity from unverified native grants,
transactions, ingress, privacy and cross-replica durability. None is promoted to
native deployment certification by configuration.

Inspected actual shared runtime, paths, source, trust, artifacts, AI, Worker,
gateway and orchestrator consumers, not just Python variables. Additional reads
included `SourceScanner`, embedded `SourceMapping`, `PersistenceSchema`,
`SourceLookupOptions`, `AuthConfiguration`, `ProviderClients`,
`ApiRateLimitOptions`, `SyntheticPreviewSample`, `PortfolioReferenceData`,
`ProgramWageSource` and the real endpoint maps. Legacy `azure.yaml` and the Python
app/worker/channel Terraform modules were reference inputs only.

Important findings:

- Resource root is **`REPOSITORY_ROOT`**, not `RESOURCE_ROOT`.
- Unset schema is `tcc_source`; trimmed empty is SQL **dbo**. Mapping overrides
  are not wired even though library patch support exists.
- Lakehouse SQL server/database are independent explicit settings, with no
  Warehouse or Fabric-item-name fallback.
- `.NET` defaults local/CSV/sqlite/local bytes; deployment lint requires explicit
  durable/Entra posture. Classification enum and allowlist completeness checks
  strengthen deployment policy; runtime alone is not those controls.
- API/gateway use fixed offline Foundry provider; model settings only affect
  orchestrator's real factory. No exporter exists in shared defaults.
- Gateway readiness is a static liveness/config assertion: constant
  `ready=true`/store label, with no `RuntimeStatus.Readiness` consumption and no
  mapped gateway `/api/ready`. Exposing dependency observations with an
  unavailable failure status is a missing host seam and release prerequisite.
  Parent owns the measured HTTP 200/true negative with source unavailable.
  Corrected parent **ordinary-published process** smoke measured API
  `/api/ready` **HTTP 200 with `ready=false`** under missing synthetic CSV.
  The earlier contrary status assumption was unmeasured and disproved; it is
  not evidence. API status-only platform probes cannot express readiness either:
  inspect the body or add the missing non-success host status mapping.
  Source handler reads settled startup observations, not continuous probes.
- Worker has no HTTP listener; fixed 600-second lease, one-second serial polling,
  no periodic heartbeat during synchronous computation.
- **Do not exclude the committed pay-period CSV merely because deployed source
  is SQL**: `SyntheticPreviewSample` reads it for drafts. Also preserve annual
  synthetic payroll and the two tracked captured ingestion JSON files.
- Orchestrator external ingress remains disabled/private; authenticating the
  service or validating a GUID-shaped subject is not verified acting-person
  ingress. Host-local state is not restart/scale durability.

## Commands and outcomes (offline)

Interpreter:
`C:\Projects\py312-oracle\.venv\Scripts\python.exe` reported **CPython 3.12.13**.
No imports from backend or another checkout, dependency installation or credential
acquisition is needed. Set `PYTHONDONTWRITEBYTECODE=1` for clean source checks.

```powershell
& C:\Projects\py312-oracle\.venv\Scripts\python.exe -m unittest discover -s dotnet\deploy\configuration -p test_*.py -v
```

Initial run exposed a validator bug: it refused unchanged setting names whose
**semantics** were classified translated (`DATA_SOURCE`). Corrected dispatch to
reject only old names with an explicit target alias; no test or policy was
weakened. Subsequent measured run: **15 tests passed in 0.176 seconds**.
Final inventory/resource checks and expanded negatives:

| Check | Measured result |
|---|---|
| CPython 3.12 stdlib unit tests, final SDK-binding correction run | **18 passed in 0.266 seconds**, exit 0 |
| Documented literal names, including mixed-case `TF_VAR_*` and `PYTHONNOUSERSITE` | **263 covered; zero missing** |
| Expanded machine inventory | **293 per-name records**, each with all four service dispositions |
| CLI examples (`api`, `worker`, `gateway`, `orchestrator`) | Four `valid:true` results, no values emitted |
| Actual checked-in resource root, API/Worker/gateway `check_resources=True` | All three returned no missing-resource setting names; presence only, not packaged executable proof |
| `git diff --check` restricted to owned D2 paths | Exit 0 |
| Deployment Python module/class/function size inspection | All modules ≤250 lines, classes ≤150, functions ≤40 |

Final negative cases also cover malformed platform booleans, unsafe log-level
emissions, absent OAuth controls, forbidden secret-setting emission and malformed
DNS URL hosts. No secret value is needed to exercise these failures.

Tests cover exhaustive documented-name inventory membership and fields; all four
secretless synthetic examples; missing and empty required inputs; unset/empty/
whitespace schema; malformed runtime-specific booleans; invalid URL/audience/
origin shapes; unsupported/legacy flags; local deployed stores; hooks/ambient
assembly loading; client binding/writer requirements; tenant/audience separation;
provider-role model resolution; TLS, egress, budgets and knowledge refusals;
value-free diagnostics; missing resources; and selected exact consumer syntax.

No values from a real environment, private payroll or fixture copies were used.
The CLI validates manifest syntax/policy only. Real SQL/Blob/Entra/Foundry
availability, packaged executable smoke, Linux execution, SDK ingress
authenticity and termination remain parent/native proof obligations.

Parent integration handoff: Worker App Service stays unavailable; orchestrator
entrypoint defaults to exit **78**. Explicit synthetic/local/proof flags alone
are insufficient: the guard also requires actual `/sys/class/net` entries to be
**only `lo`**. Parent measured bridge proof exit **78**, Docker `--network none`
SDK readiness **200** and SIGTERM **0**. The SDK overrides loopback `--urls`/
`ASPNETCORE_URLS` and binds `http://[::]:8088`; confinement is a kernel network
namespace, not listener configuration. Published-artifact proof uses the same
isolation. Inventory marks that orchestrator override unsupported, with a focused
validator regression case; no externally deployable orchestrator is claimed.
Packaging keeps `resources` under package root and stages locked restore inputs
inside deployment ownership. The D2 slice does not modify those assets.
Parent also reports all four Linux `amd64` source images built, API/gateway
SIGTERM **0**, and Worker **143 under emulation**; the latter does not prove a
graceful Worker shutdown. These are parent D4 measurements, not D2 executions.

Telemetry follow-up: unchanged ServiceDefaults still installs no exporter or
custom AI subscription, but the **separate optional deployment-owned hook** now
has local receipt/privacy/shutdown proofs. See
[`../telemetry/README.md`](../telemetry/README.md) for exact startup settings,
supported signals, drop semantics and remaining product/platform log and native
backend gaps. Terraform does not install/activate that hook. D2 did not run those
telemetry measurements or change the application graph.
