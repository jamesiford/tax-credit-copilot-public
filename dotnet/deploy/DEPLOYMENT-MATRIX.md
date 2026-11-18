# Executable deployment matrix

Source-verified D1/D2 contract; publish/container/live-platform proofs belong to
the parent deployment task. **No native Fabric, Blob, Entra or Foundry validation
is implied.** Unresolved W3 parity/privacy and native schema/grant prerequisites
still gate release. Start commands are plain published DLL invocations, not
`dotnet run`, Python startup scripts or inherited gunicorn worker settings.

| Executable / published entry | Package or image | Resources | Identity / network | Port | Liveness / readiness | Shutdown | Writable storage | Initial replicas |
|---|---|---|---|---|---|---|---|---|
| API: `TaxCredit.Api.dll`; `dotnet TaxCredit.Api.dll` | Parent-owned App Service code package; independent Linux .NET 10 image alternative | `REPOSITORY_ROOT` tree described below; rules + schema + synthetic reference files | Own UAMI; full Warehouse Gold/ops, SQL source read, Blob bytes; Graph only for selected writer policy. HTTPS restricted ingress; VNet/private dependency DNS; validates API bearer trust and acting person/client scope | Explicit `ASPNETCORE_URLS=http://0.0.0.0:8080`; code deployment listener matches platform; no inference from `PORT` | `/api/health`: process status. Parent ordinary-published process smoke measured `/api/ready` **HTTP 200 with `ready=false`** under missing synthetic CSV. Status-only platform probes cannot express API dependency readiness: inspect `ready` body or add a host non-success mapping. Handler reads settled startup observations, not a continuous probe | ASP.NET/Generic Host cancellation on SIGTERM; synchronous certified compute is not immediately interruptible; wait for cancellation/publication boundary; unknown accepted writes need reconciliation | Warehouse decisions + Blob bytes only; read-only resource tree. Ephemeral framework scratch only, not a SQLite durability fallback | 1 initially |
| Worker: `TaxCredit.Worker.dll`; `dotnet TaxCredit.Worker.dll`; finite `--once` | Parent-owned Generic Host process/image **only**; App Service topology unavailable, no wrapper claimed | Same full runtime resources as API; shares graph, not API process | Own attached UAMI or explicitly selected identity; same calculation/store/source/Blob grants as API. No inbound route | **None** | **No HTTP listener, `/healthz`, `/api/health`, or `/readiness`.** `RuntimeStatus.Settle()` is startup observation, not an exposed health endpoint. Queue progress/exit supervision needs an external approved host | Hosted `QueueWorker` observes cancellation; executor releases claimed work on observed cancellation. Synchronous calculation may outlast termination grace; lease expiry protects ownership, not completion certainty | Warehouse queue/leases/manifests; Blob outputs; no local operational DB deployed | 0 on App Service; at most 1 only under approved non-HTTP supervisor |
| Gateway: `TaxCredit.Gateway.dll`; `dotnet TaxCredit.Gateway.dll` | Parent-owned App Service code package; independent Linux .NET 10 image alternative | Same full application resource tree; not an HTTP-forwarding shim | Own UAMI needs **full application data/source/Blob permissions**, not old Python audit-only grant. In-process services; validates gateway audience, service caller roles and verified acting-person/client/writer policy. Restricted HTTPS ingress, private dependencies | Explicit `ASPNETCORE_URLS=http://0.0.0.0:8080` | `/channel/health` and `/api/health`: process status. `/channel/ready` is a **static liveness/config assertion**: HTTP **200**, constant `ready=true`, echoed store label, **no `RuntimeStatus.Readiness` read**. It can remain true with unavailable source. No mapped `/api/ready`; dependency-readiness host seam is a release prerequisite | ASP.NET host cancellation; in-flight commits can be uncertain; never silently retry unknown writes. No durability claim for host-local exclusion/ledger | Warehouse channel audit/confirmations/application state + Blob; host-local fact ledger, limiters, MCP sessions and different-key leases lost on restart | 1; host-local consistency is not scale-out safe |
| Orchestrator: `TaxCredit.Orchestrator.dll`; `dotnet TaxCredit.Orchestrator.dll` (guarded by parent image entrypoint) | Parent-owned Linux `amd64` Responses image; **no externally deployable topology** | Published assemblies and embedded resources only; **no payroll/rules/schema/contract seeds required** | Future contract: model identity + gateway `Channel.Invoke`, no database/payroll/Blob role. Current proof requires a **kernel-isolated network namespace with only `lo`**; no external gateway/model access. SDK ingress does not authenticate original subject | **Fixed measured `http://[::]:8088`**: preview SDK `ListenAnyIP` overrides `--urls`/`ASPNETCORE_URLS`, including loopback requests. URL configuration is not confinement | SDK `/readiness` measured **200** only inside isolated proof namespace; not authenticated ingress or model/gateway readiness. Normal launch and proof on bridge both exit **78** | Isolated `--network none` proof measured SIGTERM exit **0**; published-artifact proof also requires isolated namespace. Responses cancellation is not a production ingress certification | In-memory conversations, confirmations/checkpoints and budgets; restart loses state, unknown writes require authoritative inspection | 0 externally; one isolated synthetic proof only |

Parent D4 measurements (not rerun by D2): four Linux `amd64` source images built;
API/gateway SIGTERM exit **0**; Worker exit **143 under emulation**, which is not
a successful graceful-shutdown proof. Orchestrator default guard exit **78**,
proof flags on a bridge exit **78**, isolated Docker `--network none` SDK
readiness **200** and SIGTERM exit **0**. Its ordinary published artifact also
runs only inside the isolated network namespace because SDK binding ignores
loopback CLI configuration.

## Evidence paths

All source paths below are under `dotnet/src/`:

- API `TaxCredit.Api/Program.cs`, `Hosting/HostComposition.cs`,
  `Endpoints/Framework/FrameworkEndpoints.cs`; shared
  `TaxCredit.ServiceDefaults/Hosting/RuntimeStatus.cs` snapshots store/source
  observations at startup, not continuously on each readiness request.
- Gateway `TaxCredit.Gateway/GatewayHost.cs`, `ChannelEndpoints.cs`,
  `ChannelConfiguration.cs`, `Trust/ChannelAuthenticator.cs`.
  `API_BASE_URL` has no forwarding consumer.
- Worker `TaxCredit.Worker/Program.cs`, `QueueWorker.cs`;
  `TaxCredit.Application/Hosting/RunWorkExecutor.cs`.
  `--once` uses `CancellationToken.None` and prints a processed-item count;
  daemon uses one item per poll, then a one-second wait.
- Orchestrator `TaxCredit.Orchestrator/Program.cs`,
  `Hosting/ResponsesHosting.cs`, `Hosting/RuntimeSettings.cs`,
  `Boundary/IdentityResolver.cs`, `Hosting/ProviderClients.cs`.
  Existing `ORCHESTRATOR-REPORT.md`/traceability documents provide local SDK
  readiness/cancellation evidence, not production ingress certification.

## Resources and durable state

Set **`REPOSITORY_ROOT`**, not nonexistent `RESOURCE_ROOT`.
Parent staging uses `/app/resources` in images and
`/home/site/wwwroot/resources` on App Service: the `resources` directory is under
the published package root, not an external checkout. Locked-restore inputs are
staged by parent-owned deployment tooling, without application/package edits.
Preserve Linux case and:

- Entire authored `backend/rules/**`.
- `docs/data/schema/tcc-schema.sqlserver.sql` and `migrations/*.sql`
  (runtime metadata reads; native DDL application remains Python/operator-owned).
- Tracked synthetic `backend/data/payroll.csv` (wage/reference reads) and
  `backend/data/payroll_pay_periods.csv` (draft previews even when lakehouse selected).
- Tracked `backend/data/rules_ingested/ga_jtc.json` and `tn_jtc.json`;
  omitting them silently changes captured ingestion inputs.

Do not ship private extracts, `.env`, SQLite files, token caches, contract seeds
or all of `backend` as a shortcut. `SEED_ROOT` can name an absent directory
with hooks off. All runtime repositories share `PERSISTENCE_PROVIDER=warehouse`
and `FABRIC_SQL_*`; payroll independently uses `SOURCE_SQL_*`.

Native additions `write_sequence`, `manual_override.write_order`,
`run_work_identity`, `run_source_observation`, `finding_audit` still require
approved operator schema/grant work described in `COMPOSITION-SCHEMA-PROVISIONING.md`.
No schema apply is performed here. Fabric `NOT ENFORCED` constraints do not prove
unique publication or cross-replica exactly-once behavior.

## Deliberately unavailable topologies and negative guarantees

1. **Worker on App Service remains unavailable.** A Linux App Service's HTTP
   startup/health expectations cannot be satisfied by this Generic Host. No dummy
   web listener or sidecar is introduced that could report a dead poller healthy.
   The exact missing seam is an authenticated/no-data HTTP health and progress
   listener coupled to the real worker lifecycle, or a separately approved
   non-HTTP supervisor with bounded-exit/progress/cancellation proof.
2. **Orchestrator is not externally deployable.** Parent startup guard refuses
   normal launch (exit 78). Proof additionally requires explicit synthetic/local/
   proof flags and an actual `/sys/class/net` inventory containing **only `lo`**;
   bridge networking remains refused (exit 78). The SDK's `ListenAnyIP` binds
   `http://[::]:8088` despite loopback `--urls`/`ASPNETCORE_URLS`, so containment
   is the **kernel network namespace**, not URL configuration. Both image and
   published-artifact proof use that isolation. `ResponsesHosting` copies headers
   directly. The SDK's opaque
   `PlatformContext.UserIdKey` and GUID-shaped headers are not authenticated
   Entra subjects. External enablement requires verified upstream issuer,
   audience and tenant; removal/replacement of all caller
   `x-ms-original-subject-*`, `x-ms-user-identity`, `x-agent-user-id`, and `x-client-*`;
   a protected origin that cannot bypass ingress; and actual employer/client
   authorization. A private endpoint is containment, not proof of this binding.
3. **No scale-out durability claim.** Gateway host-local ledgers/limiting and
   different-confirmation key leases, orchestrator checkpoints/sessions/budgets
   require one replica. Sticky routing does not survive crash or prove
   cross-replica exclusivity. Durable gateway confirmations do not preserve the
   orchestrator's pending state or supply the missing result-recovery endpoint.
4. **Lease is not a heartbeat service.** Fixed 600-second lease, max attempts 3,
   initial heartbeat only; no periodic heartbeat during synchronous computation.
   Python concurrency, lease or heartbeat environment strings do not alter it.
5. **Default instrumentation is not an exporter.** Unchanged ServiceDefaults has
   no exporter or custom `TaxCredit.Ai` subscription. The optional deployment-owned
   startup hook has separate local receipt/privacy/shutdown evidence and an
   explicit integration contract in [`telemetry/README.md`](telemetry/README.md).
   It is not automatically installed by Terraform or ordinary application hooks;
   its synthetic telemetry proof does not certify real business monitoring.
   Existing API/gateway model invocation remains unavailable despite Foundry
   endpoint status.
6. **HTTP readiness adapters remain incomplete.** API returns HTTP 200/
   `ready=false` for the measured missing-source case; an HTTP status-only
   platform probe must not treat that as dependency readiness. Use a body-aware
   probe or add a non-success status seam in the application host.
   **Gateway dependency readiness is additionally a missing result seam.**
   `ChannelEndpoints.Map` must expose an appropriate settled dependency result
   (for example via existing `GetReadinessQuery`/`IHostStatus.Readiness`) and map
   unavailable dependencies to a non-success readiness response before that
   route can drive deployment readiness. It currently does neither. A platform
   probe pointed at `/channel/ready` cannot fix it, nor can setting
   `CHANNEL_STORE`. Parent owns the measured negative proof showing HTTP 200/
   `ready=true` with unavailable source; no product host change is made here.

The D2 synthetic configuration negatives are measured in
[`configuration/config-proof.md`](configuration/config-proof.md). Actual process,
image, guard-exit and termination measurements must be appended by the parent
deployment report; they are not fabricated here.
