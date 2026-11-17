# W3 channel gateway

## Delivered boundary

`TaxCredit.Gateway` is an ordinary .NET 10 executable, not a forwarding stub.
It composes Application, the runtime adapters and discovered API feature
registrations in-process. No separately running API is needed. The API retains
its own route mapping; the gateway reuses `HostComposition.UseSkeletonHost`
without accidentally publishing portal routes or API documentation.

The official **ModelContextProtocol 1.0.0** package and its
**ModelContextProtocol.Core 1.0.0** dependency are resolved with stable
`net10.0` assets. Their licence is **Apache-2.0**. Only the marked gateway
package section changed; no existing dependency pin was raised. SDK evidence
is `artifacts\obj\TaxCredit.Gateway\project.assets.json`.
`McpServer.Create`, `RunAsync`, the SDK handlers and protocol serializer
execute real requests. `GatewayProtocolTests` also uses the official MCP
client over a real HTTP socket for initialize/list/call.

The SDK owns method dispatch; a thin `ITransport` adapter preserves the
channel's JSON HTTP, origin, identity, session and error contracts. There is
no SDK fork and no hand-written replacement JSON-RPC server. Negotiation is
covered for 2025-11-25, 2025-06-18 and 2025-03-26, including the source's
unsupported-version fallback. The SDK truthfully advertises logging; its
additional capability is registered, not stripped.

## Composition and launch

From `dotnet`, the tested conductor-style launch is:

```powershell
$env:TCC_CONTRACT_DIR = Join-Path (Split-Path $PWD) 'contract'
dotnet run --no-build --project src\TaxCredit.Gateway --no-launch-profile -- --urls http://127.0.0.1:51849
```

The marker is a **test-launch opt-in**, not a production setting.
`TaxCredit.Gateway.csproj` has its own scoped executable launch target,
equivalent to the API's target: project references do not propagate it.
Effective startup `TCC_CONTRACT_HOOKS=1` exposes the existing reset, drain,
env and mint contracts. An explicit `0` wins over a valid marker.

Three actual executable configurations were exercised: marker-on, no marker,
and marker-present/explicit-opt-out. Both hooks-off processes answered health
200, all four control POSTs 404 and anonymous tool listing 401. In-process
tests separately cover hooks-off composition. Synthetic tenant/audience
settings and isolated local stores were supplied; these are not deployment
or live identity proofs.

Application/runtime registrations precede feature construction. Startup
settling, signing-key initialization, request gating and explicit principal
push/restore are reused. The gateway maintains strict internal Entra mode
even if a contract reset requests the portal's anonymous local mode. Its
writer policy requires entitlement for **prepare as well as commit**.
Reset decorates the real runtime reset and clears sessions, facts and rate
limits. Env refresh clears stale rate budgets. Collaborators remain scoped;
the singleton SDK session obtains the current request services and verified
caller from that exchange's explicit context.

## Tool-to-application map

The inventory is a test fixture, never runtime answer data. REST and MCP
share the application's catalogue: **36 public tools**, exact schemas and
complete descriptions. The internal package redemption operation is not
advertised. Debug mode adds only `channel_ping`.

| Tool(s) | Production path |
|---|---|
| `book_rank` | Existing canonical portfolio page query and named band order |
| `client_resolve`, `client_situation`, `client_trend` | Existing direct reads: resolver, claims situation and stored history |
| `client_eligibility` | Canonical resolved statute plus stored client context/state-credit brief |
| `client_at_risk` | `CapabilityRiskReads` -> stored counted cohort and certified fragility function |
| `client_discovery` | `ReadsDiscoveryService`, excluding the selected state's programmes |
| `simulate` | Existing `SimulateUnitQuery`, resolved fiscal window and statute |
| `calc_walkthrough` | Canonical credit brief's recorder, steps and evidence hash; no payroll replay |
| `employee_drill` | Authorized token-scoped `StoredReadQuery("drill")`, with explicit unavailable evidence |
| `findings_list` | Existing `ListFindings` query and recorded decisions |
| `claim_cell_history` | Existing direct claim/history read |
| `program_catalog` | Existing `ProgramCatalogueQuery`, channel projection and verification disclaimer |
| `run_batch_list`, `run_batch_status` | Existing batch queries, visible items, health and grouped failures |
| `data_catalog`, `data_query`, `data_distinct_values` | Existing allowlisted typed governed-query port; never caller SQL |
| `verify_figures` | Gateway-local person/conversation ledger and Application numeric guard |
| `claim_package_link` | Latest actual package metadata and durable person-bound ticket |
| Internal `claim_package_redeem` | Expected person checked before atomic confirmation spend |
| `finding_resolve_prepare` / `_commit` | Pure finding preview / `ResolveFinding` |
| `finding_reopen_prepare` / `_commit` | Pure reopening preview / `ReopenFinding` |
| `claim_transition_prepare` / `_commit` | Domain transition preview / `TransitionClaim` |
| `claim_record_prepare` / `_commit` | Domain asserted-claim preview / `RecordClaim` |
| `engagement_set_prepare` / `_commit` | Validated engagement preview / `SetEngagement` |
| `base_year_set_prepare` / `_commit` | Existing rebase query / `SetBaseYear` |
| `claim_package_create_prepare` / `_commit` | Stored run/package preview / `CreatePackage` |
| `run_batch_prepare` / `_commit` | Existing resolved dry-run query / `CreateBatch` |

`ApplicationCapabilityReads` and `ApplicationCapabilityWrites` are also
registered on the ordinary API. All eight pairs have hermetic state and
audit assertions, unchanged business state during prepare, argument/person
binding and exactly one mutation on retry across new scopes. Concurrent
commits use host-local key leases plus the existing durable confirmation
consume/result recovery. No separate gateway confirmation mechanism exists.
Package command output is projected to the channel's minimal result including
`download_path`; the normal API artifact metadata shape is unchanged.

## Trust, execution and error ownership

RS256 verification checks signature/key size, issuer, gateway audience,
times, claim types and duplicate claims. App-only `Channel.Invoke` and
delegated `Channel.Access` are separate shapes; mixed tokens are refused.
Configured caller allowlisting and caller/channel bindings remain available.
Agents assert a bounded `X-Acting-*` person context for an allowed first-party
channel. Delegated headers cannot replace the verified user. Client policy
still checks the real caller and writer policy checks the acting person.

REST and MCP share `ToolPipeline`: catalogue lookup, person rate budget,
validation/defaults, required read-audit begin, authorized capability
dispatch, lane enforcement, result bounds, trusted-fact recording and
channel error translation. G1 resets to 1,000 calls/minute and G1L to six;
other people have independent budgets and health spends none.
MCP origin validation precedes parsing and identity; malformed message
validation precedes authentication as in the source.

Channel failures are `error.code/message/retryable` plus verified correlation,
not API `detail` or ProblemDetails. Authentication 401 includes
`WWW-Authenticate: Bearer`. Malformed envelopes, dependency timeout, request
cancellation, unavailable opening audit, invalid output and unexpected
failure remain distinct. A timeout warns that an accepted commit may still
land and must be retried with the same idempotency key.

A read cannot execute without its opening audit. A failed closing event emits
a safe operational alert without disguising an accepted outcome. Verified
write-envelope refusals are audited even before application dispatch, for
REST and recognizable MCP tool calls. Successful write audit remains owned
by the capability path, not duplicated in the gateway. Argument values,
rejected prose, tokens and exception diagnostics are not copied into logs.

Sessions are person-bound, limited to 5,000 and expire after eight hours.
Each uses bounded 32-message queues and one exchange at a time; responses
are matched by ID so an abandoned HTTP exchange cannot steal a later reply.
Wrong-person lookup/delete does not consume the owner's session. Requests
are bounded at 64 KiB, tool results at 1 MiB and downloads at 25 MiB.

## Figures, narration and downloads

The ledger holds only accepted trusted facts, under verified tenant/person
and conversation: at most 1,000 conversations, 200 results each, eight-hour
expiry. It excludes verification itself, diagnostics, package tickets and
redemption. Reset forgets the ledger. A caller cannot supply replacement
facts to `verify_figures`.

`ChannelComposer` reuses Application `NumericGuard`, `FactIndex` and
`NumericFormatting`. It validates trusted scalar paths, masks placeholders
before `CheckRaw`, substitutes canonical rendering, then independently
checks the complete reply. Missing/ambiguous/null/unrenderable paths and
fenced placeholders fail closed. Narration-policy patterns also reject
hedging, rounding claims, unsolicited URLs/addresses/identifier shapes,
code fences and legal guarantees. Rejected narration is dropped whole;
unverified platform blocks withhold all figures. This gateway does not
invoke a narrator or generate model prose.

Narration reporting is agent-only, schema- and verdict-checked and records
two durable rows. Submitted prose summaries are deliberately not persisted:
audit stores safe verdict/count codes and the supplied content hash instead.

Package links use durable hashed, expiring, single-use tickets. Wrong-person
optional bearer validation precedes spend; a malformed supplied bearer is
not ignored. Redemption restores the ticket owner's identity/context and
dispatches the existing authorized artifact download query. Metadata,
byte-size/hash and artifact-access audit are enforced; no Blob/SAS URL is
returned. Concurrent possession and a fresh application scope are tested.
Missing bytes or revoked owner access do not unspend a ticket.

F-19 and F-20 remain intentional: an unknown ticket is **502
`invalid_arguments`**, and reuse is **410 `confirmation_replayed`**.
Tests cover archive members, returned-body integrity, filename/content type,
no-store, owner/wrong-person, concurrency, missing bytes and revoked access.

## REST integration contract

| Method/path | Contract |
|---|---|
| `GET /api/health`, `/channel/health` | Unauthenticated process health |
| `GET /channel/ready` | Channel readiness/store description; not proof of live Fabric grants |
| `GET /channel/v1/tools` | Authenticated shared public catalogue |
| `POST /channel/v1/tools/{tool}` | `{args, idempotency_key?, confirmation_token?}`; canonical envelope and correlation |
| `POST /channel/v1/audit/narration` | Agent-only validated narration audit |
| `GET /channel/v1/downloads/{ticket}` | Owner-bound attachment; bearer optional but validated if supplied |
| `POST /mcp` | JSON MCP request/notification; initialize returns `Mcp-Session-Id` |
| `GET /mcp` | 405, no bearer required, origin still checked |
| `DELETE /mcp` | Authenticated owner delete; 200 or 404 |

Agent headers are `X-Acting-User-Oid`, `X-Acting-User-Name`,
`X-Acting-Tenant`, `X-Channel`, `X-Conversation-Id` and optional
`X-Correlation-Id`. Delegated requests derive person/tenant from the token
and may provide conversation/correlation. MCP subsequent requests carry
`Mcp-Session-Id`; optional `MCP-Protocol-Version` must be supported.
Notifications and client responses return 202 without tool execution.
The existing REST contract needs no new shared orchestrator type.

## Remaining boundaries and owner decisions

- Governed data advertises eight available datasets rather than eleven:
  three unavailable infrastructure datasets are omitted with an explicit
  availability note. Suppression/distinct operations that lack a proved
  safe typed-port implementation are refused, never fabricated as an
  empty aggregate. The changed catalogue count is **not waived**.
- The source returned unmarked person-derived risk/findings facts to two
  recorded non-writer Cowork calls. This implementation preserves the
  application's fail-closed lane checks and marks the risk cohort.
  Their missing facts/refusal differences remain visible, not waived as
  numerical equivalence. Owner review must reconcile this privacy design
  with the valid-request authorization-preservation policy.
- Previewing a Python claim allocates a throwaway new claim ID through
  `next_claim`/`build_claim`; the .NET pure preview supplies a non-persisted
  clock/identity and allocates no production ID. Later genuine confirmation,
  correlation and artifact IDs can therefore differ. No dummy ID draws
  were added and no UUID/path differences are waived.
- Different confirmations using the same idempotency key are serialized
  within a host. The existing repository port does not prove a global
  atomic key reservation across multiple gateway replicas. Same-confirmation
  consume is atomic; cross-replica/different-confirmation exclusivity needs
  a persistence-owner contract.
- Inherited M-01 ingestion overrides of year-resolved values and
  first-program credit pricing remain unchanged. Both are figure-sensitive
  owner decisions, not gateway fixes.
- Row-count/max-modified fingerprints are not Delta snapshots and miss
  count/max-preserving edits. Native monetary AVG, zero-worksite SQL
  semantics, partial strict leap-day fiscal handling and live artifact
  publication remain inherited limitations/unverified provider behavior.
- No live Fabric, Foundry, Entra or customer system was contacted. HTTP
  tests include injected failure adapters; the ordinary executable replay
  uses real application composition with hermetic seeded adapters. Neither
  is claimed to prove deployed grants, native concurrency or live bytes.

## Original delivery gates and replay evidence

SDK **10.0.404**, CPython oracle **3.12.13**, target **net10.0**.
The oracle imports this checkout. The inherited strict build and 978 fast
tests passed before implementation. Final whole-solution results:

- `dotnet build -warnaserror -v:q -m:1 -nr:false`: zero warnings/errors.
- `dotnet format --verify-no-changes --no-restore -v:q`: passed.
- All non-heavy tests: **1,114 passed, zero failed/skipped**, including
  **103 gateway tests** and **365 API tests**. The increase is 136 cases:
  103 gateway cases and 33 production-binding cases. Each fast case is
  under 20 seconds; new fixtures are below the heavy-data threshold.
- Four CPython diagnostic tests passed. They prove free error wording
  cannot waive changed tool figures, error codes or non-preview counters.
- Ownership, whitespace and local-only branch checks passed. No Domain,
  Infrastructure, product Python, recordings, comparator or threshold
  changed. No heavy/live-suite result is newly claimed.

TRX evidence: `artifacts\gateway-complete-fast`.
The actual final standalone gateway replay used the public
`contract.replay` and its existing scenario setup/reset path, not custom
token/profile inference. G1 and G1L execute repeatedly on one process;
the real write/package/download sequence is followed by subsequent reset.

| G1 scenario | Exchanges | Raw failing fields | Policy diagnostic passed | Fully register-waived cases |
|---|---:|---:|---:|---:|
| MCP | 103 | 254 | 98/103 | 6 |
| Rate limit | 10 | 12 | 10/10 | 0 |
| REST | 142 | 262 | 125/142 | 5 |
| **Total** | **255** | **528** | **233/255** | **11** |

Raw case scoring is **0/255**, because every exchange differs at least in
the globally tolerated `Vary` header. The raw replay exits 1 and remains
untouched at `artifacts\gateway-complete-replay\raw`, with its unwaived
board alongside it. **This is not a claim of literal/full parity.**

`replay-gateway-policy.json` is a committed, separately labelled read-only
policy diagnostic, **not an external conductor execution**. It records
raw-report SHA-256 values and every remaining case/path/category.
Of 528 raw fields, **459** are globally free wording/header differences,
**13** match eight exact improvement entries, and **56** remain unresolved
in **22 cases**. Eleven fully waived cases are **4.31%** of the 255 cases.
There are **zero numeric register matches** on G1; neither changed
catalogue counts nor missing numerical facts are waived.
Only same-code rendered MCP refusal wording is treated as free error text;
good tool text and changed error codes are not.

Exact remaining attribution:

| Cause | Cases and paths |
|---|---|
| Unentitled person-lane requests | MCP `call.client_at_risk.typical`, `call.findings_list.typical`: missing structured result fields and rendered text; source returned person-derived facts |
| Unavailable governed datasets | REST `tool.data_catalog.typical`, MCP `call.data_catalog.typical`: dataset count/list, availability notes and corresponding blocks |
| Governed refusal boundary | MCP `call.data_query.typical`: privacy refusal precedes `empty_query`; REST/MCP `data_distinct_values.typical`: inherited `column_not_listable` instead of `unknown_column`, missing `error.field` |
| Genuine later allocations | REST seven prepare confirmation IDs; `write.claim-package-commit` artifact ID and matching download path; seven correlation body/header fields |

The seven prepare cases are `tool.claim_transition_prepare.typical`,
`tool.claim_record_prepare.typical`, `tool.engagement_set_prepare.typical`,
`tool.base_year_set_prepare.typical`, `tool.claim_package_create_prepare.typical`,
`write.prepare` and `write.claim-package-prepare`. Correlations differ on
`tool.delegated-book-rank`, `narration.delegated`, `download.unknown-ticket`,
`download.unknown-ticket-with-token`, `download.other-user`, `download.owner`
and `download.owner-again-single-use`. The committed diagnostic gives the
exact JSON paths; no wildcard waiver conceals these values.

### API regression replay

All **nine API scenarios / 1,514 exchanges** also ran on the ordinary
no-profile API executable after bridge/composition changes. There are
1,510 HTTP cases and four control records. Its **2,325 raw failing fields**
are retained separately, not called passing tests:

| Scenario | Exchanges | Raw failing fields |
|---|---:|---:|
| `p1_artifacts_ai` | 36 | 97 |
| `p1_auth` | 114 | 182 |
| `p1_program_drafts` | 175 | 317 |
| `p1_query_edges` | 71 | 116 |
| `p1_reads` | 584 | 617 |
| `p1_workspace_unavailable` | 30 | 46 |
| `p1_writes` | 366 | 587 |
| `p2_reads_writes` | 74 | 148 |
| `p2_run_batches` | 64 | 215 |

Two post-change ordinary API executions have **identical ordered failure
lists in every scenario**. The three explicitly published convergence
scenario counts (auth 182, P2 reads/writes 148, batches 215) also reproduce.
This is not a new external conductor run or a claim that its historical
registered-only group projection was executed here.

API evidence is `artifacts\gateway-final-api-replay\raw`, `raw-board.json`
and `policy-board.json`. Under this diagnostic's per-scenario HTTP counting,
1,368/1,510 pass, including 176 fully register-waived cases; 142 cases /
604 fields remain. Existing registrations, including the narrow F-18
durable-preview exception, account for 726 fields; 995 are globally free.
Three inherited numeric-looking HTML register matches are **rejected**,
not waived. These counts include prerequisites, sealed and unassigned
operations and must not be substituted for the conductor's different
route-group denominators.

Reproduce the policy diagnostic without rerunning or changing comparisons:

```powershell
python docs\gateway_replay_report.py --raw artifacts\gateway-complete-replay\raw --out artifacts\gateway-complete-replay\policy-board.json
```

W3's replay threshold is **board only**: completion claims execution and
transparent attribution, not an all-green parity board. The actual hosts
used for replay and hooks-off proof were stopped. No remote was changed
and nothing was pushed.

## Conductor build-gate correction: 16 November 2026

The conductor launched from the repository root, selecting **SDK 11.0.100**,
not the **10.0.404** selected from `dotnet`. Reproducing its strict solution
build failed in `Microsoft.NET.Sdk.StaticWebAssets.JSModules.targets(233,3)`:
the referenced API executable contributed the Blazor hot-reload module
`_framework/Microsoft.NET.Sdk.BlazorWeb.HotReload#[.{fingerprint}]!.lib.module.js`
without a matching gateway static-asset endpoint.

Fix commit **`3b3fae2`** sets **`StaticWebAssetsEnabled=false`** in
`TaxCredit.Gateway.csproj`. This host exposes JSON/MCP/download endpoints,
not UI/static assets. Disabling that unused build pipeline is scoped to the
gateway; it neither suppresses a compiler warning nor changes API behavior,
SDK selection, net10.0, dependencies, tests or replay policy.

Fresh gate results:

| Check | Result |
|---|---|
| Root SDK 11 `dotnet build .\dotnet\TaxCredit.slnx -warnaserror` | Pass, zero warnings/errors |
| Pinned SDK 10 build from `dotnet` | Pass, zero warnings/errors |
| Root SDK 11 whole-solution build with `--no-incremental` after SDK 10 | Pass, zero warnings/errors |
| Root `dotnet format .\dotnet\TaxCredit.slnx --verify-no-changes --no-restore -v:q` | Pass |
| Root whole-solution `dotnet test` with `--no-build --no-restore --filter 'Category!=heavy' -m:1 -nr:false` | 1,114 passed, zero failed/skipped |
| Ordinary root-launched gateway replay | 255 exchanges, 528 raw failing fields, unchanged |
| Ordinary root-launched API regression replay | 1,514 exchanges, 2,325 raw failing fields, unchanged |

An initial run of parallel test projects alongside format verification hit
the inherited AI resilience test
`RetryAfterIsHonoredAndHealthyStreamsUseGapNotDuration`: its healthy-stream
timeout is 100 ms. The full suite passed with projects serialized; no test
or timeout was modified, excluded or retried selectively.
Passing TRX evidence is `artifacts\gateway-build-fix-fast-serial`; the initial
run remains separately available at `artifacts\gateway-build-fix-fast`.

Both replay hosts used the real root `dotnet run --no-build --project ...`
launch, no launch profile, the conductor's contract marker, separate local
stores and the existing public replay setup. Health probes returned 200.
The **complete ordered failure lists**, not only totals, match the original
delivery for all three gateway and nine API scenarios. Fresh raw reports are
`artifacts\gateway-build-fix-replay\raw\g1.json` and
`artifacts\gateway-build-fix-api-replay\raw\api.json`.
The separate fresh gateway policy diagnostic is
`artifacts\gateway-build-fix-replay\policy-board.json`: **233/255**,
11 fully waived cases, 56 unresolved fields in 22 cases and no numerical
waiver. Existing exact unresolved attributions above remain valid.

The public raw comparator still exits 1 on those disclosed differences;
W3's replay requirement remains **board only**, not full parity. Both proof
hosts were stopped. No live services, SDK 11-only features, new dependencies
or changes outside the assigned ownership were needed.
