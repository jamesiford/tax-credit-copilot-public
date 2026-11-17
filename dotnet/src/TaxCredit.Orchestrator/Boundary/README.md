# Person and gateway boundary

This package contains no Responses SDK types, models, planner state or HTTP
endpoints. A hosting adapter supplies `IdentityContext`; each tool invocation
supplies its own resolved `ActingIdentity`. Infrastructure may be shared between
people, but conversation resources must use `ActingIdentity.Key`.

## Host integration

```csharp
var resolution = IdentityResolver.Resolve(context, identityOptions);
var diagnostic = await debug.TryHandleAsync(text, context, runtime, cancellationToken);
if (diagnostic is not null) return diagnostic;
if (!resolution.IsResolved) return resolution.Refusal!.Message;
var person = resolution.Identity!;
```

Only continue to planning, tools or narration after successful resolution.
The host must authenticate the platform before mapping its original-subject
assertion or trusted identity headers; this resolver does not authenticate an
arbitrary HTTP caller. SDK adapters must not treat a client-supplied header as
an authenticated platform assertion.

`IdentityContext` takes optional `ClientHeaders`, `OriginalSubject`,
`AgentUserId`, `ConversationId`, `ConversationChainId` and `ResponseId`.
`PlatformOriginalSubject` takes optional `Oid`, `Tid` and `IdType`.

Source order is configurable. The current Python defaults are
`original-subject,platform,agent-user-id`; `client-headers` is opt-in. The first
present source wins, but an invalid assertion refuses rather than falling back.
An opaque agent user key is context only and does not block the next source.
GUIDs and header names are normalized; the platform subject overrides conflicting
flattened headers. The conversation is explicit conversation, then response
chain, never the response identifier or a client conversation header.

`IdentityOptions.FromEnvironment` reads `TENANT_ID`, `CHANNEL_NAME`,
`CHANNEL_IDENTITY_SOURCES`, `CHANNEL_DEBUG_WHOAMI`, `FOUNDRY_AGENT_NAME` and
`FOUNDRY_AGENT_VERSION`, independently of model/planner settings.

## REST integration

```csharp
using var http = GatewayClient.CreateHttpClient();
var gateway = new GatewayClient(http,
    new AzureCredentialTokenProvider(credential, gatewaySettings.Scope),
    gatewaySettings);
var reply = await gateway.CallToolAsync(person, tool, arguments,
    idempotencyKey, confirmationToken, cancellationToken);
var capability = reply.ToCapabilityResult(tool);
```

The composition root owns the injected `HttpClient` and `TokenCredential`.
`CreateHttpClient` disables redirects and cookies and sets a ten-second connection
budget. When injecting a different client, disable redirects and automatic
mutation retries there too. No token, identity or conversation is stored in
default request headers. Service tokens are acquired per request, not forwarded
from inbound bearer credentials.

`IGatewayClient` exposes `CallToolAsync` and `ReportNarrationAsync`. The latter
posts the provided report to `channel/v1/audit/narration` with the same acting
headers. Calls carry `X-Acting-User-Oid`, `X-Acting-User-Name`, `X-Acting-Tenant`,
`X-Channel`, `X-Conversation-Id` and `X-Correlation-Id`, **not** the backend API's
`X-TCC-Acting-User`. Workflow metadata remains in the JSON request body.

`GatewaySettings.FromEnvironment` reads `CHANNEL_GATEWAY_URL`,
`CHANNEL_GATEWAY_AUDIENCE` and `CHANNEL_REQUEST_TIMEOUT_SECONDS`. Default request
budget is forty seconds, including token acquisition and response consumption;
default response limit is four MiB and is constructor-configurable.

`GatewayReply(Status, Body)` retains the entire JSON object, including private
rows, person-only blocks, confirmation metadata and unknown extension fields.
Capability conversion clones the canonical facts/blocks/provenance/warnings and
person-only fact keys, returning null for errors or malformed lane metadata.
It is **not** a model projection. Never send the full reply body to a model.

Timeouts and dependency faults return status zero with stable sanitized error
codes. Non-JSON and oversized responses fail explicitly with their HTTP status.
Caller cancellation propagates. There are no retries; after a dispatched commit
fails, its outcome is unknown, not permission to commit again.

## Debug posture

`DebugCommandHandler.TryHandleAsync` returns null for ordinary text and for all
commands while debug is off. When enabled it recognizes case-insensitive
`/whoami`, `/netcheck` and `/modelprobe`. Supply the application's logger to the
constructor so startup emits the cleanup warning. There are no diagnostic HTTP
routes.

The identity presenter allowlists signal names and identity values and hides
opaque partition keys, credentials and unrelated private headers.
`IDebugDiagnostics` is an injection seam for sanitized network/model reports;
without one, connectivity commands report `diagnostics_not_configured`.

The concrete provider is:

```csharp
new SafeDebugDiagnostics(
    new DiagnosticOptions(environment, projectEndpoint, gatewayUrl, providers,
        stepTimeout: TimeSpan.FromSeconds(10), totalTimeout: TimeSpan.FromSeconds(90)),
    networkProbe,
    modelProbe,  // optional ModelDiagnosticCall
    timeProvider);
```

`DiagnosticOptions` accepts `IReadOnlyDictionary<string,string?>`; only safe
environment metadata is retained. `IDiagnosticNetworkProbe` separates
`ResolveAsync`, `ConnectAsync`, `TlsGetStatusAsync` and `HttpGetStatusAsync`.
`SystemDiagnosticNetworkProbe(HttpMessageHandler? handler = null)` is an explicit,
disposable real adapter: DNS, TCP/TLS on port 443, and credential-free HTTP GETs.
It disables redirects/cookies and reads no HTTP response body. Tests inject
synthetic probes/handlers instead; no live network check was executed.

`ModelDiagnosticCall(Uri endpoint, string model, CancellationToken)` returns
`Task<ModelProbeObservation>`; the observation contains only `Uri? BaseUri` and
`int ReplyCharacters`. The SDK/model adapter remains composition's responsibility.
The provider never obtains a credential, generates a prompt or returns model
reply text itself. Without this delegate it reports `model_probe_not_configured`.

Network checks derive the Foundry project/account hosts, gateway health target,
login host and public control host. Reports distinguish resolution, TCP, TLS and
HTTP-client observations. Address lists are deduplicated and bounded at sixteen;
IPv4 is preferred for the connection check. Address classification includes the
CPython oracle's reserved ranges, public exceptions and IPv4-mapped addresses.
Each operation and the full command are bounded even if an asynchronous probe
ignores cancellation. Caller cancellation still propagates.

Unlike the Python diagnostic's raw exception-message output, failures contain
only exception and inner-cause type names. URI credentials, queries and fragments
are removed from model metadata. The independent client status is named
`http_client_status`, not the Python-library-specific `httpx_status`; the model
path is honestly labelled `injected_model_probe`, not a claim that this provider
itself invoked the Python SDK.

## Specification coverage

`dotnet test tests\TaxCredit.Orchestrator.Tests\TaxCredit.Orchestrator.Tests.csproj
--filter FullyQualifiedName~Boundary` runs 116 synthetic cases.

| Python evidence | Boundary evidence |
|---|---|
| `test_orch_identity.py` | `IdentityTests`: source precedence, normalization, opt-in, refusal, tenant, header and person/conversation isolation; `DebugCommandTests`: signal shape/privacy |
| `test_orch_host.py` | `IdentityTests`: neutral context flattening, conversation fallback and correlation; `DebugCommandTests`: case-normalized gated identity reports |
| `test_orch_debug_posture.py` | `DebugCommandTests`: off by default, inert commands and enabled startup warning |
| `test_orch_netcheck.py` | `NetcheckTests`, `ModelDiagnosticTests`, `DebugCommandTests`: address classification; resolve/TCP stop boundaries; independent TLS/client outcomes; target derivation; environment privacy; metadata-only model success/failure/missing config; debug gating; cancellation and hard budgets |
| `gateway_client.py` and identity gateway assertions | `GatewayTests`, `GatewayReplyTests`: service auth, full lane-preserving envelope, exact assertions, audit, errors, bounds, cancellation and no retries |

Pipeline-level guarantees (anonymous turns call neither model nor tools,
recorded final answers, framework checkpoint isolation and per-person mutable
selection) require host/turn integration tests; resolving an identity alone does
not prove them. No live system was contacted to validate this package.
