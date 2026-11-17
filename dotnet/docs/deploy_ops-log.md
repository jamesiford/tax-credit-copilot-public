# W4 deploy_ops running log

## Plan and guardrails

Task: `prompts\W4\deploy_ops.md`, read in full. Work is confined to
`dotnet\deploy`, `infra-dotnet`, `.github-dotnet` and `dotnet\docs`.
No live Fabric, Foundry, Entra, customer access, Terraform standalone plan/apply,
push, remote change or Python/application edit is authorized.

The generic Azure preparation skill's root `.azure` plan location conflicts
with the task's explicit ownership boundary. This owned document is the plan;
no out-of-scope plan or automatically provisioning hook is created. The task
pre-approves offline implementation; no cloud context or approval is inferred.

1. D1: establish executable/resource/trust contracts. Worker App Service stays
   unavailable without a real progress/health seam; no fake web sidecar.
   Orchestrator external ingress stays disabled without verified upstream
   subject and employer binding. One gateway/orchestrator replica initially.
2. D2: consumer-verified legacy inventory, value-free deployment validator and
   synthetic negative cases.
3. D3: isolated code-deployed Linux App Service infrastructure with mocked
   provider tests, separate names/state/tags and no Python operations hooks.
4. D4: bounded exact resource staging, pinned .NET 10 publishing, nonroot Linux
   images and hermetic executable/container smoke.
5. D5: safe local telemetry receipt and dormant linted CI templates; retain
   custom-meter, heavy-suite and native release limits honestly.
6. D6: operator-owned Python/schema/grant handoff, stable integration contract,
   report/status, local commits and ownership/clean-tree checks.

## Preflight

- Clean initial worktree; branch `dotnet/w4-deploy_ops`, base `006760b`.
- SDK from `dotnet`: **10.0.404**. Oracle: **CPython 3.12.13**.
- Terraform **1.17.1**, local Docker **Linux 29.9.3** available.
- Existing W3 convergence report retains framework waiver cap **9/17** and
  unresolved privacy/catalogue/identity/native scale differences. Deployment
  does not certify or waive them.
- Read W1/W3 architecture, persistence/schema, sources/auth/AI, gateway,
  convergence, orchestrator and three traceability reports; consumer inspection
  confirms `TCC_REPOSITORY_ROOT`, not an invented resource setting.
- D2 configuration and D3 infrastructure are independent bounded delegated
  implementations; D5 telemetry is isolated under deployment ownership.
  Parent owns packaging, images, CI, handoff and final gates.

## Decisions

- No application package or central pin changes. API configured Foundry
  invocation remains unavailable; orchestrator has its own real model factory.
- A `SOURCE_MAPPING_FILE` setting is not supported by ordinary composition:
  `RuntimeSourceRegistration` calls embedded `SourceMapping.Load()` directly.
- The Worker is an actual Generic Host: no HTTP port, hardcoded one-second
  polling, executor's default 600-second lease and no periodic heartbeat during
  synchronous calculation. Emitting Python `RUN_*` settings cannot alter it.
- Hosted Responses maps spoofable header signals. A GUID-shaped assertion is
  not authenticated identity. Deploy-owned startup will fail closed for an
  externally exposed orchestrator; local synthetic proof requires kernel
  network isolation (the SDK ignores loopback URL overrides; see D4).

Subsequent implementation and measured gate results are appended below.

## D1/D2: actual host/configuration observations

- API and gateway are ordinary HTTP hosts; gateway composes business services
  in-process and needs full source/Gold/ops/Blob privileges. Worker is Generic
  Host only. App Service Worker enablement/deployment explicitly refuses;
  no dummy HTTP sidecar was added.
- API unavailable source: `/api/ready` returns **HTTP 200 / ready=false**.
  Gateway `/channel/ready` returns **constant 200 / true** even unavailable.
  These application-owned readiness seams are surfaced, not masked.
- Complete machine-readable legacy inventory and four-service dispositions,
  configuration guide, value-free validator and synthetic examples delivered.
  CPython 3.12.13: **18 configuration tests passed**.
- `SOURCE_SCHEMA` absent => `tcc_source`, empty => `dbo`; ordinary embedded
  mapping has no environment override. Both public synthetic payroll CSVs
  genuinely enter constructors/draft paths and must ship.
- API configured Foundry invocation remains unimplemented; orchestrator's
  separate factory works synthetically. Knowledge remains off. Python store,
  lease/concurrency/mapping controls are never advertised as wired .NET knobs.

## D3: independent infrastructure and azd

- Infrastructure delivered/committed in `7f142a6`; Terraform **1.17.1** /
  AzureRM **4.81.0**, backend-disabled clean-copy init/fmt/validate, **14 mocked
  test runs**, **3 offline guard tests**, TFLint **0.65.0** / ruleset **0.15.0**
  all passed in **28.90 s**. Full command/schema evidence in VALIDATION.md.
- Independent backend/names/tags, Linux `.NET 10` code stacks, startup DLLs,
  UAMIs, private ingress/egress/DNS contracts, Blob roles and diagnostics.
  No new Fabric capacity, Python adoption, provider registration or hooks.
- Owned azd manifest has three explicit .NET service names. Owned MSBuild
  proxies preserve product projects from azd user-secrets initialization.
  Actual API proxy publish produced the product DLL, resources and manifest.
  Full azd environment/package orchestration and all native deployment remain
  unexecuted; no cloud authentication was attempted.
- Official azd source JSON schema validated the independent manifest. The
  documented aka.ms short link returned non-JSON locally; the official public
  repository schema was used instead. `azd package --help` confirms explicit
  service and zip-output selection; no package/deploy cloud context was used.
- Guard defaults off, refuses Worker/infrastructure, then on explicit activation
  checks subscription, exact private .NET ARM target/tags/UAMI/stack/startup and
  pre-staged matching runtime revision. Synthetic metadata fixtures prove a
  matching target passes and public/Python targets fail without Azure.

## D4: bounded artifacts, failures and measured proofs

- SDK **10.0.404** selected from staged `dotnet`; deployment-owned locks,
  locked restore and framework-dependent `net10.0` publication for four actual
  executables. Exact tracked rules/ingested/schema/public-CSV resources,
  embedded mapping and `.resx` prompts are included. No .env/private extract/
  databases/contract seeds/token caches/blanket backend copy.
- Initial omitted prompt `.resx` caused missing resources; including the
  actually consumed resource fixed it. Sanitized Windows child environment
  originally missed uppercase SYSTEMROOT, causing Winsock **10106**; selection
  is now case-insensitive without retaining ambient credentials/settings.
- Linux engine is **arm64**, not amd64. Emulated amd64 SDK build exited **139**;
  native build-platform SDK cross-publishing linux-x64 succeeded. Container
  NuGet HTTPS then failed **NU1301 / OpenSSL handshake**. Explicit optional
  bounded feed of **113 exact public archives** plus fresh locked restore solved
  it; no TLS bypass. Offline vulnerability-feed audit is unavailable, not passed.
- All four multi-stage images built **linux/amd64**, **USER app**, runtime
  **10.0.15**. Base manifests and SDK are pinned; mutable apt contents mean no
  bit-identical full-rebuild promise. Per-file SHA-256/revision/image IDs are
  recorded without configuration.
- Actual API/gateway containers use network none, nonroot/read-only rootfs and
  verified immutable resources/checksums. Health 200, protected 401, reset 404;
  readiness limitations above reproduced; both SIGTERM exit **0**.
- Worker `--once` exit **0** with progress observation, daemon stop **143**.
  Deployed local-store configuration refusal was observed, but qemu left its
  abort unreaped: abnormal exit is explicitly unverified under emulation.
  No healthy-supervisor or graceful-drain claim follows.
- Preview Responses SDK logs **"Overriding address(es)"** and binds
  `[::]:8088` despite `--urls`/ASPNETCORE_URLS. Guard now requires actual
  `/sys/class/net` contain only `lo`, plus explicit local/synthetic proof flags.
  Default and bridge proof exit **78**; only network-none readiness **200** and
  SIGTERM **0** pass. Ordinary publication also proved in this isolated Linux
  namespace, not by exposing the SDK listener on Windows.
- Deterministic sorted/fixed-time zip verifies the manifest first and never
  replaces the previous package on a checksum failure. **10 deployment tests
  passed**, including native-target fixtures and atomic failure cleanup.

## D5: telemetry, CI and unchanged application gates

- Optional BCL-only startup hook delivered under deployment ownership, shipped
  but disabled by default; no central package, ServiceDefaults or host edits.
  It allowlists fixed signal/tag vocabularies, subscribes custom TaxCredit.Ai
  Activity/Meter, exports OTLP/HTTP JSON and emits bounded value-free diagnostic
  codes once/process for invalid enabled settings or export failures.
- Receiver **19 spans / 18 metric batches**, official collector **19 / 19**;
  native arm64 Linux synthetic probe **15 / 20**, two dependency-parent edges,
  four service/version attributions. Exit flush receiver **0.097 s**,
  collector **0.088 s**, Linux SIGTERM **0.383 s**. Stalled exporter shutdown
  **1.722 s**, 503 **0.112 s**. Malformed/partial failure/privacy tests pass.
- Actual published API/gateway each delivered **two server spans / one metric
  series**, health 200/protected 401. Actual dependency correlation is **not**
  proved; controlled probe edges must not be represented as native transactions.
  Direct orchestrator console logging was not sanitized by this hook.
- Dormant CI includes pinned SDK/Python, unchanged build/format/fast tests,
  separate existing API/gateway replay/policy, locked publication/images,
  telemetry receipts, clean-copy mocked Terraform, safe aggregate retention and
  separately scheduled/manual existing heavy suites. OIDC deployment is opt-in,
  private-runner, application-only; no infrastructure/settings/Python operations.
- **actionlint 1.7.7** passed on three explicit template paths with the owned
  config declaring the private runner label. Public tool license verified MIT:
  `https://github.com/rhysd/actionlint/blob/v1.7.7/LICENSE.txt`.
  No new application packages: Hook is BCL-only; existing Agent Framework MIT /
  OpenTelemetry Apache-2.0 dependencies remain unchanged, not repinned.
- Existing .NET solution: warnings-as-errors build **0 warnings/errors**,
  **40.35 s**; formatter passed; fast suite **1,551 passed**. Two reused existing
  bounded Worker heavy tests passed in **12 s**, proving accepted work/publication/
  reopen beyond an empty once loop. No full-heavy pass is claimed.
- Existing semantic runner and unchanged scoring: API **1,514 exchanges /
  2,311 raw differing fields**, **blocked** by framework **9/17 = 52.94%**
  waivers against cap 25%. Gateway **255 exchanges / 523 fields**, **236 pass /
  19 fail**, 11 waived (4.31%), **92.55% >=90**; threshold pass is not parity.
  Raw temporary replay bodies are not retained by the safe CI wrapper.

## D6: operator handoff and release limits

- HYBRID-OPS names actual guarded migration/grant/seed/writer/smoke tools,
  distinguishes dry-run behavior, independent endpoints and identity scopes.
  .NET gateway needs API-equivalent Warehouse grants; lakehouse tool's gateway
  exclusion requires approved enhancement/grants, never an environment bypass.
- Exact five native additions are absent from current authored migrations.
  An approved forward migration is required; the unchanged Python runner cannot
  invent it. No Warehouse DDL, grants, seed or writer edits were performed.
- All writers pause for schema/backfill, native multi-connection transaction/
  fencing/publication checks and compatibility review. Historical equal-time
  override intent is unknowable. Native NOT ENFORCED uniqueness is not proof.
- Documented 600-second unrenewed lease, uncertain-commit reconciliation,
  host-local tickets/confirmations, unsupported knowledge, missing result recovery,
  immutable Blob bytes and rollback without schema downgrade/write erasure.
- Stable artifact/config/health contract is in DEPLOY-REPORT. Integration must
  merge/cherry-pick delivery commits, rebuild/promote verified bytes and verify
  served revision privately; parallel shadow visibility is not assumed.
- W3 privacy/parity, M-01, first-program pricing, zero-worksite SQL/projector,
  leap-window and native money/AVG remain unchanged owner decisions. The
  SELECT 1 spike (3.983 s) is connectivity only. No live/cloud release gate is
  inferred from local build, Docker, telemetry or mock-provider success.

## Final artifact refresh and retained evidence

- Local implementation revision **2e8ba28** was used for the final four locked
  publications and source image rebuilds, including updated Hook diagnostics.
  OCI revision labels were inspected, not merely assumed from build arguments.
- Final hashed file counts: API **179**, Worker **176**, gateway **186**,
  orchestrator **149**. All four packaged Hook byte hashes match the final
  actual API/gateway receiver/collector proof. Each actual host again delivered
  two server spans and one metric series; dependency correlation remains false.
- Final real containers passed exact configured liveness paths, protected/reset
  checks, resources/read-only checks and kernel containment. API/gateway/
  Responses SIGTERM exits **0**, at **0.500 / 0.516 / 0.453 s**; Worker **143**
  at **0.344 s**, with emulated abnormal exit still explicitly unverified.
- Actual API/gateway zips repeated identically (180 / 187 entries); SHA-256,
  sizes, full source revision and inspection results are tracked as aggregates.
- Seven allowlisted aggregate JSON files plus an explanatory index are retained
  under deployment evidence. A redundant standalone Responses evidence filename
  was initially requested during copying but is not produced by ordinary smoke;
  that result is correctly retained inside `published-smoke.json`.
- Exact temporary staging context and initial raw replay directory removed;
  immutable local images/published artifacts remain for inspection. No wildcard
  cleanup, shared process-name kill or Docker prune was used.
