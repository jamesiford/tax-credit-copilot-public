## Your role

Implement `TaxCredit.Gateway`: REST tools, an official C# SDK-backed MCP server, person-bound downloads, narration audit and ADR-008 numeric integrity. Deliver real application results, not just a catalogue or a forwarding host whose upstream capabilities remain unavailable.

The W3 allocation includes `dotnet\src\TaxCredit.Gateway`, its tests, `TaxCredit.Api`, `TaxCredit.Application`, API tests and the central package file. Use the expanded application/API scope specifically to complete production capability bridges and reusable host composition. Orchestrator runs in parallel against the existing REST contract; it must not need a new shared type from your branch. Put new pins only in the marked gateway package section, reusing existing declarations. Infrastructure and Domain implementations remain dependencies, not alternative engines to rewrite.

## Preflight

Read `dotnet\docs\ROUTES-CONVERGENCE-REPORT.md` first: 978 passing fast tests, 141 distinct passing heavy cases, and a latest wave board of framework 17/17, reads 406/414, claims 291/316, drafts 312/323, AI 26/27, but gateway only 2/255. Distinguish the report's registered-only projection from subsequent conductor execution. Older isolated HALTs are historical where convergence explicitly repaired them.

Read `dotnet\docs\ROUTES-AI-REPORT.md`, `HOST-ARCHITECTURE.md`, `COMPOSITION-REPORT.md`, `PERSISTENCE-REPORT.md` and `SOURCES-AUTH-AI-REPORT.md`, then the actual feature registrations. `CapabilityCatalog` has 37 declarations and 36 public entries; its implemented metadata is not evidence that every production bridge exists. `CanonicalCapabilityReads` currently handles only `book_rank` and `client_eligibility`. `CapabilityDependencies.cs` names the remaining inward contracts and the default missing write bridge.

Use `contract\inventory\channel.json`, the three `contract\scenarios\g1_*.json` files and recordings: nine operations, 255 steps (REST 142, MCP 103, rate limit 10). Follow `backend\channel`, `contract\CONTRACT-REPORT.md` sections 4-5, `contract\FINDINGS.md` and `docs\architecture\ADR-008-channel-numeric-integrity.md`. Historical raw-JSON recommendations do not override current semantic comparisons; schema/description strings and money-string scale still matter.

Start development commands from the worktree's `dotnet` directory, which selects SDK 10.0.404 rather than the root's SDK 11. Establish the inherited baseline. The oracle is `C:\Projects\py312-oracle\.venv\Scripts\python.exe`, importing this session's checkout. Existing Domain numerics, fiscal resolution and calculation payloads are the foundation, not a second porting task.

## Stage G1: prove SDK compatibility and the ordinary standalone host

Verify official C# MCP package versions, protocols, licensing and net10.0 compatibility with an actual initialize/list/call test. Hand-written JSON-RPC alone is not SDK integration. Test Python SDK limitations as hypotheses, not presumed C# defects; document required channel adapters without forking the SDK.

Add missing package pins in your marked section. W1 selected compatible Azure packages after newer graphs produced NU1605 against Microsoft.Extensions.DependencyInjection 10.0.0; inspect the resolved graph instead of casually changing other sections. JsonSchema.Net 8.0.5 was MIT; do not assume a newer major has the same licence. Record the packages actually used, not proposed API names or versions.

Support the conductor's `dotnet run --no-build --project dotnet\src\TaxCredit.Gateway --no-launch-profile` launch with its supplied `--urls` value. The ready probe is `/api/health`, alongside `/channel/health` and `/channel/ready`. Compose application services in-process, without a manually started API, loopback dependency or test-only host.

Reuse/refactor owned `TaxCredit.Api\Hosting\HostComposition.cs`, feature discovery, controls and wire infrastructure. Preserve Application/Infrastructure/runtime registration before feature services/provider construction, and readiness, startup signing-key creation, request gating and principal middleware order. Keep request/scoped lifetimes and avoid duplicate endpoints.

Expose `/__contract__/reset`, `/__contract__/drain`, `/__contract__/env` and `/__contract__/mint` only with effective startup `TCC_CONTRACT_HOOKS=1`, using API contracts. `TaxCredit.Api.csproj`'s `ConfigureContractReplayLaunch` bridges the conductor's valid `TCC_CONTRACT_DIR` marker to the hook argument, respecting explicit opt-out. Project references do not transfer executable launch targets: provide the equivalent scoped gateway bridge while keeping ordinary/deployed hooks off.

Checkable result: the real no-profile executable answers health, performs initialize/list with the installed SDK, and can reset G1, mint a synthetic token and invoke a seeded capability without another process. A separate hooks-off launch exposes no controls; explicit opt-out remains authoritative. Reset also clears gateway sessions, ledger, rate limits and ephemeral download state through the existing reset boundary.

## Stage G2: finish the capability production bindings

This is assigned implementation, not a dependency to defer to W2. Build the missing `ICapabilityReadBridge` and `ICapabilityWriteBridge` production bindings over existing application features, register them in ordinary composition and preserve direct `/api/capabilities` behavior. Use `CapabilityRead` to carry facts, provenance, blocks, warnings and person-only paths together. Inspect `CapabilityDirectReads`, canonical page collaborators and feature queries before adding a new projection.

Complete the reads named in `CapabilityDependencies.cs`: at-risk counted-cohort fragility, discovery excluding the selected state's programmes, resolved-fiscal simulation, stored calculation walkthrough/trail, authorized employee drill, findings, program catalogue, visible batch list/status, package links and internal redemption. Keep existing book-rank/eligibility behavior. Reuse the already-local resolver, situation/history, trend and governed data operations rather than duplicating their calculations. Preserve the difference between unavailable data, no calculated run and a genuine zero.

Wire these eight prepare/commit pairs to their owning commands:

| Base name | Existing application contract |
|---|---|
| `finding_resolve`, `finding_reopen` | `ResolveFindingCommand`, `ReopenFindingCommand` and pure previews |
| `claim_transition`, `claim_record` | `TransitionClaimCommand`, `RecordClaimCommand` |
| `engagement_set` | `SetEngagementCommand` |
| `base_year_set` | `SetBaseYearCommand` and recalculation preview |
| `claim_package_create` | `CreateClaimPackageCommand`, artifact publication |
| `run_batch` | `CreateRunBatchCommand`, resolved scope preview |

A preview validates and returns before/after without business mutation. Use the capability feature's existing person/tool/argument-bound expiring confirmation, atomic consume, idempotency recovery and durable audit rather than minting an independent gateway confirmation system. Successful write audit belongs to that capability path. Preserve the warning that a timed-out accepted commit may still land; it cannot be automatically re-executed.

Implement `claim_package_link` and internal `claim_package_redeem` over actual stored package/artifact data. The internal operation is not advertised. Tickets are person-bound, expiring and single-use; expected-user validation precedes atomic spend. Resolve the bytes as the ticket owner through existing artifact authorization, never from a caller-selected storage URL. Test redemption concurrently and across a new application scope.

Keep governed queries on the existing allowlisted typed query port, never arbitrary SQL. Preserve explicit refusals for unsupported hidden-person/distinct suppression: W1 did not prove an atomic suppression count or safe cross-year person identity. No aggregate, missing bridge or permission error becomes a fabricated successful empty result.

Checkable result: every catalogue tool has a production dispatch path on the ordinary host, with a successful hermetic representative where supported and explicit named dependency refusals where genuinely outside the available infrastructure. All eight real prepare/commit workflows have state/audit assertions, no mutation during preview, wrong-person/arguments refusal and exactly one mutation on retry. Extend API tests for those bindings and retain existing API replay behavior. Catalogue equality alone is not completion.

## Stage G3: one trust, execution and error pipeline

Read `backend\channel\auth.py`, `pipeline.py` and the API trust adapters. Distinguish app-only `Channel.Invoke` from delegated `Channel.Access`; mixed tokens and agents lacking the required role are refused. Gateway agent assertions use `X-Acting-*`, not the API's `X-TCC-Acting-User`. Validate tenant/person/channel/conversation/correlation syntax at the intended boundary, and propagate the verified acting person into application scopes without turning arbitrary headers into identity.

Put REST and MCP execution through one pipeline: identity, request bounds, person-scoped rate limit, tool/schema/default validation, required audit, authorized application dispatch, trusted-result/ledger recording and channel error translation. Preserve origin validation before identity for MCP. Read audit begin must succeed before the capability executes; pre-capability write failures need audit without duplicating successful capability audit.

Channel failures use `error.code/message/retryable` plus correlation, not API `detail`, ProblemDetails or an SDK's incidental envelope. Translate upstream capability failures consistently. Cancellation/disconnect, malformed upstream output, unavailable audit, timeout and argument failures must be distinguished without exposing exceptions, assertions or credentials.

Exercise `g1_rest` cases `auth.agent_no_role`, `auth.agent_with_scope`, `auth.mixed`, `auth.other_tenant_user`, `acting.no-tenant`, `acting.bad-oid`, `acting.no-conversation`, `acting.cowork-channel-asserted-by-agent`, `tool.body-too-large` and `tool.idempotency-key-too-long`. Complete the rest of the recorded auth/acting-user matrix, not only these samples. For G1L test `ratelimit.1` through `.8`, `.other-person` and `.health-unaffected`: a different person has a distinct budget, health is unaffected, and reset/configuration changes do not preserve stale limit state.

Checkable result: the same tool call through REST and MCP has equal authorized facts and equivalent refusal/audit behavior; concurrent people cannot share identity, confirmation or budget accidentally.

## Stage G4: REST catalogue and MCP session transport

Serve GET `/channel/health`, GET `/channel/ready`, GET `/channel/v1/tools`, POST `/channel/v1/tools/{tool}`, POST `/channel/v1/audit/narration`, GET `/channel/v1/downloads/{ticket}`, and POST/GET/DELETE `/mcp` with their intended methods. Do not expose API documentation accidentally as channel endpoints.

Use `contract\inventory\channel.json` as a comparison fixture, not runtime result data. Verify all 36 schemas and complete description strings, including defaults, enums, required fields and nullability; debug mode adds only the documented extra tool. SDK inference must not shorten descriptions, alter schema titles/types, add wrappers or expose internal redemption. REST and MCP list from the same authoritative catalogue. Test every recorded typical and invalid call, not only the two currently wired canonical reads.

Reproduce the MCP channel semantics with the official SDK and thin transport/session adapters where necessary. Test initialize negotiation for 2025-11-25, 2025-06-18 and 2025-03-26 against the source, initialization notifications, ping, tools/list/call, unsupported versions and unknown methods. Notifications/client responses do not turn into tool execution; accepted notifications use 202 as specified. Validate JSON-RPC IDs, malformed JSON, batch arrays, empty bodies and arguments without an accidental 500.

Session state is bounded and expiring and bound to the verified person. Cover `tools-list-no-session` (400), `tools-list-unknown-session` (404), `other-user-session`, `delete-other-user`, `delete`, `after-delete`, `delete-again` and `agent-initialize`. Wrong-person access cannot delete or consume the owner's session. Cover `tools-list-bad-origin`, `tools-list-bad-protocol-version`, `initialize-old-version`, `bool-id`, `null-id`, `client-response-ignored`, `get-405` and `get-no-token` with the recorded auth/order distinctions. Use real HTTP tests for header/session behavior rather than only direct method calls.

Checkable result: all recorded catalogue entries and tool cases traverse the actual REST/MCP host, with session lifecycle/isolation and transport error cases asserted. SDK conformance and channel behavior are separately evidenced; successful SDK startup is not proof of schema fidelity.

## Stage G5: trusted-result ledger, narration and downloads

Reuse Application's `NumericGuard`, `FactIndex` and formatting primitives. `NumericGuard.CheckRaw` does not recognize placeholders: the composer must validate and mask allowed placeholders before raw checking, substitute only trusted fact paths and check the final rendered text separately. The weaker page `SummaryNumericGuard` and numerically unchecked portal chat are not ADR-008 channel guards.

Record only successful trusted tool facts in the gateway ledger under the verified person/conversation with the source lifetime and bounds. `verify_figures` is gateway-local, not an API capability call. It must not accept another person's or conversation's facts, narrator-provided replacements or stale state after reset. Cover `guard.read-facts`, `guard.verify-matching`, `guard.verify-mismatching`, `guard.verify-other-conversation` and `guard.verify-no-draft`; retain distinctions between unsupported numbers, dates/year context, percentages, abbreviations, unicode evasion and missing evidence.

Validate narration audit input and allowed verdicts with `narration.no-token`, `.delegated`, `.agent-empty` and `.agent-bad`; preserve the source auth/error order and audit ownership. Log safe codes and identifiers already authorized for audit, not rejected prose or person-level data.

For downloads retain F-19's designed 502 `invalid_arguments` on an unknown ticket and F-20's 410 `confirmation_replayed` on reuse. A malformed supplied bearer token is not ignored, and an optional bearer for the wrong person is checked before spending the ticket. Redeem internally, then fetch bytes as the ticket owner. Never reveal Blob/SAS URLs. Check filename, no-store, content type, returned-body hash and archive members with the existing normalization rules; a container hash exception does not exempt trail hashes, member contents or arbitrary neighbouring figures.

Exercise `download.unknown-ticket`, `.unknown-ticket-with-token`, `.bad-token`, `.other-user`, `.owner` and `.owner-again-single-use` after the real package prepare/commit/link sequence. Include simultaneous redemption, missing bytes and failed owner authorization so single-use semantics are not just a sequential happy-path test.

Checkable result: ledger isolation and full numeric guard tests fail on a changed fact or leaked conversation; a real package created by the application downloads once for its owner with correct headers and byte integrity.

## Stage G6: ordinary-host replay and integration evidence

Run the public contract replay against the actual no-profile gateway executable with its reset URL. `contract\replay_setup.py` now selects scenario profile/auth/env before minting: reuse that path rather than inventing product inference from account IDs or token shapes. Prove G1/G1L reset, env refresh and repeated reset after writes/downloads on the same host. W2 repaired scoped mediator/artifact leases; a new root-captured scoped collaborator can reintroduce the old reset bug.

Compare all `g1_` scenarios: current prefix grouping counts 255, not historical 251. Keep raw and policy-adjusted results. Run API scenarios against the API host after bridge/composition changes; the gateway-only fast filter misses API tests. Use existing build/format/test commands and production-path regressions.

Investigate genuine number/string/status/presence differences at the responsible adapter. W2 still records money-string scale, later real UUID allocation, valid long-text storage, provenance and stored-program differences. Seed loading consumes no runtime UUIDs; startup signing-key allocation does. Trace genuine consumers rather than drawing extra IDs to align a recording. The durable run-preview allowance is narrow and is not permission to change tool facts.

Write `dotnet\docs\GATEWAY-REPORT.md`: SDK/version/licence evidence, tool-to-handler map, pipeline/composition, scenario/API regression counts, infrastructure limits and the REST integration contract. Separate mock, ordinary hermetic host and unverified live proof.

Checkable result: unattended conductor-style launch works end-to-end; remaining differences have exact case/field attribution.

## Traps to expect

- Preserve facts, monetary string scale, null versus absent, mixed date forms and error-family boundaries. Historical strict-byte recommendations in the capture report do not require reimplementing framework artifacts.
- `AsyncLocal` identity set only inside awaited access validation does not necessarily flow back into endpoint code; reuse explicit principal push/restore middleware and request scopes.
- Python half-even rounding, compensated 3.12 sums, Decimal exponent behavior, Unicode 15.0 comparisons and evidence hashing already have certified helpers in `dotnet\docs\findings.md`; ordinary C# decimal/double formatting is not a replacement.
- M-01 ingestion overrides and first-program credit math are inherited figure-sensitive behaviors. CQ-02/CQ-05, CAP-10 and partial strict leap-day fiscal handling remain documented boundaries, not gateway cleanup opportunities.
- Row-count/max-modified fingerprints are not Delta snapshots or detection of count/max-preserving edits. Native monetary AVG, zero-worksite SQL/projector differences and live byte-publication behavior remain unverified. PLATFORM-RISKS establishes token Warehouse connectivity/cleanup, not those broader guarantees.
- Catalogue flags and fake successes do not prove production tool execution.

## Evidence this plan is based on

- `dotnet\docs\ROUTES-CONVERGENCE-REPORT.md`: repaired composition/setup, merged baseline, remaining IDs/scale/storage differences and gateway 2/255.
- `dotnet\docs\ROUTES-AI-REPORT.md`: exact catalogue, existing guards and explicit missing production read/write contracts.
- `dotnet\docs\HOST-ARCHITECTURE.md` and `COMPOSITION-REPORT.md`: startup hook bridge, principal/scoped service order, real reset and deterministic identity boundaries.
- `dotnet\docs\PERSISTENCE-REPORT.md` and `SOURCES-AUTH-AI-REPORT.md`: durable confirmations/audit, exact money, artifacts/auth, compatible dependency graph and native limitations.
- `dotnet\docs\DOMAIN-SLICE-REPORT.md`, `port-map.md`, `findings.md` and `PLATFORM-RISKS.md`: certified inward calculation path and explicitly partial/provider-only proof.
- `contract\CONTRACT-REPORT.md`, `FINDINGS.md`, `README.md`, `docs\normalisation.md` and `inventory\channel.json`: nine operations, schemas, wire families, F-19/F-20 and portable archive comparison.
- `contract\scenarios\g1_rest.json`, `g1_mcp.json`, `g1_ratelimit.json` and their recordings: the 255 concrete transport, identity, write, ledger and download cases used above.
