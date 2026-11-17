# W4 deployment and operations report

## Result and release boundary

Independent .NET 10 deployment assets are delivered beside the unchanged Python
deployment: bounded locked publication, four nonroot Linux source images,
independent guarded azd/Terraform, consumer-verified configuration, optional
safe-export telemetry and dormant CI templates. **Nothing was deployed or
activated.** No live Fabric, Foundry, Entra, Blob, SCM or customer access was used.
There was no push, PR, remote/state change or product/Python edit.

The application is **not release-approved**. The unchanged API semantic policy
still fails W3's framework waiver cap; gateway's threshold pass is not parity.
App Service Worker health, externally authenticated orchestrator ingress, native
schema/grants/transactions, meaningful gateway dependency readiness and inherited
privacy/calculation decisions remain prerequisites. This delivery does not
silently convert them into infrastructure settings.

## Stable integration contract

Consumers need the delivery commits integrated first; a parallel shadow worktree
cannot be assumed to see this branch. Paths below are repository-root-relative.
Use these interfaces rather than copying Python startup or backend configuration.

| Contract | Stable interface |
|---|---|
| azd | `dotnet/deploy/azure.yaml`, explicit `-C dotnet\deploy`; only `dotnet-api`, `dotnet-worker`, `dotnet-gateway`. Preprovision refuses; predeploy defaults off, rejects Worker and checks exact .NET target/revision before an approved API/gateway deployment |
| Terraform | `infra-dotnet`, independent remote-state identity, `tcc-runtime=dotnet`, `tcc-ownership=infra-dotnet`, distinct azd environment/service tags. API and optional gateway code-deployed Linux `.NET 10`; Worker enablement rejected. Existing source/Gold/Blob/network resources are references, not adopted resources |
| Build/publication | SDK **10.0.404**, framework-dependent **net10.0**; `publish.py --service <name> [--runtime linux-x64]`, output `.artifacts/publish/<name>`; deployment-owned locks and fresh locked restore |
| Binaries | `TaxCredit.Api.dll`, `TaxCredit.Worker.dll`, `TaxCredit.Gateway.dll`, `TaxCredit.Orchestrator.dll` at publication root, launched with `dotnet` |
| Resource root | `TCC_REPOSITORY_ROOT` points at publication `resources`: `/app/resources` in images, `/home/site/wwwroot/resources` in App Service. API/Worker/gateway retain exact authored rules, ingested JSON, schema/migrations and two consumed public CSVs. Orchestrator has no such data |
| Configuration | `dotnet/deploy/configuration/inventory.json`, value-free validator and synthetic examples; `CONFIGURATION.md` explains all legacy dispositions. Nonlocal: shared `TCC_PERSISTENCE_PROVIDER=warehouse`, `FABRIC_SQL_*`, independent `SOURCE_SQL_*`, `DATA_SOURCE=lakehouse`, Blob, explicit Entra/audiences/client/person policy, hooks off |
| API HTTP | Port **8080**, `/api/health` 200; `/api/ready` may be **200 with `ready=false`**. Do not equate transport status with ready. Protected request without bearer 401; contract reset absent/404 |
| Gateway HTTP | Port **8080**, `/channel/health` 200; `/channel/ready` is **constant 200/true**, not dependency observation. In-process application graph needs real SQL/source/Blob grants. Protected tool list without bearer 401; reset absent/404 |
| Worker | Generic Host; no port, EXPOSE, probe or invented sidecar. `--once` finite progress/exit; daemon serial polling. Portable image exists; **App Service unavailable** pending lifecycle-coupled supervision/health seam |
| Orchestrator | SDK Responses **8088**, `/readiness`; no azd/public resource. Default exit **78**. Proof requires local/synthetic/explicit flags **and kernel namespace with only `lo`**. SDK binds `[::]:8088` despite URL overrides; only `--network none` proof is permitted |
| Provenance | Publication `artifact-manifest.json`: service, full git commit, per-file SHA-256. Images: OCI revision, image ID, `/app/checksums.sha256`. Zips: fixed entry order/timestamps plus `.zip.sha256`; no configuration dumps |
| Optional telemetry | Included under `telemetry`, disabled until explicit `DOTNET_STARTUP_HOOKS`; exact safe service/version/endpoint contract in `telemetry/README.md`. No Application Insights auto-export assumption |
| CI | `.github-dotnet/*.yml`, explicitly linted with owned `actionlint.yaml`. Not discovered by GitHub until an operator deliberately installs them under `.github/workflows` |

`DEPLOYMENT-MATRIX.md` is the evidence-linked per-executable matrix, including
identity, shutdown, storage and replica limits. `README.md` in the deployment
tree gives reproducible publication, image and azd packaging instructions.
App Service is code deployment; containers are an explicitly separate option,
not two conflicting stack settings on one app.

### Revision verification after integration/deployment

Integrators must repeat bounded publication from the reviewed integrated commit,
check the manifest/resources and verify the checksum of the artifact actually
promoted. After an approved native deployment, compare mounted-package manifest
and bytes using private authorized SCM inspection, or inspect the deployed image
digest/OCI revision and checksum manifest. Independently check runtime
`GIT_COMMIT`, which run manifests record. A configured revision string or health
200 alone proves neither served bytes nor native data access. That private
consumer-side OIDC/SCM check was not executed here.

## Measured local proof

Evidence below is synthetic, aggregate-only. No application comparison, threshold
or existing waiver register was weakened; the session's improvements register is
empty because deployment introduced no intentional HTTP/calculation divergence.

| Gate/proof | Observed result |
|---|---|
| Existing solution build | SDK 10.0.404, warnings-as-errors: **0 warnings, 0 errors**, 40.35 s |
| Existing formatter | `dotnet format TaxCredit.slnx --verify-no-changes --no-restore`: passed |
| Existing fast tests | **1,551 passed**: API 370, Architecture 16, Domain 18, Gateway 103, AI 167, Auth 147, Persistence 130, Sources 108, Orchestrator 431, Parity 61 |
| Existing bounded Worker heavy tests | **2 passed / 12 s**: real accepted work consumed by finite Worker; publication survives reopen. Reused existing tests, not copied logic |
| Deployment-owned tests | **10 passed**: bounded tracked staging/resources, embedded mapping/prompts, cleanup bounds, checksum/extra-file refusal, deterministic zip, refused Worker/unactivated deploy and positive/negative mocked native target assertions |
| Configuration | **18 passed** under CPython **3.12.13**; full legacy-name inventory, four executable dispositions, explicit negatives and resource proof |
| Terraform clean-copy | Terraform **1.17.1**, AzureRM **4.81.0**: backend-disabled init, fmt, validate; **14 mocked runs**, **3 offline guard tests**, TFLint **0.65.0** / AzureRM ruleset **0.15.0**, all passed, 28.90 s |
| Ordinary publication | Four actual executables with exact resources/prompts, deployment-owned locks, fresh locked restore, checksums and optional hook. Ordinary API/gateway health/auth/reset/resource checks passed; finite Worker exit/progress and deployed-local-store refusal verified |
| azd packaging primitive | Actual deployment-owned MSBuild API proxy published the product DLL/resources/manifest without modifying product projects. Full azd environment orchestration and deployment were not run |
| Linux source images | All four built **linux/amd64**, `USER app`, runtime **10.0.15**, bounded context. Actual SDK build used native build-platform on this **arm64** engine, not unstable emulated SDK execution |
| API/gateway containers | Network disabled, nonroot/read-only resources, every checksum verified; liveness 200, protected 401, contract reset 404. API unavailable-ready body false; gateway static false-positive readiness explicitly observed. SIGTERM exit **0** for both |
| Worker container | Finite `--once` exit **0**, actual progress message; daemon termination **143**, not a graceful-drain claim. Invalid deployed config refusal observed, but qemu abort was not reaped: **abnormal exit unverified under emulation** |
| Responses container/publication | Default and bridged-proof exit **78**; only isolated namespace `/readiness` **200**, SIGTERM exit **0**. Published ordinary artifact also verified/run in isolation because SDK ignores loopback URL overrides |
| CI templates | Explicit three template paths with **actionlint 1.7.7**: passed; private runner label declared, not waived. Heavy suite remains separately scheduled/manual |
| Telemetry | Real local receiver/official collector receipts, synthetic service/version and dependency-parent checks, custom `TaxCredit.Ai` subscriptions only with hook, exit flush and collector-failure proofs; see dedicated tracked telemetry evidence and limitations below |

Final artifact/source revision is **2e8ba28**. Rebuilt publications hash **179 /
176 / 186 / 149** files respectively (API/Worker/gateway/orchestrator); all four
packaged Hook DLL hashes equal the Hook actually used for final product-host
receipt. Actual API/gateway zips each repeated identically (**180 / 187** entries).
Final container SIGTERM times: API **0.500 s**, gateway **0.516 s**, Worker
**0.344 s** (exit 143), Responses **0.453 s**. These measurements and image IDs
are persisted under `dotnet/deploy/evidence`, not just ephemeral shell output.

The build/format/fast command ran from `dotnet`, not the root's SDK 11.
The full existing heavy suite was not claimed; templates schedule it.
Terraform `VALIDATION.md` records exact clean-copy commands/provider schemas;
all providers, including test aliases, are mocked. No standalone plan/apply ran.

### Existing semantic replay: not a release pass

The existing CPython 3.12 runner and unchanged semantic policy were exercised
separately for API and gateway; `ci_replay.py` persists aggregate counts only.

| Group | Exchanges/cases | Passed / failed | Waived | Policy observation |
|---|---:|---:|---:|---|
| API overall | **1,514** | Per groups below | n/a | **Blocked**; 2,311 raw differing fields |
| API `_unassigned` | 317 | 238 / 79 | 0 | 75.08%; no scored threshold assigned |
| API `ai` | 27 | 27 / 0 | 3 (11.11%) | 100%, threshold 90 met |
| API `claims_artifacts_rules` | 316 | 295 / 21 | 70 (22.15%) | 93.35%, threshold 90 met |
| API `drafts_runs` | 323 | 313 / 10 | 68 (21.05%) | 96.90%, threshold 90 met |
| API `framework` | 17 | 17 / 0 | **9 (52.94%)** | Accuracy threshold met; **25% waiver cap failed** |
| API `reads_calc` | 414 | 406 / 8 | 26 (6.28%) | 98.07%, threshold 95 met |
| API `workspace_sealed` | 96 | 79 / 17 | 3 (3.12%) | 82.29%; no scored threshold |
| Gateway | **255** | **236 / 19** | 11 (4.31%) | **92.55%**, threshold 90/cap met; **523 raw differing fields remain** |

Pass/fail counts use the existing policy's treatment of registered improvements;
waived counts are not additional cases. The API CI job intentionally remains red
under that policy. Gateway's remaining nineteen failures include inherited
privacy/catalogue/identity boundaries; its policy pass is not native approval.

## Implementation findings and deviations

- **Resources are constructor inputs, not packaging decoration.** Omitting
  prompt `.resx` broke publication; both public payroll CSVs are consumed,
  including draft paths. The stager now includes these exact tracked inputs,
  not the private reference extract or all backend files.
- **Linux build diagnosis:** emulated amd64 SDK exited **139**. Native SDK
  build-platform + cross-publication fixed that. Container NuGet then failed
  `NU1301` / OpenSSL handshake; a separately selected bounded feed of **113**
  cached exact public archives plus fresh locked restore succeeded. TLS stayed
  verified. The offline run cannot claim online vulnerability-feed audit.
- **Runtime readiness is weaker than its names.** API returned HTTP 200 on false
  readiness; gateway returned static true with the source unavailable. No
  deployment flag changes those contracts. They remain application release seams.
- **SDK URL configuration is not containment.** The preview host logged
  `Overriding address(es)` and bound `[::]:8088` despite loopback `--urls`.
  The fail-closed wrapper now observes kernel interfaces; explicit proof on a
  bridge is refused. No externally usable orchestrator is represented.
- **No fake Worker health.** Terraform/deploy refuse its App Service topology.
  Windows ordinary-process termination is not Linux graceful shutdown, and
  emulated exit 143 is not proven drain/requeue. Re-run abnormal-exit/drain proof
  on native amd64 before choosing a supported non-HTTP supervisor or adding the
  real application-owned lifecycle/health seam.
- **azd project isolation:** deployment-owned proxy projects absorb packaging/
  user-secrets initialization; the actual published entry remains the product
  DLL, not the proxy library. No root manifest, application project, existing
  workflow or Python hook changed.
- **Telemetry is opt-in.** The BCL-only startup hook avoids changing central
  packages/ServiceDefaults. Its allowlist drops body/header/query/URL, prose,
  identifiers, tokens and exception details; collector diagnostics are bounded
  value-free codes. Service attribution is fixed, not inferred from customer
  config. See `telemetry/README.md` for measured host/probe scope; a synthetic
  probe correlation is not a native SQL/model transaction certification.
  Final dedicated proof received **19 spans / 18 metric batches** at the
  synthetic receiver and **19 / 19** through the official collector; a native
  arm64 Linux probe received **15 / 20**, with **two** dependency-parent edges.
  Actual ordinary published API **and** gateway each emitted **two server
  spans and one metric series**, health 200/protected 401. Actual product
  dependency correlation remains absent; the edges are synthetic probe
  evidence. Measured flush: receiver **0.097 s**, collector **0.088 s**, Linux
  SIGTERM **0.383 s**; stalled exporter shutdown **1.722 s**, HTTP 503 shutdown
  **0.112 s**. Invalid enabled configuration and failed export emit only
  once-per-process fixed diagnostic codes; disabled-by-choice is quiet.
- **Observability gaps remain real:** no fabricated queue-lag, lease-expiry,
  retry/refusal, dependency-readiness or uncertain-write instruments. Durable
  queue/manifests remain the authoritative operator evidence. Direct
  orchestrator console logging and inherited gateway privacy gaps need
  application-owner review; a safe exporter does not sanitize those log paths.

No application dependency was added or upgraded. Existing Agent Framework
**1.28.0**, Responses **1.0.0-beta.9** / Core **beta.30** and DI **10.0.13**
remain intact. The optional Hook uses BCL only. Public development tools stay
outside the shipped application; no commercial mediator was introduced.

## Native prerequisites and owner decisions

[`HYBRID-OPS.md`](../deploy/HYBRID-OPS.md) gives exact Python operator tools,
target guards, identities, maintenance order, diagnosis and rollback. Key
outstanding work:

1. **Approve/author native forward migrations.** `write_sequence`,
   `manual_override.write_order`, `run_work_identity`, `run_source_observation`
   and `finding_audit` have local application proof but are absent from current
   authored Warehouse DDL/migrations. Existing `apply-migrations.py` can run an
   approved migration, not invent it. Pause all writers, review historical
   equal-timestamp ambiguity, preserve DECIMAL(19,4)/DATETIME2(3), verify native
   serializable conflict/fencing/publication and no duplicate logical keys.
   Fabric NOT ENFORCED uniqueness is not evidence.
2. **Approve service-specific access.** .NET gateway needs API-equivalent
   Warehouse grants plus source/Blob, not Python audit-only grants. Existing
   lakehouse grant tool refuses the configured gateway principal; do not bypass
   that guard. Approve an operator-tool/profile enhancement or reviewed grants,
   workspace/tenant roles, UAMIs, private routes/DNS and pool token renewal.
3. **Choose Worker supervision and honest readiness.** No App Service Worker
   is created; no work should be admitted that cannot be processed. Supply
   lifecycle-coupled process health/progress/abnormal-exit handling and native
   amd64 termination proof, plus real dependency readiness/non-success behavior.
4. **Supply verified upstream subject/employer binding.** Strip and replace all
   incoming identity assertions only after issuer/audience/tenant verification,
   isolate origin and test spoofed/opaque/cross-client subjects. Keep
   orchestrator disabled until then. One gateway/orchestrator replica is the
   initial ceiling; sticky routing does not solve memory loss or key exclusivity.
5. **Resolve inherited application decisions.** W3 halt/privacy/parity,
   ingested-over-year-pack M-01 (contrary to ADR-005), first-program pricing,
   zero-worksite SQL/projector, leap-window context and native monetary AVG/
   precision remain unchanged. No changed figure was waived as an improvement.
6. **Approve native deployment/promotion.** Dedicated .NET backend/targets and
   protected private OIDC runner; no Python resource/state adoption. Review
   optional telemetry activation and full privacy, run the scheduled heavy gate,
   then verify mounted revision and native end-to-end behavior. The spike's
   SELECT 1 / **3.983 s** is connectivity only, not throughput or cutover proof.

The 600-second lease lacks periodic renewal; uncertain commits require reopened
queue/manifest/publication reconciliation, not blind retry. Restarts lose
gateway tickets/ledgers and orchestrator confirmations/checkpoints/budgets;
there is no result-recovery gateway endpoint. Knowledge retrieval remains off.
Blob immutable bytes must be preserved; built-in Contributor is not WORM.
Image/config rollback does not undo accepted writes or downgrade schema.
The source count/max-modified marker is a weak data-version stand-in, not a
transactional Delta snapshot; edits preserving those markers may be missed.

## Delivery index

- `dotnet/deploy/README.md`: publication, source images, bounded offline restore,
  azd service selection and lock maintenance.
- `dotnet/deploy/DEPLOYMENT-MATRIX.md`, `CONFIGURATION.md`,
  `configuration/config-proof.md`: executable and configuration evidence.
- `infra-dotnet/README.md`, `VALIDATION.md`: isolated infrastructure interface
  and clean-copy mocked validation.
- `dotnet/deploy/telemetry/README.md`, `telemetry/evidence/`: safe collector proof
  with measured versus unverified boundaries.
- `.github-dotnet/README.md`: dormant CI/deployment template installation.
- `dotnet/deploy/HYBRID-OPS.md`: guarded Python operations and native checklist.
- `dotnet/deploy/evidence/`: selected sanitized aggregate local results; raw
  replay bodies/configuration/tokens are not retained there.
- `dotnet/docs/deploy_ops-log.md`, `improvements/deploy_ops.json`,
  `status/deploy_ops.json`: running decisions and machine-readable handoff.
