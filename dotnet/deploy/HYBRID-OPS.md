# .NET runtime / Python operator handoff

**Do not release against private payroll yet.** These assets have synthetic local
proof, not native deployment certification. Close the prerequisites in
`dotnet/docs/DEPLOY-REPORT.md` before enabling writers or external channel ingress.
No command below was executed against a live target in this session.

## Responsibility and target boundaries

Keep schema migrations, grants, illustrative seeding and established smoke tools
in **Python**. There is no second .NET migration engine and no automatic
postprovision hook. Use a reviewed operator environment and CPython 3.12, never a
copied application `.env`. Real endpoints, principal names, client bindings and
tokens belong only in the approved operator environment/audit system, never
checked-in tfvars, transcripts, screenshots or CI artifacts.

API and gateway have **separate UAMIs**, each needing actual source SELECT,
Warehouse Gold/ops read/write and Blob operations. Gateway composes business
services in-process; Python's forwarding gateway grants are insufficient.
Worker has no approved App Service host/identity here. Orchestrator is disabled
and must never receive payroll/SQL/Blob access; its eventual identity needs only
approved model egress and its own gateway audience/`Channel.Invoke` service role.
Service authentication never grants the acting person writer or client rights.

| Existing tool | Guard/input and affected identity/state |
|---|---|
| `scripts/apply-migrations.py --target deployed [--dry-run]` | Fabric `FABRIC_WORKSPACE_ID`/`FABRIC_WAREHOUSE_ID` resolve the allowlisted item; `WAREHOUSE_SERVER`/`WAREHOUSE_DATABASE` must independently match. Other target names must be pinned in existing target metadata. Uses the operator's schema privileges, not app identity. **Even dry-run can resolve/contact the target.** |
| Same tool `--bootstrap` | Destructive bootstrap only for an approved fresh target (`FABRIC_CREATED`, or approved pinned target; Azure SQL uses `SQL_CREATED`). An existing `tcc_ops.schema_migration` means pending forward migrations only. Never assert a "created" flag to bypass D22. |
| `scripts/grant-warehouse-sql.py --target deployed --profile api --principal <approved-app-principal> [--dry-run]` | Operator supplies the explicit API **or .NET in-process gateway** principal. `api` grants SELECT/INSERT/UPDATE/DELETE on `tcc_gold`/`tcc_ops`, covering newly added tables; it does not grant Fabric workspace membership. Dry-run prints statements only and does **not** prove target resolution or access. |
| Same tool `--profile gateway` | INSERT/SELECT on `channel_audit` only: **not a .NET gateway profile**. Do not select it for the in-process host. |
| Same tool `--profile lakehouse --principal <approved-api-principal>` | Read-only object SELECT on the guarded lakehouse SQL endpoint using `LAKEHOUSE_SQL_*`/source schema and existing semantic-model table inventory. Requires source-table coverage review against the .NET embedded mapping. It explicitly refuses the configured `GATEWAY_IDENTITY_NAME`: an approved operator-tool enhancement/reviewed grant procedure is needed for the .NET gateway source role. **Do not unset/rename that guard input to bypass it.** |
| `scripts/grant-sql.py --platform azure_sql --target deployed --profile api --principal <approved-app-principal> [--dry-run]` | Azure SQL alternative only: Entra administrator creates users `FROM EXTERNAL PROVIDER`, then grants matching profiles. Independent `SQL_SERVER_FQDN`/`SQL_DATABASE_NAME` are checked against connection `WAREHOUSE_*`; other names need Azure-SQL-pinned metadata. Not the Fabric path or proof that this Terraform stack provisions Azure SQL. |
| `scripts/seed-operational-store.ps1 [-WhatIf]` | Existing wrapper checks `WAREHOUSE_*`, requires `DATA_CLASSIFICATION=synthetic`, selects Python Warehouse stores and `ALLOW_SEED=1`. No DDL. It lacks the migration tool's independent named-target guard: operator must verify the target first. Optional synthetic demonstrations only, never private/client filings. Assertions retain the existing **Illustrative assertion** marker and explicitly state **no prior filing supplied**. |
| `scripts/channel-writers.py list`, `add <oid> [--name ...] [--by ...]`, `remove <oid>` | Uses the Python configured repository and loads local `.env` defaults; **no `--target` guard**. Verify Warehouse selection/connection and operator authority first. Changes durable `tcc_ops.channel_user`; removal preserves history. Grant people, not orchestrator/gateway service principals. Do not retain its identifying console output here. |
| `scripts/live-smoke.py --target <approved-name> [--token-env SMOKE_TOKEN]` | GET-only; explicit names in `SMOKE_TARGETS`; production names also require `--allow-production`. Token stays in operator memory/environment. Tool prints target/results, so no public artifact capture. |
| `scripts/channel-live-smoke.py --only catalog,reads,verify,audit` | Explicit `GATEWAY_BASE_URL`, delegated `GATEWAY_TOKEN`, wrong-audience test token and approved `SMOKE_CLIENTS`; **not** the named-target guard above. Validate destination independently. Default includes writes and rate bursts: never run the default against customer data. `writes` requires explicitly chosen synthetic `SMOKE_WRITE_CLIENT`; `limits` sends 150 concurrent checks. `--compare-local` reads the same live Warehouse through Python; it is not hermetic. Avoid `--evidence` for private operation. |

`scripts/grant-fabric-mi-access.ps1` remains the existing Fabric workspace-role
operator aid; `scripts/channel-smoke.ps1` is an existing entry point, not inherited
as an azd hook. Inspect their guarded inputs before approved use. Azure
Subscription Owner alone supplies neither Fabric item access nor T-SQL grants.
The Fabric service-principal tenant setting, workspace/item roles, source SELECT,
application SQL grants and private DNS/routes all need separate verification.

## Native schema: exact outstanding work

`COMPOSITION-SCHEMA-PROVISIONING.md` is authoritative. All additions live in the
**same operational database/transaction destination as Gold publication**:

| Object | Required native shape/invariant |
|---|---|
| `tcc_ops.write_sequence` | `sequence_name VARCHAR(64) NOT NULL`, `last_value BIGINT NOT NULL`; exactly one `manual_override` sequence row |
| `tcc_ops.manual_override.write_order` | `BIGINT`, populated for every historical row; new append allocation/insertion in one serializable transaction |
| `tcc_ops.run_work_identity` | `client_id BIGINT NOT NULL`, `item_id VARCHAR(64) NOT NULL`, `run_id VARCHAR(64) NOT NULL`; logical uniqueness `(client_id,item_id)` |
| `tcc_ops.run_source_observation` | `client_id BIGINT NOT NULL`, `run_id VARCHAR(64) NOT NULL`, `observation_json VARCHAR(8000) NOT NULL`; logical uniqueness `(client_id,run_id)` |
| `tcc_ops.finding_audit` | `audit_id VARCHAR(64)`, `client_id BIGINT`, `finding_id VARCHAR(128)`, `action VARCHAR(16)`, `actor VARCHAR(256)`, `at VARCHAR(40)`, **all NOT NULL** |

Inspection of the current authored schema/migrations found **none of these five
additions**. The unchanged migration runner cannot create an unauthored migration.
The next approved owner must author/review a forward-only Fabric-compatible
migration in the product schema tree, then use the existing guarded runner.
This task does not fabricate DDL in Terraform or claim its local SQLite upgrade
has applied to Warehouse. Keep monetary **DECIMAL(19,4)**, UTC **DATETIME2(3)**,
typed bindings and existing public IDs unchanged.

Stop **every participating Python and .NET writer**, not just the new Worker.
Backfill missing orders after the existing high water mark under an exclusive
maintenance window, ordered `created_at, override_id, client_id`; seed/update
`last_value` without resetting an existing counter. Verify exactly one sequence
row, no null/duplicate assigned orders, original counts/IDs/timestamps and
idempotent re-execution. Historical equal-timestamp intent was **never stored**:
that order is deterministic repair, not evidence of which save/clear the person
intended. The owner must review those decisions.

Before resuming, prove with two independent native connections and tenants:
save/change/clear/later-save at one timestamp; transactional sequence conflict
handling; durable work identity/source observation; Gold + manifest + claim +
terminal queue publication; cancel/lease fencing and reopen reconciliation.
Fabric `NOT ENFORCED` keys do not prove uniqueness. Verify role grants, supported
isolation/DDL, conflict codes, native numeric AVG/scale and pooled token refresh.
Do not resume an older Python override writer unless its compatibility with the
new ordering protocol has been approved; side-by-side assets do not prove
mixed-runtime writer compatibility.

## First deployment and controlled activation

1. Review the W3 halt/convergence reports and close parity/privacy/calculation
   decisions. Approve native schema/grants and the unavailable hosting seams.
   API/gateway artifacts may be evaluated privately/read-only; this is not full
   runtime activation. With no supervised Worker, do not admit calculation work
   that the deployment cannot process.
2. Have the infrastructure owner verify the dedicated .NET backend account/
   container/environment key, independent resource names and explicit existing
   subnet/private-endpoint/DNS/Fabric/Blob references. No state import/migration,
   root `azd up`, Python resource adoption or provider registration is implied.
   This delivery ran backend-free mocked validation only.
3. Pause ingress/writers for the approved maintenance window, drain or account
   for accepted queue work/leases, apply the reviewed forward migration with
   the existing Python tool, then perform native grants and transaction checks.
   Optional synthetic seeding is separate, never automatic.
4. Validate explicit non-secret settings with the value-free configuration CLI
   and packaged-resource check. Translate `WAREHOUSE_*` to `FABRIC_SQL_*`,
   `LAKEHOUSE_SQL_*` to `SOURCE_SQL_*`; keep tenant/audience/client/person policy
   distinct. Set `SOURCE_SCHEMA` deliberately: absent means `tcc_source`, empty
   means SQL `dbo`. API/gateway need Warehouse/lakehouse SQL/Blob/Entra with hooks
   off; no local-store or anonymous fallback.
5. Promote a checksum-verified immutable package/image. App Service is **code
   deployed .NET 10**, startup at zip root, resource root
   `/home/site/wwwroot/resources`, listener 8080. Docker is a separate alternative,
   not a conflicting container stack on that resource. Use only explicit
   `dotnet-api` or `dotnet-gateway` service selection and the opt-in target guard,
   or the manually activated private OIDC workflow. Provisioning, app-setting
   changes and Python hooks are not part of that workflow.
6. Observe health and dependency evidence separately, verify the actual served
   revision, read-only client scope, wrong-audience/tenant/caller refusal, person
   writer policy and absent contract controls. Preserve SSE streaming without
   buffering/re-serializing figures. Only then deliberately resume the approved
   writer protocol and monitor durable accepted/terminal work.

**Readiness trap:** API `/api/ready` returns 200 with `ready=false` for an
unavailable source; status-only probes are inadequate. Gateway `/channel/ready`
returns constant 200/`ready=true`; it is not dependency readiness at all.
Both platform health paths currently use liveness. API needs body-aware
readiness or non-success mapping; gateway needs the real dependency-result host
seam. Configuration strings cannot fix these application-owned boundaries.

**Orchestrator:** default startup exits **78**. Proof flags alone are insufficient:
the guard requires the kernel namespace to contain only `lo`. The installed SDK
overrides `--urls`/`ASPNETCORE_URLS` and binds `[::]:8088`; a claimed loopback URL
would be unsafe. Local proof uses `--network none`, with `/readiness` reached
only from inside that namespace. External enablement requires reviewed upstream
issuer/audience/tenant authentication, header removal/replacement from a verified
person (`x-ms-original-subject-*`, `x-ms-user-identity`, `x-agent-user-id`,
opt-in `x-client-*`), real employer binding and direct-origin isolation. No such
ingress resource is delivered. SDK readiness does not establish any of these.

## Operations, diagnosis and rollback

| Observation | Check first; do not "fix" with |
|---|---|
| Process health 200, no application data | Settled source/store observation, actual SQL endpoint/database/schema and Fabric/T-SQL grants; not CSV/SQLite fallback |
| Bearer 401 / 403 | Correct API versus gateway audience, tenant/issuer and caller role; then the **person's** client/writer entitlement. Never turn auth off or grant service principal person rights |
| SQL failures / readiness false | Source versus Warehouse endpoint, workspace/item access, per-object/source grants, private DNS/egress, expired pooled token; no invented `LAKEHOUSE_*` runtime alias |
| Blob failures | Correct endpoint, attached UAMI selected by `AZURE_CLIENT_ID`, two container grants and private DNS; no account key/SAS or public-network workaround |
| Queue stops moving | Real accepted/terminal queue state and last progress, supervisor/exit status, lease expiry and native locks. Worker has no HTTP endpoint; don't add a healthy sidecar |
| AI unavailable in API/gateway | `RuntimeAiRegistration` has no configured Foundry invocation factory. Endpoint/model strings do not implement it |
| Orchestrator refusal / lost turn | Default ingress guard or missing verified subject; restart loses workflow state. Do not enable client-header trust or multi-replica scaling as a workaround |
| No telemetry | Hook activation, exact fixed service/version, private HTTPS or shared-namespace collector, receiver health. App Insights connection string alone exports nothing |

The execution lease is fixed **600 seconds**, max attempts 3, initial heartbeat
only; synchronous calculation has no periodic renewal. Worker polls serially at
one-second intervals. Python lease/concurrency settings do not tune it. No fake
queue-lag/lease/readiness/uncertain-write metrics are promised: use real durable
records until application owners add safe instruments.

Retry only **confirmed aborted** SQL 24556, 3960 or 1205 through the existing
boundary. On a timeout/lost acknowledgement, pause the affected write and inspect
durable work identity, reopened queue terminal state, manifest and publication
under proper authority. A commit may already have succeeded. Never blind-retry
with a new key. There is **no gateway result-recovery endpoint** to resolve an
orchestrator's unknown outcome automatically.

The SQL source's count/max-modified data-version stand-in is not a Delta
snapshot or content hash of all consumed payroll. An edit that leaves those
markers unchanged can escape detection. Preserve the run's source observation
and verify native read consistency; do not turn marker equality into a stronger
audit/reproducibility claim.

Keep one gateway/orchestrator replica initially. Restart loses gateway fact
ledgers, limits, sessions/download tickets and host-local key exclusions, plus
orchestrator selections, confirmations/checkpoints and budgets. Sticky sessions
are not crash durability or cross-replica exactly-once execution. SDK response
storage is not proof of durable application workflow recovery. Knowledge
`foundry-iq` is unavailable; leave knowledge off.

Blob adapters preserve immutable output bytes; retained access/audit metadata and
hashes matter across rollback. The current built-in Blob Contributor role also
permits delete: it is **not** a storage WORM policy. Never overwrite/delete bytes
to make an old release appear consistent.

Rollback promotes the previous verified image digest or code zip **and its
reviewed compatible configuration**; pause new admissions, account for in-flight/
uncertain work, preserve Gold/manifests/Blob bytes, restore the matching runtime
`GIT_COMMIT`, then repeat native observations. Do not downgrade/drop schema,
reset sequence counters, erase accepted writes or regenerate confirmations.
Disabling the optional telemetry hook rolls back diagnostics only.

For consumer-side revision proof after deployment, compare the release zip
SHA-256 and embedded `artifact-manifest.json` to approved private SCM/Kudu
inspection of the mounted package, or the container image digest plus OCI
revision/checksum manifest. Check runtime `GIT_COMMIT` independently: run
manifests record it, but a configured string alone does not prove served bytes.
Do not invent a public version endpoint or use `/api/health` as revision proof.
The native private-SCM/OIDC inspection remains an approved operator check.
