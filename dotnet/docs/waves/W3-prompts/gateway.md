# Channel gateway: 36 MCP tools, REST, downloads, narration, numeric guard

Session `gateway` of wave `W3`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-w3-gateway` (branch `dotnet/w3-gateway`, created from `dotnet/integration`).

---

## Pre-approved decisions (policy)

The owner decided these in advance. Follow them without asking. If something needs a decision that is not covered here, choose the reading closest to the documented design and the Python behaviour, record it in STATUS.json under `needs_human`, and continue.

- **parity**: Equivalent behaviour, not bug-for-bug. The target is the designed functionality and the contract a client depends on: the same routes and methods, authentication and authorisation, request and response fields and their types, the meaning of each status code, money as a decimal string with its scale, and the same calculated figures for the same valid input. Do not reproduce defects, accidents of Python, FastAPI or Pydantic, or artefacts of the recording harness (plain-text error bodies, key order, number lexemes such as 5.0 versus 5, byte-level headers and wording, HEAD and trailing-slash quirks, reflected CORS headers). Never write code whose only purpose is to reproduce a defect or a framework artefact. Where the Python behaviour is a bug or an accident, implement what the design, the ADRs, the docs or sound engineering intend, and record it in dotnet/docs/improvements/<session>.json (see improvements_register). If the same issue turns up naturally in the .NET code, that is acceptable; note it as a finding.
- **parity_tiers**: The replay runs in semantic mode (values equal; key order and number lexeme free). Tier A (certified-figure routes and every gateway tool result): the values must be equal, and a changed figure is never an improvement. Tier B (everything else with a JSON body): values equal. Tier C (error responses): keep the error shape family (a JSON body with `detail`, as the clients read it) and the right status; the message text is free. Tier D (zip and xlsx container bytes, timing, model output): out of scope. Anything else that differs from a recording for a good reason goes in the improvements register, not into reproduction code.
- **python_oddities**: Fix defects instead of reproducing them. F-2 to F-6 (plain-text 500s): return the JSON error family with the correct status, a 4xx where the cause is a client error, and never a stack trace. F-8 (duplicate claims): handle duplicates as the claims design intends (idempotent or a 409), and record which. F-14 to F-16 (inconsistent writer checks): apply the writer check consistently to every route that writes. F-1 (a GET that never returns because magnitude is unbounded): bound it and refuse out-of-range values with a 422. F-17 and every other entry in contract/FINDINGS.md: apply the same principle; read the finding first. Exception: if fixing something would change a calculated figure, a stored value or an authorisation outcome for a valid request, keep the Python result, and list it under needs_human as a fix candidate for the owner.
- **list_totals**: Response metadata that counts things (totals, counts, populations) keeps the recorded Python semantics, so a list endpoint returns what the recordings show. Do not introduce page-independent totals or other metadata redesigns during the port; record any real concern as a finding for after cutover.
- **replay_scoring**: The replay runs in semantic mode and the policy tolerates free-text paths globally (validation message wording, echoed input and context, the Vary header, validation finding messages), so these never need a register entry. A status difference, a changed number or a missing or extra field elsewhere is a real difference: fix it, or register it only if it is a defect fix. During route-group sessions the replay is informational; the thresholds apply to the merged branch.
- **durable_manifest_counts**: Dry-run preview counters in run-batch responses (never_run, skip_coverage and similar, under `preview` or `dry_run_summary`) follow the real durable run manifest, as deployed, not the recording harness's disconnected in-memory store (finding F-18). Where they differ from a recording for that reason, register an improvement entry for that exact route and path; the policy permits numeric differences on those paths only. This does not extend to any calculated figure.
- **oracle**: CPython 3.12 is the only oracle interpreter. The recordings, goldens and seeds were made on it.
- **target**: net10.0 only. Do not use .NET 11 features or preview packages unless a decision below names them.
- **delta_read**: No Delta library at runtime. Payroll is read over the lakehouse SQL analytics endpoint behind an IPayrollSource port. For the data-version stand-in use the design recommended in dotnet/docs/PLATFORM-RISKS.md if that file exists; otherwise use a per-account fingerprint of row count plus the maximum modified date, record it with each run, and list the limitation.
- **warehouse_writes**: Use multi-row parameterised INSERT batches (the Python adapter's method) unless dotnet/docs/PLATFORM-RISKS.md proves a faster supported bulk path on Fabric Warehouse. Retry on SQL errors 24556, 3960 and 1205. Never use EF Core migrations against Fabric Warehouse.
- **mediator**: Use the in-house mediator (ADR 0003). No MediatR, and no libraries with commercial licences. Check a package's licence before adding it and record it in the session log.
- **scope_cuts**: Out of scope: the 10 sealed /api/workspace routes (answer exactly what the recordings show when the reference extract is absent), tools/reference_*, web retrieval inside tools/rules_ingestion beyond its HTTP surface, the mock AI gateway, and the ops scripts (migrations, grants, seeding, smoke checks), which stay in Python for now.
- **external_systems**: Never contact live Fabric, Foundry, Entra or any customer system unless the session's task names it and its approval variable is set. The hermetic seeds under contract/seed are the data source for development and replay.
- **numeric_guard**: Agents narrate and tools calculate (ADR-008). The numeric guard ports as is, with the same refusals.
- **heavy_tests**: Tag every test that runs longer than about 20 seconds or loads more than 20 MB as [Trait("Category", "heavy")]. A session's own gate is build, format, fast tests and its replay groups; heavy suites run at wave end and at the final gate.
- **route_ownership**: Each route group lives in its own folders: src/TaxCredit.Application/Features/<Group>/ and src/TaxCredit.Api/Endpoints/<Group>/ plus tests under tests/TaxCredit.Api.Tests/<Group>/. A group registers itself through an endpoint-group class discovered by the host; no shared file is edited to add or retire a route.
- **schema_messages**: Pack and draft validation (domain slice, finding on JsonSchema.Net): verdicts, keywords and paths must be correct; the English wording of messages is free. Record any case where a verdict differs from Python's jsonschema in dotnet/docs/pack-validation-deviations.md, with the reason.
- **ingestion_override**: Captured ingestion overrides a year-resolved pack's wage_basis, measuring_date and pay codes (domain finding M-01). This changes calculated figures, so keep it as ported and list it under needs_human as a fix candidate for the owner. Read the finding and the ADRs first: if the design clearly says otherwise, say so in the report, but still do not change it without the owner's decision.
- **multi_program_credit_math**: In credit_math a state with several programs prices its first program, as Python does; the typed refusals live in the run-resolution code (_client_run, program_defaults), which is ported. Do not add a refusal to credit_math. List this under needs_human as a fix candidate for the owner, since it affects figures.
- **improvements_register**: Each deliberate difference from the recorded Python behaviour is an entry in dotnet/docs/improvements/<your session>.json: {"improvements": [{"id": "IMP-<session>-1", "kind": one of defect_fix, error_text, wire_incidental, framework_default, "route": "METHOD /path/template", "case": optional text matching a recorded case id, "categories": optional list of replay categories, "path_prefix": optional JSON path, "finding": "F-n or empty", "reason": what was wrong and what the .NET host does instead (at least 20 characters)}]}. The replay gate treats failures covered by an entry as waived and shows them on the board and in the wave report for the owner to review; a changed number is never waived, and a group that relies on the register for more than the policy limit of its cases fails.
- **domain_slice**: The domain slice is certified (dotnet/docs/DOMAIN-SLICE-REPORT.md): build the application layer on top of it and do not re-port or re-verify its modules. Anything marked partial or pending in dotnet/docs/port-map.md and needed by your routes is yours to finish.

---

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

---

## Gates (checked by the conductor after you finish, mechanically)

- `no_halt`: no HALT.md in the worktree
- `commits_present`: at least one commit on your branch
- `clean_tree`: everything committed
- `not_pushed`: the branch is not on any remote
- `owned_paths`: every changed file is inside your owned paths
- `status_json`: the STATUS.json finish file exists and parses
- `report_present`: the report files named below exist
- `stages_done`: no stage in your status file is marked skipped
- `dotnet_build`: `dotnet build -warnaserror` passes on the whole solution
- `dotnet_format`: `dotnet format --verify-no-changes` passes
- `tests_fast`: all tests not tagged `heavy` pass
- `replay`: the contract replay (semantic mode) meets the thresholds for your route groups; failures covered by your improvements register entries are shown separately and are capped
- report required: `dotnet/docs/GATEWAY-REPORT.md`
- replay thresholds: board only (the replay must run and produce a report)

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-w3-gateway`** (branch `dotnet/w3-gateway`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/src/TaxCredit.Gateway/**`, `dotnet/tests/TaxCredit.Gateway.Tests/**`, `dotnet/Directory.Packages.props`, `dotnet/src/TaxCredit.Api/**`, `dotnet/src/TaxCredit.Application/**`, `dotnet/tests/TaxCredit.Api.Tests/**`, `dotnet/docs/**`. The last entry, `dotnet/docs/**`, is always yours for reports, logs, status files and the improvements register; it never needs an exception. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/gateway.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/gateway-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-gateway.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/gateway.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "gateway",
  "branch": "dotnet/w3-gateway",
  "head": "<short commit>",
  "summary": "<at most ten lines: what was built, what the gates say, what surprised you>",
  "stages": {"<stage id>": "done | partial | skipped"},
  "gates_claimed": {"<gate>": true},
  "deviations": [{"id": "DEV-1", "what": "...", "why": "...", "decision_needed": false}],
  "findings": ["Python behaviour that looks wrong, or traps found"],
  "open_questions": ["..."],
  "needs_human": [{"item": "...", "why": "..."}],
  "reports": ["relative path of each report you wrote"]
}
```

Then print a short summary. The conductor reads your reports and `STATUS.json` to plan the next wave, so write them for a reader who has not seen your session: numbers, evidence, exact error messages, and what the next session can now rely on.
