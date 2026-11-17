# W3 orchestrator handoff

## Result and evidence boundary

`TaxCredit.Orchestrator` is now an executable .NET 10 hosted orchestrator,
using the **actual Microsoft Agent Framework and Azure Responses SDKs**.
It calls the existing service-authenticated gateway REST contract; it does not
vendor Python, own payroll access, recompute figures or depend on unfinished
sibling capability types.

**Whole-solution gates passed:** warning-as-error build, format verification,
and **1,509 fast tests** with zero failures/skips. **431** are orchestrator cases;
the existing **1,078** foundation cases remain green. All **39** captured
orchestrator records pass. The complete specification index enumerates all
**313 guarantees across 32 groups**, classified **156 directly exercised,
103 partial, 15 unverified, 39 source/deployment/other-surface boundaries**.
Those are different evidence counts, not interchangeable coverage claims.

This is **local package-backed execution evidence**, not a Foundry deployment
or complete portal/API/gateway/MCP parity certification. No live external
system, customer data or model generation was used.

## Packages, compatibility and licences

| Dependency | Resolved version | Maturity / licence |
|---|---|---|
| Microsoft.Agents.AI | 1.28.0 | Stable, MIT; net10.0 asset |
| Microsoft.Agents.AI.Workflows | 1.28.0 | Stable, MIT; actual checkpoint APIs |
| Azure.AI.AgentServer.Responses | 1.0.0-beta.9 | Preview, MIT; net10.0 |
| Azure.AI.AgentServer.Core | 1.0.0-beta.30 | Transitive preview hosting dependency |
| Microsoft.Extensions.AI.OpenAI | 10.11.0 | Stable, MIT |
| OpenAI | 2.14.0 | Transitive stable SDK, MIT |
| Azure.Core / Azure.Identity | 1.63.0 / 1.17.1 | Shared Azure dependencies |
| DependencyInjection / Abstractions | 10.0.13 | Serviced floor required by the framework |

Installed nuspec licence metadata, resolved restore graph and actual compile
were checked. Only the marked orchestrator section of central package pins
changed. Existing DI declarations are updated, not duplicated. The initial
10.0.0 pins could not satisfy the framework's >=10.0.13 floor.

The official OpenAI token-policy constructor carries `OPENAI001`; one narrowly
scoped pragma acknowledges that experimental API in an otherwise stable SDK.
An assembly alias resolves the overlapping `DefaultAzureCredential` type name
in the resolved Azure graph. SDK retries are off; W1 owns retries.

References:

- <https://www.nuget.org/packages/Microsoft.Agents.AI/1.28.0>
- <https://www.nuget.org/packages/Microsoft.Agents.AI.Workflows/1.28.0>
- <https://www.nuget.org/packages/Azure.AI.AgentServer.Responses/1.0.0-beta.9>
- <https://www.nuget.org/packages/Microsoft.Extensions.AI.OpenAI/10.11.0>
- <https://learn.microsoft.com/azure/foundry/how-to/develop/framework-hosted-agents>
- Installed Responses README/XML API documentation supplied the beta.9
  `CreateResponse`, `ResponseContext` and `TextResponse` signatures.

## Architecture and runtime

`Program` reads environment configuration, composes adapters and runs the
SDK-created app. `ResponsesHosting` is the only Responses transport seam.
It registers one text handler; the SDK owns framing, routes, readiness,
client cancellation and shutdown. Port **8088** is the default unless URL
configuration supplies another. There is no Bot Activity/card implementation
and no stream of unverified narrator text.

The project references **Application** and **ServiceDefaults**. Existing W1 AI
adapters remain reachable through those references. SDK-specific code lives
under `Framework`, `Workflow` and `Hosting`; selection/settlement and composition
remain host-independent. Architecture tests check SDK import placement,
inward reference isolation, state-free definitions, net10.0 and the 250-line
module ceiling.

Exactly **25** tools come from the canonical Application model projection,
including its words and schemas. Commit, resolver and internal plumbing are
not model tools. Singleton bodies require invocation context; they do not
capture a person or conversation. All three planners enter the actual framework
function middleware and the same settling runner.

Runner order is attempt budget, whitelist, reader client resolution, reader
year/scenario settlement, clarification, canonical schema validation,
deduplication and forwarding. Both-method expansion has distinct labels and
consumes attempts. Unknown/refused/duplicate attempts cannot evade the budget.
Resolver use is once per turn, including failures.

The production model bridge preserves W1 per-role chains, egress guards,
budgets, retries, breaker, bulkhead and timeouts. The orchestrator uses the
**Narrator role**, as the Python channel does. A text-only provider is skipped
for tool requests but remains eligible for JSON/text requests. A missing
configured provider is not replaced with an ambient default.

## Person and gateway contract

Identity resolution preserves configured source precedence and normalized
person/tenant identifiers. Opaque platform user IDs are context, not identity.
Anonymous/invalid-person requests never reach a gateway or model.
Conversation precedence is explicit SDK conversation, response-chain and
source fallback; verified person plus tenant plus conversation partitions
selection and workflow state. Whole-turn leases serialize confirmation and
ordinary requests, including active/waiting TTL boundaries.

The gateway client sends:

- `POST /channel/v1/tools/{name}` with the existing `args` wrapper.
- `POST /channel/v1/audit/narration` for model participation/guard metadata.
- A service bearer token for `CHANNEL_GATEWAY_AUDIENCE/.default`.
- Verified `X-Acting-*` reader assertions, conversation/correlation and,
  where applicable, the original idempotency identity.

It does **not** forward inbound authorization or send API
`X-TCC-Acting-User`. Responses retain both authorized reader lanes and
model-safe facts; projection occurs deliberately later. Deadlines,
cancellation, bounded responses and sanitized dependency failures are tested.
The client does not retry gateway mutations.

**Ingress authentication is still a W4 prerequisite.** The installed .NET SDK
does not expose Python's original-subject context object. This seam maps
platform-injected original-subject headers and SDK context into the neutral
resolver. W4 must authenticate the hosting boundary and strip/replace
spoofable inbound assertion headers. Local tests prove resolution/propagation,
not the authenticity of arbitrary Internet headers or employer binding.

`/whoami`, `/netcheck` and `/modelprobe` are gated text commands, default off.
Enabling debug warns. Diagnostics use injectable bounded collaborators;
production binds a BCL network probe and an explicitly configured Foundry
client, but no live diagnostic call was executed here. Model output from a
probe is discarded; only metadata is reported.

## Guarded replies and confirmation

The common model brief contains fact names/placeholders, not trusted numeric
values. Person-only rows, record identifiers and confirmation tokens are
excluded from model projections. Unknown audiences fail closed. Every visible
request is inspected in lane tests, including actual official SDK tool-result
requests.

Composition validates deterministic blocks, validates and masks placeholders
before raw-numeral checking, substitutes trusted formatting, then independently
checks the finished **body**. Copied/invented numerals, invalid paths/formats,
Unicode numeric evasions and misleading approximation are rejected. Failed
narration is dropped as a whole; independently valid blocks survive. Lookup
blocks are omitted beside an answering tool, but a genuine catalogue answer
remains.

Trusted provenance is appended after body verification. Optional quoted
reference text has a separate labelled footer and never becomes numeric
authority. Neither identifier footer nor quoted references are falsely
included in the claim that the numeric **body** independently passed.
Knowledge defaults off. `fake` is a labelled synthetic corpus; enabled
`foundry-iq` fails startup explicitly, as it is not implemented.

The write path is an actual framework graph:
**prepare -> request/pause -> fresh-graph resume -> commit**. Its framework
checkpoint, not a second parent pending-command dictionary, holds canonical
arguments, owner, preview, expiry, confirmation and idempotency metadata.
Returned envelopes are sanitized. The confirmation secret never reaches the
reader, a model request or narration audit.

Source confirmation grammar is preserved: `confirm`, `yes, apply` or
`yes apply`, case/whitespace insensitive with trailing `.`/`!` accepted.
Bare `yes` is not confirmation. Wrong person, exact expiry, cancel, unrelated
request, replay/refusal and concurrent confirmation are exercised. One
successful preview/confirm produces one mutation. Gateway records attribute
both steps to the acting person.

An uncertain commit is never retried or made confirmable again. The recovery
API retains/reuses the original idempotency identity. Unrelated reads remain
usable while another prepare stays blocked. For a known successful package
commit, the resumed executor fetches `claim_package_link` using checkpointed
client/year. Link failure or cancellation preserves known mutation success
and reports link unavailability, never a fictional rollback.

Checkpoint storage is **in memory**. No crash/restart durability or
cross-replica exactly-once claim is made. Workflow tests exercise fresh graph
construction inside that process, not process restart.

## Validation and traceability

Commands ran from `dotnet`, selecting SDK **10.0.404**:

```powershell
dotnet build -warnaserror --nologo -v quiet
dotnet format --verify-no-changes --no-restore --verbosity quiet
dotnet test --no-build --filter 'Category!=heavy' --nologo -v quiet
```

| Suite | Passing cases |
|---|---:|
| API | 332 |
| Architecture | 16 |
| Domain | 18 |
| AI infrastructure | 167 |
| Auth infrastructure | 147 |
| Sources infrastructure | 108 |
| Persistence infrastructure | 129 |
| Parity | 61 |
| Orchestrator | 431 |
| **Total** | **1,509** |

All **39** records are checked by ID: keyword.00-.24, conversation.00-.05,
identity.nobody, six host answers and host.conversation-key. Plain text is
exact; debug JSON is semantic. Keyword rigs are fresh. Each conversation
case replays its shared prefix and compares the cumulative last-two-call
tail, not a per-turn delta.

The captured Resolve/yes/yes sequence is an eligibility-read sequence, not
confirmation evidence. `keyword.10` is a clarification, not a successful
simulation. The independent scripted/checkpoint tests supply real write proof.
No recording, pinned figure, Python test or comparison threshold changed.

Actual package-backed proofs include inbound Responses HTTP framing, input
extraction, explicit conversation precedence, guarded final text, readiness,
cancellation and disposal; outbound official OpenAI bearer/deployment/tools
and sampling shapes; a complete official SDK framework loop; and the full
Responses -> identity -> W1 -> framework -> REST gateway -> guard/audit path.
Models, credentials and gateway transports in these proofs are synthetic.

The full source-name index is
`orchestrator-spec-traceability.md`; composition and workflow details are
`orchestrator-composition-traceability.md` and
`orchestrator-workflow-traceability.md`. All source-name pairs and named test
references were checked. The **E/P/U/X labels are intentional**: passing
theory counts do not prove all 313 source guarantees.

## Runtime configuration and remaining work

Required: `TENANT_ID`, `CHANNEL_GATEWAY_URL`, `CHANNEL_GATEWAY_AUDIENCE`,
plus every selected provider's endpoint/model/auth configuration.
Foundry uses `FOUNDRY_PROJECT_ENDPOINT`; model selection is
`AI_MODEL_<ROLE>__<PROVIDER>`, then `AI_MODEL_<ROLE>`, then `FOUNDRY_MODEL`
or the platform's `AZURE_AI_MODEL_DEPLOYMENT_NAME` fallback.

Other supported groups are `CHANNEL_NAME`, `CHANNEL_IDENTITY_SOURCES`,
`CHANNEL_DEBUG_WHOAMI`, `CHANNEL_MAX_TOOL_CALLS`,
`CHANNEL_CONFIRM_TTL_SECONDS`, `CHANNEL_STATE_TTL_SECONDS`,
`CHANNEL_REQUEST_TIMEOUT_SECONDS`, `CHANNEL_TURN_TIMEOUT_SECONDS`,
`FOUNDRY_AGENT_NAME/VERSION`, `AI_PROVIDER_CHAIN[__<ROLE>]`,
`AI_EGRESS_POLICY`, daily/per-principal token budgets, W1 retry/breaker/
bulkhead/deadline settings, `AI_OUTPUT_ALLOWED_HOSTS`, and the three
`KNOWLEDGE_*` settings. Gateway-provider configuration uses existing
`AI_GATEWAY_*` dialect, explicit auth, token, timeout and header settings.
No actual endpoint, tenant, credential or customer value is embedded.

The complete source environment-reference inventory is not independently
certified. The improvements register records intentionally stricter startup
controls and unknown-write recovery behavior; none waives a changed figure or
one of the 39 comparisons.

Remaining limits for the next wave:

1. **W4 deployment/authentication:** publish the .NET entry point, establish
   trusted ingress/employer binding, then prove real platform original-subject
   and conversation delivery. Existing Python manifests and W2 fake-client
   registrations are not .NET deployment evidence.
2. **Gateway integration/parity:** the REST client is implemented, but real
   capability completeness and the full portal/API/gateway/MCP figure matrix
   require the parallel gateway/integration work. The complete source
   model-scripted golden/data-question corpora are not ported as matrices.
3. **Unknown-write operation:** `WriteWorkflow.RecoverAsync` supports a
   read-only lookup using the original key, but the existing gateway contract
   exposes no agreed result-recovery endpoint. Production root does not invent
   one. Recovery-only slots remain blocked for new writes until reconciled;
   slot capacity/retirement and process/replica durability need an operational
   decision. In-memory UTC token budgets are likewise not fleet-wide quotas.
4. **Coverage limits:** selected names-only diagnostic/instruction/documentation
   assertions remain unverified. Live knowledge retrieval, real network probes
   and live model/provider fallback remain unexecuted. `aggregates_only`
   remains conservatively subject to existing W1 admission rules.
5. **Inherited calculation limits:** M-01 ingestion precedence, first-program
   multi-program pricing and count/max source fingerprints are unchanged.
   Orchestration cannot reinterpret those figures or turn a fingerprint into
   a snapshot. Owner decisions remain necessary.

No infrastructure, remote, Python implementation, payroll fixture or shared
capability binding was changed. Work is committed locally only.
