# AI routes and prompt agents

## Scope and host composition

Four owned operations are registered through ordinary feature discovery:
`GET /api/capabilities`, `POST /api/capabilities/{tool}`, `POST /api/chat`
and `POST /api/summary`. Endpoints send mediator requests; streaming handlers
produce application events and reuse the host's flushing `EventStream`.
No shared startup, provider, package, Domain or Python product file is changed.

The feature loads twelve validated prompt agents and bridges them to the
existing W1 `ModelRouter`. W1 still owns injection/egress guards, budgets,
retries, circuit breaking and provider availability. No Foundry publishing
transport or invocation factory has been installed. Configured-but-unavailable
Foundry remains unavailable; fake publication is not a deployed agent.

## Prompt publication matrix

Every request uses `agents.create_version`, `PromptAgentDefinition`,
`tcc-<AgentName>`, empty tools and no extra keyword arguments. Tests supply
`contract-model` through role configuration; it is not a runtime deployment
choice. Returned name/version/id projections, supported versus omitted
temperature, universal newlines, manifest history and prompt mutations are
covered by the publication seam.

| Agent | Role | Temperature | Version | Characters | Current SHA-256 |
|---|---|---:|---:|---:|---|
| OrchestratorAgent | router | 0.2 | 1 | 1213 | `112c8b03130c3ae35c1c1f6236d55b2e0b50772d35031783116bd3e7ddc59a68` |
| PayrollIngestAgent | narrator | 0.2 | 1 | 611 | `cfe97ba1377ffc3d86f336904368ccedc8cead06751907a264da95ac293ead8b` |
| HeadcountAgent | narrator | 0.2 | 1 | 364 | `d1afada16d0acc0c8d300d652691b9f21c5245533903bde43a67fe784281e96c` |
| CreditRulesAgent | narrator | 0.2 | 1 | 531 | `3082d9d944d6b720612d4d5939dc3a32c7ccd16ea82154762e54ba4934053017` |
| CreditDiscoveryAgent | narrator | 0.2 | 1 | 289 | `12020f37b3e1cfe5edf4f3d191339cbebf05f60d8a0d52113e92dfa545dadbfd` |
| ClientSituationAgent | narrator | 0.3 | 1 | 1471 | `911b65b6d2715d08376d9ee1e30b7f88ebbf7f4a162b703f14452e9bf6a171a9` |
| PageSummaryAgent | narrator | 0.2 | 1 | 1708 | `0eab358f660bc677e339be09f88343a28b86faf6941bca9ea4cda031006be1be` |
| ReportingAgent | narrator | 0.3 | 1 | 509 | `af874e7eacc2bc29e83081534bbaaafc2877e7944157e1fe5d1e48d910319344` |
| RulesIngestionAgent | analysis | 0.1 | 1 | 816 | `f3544e6dde65b0be80f93aa38df1d446bf37587724d691d8d1a6ff7c3d725e2d` |
| ExceptionReportAgent | analysis | 0.2 | 1 | 667 | `66d8e1fe18c7984e2c77a0049cb20d3fc778eed5600cea6a7abc0b4b7fcbbda7` |
| LegislativeMonitorAgent | analysis | 0.2 | 1 | 650 | `ecae917ba8fbf4182a1833b9c36e773dbbed43e5fec036a53327bc355afc656b` |
| ChannelNarratorAgent | narrator | 0.2 | 4 | 11063 | `fa17204c8dbe38c53b6d3c78d57070e10567f1c0aba9b0f2c692e6db41adcd61` |

`manifest.json` is metadata, not a thirteenth prompt. The packaged resx bundle
uses the existing SDK resource convention and does not search an absolute
planner checkout. An explicitly supplied bundle directory has the same
normalization and validation contract. CPython 3.12.13 independently matched
all twelve packaged bodies, instruction counts and current hashes.

## Briefs, routing and numeric integrity

Pure builders cover portfolio, client, unit and employee pages, with the
recorded null/unavailable distinction, open-year caveats, supplied hours lever,
stored eligibility verdicts and fiscal/month allocation. Client summaries
read `IGoldReadPort.UnitPage`, never replay payroll. Other page owners bind
their canonical payload through `IAiPageCollaborator`, selected by `Page`.

Chat preserves keyword routing order, compound questions, the intent
whitelist, history referents, explicit confirmation and per-capability scope
refusals. It does not answer against a default client. The normal capability
boundary supplies seven intents. `client_situation` receives `year`, not
`tax_year`; eligibility retains the portal's explicit Pay Period selection
(D-05), rather than silently changing figures to match another selector.
`simulate` needs explicit worksite resolution, while `multi_state` needs a
scan with no exclusions; their narrow `IChatIntentCollaborator` bindings
must not be replaced with a guessed location or an excluding discovery call.

Strict numeral integrity is separate from W1 model safety:
`NumericGuard.CheckRaw` checks model-authored digits; `Check` checks finished
facts/context with exact decimal values. The caller masks placeholders before
`CheckRaw`, as the Python composer does. Fact/context/date/year, structural,
percentage, abbreviation and Unicode-evasion lanes are distinct.
The page-summary checker intentionally has Python's less strict
written-precision semantics, including binary64 and the `1e-9` boundary.
It reports unsupported figures after streaming; it is not a pre-display
integrity guarantee. Portal chat remains numerically unchecked model prose,
matching the documented ADR-008 limitation. No W3 composer or gateway ledger
is claimed.

Employee summaries never reach a model. Unit person-level lines and capability
`user_only_facts` are excluded from narrator facts. Capability envelopes and
local deterministic blocks remain available to the authorized reader.

## Streaming contract

Offline summaries emit `brief`, `fallback`, `done`; a successful model path
emits `brief`, `agent_start`, `token` events, `agent_end`, `check`, `done`.
A failed read emits `error`, `done`; interrupted narration closes the agent,
falls back once and ends once. Employee scope deliberately uses deterministic
fallback even when a model is available. Model output is never used to fill
missing trusted facts.

Clarification emits `status`, `agent_start`, `token`, `clarify`, `agent_end`,
`done`. A compound plan runs each satisfiable intent in order, names refused
scope-dependent parts, and emits one terminal `done`. Unlike Python's
unconfigured demonstration, offline chat uses real capability blocks or a
named dependency refusal; unrelated fixed figures are not copied.

Tests exercise the actual Kestrel stream as well as TestServer: frame
boundaries, per-frame flushing, no-cache and no-buffering headers, UTF-8/JSON,
disconnect disposal and one terminal sequence. Cancellation before output
does not open a provider. The composed W1 failure test uses its actual
decorator chain to check no retry/provider hop after visible output and
reservation/span/request-scope cleanup.

## Capability completeness and production bindings

The immutable Python catalogue has **37 declarations, 36 public entries**:
20 public reads and eight prepare/commit pairs. The internal package redemption
operation is not listed. `verify_figures` remains gateway-local and refuses API
execution with 501; debug/unknown names refuse with 404. The captured
`implemented` flags describe the catalogue, not proof that every sibling
production service is installed in this branch.

All names dispatch through schema/default validation, caller/client policy,
bounded execution and the canonical facts/blocks/provenance/warnings/disclaimer
envelope. Non-object arguments and invalid request fields use the `detail`
validation family; controlled tool errors retain Python's distinct
`error.code/message/retryable` family. Missing bindings return controlled 503
`dependency_unavailable`, never recorded success data or invented zeroes.

| Locally implemented calls | Existing inward dependency |
|---|---|
| `client_resolve` | Source account book and client authorization |
| `client_situation`, `claim_cell_history` | `IClaimRepository` and certified coverage functions |
| `client_trend` | `IGoldReadPort.ClientYearSeries` |
| `data_catalog`, `data_query`, `data_distinct_values` | `IGoldDataQueryPort`, dataset/column/operation allowlists, bounded query specs and writer/client policies |

The exact captured public catalogue and full situation envelope pass through
ordinary host discovery and real hermetic W1 repositories. Other local reads,
governed queries and writes have port-level tests; those tests are not claimed
as evidence that an absent sibling is bound on the ordinary host.

Every remaining read uses `ICapabilityReadBridge.ReadAsync(name, arguments,
principal, cancellationToken)` and returns `CapabilityRead`: trusted `Facts`,
optional captured `Provenance`, warnings, canonical blocks and explicit
`UserOnlyFacts`. Integrators replace the default missing bridge, rather than
calling another HTTP route.

| Capability | Owner | Required application contract |
|---|---|---|
| `book_rank` | ReadsCalc | `portfolio_page`, priority ascending across all years; `items`, `total_clients`, `assessed_clients`, degraded/unavailable distinctions |
| `client_eligibility` | ReadsCalc | `resolve_statute`, `chat_client_context`, `chat_state_credit`; `snapshot`, `credit`, captured run/trail |
| `client_at_risk` | ReadsCalc | `chat_jobs_at_risk`, counted-cohort fragility under the resolved statute |
| `client_discovery` | ReadsCalc | `discover_credits`, `hits`, excluding selected-state programmes |
| `simulate` | ReadsCalc | `simulate_unit`, deterministic baseline/projected/delta under the resolved fiscal statute |
| `calc_walkthrough` | ReadsCalc | Stored `calculation_walk`, derivation rows and trail SHA-256 |
| `employee_drill` | ReadsCalc | `get_employee_drill`, token-scoped Gold projection, statute and `not_available` |
| `findings_list` | ReadsCalc | `list_findings`, client/year summary, decisions and recorded finding evidence |
| `program_catalog` | ClaimsDrafts | `ListProgramCatalogQuery`, `GetProgramDetailQuery`, registry validation and engagement availability |
| `run_batch_list` | Runs | `ListRunBatchesQuery`, visible summaries, progress and total |
| `run_batch_status` | Runs | `GetRunBatchQuery`, `ListRunBatchItemsQuery`, visibility, worker health and grouped failures |
| `claim_package_link` | ClaimsDrafts | Person-bound, single-use, audited download ticket |
| `claim_package_redeem` (internal) | ClaimsDrafts | Expected-user validation before atomic ticket spend |

Every write uses `ICapabilityWriteBridge.PreviewAsync` for pure `{before,after}`
and `CommitAsync` for the owning mediator command and its durable audit. No
confirmation is minted before a valid preview exists.

| Prepare/commit base name | Owner | Required command and preview |
|---|---|---|
| `finding_resolve` | ReadsCalc | `ResolveFindingCommand` |
| `finding_reopen` | ReadsCalc | `ReopenFindingCommand` |
| `claim_transition` | ClaimsDrafts | `TransitionClaimCommand` |
| `claim_record` | ClaimsDrafts | `RecordClaimCommand` |
| `engagement_set` | ClaimsDrafts | `SetEngagementCommand` |
| `base_year_set` | ReadsCalc | `SetBaseYearCommand`, recalculation preview |
| `claim_package_create` | ClaimsDrafts | `CreateClaimPackageCommand` |
| `run_batch` | Runs | `CreateRunBatchCommand`, resolved scope preview |

The feature supplies writer checks, hashed person/arguments/tool-bound expiring
confirmations, atomic consume, same-key result recovery and durable channel
audit using W1 repositories. A timeout explicitly warns that an accepted
commit may still land; it is not retried by the endpoint. Synthetic bridge
tests demonstrate prepare/commit/replay, wrong-user/arguments/expired-token
refusals and that the same mutation is not executed twice.

Governed queries never accept SQL. W1 does not expose an atomic hidden-person
count or cross-year identity suitable for safe distinct-person suppression.
Those cases and employee distinct-value suppression fail closed, naming the
missing binding, rather than reporting unsafe aggregates as protected results.
Existing warehouse monetary-AVG and source-fingerprint limitations remain W1
limitations; narration does not repair or reinterpret them.

## Page, chat and composition integration

`IAiPageCollaborator.Page` selects `portfolio`, `unit` or `employee`, and
`ReadAsync(SummaryQuery, cancellationToken)` supplies the corresponding
canonical page projection. The portfolio projection is identified in the
runtime refusal as `ClaimsArtifactsRules.PortfolioPage`; the capability's
cross-book projection is inventoried under ReadsCalc. Integration must bind
the agreed canonical portfolio projection once, not construct two rankings.
Unit and employee bindings are `ReadsCalc.unitPage` and
`ReadsCalc.employeePage`. Client-page facts already use the W1 Gold grid.

`IChatIntentCollaborator.Intent` and its `ReadAsync` bind the richer `simulate`
and `multi_state` chat briefs. The former needs explicit worksite resolution;
the latter needs an all-program scan without discovery's exclusions.
The other seven intents use the capability mappings described above.

Two composed-host issues were fixed without shared-file edits:

- The shared mediator is singleton and resolves handlers from its captured
  root provider. These four routes use a keyed request-scoped instance of the
  **same mediator implementation and pipeline**, so lazy streams release
  scoped collaborators on completion and disconnect.
- `AddApplication` scans every concrete application `IRequestHandler`.
  Optional-feature handlers must not become dangling registrations in a
  bare runtime container. Application use cases retain their logic; the owned
  API module registers small forwarding mediator adapters only with their
  dependencies. No service locator or nullable dependency fallback is used.
  Prompt adapter registration is an infrastructure-owned DI extension, so
  endpoint files do not import concrete infrastructure types.

The book adapter also retains the Python application's fixture display-name
rule instead of leaking the lower-level transport fixture label. No employee
identifier is used to establish a conversation referent or prompt context.

## Evidence and gate results

Final checks cover the whole solution, not only the feature's project:

| Gate | Measured result |
|---|---|
| `dotnet build -warnaserror -m:1 -nr:false` | Pass; net10.0, zero warnings/errors |
| `dotnet format --verify-no-changes` | Pass |
| `dotnet test --filter 'Category!=heavy'` | Pass; 1,025 tests, no failures or skips |
| Final compiled API regression run | Pass; 279 tests, including 213 owned AI tests |
| Complete semantic AI replay | **Fail; 5/23, 21.74%, required 95%** |

The whole fast run comprises Domain 18, parity 61, AI infrastructure 167,
auth 147, sources 108, persistence 129, architecture 16 and API 279.
After moving prompt registration behind the infrastructure DI extension,
the whole solution was rebuilt warning-free, all 279 API tests were rerun,
and whole-solution formatting passed again. Oracle-dependent tests used
`TCC_PYTHON` pointing to the approved CPython 3.12.13 interpreter.

The owned tests additionally exercise realistic sibling contracts for eligibility,
fragility, simulation and a stored calculation walk, preserve their evidence,
and verify every formatted numeral against their supplied synthetic facts.

The complete `p1_artifacts_ai` semantic replay was run unchanged through an
ordinary hermetic host, including the unit/token, findings and package setup
exchanges. Both the initial and final compiled-host boards report
**36 exchanges, 192 differences and
6 tolerated differences**. AI is **5/23 passing (21.74%)**, below the required
95%; claims/artifacts setup is 1/12 and reads setup is 0/1. This is **not a
passing replay gate**.

The two successful-body capability failures require the missing `book_rank`
and `client_eligibility` sibling projections. Portfolio/unit/employee summaries
correctly emit `error, done` without their projections rather than reproducing
the captured `brief, fallback, done` from unavailable application services.
The client summary now reads inward successfully instead of reproducing the
captured router-default SQL error. Offline chat refuses an unavailable real
brief rather than emitting the recording's unrelated fixed demonstration.
Other raw differences are validation wording/context and the shared SSE
charset header. No calculated result has been waived, substituted or changed.

The unchanged W1 `replay_board.py` explicitly reports raw results with
`waived_cases: 0`; it does not apply the improvements register. The register
documents intended policy differences but is not used to inflate this score.
Even removing incidental differences would not supply missing application
projections. Full replay acceptance remains an integration item, not something
proved by fake collaborators or these unit tests.

The final absolute diagnostics are
`dotnet\artifacts\ai-replay-final\board.json` and
`dotnet\artifacts\ai-replay-final\diagnostics\p1_artifacts_ai.json`
under this worktree. They are generated/ignored artifacts, not checked-in
response substitutes. The temporary replay hosts were stopped.

To reproduce with a separately started hermetic host, invoke the unchanged
wrapper from the worktree root using the approved interpreter:

```powershell
& C:\Projects\py312-oracle\.venv\Scripts\python.exe `
  dotnet\src\TaxCredit.Api\Contract\replay_board.py `
  --base-url http://127.0.0.1:51821 --scenario p1_artifacts_ai --group ai `
  --out "$PWD\dotnet\artifacts\ai-replay-final\board.json" `
  --raw-dir "$PWD\dotnet\artifacts\ai-replay-final\diagnostics"
```

No live Fabric, Foundry, Entra or customer system was contacted. The production
Foundry SDK publication/invocation factory, sibling projections/commands and
ordinary-host success for those bindings remain unverified. No package,
shared project/startup, Domain, Python product or replay comparator was changed.

### Conductor follow-up

The reported CA2026 test-helper leak is fixed by explicitly disposing the
parsed document after cloning its element. Whole-solution build, formatting
and all 1,025 fast tests pass again. The repository-root warning-as-error build
also passes under its newer SDK 11.0.100 analyzer without changing the pinned
10.0.404 SDK configuration or net10.0 target. Fresh complete diagnostics in
`dotnet\artifacts\ai-ca2026-replay` reproduce the existing 5/23 raw AI replay
result; the missing production bindings and replay acceptance remain unresolved.

### Conductor follow-up: waiver coverage is not implementation

The conductor's **full** 1,769-exchange replay reported 24/27 AI cases passing
after improvements (88.9%), including 16/27 waiver-dependent cases (59.3%).
Both the 95% acceptance threshold and the 25% waiver cap failed. That result
is different from the earlier **raw, single-scenario** 5/23 score; neither is
a passing result.

The register was overbroad. In particular, entry 3's privacy rationale matched
every summary failure, including missing portfolio/unit/employee services.
A privacy improvement does **not** make an absent application service work.
Entry 1 also covered unrelated history validation and headers; entry 2 matched
the header-only missing-client refusal. These blanket scopes are removed.

The retained two entries are constrained simultaneously by route, case-name
family, `event` category and `events` path. Against the conductor's evidence,
they can match only `chat.ask`, `chat.ask-client` and `summary.client` event
differences. They cannot cover headers, validation, capability facts/statuses,
or other summary pages. They do not prove a case has no remaining failures.
An assertion over all conductor failures verifies that scope boundary.

Prior entries 3-5 are withdrawn from replay matching: person-only model
filtering, scoped explanation and safe exception text remain implementation
properties, not blanket exceptions for missing dependencies. Entries 6-11
(incidental headers and validation metadata/text) are also withdrawn pending
the explicit `needs_human` policy decision below. Exposing these differences
as failures is intentional; it does not change production behavior or make
the actual replay result better.

| Decision recorded in finish status | Evidence and proposed disposition |
|---|---|
| `DEC-AI-1`: policy versus cap | Eight wording/validation cases plus two header-only refusals already exceed the six cases allowed by a 27-case denominator. The task says not to reproduce these artifacts. Preserve semantic behavior; the policy owner must resolve the conflicting acceptance/accounting requirements. |
| `DEC-AI-2`: designed offline/read contract | The recording has a fixed 117-frame offline demo for two chat cases and a SQL binding error for the client summary. Do not reinstate either defect solely for replay; confirm the intended contract explicitly. |
| `DEC-AI-3`: canonical sibling bindings | The uncovered capability cases are `capabilities.book-rank`, `capabilities.client-eligibility` and `agent.capabilities-book-rank`. Bind their canonical ReadsCalc projections; likewise bind portfolio/unit/employee pages. Missing services must stay unwaived failures until integrated. |

The eight incidental error cases are `capabilities.book-rank-bad-arg`,
`capabilities.args-not-object`, `capabilities.idempotency-key-too-long`,
`chat.history`, `chat.bad-history`, `summary.bad-page`, `summary.short-token`
and `summary.bad-month`. The two header-only cases are `chat.empty-message`
and `summary.client-without-client`. They preserve their validation/refusal
status and error shape family. This is a concrete decision request, not
permission assumed from a broad register entry.

Those ten incidental cases alone make the current requirements incompatible:
the cap permits six waived cases, leaving at least four failing even if every
other feature case were implemented. That ceiling is 23/27 (85.2%), below
95%. This is why `DEC-AI-1` needs an explicit policy decision rather than
another reproduction patch or a larger self-approved register.

No compatibility code, canned result, second portfolio ranking, changed
calculated value, authorization change, relaxed threshold or replay-comparator
edit was introduced. Canonical sibling projections still must come from their
owners; copying their algorithms here would create the competing source of
truth the task explicitly excludes.

Verification after narrowing the register:

- Whole-solution warning-as-error build and formatting pass; all 1,025
  non-heavy tests pass again, with no failures or skips.
- Replayed **all twelve scenarios and all 1,769 exchanges** through a fresh
  ordinary hermetic host. Raw aggregate diagnostics contain 9,472 field
  differences and six tolerated differences. The AI scenario itself remains
  at 192 differences; unrelated-group failures are not repaired in this slice.
- Exact four-operation method/path selection yields **8/27 raw AI cases
  passing**. The unchanged local board's looser route classifier includes four
  additional method/trailing-slash cases and reports 11/31; it is not the
  conductor's 27-case grouping, and is not presented as an adjusted gate.
- Checked every retained entry against the fresh failures. At most **three
  of the conductor's 27 AI cases (11.1%)** contain matches, below the cap.
  This is a conservative match-scope upper bound, **not** a claim that those
  whole cases pass: their header differences remain unwaived. No missing
  capability or portfolio/unit/employee-page dependency can match an entry.

The fresh raw reports are in
`dotnet\artifacts\ai-waiver-review\diagnostics`, with the unchanged wrapper's
board in `dotnet\artifacts\ai-waiver-review\board.json`. No scenarios were
omitted or modified. The host was stopped. Full AI replay acceptance remains
blocked by the three explicit decisions and missing sibling services;
`gates_claimed` still intentionally omits `replay`.

## Latest conductor follow-up: required hard stop

The new conductor result is **13/27 AI cases passing (48.1%)**, with
**5/27 waiver-dependent cases (18.5%)**. Its aggregate is 1,769 exchanges,
8,868 failing fields and 737 covered fields. This supersedes the older
adjusted board, not the underlying implementation or its missing bindings.
The five waiver-dependent cases also include the W1 `sources_auth_ai`
register; this feature's two narrow entries alone do not account for all five.

Inspected the current failures and confirmed that the branch still has only
Ai, Framework and WorkspaceSealed application feature folders. The required
ReadsCalc/ClaimsDrafts implementations have not appeared. No new owned defect
was found that could resolve replay within the assignment's constraints.
Neither product code nor improvements coverage was changed on this follow-up.

Re-ran the warning-as-error build, format verification and all 1,025 fast
tests successfully. Re-ran all twelve unchanged semantic scenarios through a
fresh, health-checked ordinary host with CPython 3.12.13: 1,769 exchanges,
9,472 raw differences, six tolerated, and 8/27 raw passing exact AI cases.
The existing wrapper still reports 11/31 because it additionally groups four
method/slash cases and applies no improvements. These local raw results are
not represented as a new conductor-adjusted percentage.

Fresh diagnostics are under `dotnet\artifacts\ai-hard-stop-replay`; the host
was stopped. `HALT-routes_ai_agents.md` now records hard stop 1: supplying
the missing sibling implementations requires unowned changes, while copying
their calculations or changing fixed replay policy is forbidden. `no_halt`
and `replay` are therefore not claimed. The HALT document names the exact
integration and policy decisions required to resume; further identical
replay/register-only cycles are not implementation progress.
