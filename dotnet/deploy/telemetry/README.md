# D5: optional deployment-owned telemetry

**Measured locally; not a cloud or application-release certification.**
No application project, ServiceDefaults, central package file or Python asset is
changed. This tree contains the runtime startup hook, synthetic host, collector
configuration, receipt tests and aggregate-only evidence.

## What actually exports

`src/TaxCredit.ServiceDefaults/Extensions.cs` registers ASP.NET Core/HTTP/runtime
instrumentation, **no exporter**, and neither `AddSource("TaxCredit.Ai")` nor
`AddMeter("TaxCredit.Ai")`. API/gateway use those defaults; Worker uses them on its
Generic Host. `APPLICATIONINSIGHTS_CONNECTION_STRING` alone does not export.

The optional hook uses the supported [.NET startup-hook mechanism][hook],
`ActivityListener` and `MeterListener`, and sends [OTLP/HTTP JSON][otlp] to a
collector. It is **deployment-owned code, not the OpenTelemetry automatic
instrumentation distribution or an Azure Monitor SDK**. The production hook has
**zero NuGet dependencies**: no assembly-binding competition with the existing
OpenTelemetry SDK. Both independent projects set
`ManagePackageVersionsCentrally=false`; all outputs stay in `.artifacts/`.

| Signal | Existing defaults alone | Enabled hook |
|---|---|---|
| ASP.NET incoming / HttpClient outgoing spans | Instrumented, no export | Subscribed and exported; W3C IDs preserve parentage |
| Native request/dependency duration meters | Instrumented, no export | Two named instruments exported |
| `TaxCredit.Ai` activity/meter | Not subscribed | Explicit source and instrument allowlist |
| `TaxCredit.Orchestrator.Tools` activity | Not subscribed here | Explicitly subscribed when emitted |
| Runtime metrics | Registered in defaults, no export | **Not exported**; no observable-meter polling |
| SQL/Blob SDK dependency spans | Not established | **Not subscribed**; HTTP transport may emit its own dependency |
| Logs | No exporter added here | **No log capture/export** |
| Queue lag, lease expiry, readiness state, uncertain writes | No meter found in inspected host paths | **Not fabricated or inferred from HTTP success** |

`ActivityAiTelemetry.cs` actually emits the named AI instruments;
`RuntimeAiRegistration.cs` registers that adapter, but its Foundry runtime is
currently unavailable. A listener cannot create successful provider calls.
`ToolSession.cs` emits orchestrator tool activities; synthetic tests do not invoke
Foundry, run the Responses host, or claim its business coverage.

## Startup integration contract

From `dotnet`, using SDK **10.0.404**:

```powershell
dotnet publish deploy\telemetry\Hook\TaxCredit.Deployment.Telemetry.csproj -c Release -o deploy\telemetry\.artifacts\publish\hook
```

Copy the published hook DLL to a **separate, immutable** directory in the runtime
image/package (for example `/opt/tcc-telemetry/`). Before the ordinary `exec dotnet
TaxCredit.Api.dll` entry point, set the following Linux environment:

```sh
DOTNET_STARTUP_HOOKS=/opt/tcc-telemetry/TaxCredit.Deployment.Telemetry.dll
TELEMETRY_ENABLED=1
OTEL_SERVICE_NAME=taxcredit-api
TELEMETRY_VERSION=1.2.3
TELEMETRY_ENDPOINT=http://127.0.0.1:4318/
Logging__LogLevel__Default=None
```

Use the corresponding fixed service name `taxcredit-gateway`, `taxcredit-worker`
or `taxcredit-orchestrator`. Version must be a 7–40 lowercase-hex commit or a
numeric `major.minor.patch`, not arbitrary metadata. Endpoint must be an origin
with `/`, no credentials/query/fragment. Plain HTTP is permitted **only on
loopback**; HTTPS uses platform certificate validation. Proxy use, redirects,
auth headers and exporter trace propagation are disabled. This exporter supports
no bearer token, client certificate or Azure-specific connection string.

Startup env must reach the **application**, not SDK/publish processes. Retain the
normal application entry point and SIGTERM handling. For a container, the local
collector must share its network namespace; `127.0.0.1` does not mean a separate
Compose service. Otherwise supply an operator-approved private HTTPS collector.
Do not enable additional auto-agents/exporters alongside this privacy boundary.
An unset enable flag or explicit `0` disables export without a warning. A malformed
flag or invalid enabled configuration disables export without stopping the
application, but emits `TCC_TELEMETRY_INVALID_CONFIGURATION` to stderr once per
process. No setting names or values are included.
Disabling `TELEMETRY_ENABLED` is the rollback; no host edits are necessary.
NativeAOT, trimming and single-file deployment have not been qualified.
Republish/repackage the hook with parent package/image manifests after a hook
change; do not replace bytes behind an old artifact checksum.

`collector.yaml` is a **local receipt fixture**, not a cloud backend: set
`TELEMETRY_RECEIPT_ENDPOINT` to the local test receiver. It exposes no logs pipeline,
uses bounded memory, batches, and disables backend retries/queues. In tests its
port is published on host loopback only. Production requires operator-owned
collector TLS/network/backend configuration and independent collector health.
Only trusted hook traffic may enter this collector: it is not a general-purpose
sanitizer for other producers.

## Privacy and loss semantics

The producer constructs a new envelope rather than deleting known bad tags.
Only fixed service/version, source-plus-kind span name, diagnostic trace/span/
parent IDs, timestamps, numeric error status, and allowlisted metric count/sum
leave the process. **All** activity tags, resource env attributes, span names,
status descriptions, events, links, tracestate, baggage, metric labels and
exemplars are omitted. No URLs, queries, request/response/body/header contents,
person/client/model/provider identifiers, prose, exception details or tokens
are exported. Trace IDs are correlation identifiers, not business identifiers.

Allowlisted meters/instruments are the complete literals in `SafeSignals.cs`.
Measurements are exported as delta, single-bucket histograms under
`tcc.deployment.measurement.*`: `count` is measurement count, `sum` is measured
value total. Thus a counter increment of 5 contributes count 1 / sum 5.
Dimensions and percentile buckets are intentionally unavailable. Nonfinite and
negative measurements are dropped.

The hook writes only the two fixed diagnostic codes described here, never data
logs. The test host clears all log providers. **Product and
platform logs are a separate privacy prerequisite**: `Default=None` alone cannot
override more-specific category settings or direct console writes. Disable
HTTP access/request logging and verify category overrides; never export those
streams through this collector. `QueueWorker` currently logs a failure type;
this hook does not capture it or turn it into a lease/uncertain-write metric.

At most 2,048 completed spans are queued; excess spans are dropped. Metric
cardinality is bounded by the fixed instrument list. Every two seconds and at
normal process exit/SIGTERM, queued data is drained. Each HTTP attempt is bounded
to 750 ms with a 4 KiB response limit; two signal requests can cost about 1.5 s.
An already-running flush can add another bounded flush interval to shutdown.
Allow at least **5 s** termination grace plus the application's own shutdown.
Failures, timeouts, 4xx/5xx and overflow **drop data without retry or persistence**.
Export transport failures, unexpected statuses, malformed responses, and OTLP
partial rejections emit `TCC_TELEMETRY_EXPORT_FAILED` to stderr **once per process**,
even when both trace and metric exports fail repeatedly. No response contents,
status details, endpoint, payload or exception are printed. Fixed diagnostics
are best effort if stderr itself has already been closed.
No exporter health/success assertion is exposed to readiness. SIGKILL/crash can
lose everything pending. This is diagnostic telemetry, never the audit ledger.

## Reproduce / measured evidence

Run from `dotnet` (Python standard library only):

```powershell
dotnet build deploy\telemetry\Telemetry.slnx -c Release
dotnet format deploy\telemetry\Telemetry.slnx --no-restore --verify-no-changes
python deploy\telemetry\verify.py
python deploy\telemetry\verify.py --collector
python deploy\telemetry\verify.py --linux
python deploy\telemetry\verify_published.py
python deploy\telemetry\verify_published.py --collector
```

The probe **compiles the unchanged real ServiceDefaults source** with independent
matching package pins. OpenTelemetry packages are Apache-2.0;
`Microsoft.Extensions.Http.Resilience` is MIT, checked in the exact restored
NuGet manifests. The hook itself is BCL-only.

Three synthetic HTTP hosts model API → gateway → dependency, not real published
application executables. The dependency uses the permitted Worker resource name;
this does **not** make the actual Generic Host Worker an HTTP service. A fourth
short-lived probe tests another allowed service attribution and immediate flush.
Tests assert custom ActivitySource/Meter listeners are absent without the hook
and present with it, reject six disabled/invalid configurations, inject private
canaries into every forbidden field, and inspect receipts in memory only.
Local receiver/collector runs also capture stderr in memory and require exactly
the expected fixed code once, with no other content. Linux probes disable Docker
logging; their evidence does not claim stderr-code inspection.

`evidence/receiver.json`, `collector.json`, and `linux.json` record aggregate
counts/timings, hook SHA-256 and public image digests, never payloads, IDs or endpoint addresses.
The Linux path uses nonroot, read-only .NET 10 containers and real SIGTERM.
The pinned collector accepts and forwards **both signals**; tests verify two
cross-service W3C parent edges. Exact counts vary with batching/shutdown timing.
No live customer, Fabric, Entra, Foundry, or external telemetry service is used.

Last recorded run (SDK 10.0.404; Docker 29.9.3, native **arm64** engine/runtime):

| Path | Received spans | Metric series/batches | Immediate shutdown |
|---|---:|---:|---:|
| Local receiver | 19 | 18 | 0.097 s |
| Official Linux collector → receiver | 19 | 19 | 0.088 s |
| Nonroot Linux probes → collector → receiver | 15 | 20 | 0.383 s |

Every path passed privacy, four service/version attributions, two parent edges
and six disabled/invalid configurations. The immediate Linux probe lived
**1.563 s total**, below the 2 s periodic interval, so receipt proves exit flush.
Direct hook tests against a 503 receiver and a stalled receiver kept application
requests successful; shutdown took 0.112 s and 1.722 s respectively in the
collector evidence run. Partial-rejection and malformed-response fixtures also
passed, including a private canary in the rejected response. These failure
fixtures run as separate direct receiver tests, not through the collector.
Linux connection-refusal shutdown took 0.581 s. Build and format verification
passed with zero warnings/errors.
The portable IL was published by the local pinned SDK, then mounted into native
arm64 runtime containers. This is **not** an amd64 image/source-build proof;
amd64 SDK emulation and container NuGet restore are not exercised by these tests.

### Ordinary published hosts

`verify_published.py` reuses the parent's credential-free synthetic launch
contract with its ordinary `.artifacts/publish/{api,gateway}` DLLs/resources,
overriding only the hook path/configuration. SQLite/absent-CSV work is confined to
this tree and deleted afterward; parent artifacts are not modified.
`evidence/published-{receiver,collector}.json` proves **each real host** received
two server spans and one request-duration metric series, with correct service/
version attribution, health 200, protected route 401, and no export diagnostic.
No actual dependency span/correlation or custom AI activity was observed or is
claimed. The two dependency edges above remain **synthetic three-host proof**.
Actual-host receipt precedes termination; this test does not claim graceful
flush for those real Windows processes. Hook/image hashes identify exact bytes.

For business monitoring, application owners must add identifier-free instruments
at `RunWorkExecutor`/`QueueWorker` lease, retry and ambiguous-commit boundaries,
and at `RuntimeStatus` readiness transitions, then extend the producer allowlist
with tests. There is deliberately no promise of those metrics in this delivery.

[hook]: https://learn.microsoft.com/dotnet/core/tools/dotnet-environment-variables#dotnet_startup_hooks
[otlp]: https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding
