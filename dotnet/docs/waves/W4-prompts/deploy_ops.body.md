## Your role

Deliver the deployable .NET 10 operations surface beside the existing Python deployment: independent azd service definitions, Terraform for the API, Worker and gateway, publish/startup packaging, Linux container images including the hosted orchestrator, CI templates, observable health and an explicit Python-operations handoff. This is deployment engineering, not another application-port session.

Implementation belongs in the new `dotnet\deploy\`, `infra-dotnet\` and `.github-dotnet\` trees. The existing root `azure.yaml`, `infra\`, `.github\workflows\`, Python scripts and .NET application projects are reference inputs, not destinations. Put the azd manifest at `dotnet\deploy\azure.yaml`. Workflow files under `.github-dotnet\` are installable templates, not automatically discovered GitHub workflows. Make their activation and relative-path handling explicit in the handoff.

The brief's "everything needed" does not establish that the merged application is release-ready. The platform spike measured connectivity only; W3 reports unresolved ingress, durability and parity boundaries. Deliver runnable deployment assets and measured local proofs, with those deployment prerequisites visible rather than implied solved.

## Preflight

Read `dotnet\docs\PLATFORM-RISKS.md`, `PERSISTENCE-REPORT.md`, `SOURCES-AUTH-AI-REPORT.md`, `COMPOSITION-REPORT.md`, `COMPOSITION-SCHEMA-PROVISIONING.md`, `HOST-ARCHITECTURE.md`, `ROUTES-CONVERGENCE-REPORT.md`, `GATEWAY-REPORT.md`, `GATEWAY-CONVERGENCE-REPORT.md`, `HALT-integrate-W3.md` and `ORCHESTRATOR-REPORT.md`. Read the three `orchestrator-*-traceability.md` documents for their deployment-specific partial/unverified rows. Read `contract\CONTRACT-REPORT.md` sections 4-5, `contract\FINDINGS.md`, `dotnet\docs\findings.md` and the improvements registers.

Inspect the actual consumers before mapping configuration: `TaxCredit.ServiceDefaults\Hosting\RuntimeRegistration.cs`, `RuntimeSourceRegistration.cs`, `RuntimePaths.cs`, `RuntimeTrustRegistration.cs`, `RuntimeAiRegistration.cs`, `TaxCredit.Worker\Program.cs` and `QueueWorker.cs`, `TaxCredit.Gateway\GatewayHost.cs`, and the orchestrator's `Hosting\ResponsesHosting.cs`, `RuntimeSettings.cs` and `Boundary\IdentityResolver.cs`. These source paths are under `dotnet\src\`.

Read `docs\architecture\ENV-VARS.md`, the existing root `azure.yaml`, `infra\modules\app_service\main.tf`, `infra\modules\run_worker\main.tf`, `infra\modules\channel\main.tf`, their tests, and existing CI/deployment workflows. They document the Python deployment, not automatic .NET compatibility. Run build/publish commands from `dotnet` so `global.json` selects SDK 10.0.404; root launches have selected SDK 11.0.100. Keep the existing central package graph, including W3's serviced DI floor, intact.

## Stage D1: settle deployability and trust boundaries first

Create `dotnet\deploy\DEPLOYMENT-MATRIX.md` with one row per executable: published DLL, package/image, entry point, resources, identity, network path, port, liveness, readiness, shutdown, writable storage and initial replica count. Prove these from the executable, not from Python's startup scripts.

The API and gateway are HTTP hosts. The gateway composes application services in-process; it does not forward business calls to a separate API listener. Its identity therefore needs the real application data/storage permissions, not merely the old Python gateway's channel-audit grant. The orchestrator is a separate Responses host calling gateway REST with its own service token and verified acting-person assertions. It has no payroll/database role.

The Worker is currently a Generic Host with bounded polling and `--once`; it exposes no HTTP health listener. Do not copy Python's `/healthz` setting onto it. Establish a working deployment-owned hosting/supervision mechanism for App Service's HTTP startup expectations, or identify the exact missing application seam and keep that topology explicitly unavailable. A dummy healthy web server next to a failed poller is not worker health. Prove child-exit propagation, termination and progress observation for any wrapper.

Resolve the orchestrator trust boundary before describing it as externally usable. `ResponsesHosting` maps incoming headers; the SDK does not supply Python's original-subject object. Specify and implement the deployment-owned ingress controls that authenticate the upstream, validate issuer/audience/tenant, remove caller-supplied identity assertions and replace them only from a verified subject. Cover `x-ms-original-subject-*`, `x-ms-user-identity`, `x-agent-user-id` and opt-in `x-client-*` signals; prevent direct-origin bypass. A GUID-shaped header and an opaque platform user key are not proof of identity or employer authorization. If the selected platform cannot supply the needed binding within this session's paths, retain a disabled/private endpoint and document the precise external work required.

Use one gateway/orchestrator replica initially and record why: gateway ledgers/limiting and different-confirmation key leases are host-local; orchestrator checkpoints and budgets are in memory. Sticky routing is not crash durability or cross-replica exactly-once execution. Record restart effects on confirmations, sessions and uncertain writes.

Result: an evidence-linked matrix and local negative checks demonstrating that a forged identity or a dead Worker cannot look like a deployable healthy service.

## Stage D2: build a consumer-verified configuration contract

Write a machine-readable mapping plus `dotnet\deploy\CONFIGURATION.md`. For each existing variable in `docs\architecture\ENV-VARS.md`, classify it as unchanged, translated, Python-ops-only, platform-injected, unsupported or irrelevant to this executable. Record the .NET consumer, required/default semantics, service scope and non-secret source. Distinguish unset from empty values, especially schemas. Unsupported controls must not be advertised as functioning merely because Terraform can emit a string.

At minimum settle these mappings:

- Python `WAREHOUSE_SERVER` and `WAREHOUSE_DATABASE` feed .NET `FABRIC_SQL_SERVER` and `FABRIC_SQL_DATABASE`; `TCC_PERSISTENCE_PROVIDER=warehouse` selects the shared Gold/ops destination. Separate Python store-selection flags are not separate .NET databases.
- The SQL payroll adapter needs `SOURCE_SQL_SERVER`, `SOURCE_SQL_DATABASE` and `SOURCE_SCHEMA`; old `LAKEHOUSE_SQL_*` inputs and Fabric item names require an explicit mapping. .NET reads through SQL, not Delta/OneLake. `RuntimeSourceRegistration` currently calls `SourceMapping.Load()` without a supplied mapping path; verify support for each advertised mapping override rather than assuming Python's `SOURCE_MAPPING_FILE` family is wired.
- Nonlocal runtime validation requires Warehouse, `DATA_SOURCE=lakehouse`, Blob and contract controls off. Explicitly select deployed auth/classification, correct API/gateway audiences, `CLIENT_ALLOWLIST`, writer source and acting-person policy; do not inherit local SQLite/CSV/anonymous defaults. Gateway trust remains Entra-only.
- Preserve `AZURE_CLIENT_ID`, Blob endpoint, required model/provider settings, role chains, budgets and safe egress. Separate `TENANT_ID`, `AUTH_TENANT_ID`, `API_AUDIENCE`, `GATEWAY_AUDIENCE` and `CHANNEL_GATEWAY_AUDIENCE`. Do not turn one audience into another for convenience.
- `RuntimePaths` needs the product resource/schema root. Publish the exact authored `backend\rules` tree, required schema/migration resources and any genuinely consumed public wage/reference data with correct case-sensitive Linux paths. Verify actual constructor reads before excluding fixtures. Do not ship `.env`, private extracts, databases, tokens or all of `backend` as a shortcut.
- Python `RUN_LEASE_SECONDS`, concurrency, heartbeat and polling controls must be checked against actual .NET consumers. The inherited execution options use a 600-second lease with no periodic heartbeat during synchronous computation; emitting Python settings does not change this.
- Orchestrator defaults include Responses port 8088, `/readiness` from the SDK, knowledge off, debug off, injection/output controls on and TLS verification on. Platform-reserved Foundry variables remain platform supplied. Distinguish the orchestrator's actual model factory from the API runtime's still-unavailable configured Foundry invocation seam.

Provide a value-free configuration validator and synthetic examples that exercise missing settings, malformed booleans, invalid audience/URL shapes, unsupported flags and prohibited deployed local stores. Its diagnostics name settings, not their contents.

Result: every required emitted setting has a verified consumer; every legacy setting has an explicit disposition; packaged executables locate all required resources from a published directory.

## Stage D3: independent azd, Terraform and startup assets

Implement `dotnet\deploy\azure.yaml` with .NET API/Worker/gateway entries and explicit working-directory/build/package behavior. Resolve project/resource paths relative to this manifest, not an operator's incidental current directory. Use distinct .NET resource names, service tags, outputs and remote-state identity; side-by-side assets must not adopt, recreate or mutate Python-managed resources. Existing plans/subnets/Fabric/Blob resources can be explicit references. There is no need to create a replacement capacity or alter its state.

Create `infra-dotnet\` with provider constraints, variables, outputs, modules and mock-provider tests. Represent Linux .NET 10 runtime stacks, startup commands `dotnet TaxCredit.Api.dll`, `dotnet TaxCredit.Worker.dll` and `dotnet TaxCredit.Gateway.dll`, managed identity, HTTPS, certificate verification, restricted ingress, VNet/DNS dependencies, disabled basic-auth publishing and diagnostics. Choose code deployment for the App Service path; container alternatives must be separately explicit, not conflicting runtime stacks on the same resource. Keep Python's migration/grant hooks out of automatic provisioning for these new assets.

Validate a clean, explicitly located copy with backend disabled: `terraform init -backend=false -input=false`, `terraform fmt -check -recursive`, `terraform validate` and `terraform test`, plus the repository's existing Terraform linting pattern where applicable. These are offline/mocked validations only. Do not run standalone Terraform plan/apply commands. Every test provider, including aliases, must be mocked; reject a test fixture that could contact a real subscription or Fabric. The existing Python tests contain plan/apply test-run modes: use mock-backed test execution, not a copied real provisioning workflow.

Assert actual resource attributes: .NET stacks and DLL startup, disabled/enabled optional resources, unique service tags and names, no Python commands or Python resource ownership, required translated settings, hooks/debug off, network restrictions and identity attachments. Prove invalid configurations fail. Report provider/schema versions and the clean-copy command outcomes.

Result: validated independent infrastructure and an azd packaging path that can select only .NET services; no change to Python state or deployment files.

## Stage D4: portable Linux images and artifact proofs

Create multi-stage Dockerfiles/startup assets under `dotnet\deploy\` for API, Worker, gateway and orchestrator. Publish with the pinned SDK and run against .NET 10 Linux runtime images, as a non-root user where supported. The orchestrator target is `linux/amd64`, Responses on 8088 with SDK readiness and SIGTERM handling. Use the actual installed preview Responses hosting package rather than Python's image, vendoring step or entry point.

Use a bounded build context and deployment-owned ignore/staging logic; no dependency on editing root `.dockerignore` or application `.csproj` files. Include shared runtime assets such as rule/schema files without copying development secrets. Make artifact checksums and commit provenance available without logging configuration. Ensure App Service's port setting, executable URL configuration, container `EXPOSE` and readiness probes agree.

Build the images when the local Linux engine is usable; smoke-test the ordinary published executables and containers with synthetic configuration/fake dependencies. Check API/gateway health, unavailable readiness, unauthorized protected calls, absent contract-control routes, resource resolution, orchestrator `/readiness` and cancellation/shutdown. Worker checks must cover actual process/progress behavior from D1. A local image proof is not native Fabric/Blob/Entra or Foundry hosting certification. Record a precise unavailable-tool or runtime failure rather than a successful image claim.

Result: reproducible publish/image instructions, buildable artifacts and a per-service smoke matrix with measured versus unverified deployment behavior.

## Stage D5: telemetry and CI that operate rather than merely declare

Inventory actual instrumentation in `TaxCredit.ServiceDefaults\Extensions.cs`: ASP.NET/HTTP/runtime instrumentation is registered, but no exporter is installed there and the custom `TaxCredit.Ai` Activity/Meter is not explicitly subscribed. `APPLICATIONINSIGHTS_CONNECTION_STRING` alone is not proof of exported telemetry. Within deployment ownership, provide a verified supported startup/agent/collector integration, or isolate the exact missing host changes as a release prerequisite. Do not edit ServiceDefaults or central packages from this session.

Demonstrate an emitted synthetic trace/metric reaching a local collector or test receiver, service/version attribution, API/gateway-to-dependency correlation, graceful flush and the behavior when the collector fails. Distinguish available automatic telemetry from absent custom-meter coverage. Exclude request/query/body/header contents, model prose, person/client identifiers, tokens and exception details from logs and exporters. Include safe queue lag, lease expiry, retry/refusal, readiness and uncertain-write monitoring only where a real signal exists.

Create lintable CI/workflow templates under `.github-dotnet\`: pinned SDK 10 and CPython 3.12 configuration, deterministic restore/build/publish, existing formatting/tests, hermetic API and gateway replay separately, clean-copy mocked Terraform validation, Linux image build/smoke and safe artifact retention. Keep expensive existing heavy suites visibly scheduled rather than replacing them with a fast-only claim. Reuse tests without copying their logic. Run actionlint with explicit template paths because default discovery targets `.github\workflows`.

Deployment templates may package or deploy application artifacts only when explicitly activated against pre-provisioned .NET targets with OIDC and target assertions. Do not copy the existing workflow's infrastructure-changing steps or Python postprovision chain. Templates remain dormant in this task. Document that `.github-dotnet` is not natively executed by GitHub.

Result: telemetry receipt evidence and locally validated CI assets, with honest labels for any application-owned observability gap.

## Stage D6: Python operator handoff and deployment report

Write `dotnet\deploy\HYBRID-OPS.md` and `dotnet\docs\DEPLOY-REPORT.md`. Keep migrations, grants, seeding and established smoke tools in Python. Name the existing tools (`scripts\apply-migrations.py`, `grant-warehouse-sql.py`, `grant-sql.py`, `seed-operational-store.ps1`, `channel-writers.py` and relevant smoke scripts), their guarded target inputs and the identity/service each operation affects. Describe operator invocation and ordering, not a second migration implementation.

Carry the exact native additions from `COMPOSITION-SCHEMA-PROVISIONING.md`: `write_sequence`, `manual_override.write_order`, `run_work_identity`, `run_source_observation` and `finding_audit`. They have local proof, not an applied Warehouse migration. Explain historical equal-timestamp override ambiguity, supported grants, transaction verification and why Fabric NOT ENFORCED constraints do not prove uniqueness. Determine which existing operator scripts can supply these additions and identify missing approved operator work without editing them.

Document first deployment, resource/config validation, writer pause/resume, identity grants, smoke observations, role-specific failure diagnosis and image/config rollback. Cover the process-local 600-second lease, unknown commit reconciliation, ticket/session loss, immutable Blob bytes, unsupported knowledge retrieval and the lack of a gateway result-recovery endpoint. Rolling back an image is not undoing accepted writes or downgrading schema.

Integration runs in parallel, not after this session. Publish a stable artifact/config/health contract in the report, and describe consumer-side verification of the deployed revision; do not assume the shadow session can see this branch before wave integration. Separate assets delivered, local proofs, native prerequisites and remaining owner decisions.

## Traps to expect

- Old contract sections 4-5 recommend several framework-byte emulations that current host policy intentionally supersedes. Preserve money-string scale, null/presence, error families, auth order and SSE streaming; do not install a proxy that buffers SSE or reserializes tool figures.
- App Service runtime selection does not solve Generic Host Worker health, exporter registration or orchestrator subject authenticity. These are D1/D5 experiments, not checklist checkmarks.
- `PLATFORM-RISKS.md` proves only guarded `SELECT 1` connectivity (3.983 seconds including open). Bulk paths, source reads, fingerprints, Linux Delta and native publication remain untested. No deployment claim follows from Docker availability.
- The in-process gateway has a different privilege footprint from Python's HTTP-forwarding gateway. Keep least privilege service-specific without inheriting insufficient audit-only grants.
- .NET package versions are current merged evidence, not the spike's historical package recommendations. Root SDK 11 asset/analyzer repairs do not change the .NET 10 runtime target.
- M-01 ingestion precedence, first-program multi-program pricing, zero-worksite SQL/projector differences, strict leap-window context and native monetary AVG remain unresolved calculation boundaries, not deployment corrections.

## Evidence this plan is based on

- `dotnet\docs\PLATFORM-RISKS.md` and `platform-risks-log.md`: repaired `BulkOpenRowset` guard, 20 negative/11 positive fixtures, limited connectivity and zero scratch objects; no throughput certification.
- `dotnet\docs\PERSISTENCE-REPORT.md` and `COMPOSITION-SCHEMA-PROVISIONING.md`: actual money DDL is DECIMAL(19,4), exact typed binding, operator-owned additions and unverified native transaction/grant behavior.
- `dotnet\docs\COMPOSITION-REPORT.md` and `HOST-ARCHITECTURE.md`: ordinary API/Worker shared graph, real readiness, resource discovery, native configuration, hook-off deployed posture and lease limitations.
- `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`: SQL read path, count/max marker limits, Blob-only deployed durability, safe telemetry vocabulary and partial strict leap-shift bridge.
- `dotnet\docs\GATEWAY-REPORT.md`, `GATEWAY-CONVERGENCE-REPORT.md` and `HALT-integrate-W3.md`: standalone in-process gateway, unresolved parity/identity/privacy issues and local-only idempotency exclusivity.
- `dotnet\docs\ORCHESTRATOR-REPORT.md` and its three traceability indexes: actual Responses hosting, port 8088, W4 ingress obligation, in-memory checkpoints and missing unknown-write recovery contract.
- `contract\CONTRACT-REPORT.md`, `contract\FINDINGS.md`, `dotnet\docs\findings.md` and `docs\architecture\ENV-VARS.md`: wire traps, inherited calculation boundaries and the Python-to-.NET configuration inventory.
