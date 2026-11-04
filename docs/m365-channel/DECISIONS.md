# Microsoft 365 channel — decisions

One short entry per decision: context, choice, why.

## D-01 Integration branch is the worktree branch

- **Context.** The brief names `feat/m365-channel` as the integration branch.
  This session runs in a git worktree, and `feat/m365-channel` is checked out in
  the main checkout, which the session must not touch. Both branches point at
  the same commit.
- **Choice.** The worktree branch `jamesiford-m365-capability-layer` acts as the
  integration branch; `wp/CH-nn-*` branches are cut from and merged back into it.
- **Why.** Git refuses to check out one branch in two worktrees. The owner can
  fast-forward `feat/m365-channel` to this branch when ready; nothing is pushed.

## D-02 Python 3.14 for the local `.venv`

- **Context.** The brief prefers Python 3.12; only 3.13 (arm64) and 3.14 are
  installed here.
- **Choice.** `.venv` is built with `py -3.14`.
- **Why.** Newest available ≥ 3.12. CI and production stay on 3.12; no code in
  this work depends on a 3.13+ feature.

## D-03 Facts keep the producer's own types

- **Context.** `ToolResult.facts` must hold "canonical values". The existing
  queries return money as strings (claims layer), integers and floats (credit
  math, headcount), and nested dicts.
- **Choice.** Facts are exactly what the existing query or tool returned, in its
  own key order. Nothing is converted on the way in. `to_dict()` is the stable
  wire form (sorted keys, `Decimal` as its string, dates as ISO). The numeric
  guard canonicalises a fact with `Decimal(repr(value))` for floats and
  `Decimal(value)` for ints and numeric strings (`format.to_decimal`).
- **Why.** The portal narrator is handed `json.dumps(facts, indent=2)` and its
  prompt must stay byte-for-byte identical; converting at the boundary would
  change it. `repr` is the shortest round-tripping string, so `12.67` stays
  `12.67`.

## D-04 Test seams instead of edited tests

- **Context.** The existing suite patches `api.claims._client_book`,
  `_footprint`, `_priceable_states` and `api.claims.portfolio_v2`, and imports
  `_KINDS`, `_INSTANCE_CAP` and `_is_ambiguous` from `api.findings`. CH-01 moves
  that logic into `application/`.
- **Choice.** No existing test was edited (only `test_architecture.py` gained
  rules). `portfolio_page` takes its three external readers as parameters that
  default to the real ones, and `api.claims.portfolio_v2` passes its own
  module-level names; `book_rank` takes a `page_reader`, which `api.chat._book_brief`
  fills with the router function. `api.findings` re-exports the moved names.
- **Why.** The done-when says the existing chat, claims, scope and trend tests
  stay unchanged. The seams are small, named and covered by the equivalence tests.

## D-05 The portal's eligibility brief reads the pay-period average explicitly

- **Context.** `_pipeline_eligibility` called `chat_client_context` with no
  method, so it has always read `pay_period`; the scope's method selector never
  reached it. The channel's `client_eligibility` defaults to `min_max`.
- **Choice.** The chat passes `method="pay_period"` to the capability, with a
  comment. The capability honours `min_max` and `pay_period`, and maps `both` to
  `pay_period`.
- **Why.** "Chat output must not change." Whether the selector *should* reach
  this brief is a product question for the owner.

## D-06 Discovery scoping differs between the chat and the capability

- **Context.** `discover_credits` takes no client, so the chat's `discovery` and
  `multi_state` answers scan the configured default tenant even though the
  capability text says "for the selected client".
- **Choice.** `discover_credits` gained optional `account_id` and `tax_year`
  (default `None` = old behaviour). `client_discovery(client_id=...)` scopes by
  them; the chat passes no client, preserving its output.
- **Why.** Fixing the chat silently would change its answers on a live lakehouse
  that cannot be verified here. The channel must not read another client's
  payroll, so it scopes. Recommend the owner decide whether the chat should too.

## D-07 Situation facts include the client name; the narrator brief does not

- **Context.** The REST endpoint returns the situation plus `client_name`; the
  chat narrator has only ever received the query result.
- **Choice.** `client_situation(...).facts` equals the endpoint body. The chat
  pipeline drops `client_name` before building the narrator prompt.
- **Why.** Both promises hold: equivalence with the endpoint, and an unchanged
  narrator prompt.

## D-08 Employee-level tools are marked sensitive

- **Context.** The catalog marks `employee_drill` sensitive. `findings_list`
  (instance findings carry an employee id in `evidence`) and `client_at_risk`
  (the cohort rows carry employee ids) also return them.
- **Choice.** Both are `sensitive: true`, and their blocks name no employee.
- **Why.** Employee ids must not reach prompts or telemetry; the flag lets the
  gateway and orchestrator treat these results accordingly.

## D-09 `on_run` hook on the chat tools

- **Context.** Provenance needs the run a figure was read from, but adding a key
  to `chat_client_trend` / `chat_jobs_at_risk` / `chat_client_context` would
  change the JSON the narrators receive.
- **Choice.** Each takes an optional `on_run` callback, called with the Gold run
  row. `_support.RunCapture` collects it.
- **Why.** No extra Gold read, no change to any brief.

## D-10 Two simulate functions

- **Context.** The chat's what-if is the straight-line prototype
  (`tools.simulation.simulate_hiring`, city and count, default tenant). The
  catalog's `simulate` is the location what-if (`SimulateUnitQuery`).
- **Choice.** `simulate` is the location what-if; `simulate_headcount` wraps the
  chat tool and carries a warning that it is not client-scoped.
- **Why.** One function cannot honestly serve both; the catalog name stays the
  client-grade one.

## D-11 One statute-refusal mapping

- **Context.** `ClientRunNotAvailable` means either "statute not authored" or
  "no run holds this".
- **Choice.** `_support.refusal` maps messages naming a rule pack, an unmapped
  state or ADR-005 to `YearNotAuthored` and the rest to `NotCalculated`.
  `_support.statute` resolves statute and raises `YearNotAuthored` outright.
- **Why.** The queries carry the distinction only in the message; changing their
  exception types is outside CH-01.

## D-12 Writes are declared as prepare/commit pairs

- **Context.** DESIGN-AND-PLAN §5 lists seven write tools; §5's safety rules make
  each two steps.
- **Choice.** The catalog declares `<tool>_prepare` (`write_prepare`) and
  `<tool>_commit` (`write_commit`) for each, all `implemented: false`, plus
  `verify_figures`.
- **Why.** The audit schema and orchestrator can name them now; CH-05 builds them.

## D-13 Findings code moved verbatim, dead branch dropped

- **Context.** `api/findings.findings` held a `continue` followed by an
  unreachable block.
- **Choice.** The move kept every reachable line and dropped the unreachable one.
- **Why.** Pure move; behaviour identical, and the equivalence test compares the
  endpoint to the capability on the synthetic payroll.

## D-14 The guard imports the formatter; both are stdlib-only

- **Context.** CH-02 allows either a fully self-contained guard or one that
  imports `format.py`.
- **Choice.** `numeric_guard.py` imports `application.capabilities.format` (itself
  stdlib-only); `composer.py` imports the guard, the formatter and
  `capabilities/envelope.py` (also stdlib-only). Tests assert each file's imports,
  and the architecture test now also holds `envelope.py` to stdlib-only.
- **Why.** The guard must accept exactly the spellings the formatter emits; one
  source for both cannot drift. All five files are vendored together.

## D-15 Guard and composer are functions, not `ChatMiddleware`

- **Context.** ADR-004 §3 names a `NumericIntegrityMiddleware`; MAF workflows are
  not built.
- **Choice.** `check` / `check_raw` and `compose` are plain functions the hosted
  orchestrator calls in code. ADR-008 records this.
- **Why.** Middleware needs the MAF runtime this work package does not build.
  Wrapping them later changes the call site, not the check.

## D-16 Strictness choices in the guard

- **Non-ASCII digits** (full-width, Arabic-Indic, vulgar fractions) and a figure
  split by a thin or no-break space are **rejected**, not normalised.
- **A narrator's raw digit is rejected even when it equals a fact.** Only the
  reader's own numerals and structural digits pass the pre-substitution gate.
- **Structural allow-list** is narrow: a list marker (up to 99) at the start of a
  line, `step N` (up to 20), and ordinals up to the tenth.
- **Percentages** are accepted only for a fact a placeholder has declared a ratio
  or percentage (`|percent`, `|percent_points`, or a `_pct` name).
- **Digits inside a string fact** (a citation, a date, an engine note) are the
  engine's own words and are accepted in the final text; the raw gate is what stops
  a model using that door.
- **Why.** Each is the strict direction ADR-004 asks for: a rejected sentence is an
  inconvenience, a wrong figure on a return is not.

## D-17 `compose` degrades; `substitute` raises

- **Context.** CH-02 says an unknown placeholder or formatter raises
  `PlaceholderError`, and that a failed check returns the blocks alone.
- **Choice.** `substitute` raises. `compose` catches it, records a `placeholder`
  violation and returns the blocks alone (`guard.status == "rejected"`).
- **Why.** A channel reply must still be produced when a model invents a path.
  Placeholders inside a fenced code block are refused for the same reason: the
  formatting of a figure cannot be trusted there.

## D-18 The roster test is updated; the Workbench route does not exist

- **Context.** `test_rules_ingestion.py` pins the agent roster at eleven.
  CH-02 asks that `/api/agents` still return a valid profile.
- **Choice.** The pinned count became twelve, with a comment naming
  `ChannelNarratorAgent` (the only existing test edit in CH-02). There is no
  `/api/agents` route in this repository (it was removed; `test_api_ga_pass.py`
  says so), so the profile is validated by the existing agent-module contract tests
  plus `test_channel_narrator.py`, which also checks it serialises to JSON.
- **Why.** The count is a deliberate gate; adding an agent is meant to need this
  edit. Creating a route to satisfy a sentence would add to the pinned API surface.

## D-19 The narrator is never shown a value

- **Choice.** `composer.narrator_brief` lists fact paths with a format hint and no
  values; the narrator's instructions contain no digit.
- **Why.** A model that has not seen a figure cannot copy it as a digit, so the
  guarantee does not rest on the model obeying an instruction.

## D-20 Reads write one `single` audit event; writes write `begin` + `end`

- **Choice.** A read is one row (`phase = single`). A write is `begin` (outcome
  `pending`) then `end`. `collapse()` reports a `begin` with no `end` as `pending`.
- **Why.** A crash between begin and end must still leave evidence that a write was
  attempted. Doubling every read would add cost and no information.

## D-21 The opening audit event fails closed

- **Choice.** If the `begin`/`single` event cannot be written the call is blocked.
  A failure on the closing event is logged, not raised.
- **Why.** An unaudited action must not happen; once the action has happened,
  raising would misreport it as failed.

## D-22 `CHANNEL_STORE` defaults by deployment, with no Terraform change

- **Choice.** `store_choice("CHANNEL_STORE")` is `sqlite` locally and `warehouse` when
  `ENVIRONMENT` is not `local`; an explicit `sqlite`/`memory` when deployed is refused.
- **Why.** Keeps the existing deployment tests and `infra/` untouched while the
  durable store is still the only one a deployed process can use. Setting it
  explicitly in Terraform is a later, owner-approved infra change.

## D-23 Migrations keep `NOT ENFORCED` primary keys

- **Choice.** `0001` declares PKs `NOT ENFORCED`, as the bootstrap DDL does. The
  SQL Server runner path strips it as `generate_variants.py` does; `channel_user`
  declares no PK.
- **Why.** Fabric Warehouse only accepts non-enforced constraints.

## D-24 Channel tables are reached through named tenant exemptions

- **Choice.** `warehouse_channel*.py` declare module-level `tenant_exempt(...)`
  objects with reasons; `test_architecture.py` pins the exact reason set, limits
  those modules to the four channel tables and forbids other adapters reusing them.
- **Why.** The audit trail spans clients by nature, so `TenantScopedQuery` does not
  fit; the exemption is explicit and enforced rather than a bypass.

## D-25 Two token shapes, never mixed; the gateway is an agent principal

- **Choice.** A delegated token (`scp` ∋ `user_impersonation`, role `TCC.User`) is a
  `user`. An app-only token (no `scp`; `idtyp=app`, or `sub == oid` with no user
  name) with role `TCC.Agent` is an `agent`. A token showing both shapes, or the
  other shape's role, is a 403.
- **Why.** Guessing which a half-and-half token means is how a service acquires a
  person's rights.

## D-26 An agent must name its user on every request; users cannot

- **Choice.** `X-TCC-Acting-User` (base64url JSON) is parsed only for agent
  principals and is required on every route except `/api/health` and `/api/ready`
  (400 when absent, malformed, oversized, a non-GUID `oid` or a foreign `tid`).
  From a signed-in person it is ignored with a warning.
- **Why.** A read with no named user cannot be audited per user, and a header a
  person can set is impersonation.

## D-27 Authorization runs first, refuses when it cannot decide, and checks authorship

- **Choice.** `Authorization → Validation → Handler → Audit`. A command declaring a
  policy on a mediator with no authorizer is refused. For an agent, the command's
  `actor` must equal the acting user's actor. The caller is the `principal`
  argument, else the ambient principal the API guard set for the request.
- **Why.** A control that silently does not run is the failure this stage exists to
  prevent; an author mismatch means code built the command without the principal.
  The ambient principal means a router that forgets to pass one cannot demote an
  agent to anonymous. `_scope_tenant` stays absent.

## D-28 Entitlement is by person; users are exempt unless enforced

- **Choice.** Writer entitlement is checked against the acting user's oid, never the
  gateway's. Signed-in people and the anonymous local caller keep writing unless
  `CHANNEL_ENFORCE_WRITER_FOR_USERS=true`. `CHANNEL_WRITER_SOURCE` is `allowlist`
  (default) | `entra_group` | `either`; every source fails closed and an unknown
  value raises.
- **Why.** Shipping the channel must not lock out the portal's existing users.

## D-29 Person-only write routes are refused to the agent

- **Choice.** `AGENT_FORBIDDEN_WRITES` in `api/auth.py` lists eight state-changing
  routes that do not go through a writer-gated command (QC resolve, employee review,
  rule verify, rule apply, workspace refresh and comparison stage, calculation run,
  claims assess). A test checks each pattern still matches a real route.
- **Why.** An agent token would otherwise reach them with no entitlement check.
  Prompt 3 may re-open any of them behind a command.

## D-30 Existing tests and docs changed deliberately in CH-04

- `test_mediator.py::test_the_pipeline_does_not_claim_stages_it_does_not_have` now
  asserts `_authorize` IS a stage (and `_scope_tenant` still is not), because an
  identity to authorize now exists. ADR-003, `.github/copilot-instructions.md`
  ("That is the whole pipeline") and the mediator docstring were rewritten to match.
- `test_auth.py::test_me_returns_the_callers_identity` gained `principal_type` and
  `acting_for` (additive fields on `/api/me`).
- Routers `ingestion`, `onezero` and `rules` now attribute through `attributed()`;
  `PUT /api/claims/engagement` records `set_by`/`set_at`. Unauthenticated behaviour
  is unchanged.

## D-31 Writes are prepare/commit, bound to person, tool and arguments

- **Choice.** `application/confirmations.py`: a token (256-bit, only its SHA-256 stored)
  is bound to the acting user's oid, the base tool name and the SHA-256 of the
  arguments; single use by atomic `consume`; TTL `CHANNEL_CONFIRM_TTL_SECONDS`
  (default 600, 30–3600). Commit re-supplies the arguments, so the commit schema
  gained an `arguments` property (the declared schema had only token and key).
- **Why.** The person agrees to what they were shown; a token for a different
  person, tool or change is refused with a distinct error (unknown, expired,
  replayed, wrong_user, wrong_tool, wrong_args, idempotency_conflict).

## D-32 A retry replays; a consumed token with no recorded result is refused

- **Choice.** Same idempotency key + same confirmation replays the stored result.
  If the process died between consuming and recording, or the write failed, the
  retry is refused as replayed and a fresh prepare is needed.
- **Why.** The safe failure is "do it again on purpose", never a second write.

## D-33 Prepare is audited, authorised first, and previews are derived, not duplicated

- **Choice.** Prepare and commit each run inside the channel auditor
  (`write_prepare`, `write_commit`); a non-writer is refused before anything is
  read. Each preview comes from the command's own pure function (`build_claim`,
  `next_claim`, `plan_base_year`, the rebase query), so preview and row cannot drift.
- **Why.** A write cannot happen unaudited, and a preview that disagreed with the
  commit would be a figure nobody can vouch for.

## D-34 The channel can only record an unverified claim

- **Choice.** `claim_record` fixes provenance to `client_asserted` and takes no
  provenance argument. `claim_package_create` stays unimplemented (Prompt 3).
- **Why.** A claim typed into a chat is somebody's word, never a filing; the
  platform's own rule is that a band is never derived from an unverified claim.

## D-35 Claims and engagement writes moved behind the mediator

- **Choice.** `RecordClaimCommand`, `TransitionClaimCommand`, `SetEngagementCommand`
  (all `Policy.WRITER`) replace the logic in `api/claims.py`; the routers are thin
  and their existing tests pass unedited. `plan_base_year` was extracted from
  `handle_set_base_year` so a preview and the commit share the same checks.
- **Existing tests edited.** `test_capabilities_envelope.py` (six of seven write
  pairs are now built; only the package build remains unbuilt) and
  `test_capabilities_equivalence.py` (the unbuilt-tool probe uses
  `claim_package_create_commit`).

## D-36 AI-01: SDK pins, Python version, and the breaking changes read

- **Choice.** `agent-framework-foundry` 1.7.0 → **1.16.0** (newest stable; pulls
  `agent-framework-core` 1.24.0 and `agent-framework-openai` 1.18.0),
  `azure-ai-projects` 2.1.0 → **2.7.0** (newest 1.16.0 accepts, `<2.8.0`; 2.10.0
  exists but the framework would refuse it), `azure-identity` 1.25.3 → 1.27.0,
  `azure-monitor-opentelemetry` 1.8.8 → 1.8.11. `httpx` 0.28.1 is already latest.
  `azure-ai-agentserver-responses` (2.4.0) is NOT added: it belongs to the
  orchestrator's requirements (Prompt 4).
- **Python.** `py -3.12` is not installed here; the suite ran on 3.14 (D-02). Nothing
  introduced needs more than 3.12 features.
- **Breaking items read** (Learn "Python 2026 significant changes", updated
  2026-10-26, and the 1.7 → 1.23 entries): MCP SDK 2.x lifecycle (1.23), AG-UI
  authorization ownership (1.23), `Content` metadata and stream merge modes (1.22),
  middleware must be a sequence (1.17), `SecretString` no longer a `str` (1.18),
  Responses/Invocations hosting changes (1.20), Lab installs separately (1.18).
  None touches what this product calls — a `FoundryAgent` built from
  `project_endpoint`/`agent_name`/`agent_version`/`credential` and streamed with
  `run(prompt, stream=True)` — so the code needed **no migration**. We use no MCP,
  AG-UI, middleware or persisted sessions, so the persisted-state warning does not
  apply. Sources: <https://learn.microsoft.com/en-us/agent-framework/support/upgrade/python-2026-significant-changes>.
- **Guard.** `tests/test_ai_sdk_surface.py` pins the symbols the adapters use;
  `scripts/check-sdk-versions.py` prints pinned vs latest (offline-safe).
- **Why.** A bump should fail on a named symbol in CI, not at runtime.

## D-37 AI-02: the provider unit is an `AgentRuntime`; `ChatModel` sits beneath it

- **Choice.** Providers implement `AgentRuntime` ("stream this agent's answer to this
  prompt", plus `ready_for`, `version_of`, `status`). A Foundry prompt agent is one;
  an OpenAI-compatible endpoint is wrapped by a `ChatModelAgentRuntime` (AI-03).
  `ChatModel` is the port under that wrapper. Resilience decorators (AI-04) wrap
  `AgentRuntime`, which covers both — the prompt says "over `ChatModel`/`AgentRuntime`".
- **Why.** The pipelines need agent semantics (instructions, versions), not raw
  completions; one decorated type avoids writing every decorator twice.
- **Provider chain.** `ProviderChain` skips a provider that is not ready, falls through
  on a failure BEFORE output, and does not splice after output; it records every hop in
  the final `StreamEnd`. Providers are added with `ProviderRegistry.register(name, factory)`.

## D-38 AI-02: `StreamingQuery` and `Mediator.stream`

- **Choice.** `StreamingQuery(Query)` dispatches through `Mediator.stream()`, sharing
  `_prepare` (lookup, authorization, validation) with `send`. `send` on a streaming
  query and `stream` on anything else raise `TypeError`. `AuditLog` and `AuditRecord`
  moved to `application/mediator_audit.py` and are re-exported, so `mediator.py` stays
  under the module-size limit and every import path still works.
- **Why.** A streaming read must not be a side door around the pipeline.

## D-39 AI-02: `api/chat.py` became the `api/chat/` package (1094 → ten modules ≤ 191 lines)

- **Choice.** By responsibility: `models`, `sse`, `scope`, `routing`, `narration`,
  `pipelines_core`, `pipelines_briefs`, `pipelines_whatif`, `dispatch`, `__init__`
  (router, endpoint, re-exports). Every name tests imported is re-exported.
  Pipelines no longer carry a `registry` argument; they call `_stream_agent(name, prompt)`.
- **Existing tests edited (module layout, not behaviour):** `test_chat_scope.py` patches
  `api.chat.scope` (where `_chat_clients`/`_candidate_year` are looked up);
  `test_channel_audit.py` drives `_stream_agent` through a real `FoundryAgentRuntime`
  over a fake agent and patches `api.chat.narration`;
  `test_architecture.py::test_chat_pipelines_call_capabilities_not_tools` now reads every
  module of the package (stricter, not weaker); `test_page_summary.py` installs a fake
  provider instead of an `app.state.registry`.
- **Behaviour note.** The scripted-stream status note now reads "No model is available;
  scripted stream." (was "Foundry not configured; …"): a gateway-only deployment is not a
  Foundry deployment. No test or frontend reads it.

## D-40 AI-02: agents declare an `AgentSpec`; prompts are files

- **Choice.** Each agent module exports `NAME`, `INSTRUCTIONS`, `AGENT_PROFILE`, `SPEC`
  and no `build()`. `agents/factory.py` yields `all_specs()` and imports no SDK. The
  instruction text moved byte for byte to `agents/prompts/<module>.md` (front matter:
  version, owner, changelog), loaded by `FilePromptStore`, so existing published Foundry
  versions are still reused (identical definition). Roles: Orchestrator = router;
  RulesIngestion, LegislativeMonitor, ExceptionReport = analysis; the rest = narrator.
- **Existing tests edited:** `test_agent_modules.py` (the `build()` signature and
  `build_all` KeyError tests pinned SDK wiring; replaced by spec/roster checks) and
  `test_channel_narrator.py` (`SPEC` instead of `callable(build)`).

## D-41 AI-02: warm in the background; health reports AI, readiness never fails on it

- **Choice.** `FoundryAgentCatalog.warm()` publishes on a daemon thread with backoff
  (2, 4, 8 … ≤ 30 s). Startup validates settings (a bad configuration stops startup)
  but never waits on Foundry. `/api/health` keeps `foundry_configured` and
  `agents_registered` and adds an `ai` object (provider states, no secrets);
  `/api/ready` adds `ai` and its `ready` value is unchanged by a model being down.
- **Why.** The engine answers without a model. A `conftest` autouse fixture
  (`reset_ai_wiring`) clears the cached composition between tests.

## D-42 AI-03: the gateway is a provider, not a second pipeline

- **Choice.** An OpenAI-compatible `ChatModel` is wrapped by `ChatModelAgentRuntime`
  into the same `AgentRuntime` unit Foundry uses, registered as `gateway`. It joins
  the provider chain like any other; nothing in `api/` knows it exists. Tool-call
  events from a model are dropped — agents hold no tools (ADR-004).
- **Why.** One chain, one failure taxonomy, one place to add resilience.

## D-43 AI-03: no default gateway auth; secrets only as Key Vault references

- **Choice.** `AI_GATEWAY_AUTH` has no default (`api_key`, `oauth_client_credentials`,
  `entra_token`, `none`). A deployed process refuses to start with TLS verification
  off or auth `none`. Terraform emits `AI_GATEWAY_API_KEY` /
  `AI_GATEWAY_OAUTH_CLIENT_SECRET` only as `@Microsoft.KeyVault(...)` references and
  only with `enable_key_vault`; the secret must already exist in the vault.
- **Why.** The customer's scheme is unknown; guessing one would be an invented control.

## D-44 AI-03: egress invariant for external providers

- **Choice.** Providers in `EXTERNAL_PROVIDERS` (`gateway`, `foundry_connection`) are
  wrapped in `GuardedRuntime`: a prompt containing a record token, SSN shape or an
  employee-identifier JSON key is refused (`EgressRefused`, never echoing the match).
  `AI_EGRESS_POLICY` is the lever (`allow_all` | `aggregates_only` | `block`).
- **Why.** Narration briefs already carry aggregates only; the guard makes that a
  checked property when the model is outside the tenant.

## D-45 AI-03: mock gateway and connection script are manual-deploy aids

- **Choice.** Terraform creates only the empty mock App Service (non-enterprise,
  tagged `purpose=poc-mock`); the script is copied to it by hand. The
  `create-model-connection.ps1` Bicep parameter names (`apiKey` …) are a best guess
  and the script has not been run against Azure.
- **Why.** No cloud-changing commands are permitted in this run; flagged as an open
  owner question.

## D-46 AI-04: one resilience stack for every provider, in a fixed order

- **Choice.** `ai_wiring._decorate` wraps each provider as egress → budget →
  bulkhead → breaker → retry → timeout → call. The decorators are in
  `infrastructure/ai/resilience/`, share a `RuntimeDecorator` base and take a `Clock`.
- **Why.** The order carries the semantics: bulkhead outside the breaker so shedding
  load is not a provider failure; breaker outside retry so one retried request is one
  failure. Adding a provider adds no resilience code. Timeouts are a gap between
  events, not a cap on the call, so a long healthy narration is not cut off.
  Retry happens only before text and only for retryable errors.

## D-47 AI-04: an open breaker does not change readiness or the stub rule

- **Choice.** An open breaker makes `stream` fail at once and reports the provider
  `unavailable` in `/api/health`; `ready_for` is unchanged and `/api/ready` never
  depends on AI.
- **Why.** Making an open breaker "not ready" would send the chat to the scripted
  stub stream mid-outage, which shows invented figures. The chain moves on or the
  reader gets the engine's figures.

## D-48 AI-04: degradation is the engine's figures, once-per-request sentence

- **Choice.** `_stream_agent(degrade=True)` turns `NarrationUnavailable` into
  "The assistant is unavailable; here are the engine's figures." plus the brief's JSON
  flattened to `name: value` lines (≤30). After text, a failure appends the
  interrupted sentence and the figures. The sentence is said once per request
  (flag in `_TELEMETRY_CONTEXT`). A cancelled stream is audited as not-ok and the
  cancellation re-raised. The page summary passes `degrade=False` and keeps its
  `[Agent failed` marker and facts fallback.
- **Why.** Nothing is computed by the fallback; it restates what the engine produced.

## D-49 AI-04: in-memory token budget, per process

- **Choice.** `InMemoryTokenBudget`: daily UTC buckets, overall and per principal
  (object id, or `anonymous`), checked before and charged after the call, estimated
  at 4 chars/token and marked estimated when the provider reports no usage. One
  instance is shared by all providers. Not shared across workers.
- **Why.** A guard rail needs no store. A shared store is the follow-up if a
  customer needs exact accounting.

## D-50 AI-04: tests run on an instant clock

- **Choice.** `conftest` installs `InstantClock` (real timeouts, instant sleep) via
  `wiring.set_ai_clock`. The two `test_ai_fallthrough` cases that injected a single
  fault now inject three, because a single 503/429 is now retried and recovers —
  which is new, tested behaviour.

## D-51 AI-06: telemetry is shape only, through an allow-list

- **Choice.** `OtelTelemetry` (GenAI semantic conventions: span `chat`, the
  `gen_ai.client.operation.duration` and `.token.usage` histograms) sits behind the
  `AiTelemetry` port; `ObservedRuntime` is the outermost decorator so egress,
  budget and breaker refusals are observed too. Span attributes pass an allow-list
  (`ALLOWED_EXTRA`); counters accept only `provider`/`scope`/`agent`. Errors are
  recorded by exception class, never message. No prompt, reply, identifier or hash.
- **Why.** A prompt carries engine figures and a reply can quote them; an
  allow-list means a future keyword cannot widen what leaves. `test_ai_telemetry.py`
  plants sentinels everywhere and searches every exported attribute.

## D-52 AI-06: prompt manifest records a hash per version

- **Choice.** `agents/prompts/manifest.json` holds `{name: {versions: {N: sha256}}}`.
  A test fails if text changes under the same version, a version is unrecorded, a
  version goes backwards, a changelog line is missing, or a file/entry is orphaned.
  `scripts/prompt-manifest.py --refresh` never overwrites a recorded version.
- **Why.** The edit-then-refresh shortcut is the failure to prevent; refusing to
  rewrite a recorded hash makes the version bump unavoidable and reviewable.

## D-53 AI-06: evals share datasets across offline and live modes

- **Choice.** `backend/tests/ai_evals/` (routing / narration / refusal jsonl,
  `thresholds.json`), marker `ai_eval` on by default. Offline scores the
  deterministic paths at 1.0; `TCC_AI_EVALS_LIVE=1` runs the configured providers
  against looser thresholds. `scripts/ai-eval.py` prints a table and exits non-zero
  below threshold. Datasets were written from the question's intent, not from the
  router's output.
- **Why.** A regression becomes a failing number; live mode is opt-in because CI has
  no model (same rule as the live-Fabric tests).
- **Removed.** `application/ai/telemetry_null.py` (added in AI-04, never used once
  the OTel adapter, which is a no-op without an SDK, became the default).

## D-54 AI-07: the injection screen refuses to SEND; it does not rewrite

- **Choice.** `PromptInjectionGuard` runs in `NarrationService` (every model call
  passes it). On a hit it raises `PromptInjectionBlocked(rules)`: no provider is
  called, the portal shows the engine's figures with a sentence saying why, and the
  router's existing exception path falls back to keyword routing. Rule NAMES are
  logged and counted (`ai.injection_blocked`), never the text. Well-formed
  `UntrustedText` fences are unwrapped before scanning so the product's own wrapper
  is not an attack; a stray marker is `fence_spoof`.
- **Why.** Rewriting or "neutralising" attacker text invites a second bypass; not
  calling the model is simple and safe because the engine answers without one. A
  false positive costs prose, never an answer, which is what lets the rules be strict.
- **Also.** Every pipeline now sends the reader's question through
  `UntrustedText.fenced()`; `defang` breaks `<<<`, `>>>` and `JSON:` so a question
  cannot forge a fence or plant a second figures block (the degraded answer reads
  the LAST `JSON:`). The routing prompt labels assistant turns `copilot:` because a
  line starting `assistant:` is what a forged turn looks like.

## D-55 AI-07: the output policy is stdlib-only so the composer can vendor it

- **Choice.** Rules live in `application/output_policy.py` (stdlib only, like
  `numeric_guard`); `RuleOutputPolicy` adapts them to the port. `compose` applies
  them to the narration after substitution and drops it like a bad figure
  (`allowed_hosts` parameter; default none). Codes only, never text.
- **Existing test touched.** `test_composer.py` import allow-list gains
  `application.output_policy` (the composer is vendored, so its imports are pinned).

## D-56 AI-07: portal prose is gated as it streams, at word boundaries

- **Choice.** `OutputGate` holds text after the last whitespace and reviews
  everything that would be released, whole, before releasing it; once a rule fires
  nothing further is released and the reader gets the withheld sentence plus the
  engine's figures. `_stream_agent` was split (`_Run`, `_frames`, `_withheld`).
- **Why.** Tokens are shown as they arrive, so the policy cannot wait for the end.
  Whitespace-delimited leaks (links, addresses) are held whole; a phone number can
  show its first digits before its last are stopped — stated in ADR-008/SECURITY.
- **Existing test touched.** `test_ai_degraded` cancellation case now yields text
  ending in a space (held text is not "shown").

## D-57 AI-07: both controls default ON; OFF is logged

- **Choice.** `AI_INJECTION_GUARD` / `AI_OUTPUT_POLICY` (`on`|`off`), and
  `AI_OUTPUT_ALLOWED_HOSTS`. A value other than on/off is a startup error.
- **Why.** A control silently off reads as on. `off` is a break-glass for a false
  positive in production while a rule is fixed.

## D-58 AI-08: a ratchet, not a retroactive standard

- **Choice.** `tests/code_standards_baseline.json` records every existing violation
  (module 250 / class 150 / function 40 / complexity 10 / args 7 / bare except /
  docstrings / exact duplicate bodies) with its magnitude; `test_code_standards.py`
  fails on a new or worse violation, and on an improved one until the baseline is
  tightened (`scripts/code-standards.py --update`, which refuses to loosen). A
  function that moves file unchanged is recognised as a move. Pure AST
  (`tools/code_standards/`). Tests, `data/` and `__pycache__` are not measured.
- **Baseline.** 540 violations at first measurement; 483 after the AI/channel code
  was brought up to standard. A test holds `application/ai`, `infrastructure/ai`,
  `domain/ai*`, `api/chat` (bar five moved pipeline functions) and the tooling to
  zero shape violations.
- **Why.** A standard nobody can meet on day one is ignored; a ratchet makes the
  direction of travel the rule.

## D-59 AI-08: splits keep every import path; vendoring is by package

- **Choice.** `numeric_guard` → `numeric_types`/`_extract`/`_context`/`_facts`;
  `composer` → `composer_placeholders`/`composer_render`; `capabilities/format` →
  `format_core`/`format_renderers`; `capabilities/client` → `client_eligibility`/
  `client_analysis`; `capabilities/catalog` → `catalog_types`/`catalog_intents`;
  `domain/ai` → `ai_errors`. Code moved verbatim (plus small extractions in
  `composer.compose`, `client_eligibility`, `client_trend`, `_stream_agent`,
  `decode_message`); the original modules re-export every public and test-used name.
  Documented in `ORCHESTRATOR.md` as vendored packages.
- **Existing tests touched, and why.** `test_numeric_guard` and `test_composer`
  (the import-purity checks now cover the sibling set, not one file),
  `test_architecture` (vendored-module rule: stdlib plus vendored siblings),
  `test_architecture_ai` (domain stdlib check includes `ai_errors`). No behavioural
  test was edited; the mutation tests over the guard pass unchanged.

## D-60 AI-05 deferred (stretch): conversation continuity is not started

- **Decision.** Not built. It needs, in one WP: migration `0003_conversation.sql`
  (`tcc_ops.conversation_turn`, Fabric constraints as in 0001), a SQLite and a
  Warehouse `ConversationStore` with contract tests, a deployed-store check in
  `application/deployment.py`, a Terraform setting and `terraform test` case, a purge
  job for `CONVERSATION_RETENTION_DAYS` (default 30), redaction before write, the
  server preferring its own history when `conversation_id` is supplied, and a new
  `suggestions` SSE event with frontend handling. That is a schema, an infra change and
  a UI change; the manual says to defer a stretch package rather than spend long, and
  the rest of Prompt 2B is complete and gated.
- **Ready to pick up.** The `ConversationStore` port already exists in
  `application/ai/ports.py`; the chat already sends history with each request
  (`ChatRequest.history`) and pins scope (`api/chat/scope.py`), so the server-side
  store replaces what the client sends, not a new concept. Follow `ConfirmationRepository`
  (`sqlite_channel_state.py` / `warehouse_channel_state.py`) for the adapter pair.
  Redact with the same rules as the egress invariant and the output policy; store
  rule codes, never matched text. Follow-up suggestions should be a pure function of
  the intents that ran (deterministic, no model).

## D-61 Prompt 3 runs on `feat/m365-channel` in the main checkout

- **Context.** Prompt 3 was started in the main checkout, on `main`. The previous prompts
  ran in a worktree on `jamesiford-m365-capability-layer` (D-01) and left
  `feat/m365-channel` at the same commit (`98462b0`), checked out nowhere.
- **Choice.** The checkout was clean, so it was switched to `feat/m365-channel` (the
  branch the brief names) and `wp/CH-06a-*`, `wp/CH-06b-*` and `wp/CH-07-*` are cut from
  it. D-01 no longer applies to this prompt: the fast-forward is not left to the owner.
- **Why.** The brief's own rule: be on `feat/m365-channel`, or on a branch containing it.

## D-62 Python 3.14 venv, seeded from the sibling venv

- **Choice.** `.venv` is built with `py -3.14` (D-02; 3.12 is not installed). Its
  site-packages were copied from the Prompt 2B worktree's venv rather than re-resolved,
  because installing `deltalake[pyarrow]` from source on 3.14 takes many minutes.
  `jsonschema==4.26.0` is the one new runtime pin (CH-06a).

## D-63 CH-06a: `verify_figures` and the package tickets

- **`verify_figures` is `implemented` but gateway-local.** The catalog test requires every
  implemented tool to have a registry function, so `application/capabilities/verify.py`
  holds the stateless guard call. The tool carries the tag `gateway-local`, and the API
  answers it `501 gateway_local`: only the gateway knows which results a conversation
  received, and an API answer with no facts would be a confident "every figure is wrong".
  `facts` is a keyword the gateway passes, not a schema property, so a caller cannot
  choose the facts it is checked against.
- **A ticket is a row in `channel_confirmation`.** `claim_package_link` mints a 256-bit
  token (hash only stored), bound to the person, valid 15 minutes, spent atomically by the
  internal tool `claim_package_redeem` (tag `internal`, never listed). The confirmation
  store was chosen because it is already "a secret handed out once, kept as a hash, spent
  atomically", is durable, and needs no grant the gateway lacks. The row's `result_json`
  carries the conversation context so the download can be audited as the right person.
- **A commit's body.** `args` may be the prepare's own arguments (the token and key beside
  them, at the top level of the body) or the catalog's full commit shape; the two may not
  disagree. Top-level token/key on a non-commit tool are ignored.
- **Timeouts.** A timed-out call returns `504 timeout` (retryable). The worker thread is
  not killed, so a timed-out COMMIT may still land; the retry carries the same idempotency
  key and replays instead of repeating.

## D-64 CH-06a: existing tests edited

- `test_capabilities_envelope.py` (the "unbuilt tools" pin is now "nothing is unbuilt"),
  `test_capabilities_equivalence.py` (an unbuilt tool cannot be called → an unknown name
  cannot) and `test_channel_writes.py` (seven write specs, not six; the package pair is
  built). Each asserted precisely the thing this work package changes.
- `application/wiring.py` is a baselined offender in the standards ratchet (605 lines);
  the three new lines were paid for by removing three elsewhere in the same file.
  (Superseded in CH-06b: the channel stores moved to `channel_wiring.py`, see D-66.)

## D-65 CH-06b: the MCP facade is a hand-written Streamable-HTTP subset

- **Context.** The brief prefers the official `mcp` SDK and allows a minimal JSON-RPC
  subset when the SDK cannot share the auth/audit pipeline cleanly. PyPI's current stable
  is `mcp 2.3.0` (Requires-Python >=3.10; it installs on 3.14 here, 3.12 is not
  installed). Its Streamable-HTTP server runs handlers in session-scoped tasks under a
  session manager with its own lifespan and a dual-era protocol loop, so the request's
  bearer token and acting user are not in the handler's context without reaching into SDK
  internals; it also pulls `httpx2`, `sse-starlette` and `mcp-types`.
- **Choice.** `channel/mcp.py` implements `initialize`, `notifications/*`, `ping`,
  `tools/list` and `tools/call` over `POST /mcp` (one JSON reply per request, session id
  in `Mcp-Session-Id`, `GET` 405, `DELETE` ends a session). Every `tools/call` goes
  through `ToolPipeline`, the same code as REST; a test compares the two trails event for
  event. The SDK is not a dependency (it stays out of `requirements.txt`).
- **Why.** An audited pipeline that a transport can bypass is not audited. The subset is
  about 150 lines, fully tested, and swappable for the SDK if a later version exposes
  per-request context.

## D-66 CH-06b: `channel_wiring` is split out of `application.wiring`

- **Choice.** The audit, writer, confirmation and entitlement getters moved to
  `application/channel_wiring.py`; `wiring.py` re-exports them, so no import path changed.
  `wiring.py` fell from 605 to 471 lines and the ratchet baseline was tightened.
- **Why.** `wiring` imports every query and command. A gateway composing through it would
  load the engine to write an audit row. `test_importing_the_gateway_does_not_load_the_engine`
  proves the gateway's imports stay light.

## D-67 CH-06b: what the gateway audits, and what it cannot

- A **read** is a `begin` and an `end` event (the brief's wording). The API's own read
  capabilities write nothing, so the gateway is the only record of a read.
- A **write** success adds no gateway event; the capability's own begin/end pair is the
  record. The gateway adds one `single` event only for failures the capability never saw
  (`BEFORE_CAPABILITY` in `channel/pipeline.py`): rate limit, its own writer check, API
  unreachable or timed out, an API-guard refusal, or a pre-dispatch rejection. To make
  that decidable the API's client-entitlement refusal has its own code,
  `client_not_authorized`, distinct from the capability's `not_authorized`.
- **Not audited:** a request that fails before there is a person (no/invalid token, bad
  acting headers) and a request for a tool that does not exist. There is no user to
  attribute them to and an arbitrary tool name does not belong in a column; they are a
  response and a log line without the token.
- `verify_figures` is audited as a read and its `numeric_guard` column carries the
  verdict (`pass` / `rejected`); every other tool records `n/a`, because the orchestrator
  owns the guard on its own prose.
- If the opening event of a read cannot be written, nothing is called (`503
  audit_unavailable`). A refusal whose event cannot be written still refuses.

## D-68 CH-06b: download tickets

- The ticket is minted by the API (`claim_package_link`), spent by the API
  (`claim_package_redeem`), and the gateway's `GET /channel/v1/downloads/{ticket}` does the
  two-step. When it spends the ticket nobody has been identified, so the redeem call acts
  for the nil GUID user `00000000-0000-0000-0000-000000000000`, named "download ticket";
  the ticket row says whose it is, and the artifact fetch and the audit event are made as
  that person, with the channel and conversation recorded at mint time.
- A presented token is optional and, when present, is checked against the ticket's person
  BEFORE the ticket is spent. Unauthenticated attempts are rate-limited per client address
  (`download:<ip>` bucket in the same limiter).
- Tickets are durable (the confirmation store), so a gateway restart does not strand a
  link. The fact ledger and the rate limiter are not: they are per process, `WEB_CONCURRENCY`
  defaults to 1, and a restart makes `verify_figures` answer "no" for earlier results.

## D-69 CH-06b: the ledger records less than everything

- Not recorded: `verify_figures` and `channel_ping` results (positions and counts are not
  the engine's), `claim_package_link`/`redeem` (a ticket is a secret with digits in it),
  and the `confirmation` object of a write preview (a token's digits are not a licence to
  quote digits). The preview's own figures ARE recorded: they are what the user is
  shown and the orchestrator narrates.
- A delegated caller with no MCP session and no `X-Conversation-Id` is keyed by their
  user id, so one person's calls without a conversation share a ledger entry.

## D-70 CH-07: the channel module, and what "off" means

- **Choice.** `infra/modules/channel` creates, only when `enable_m365_channel`: one
  user-assigned identity, one Linux web app on the existing plan (Python 3.12, `sh
  startup-channel.sh`, same integration subnet, HTTPS only, TLS 1.2, FTPS and basic-auth
  publishing off, `vnet_route_all_enabled`, inbound public, `Allow` unless
  `channel_allowed_ip_ranges`), the Monitoring Metrics Publisher role and a diagnostic
  setting. Everything is `count = 0` when off.
- **Proof of "strict no-op".** A real `terraform plan` needs Azure credentials and a
  subscription, and the brief forbids cloud changes in this prompt, so it was not run.
  The proof is structural and tested: the module's resource list is empty (`resource_types`),
  its outputs are empty, no existing module's inputs changed (the only edit to
  `app_service` is a new read-only OUTPUT), and the 30 existing Terraform tests pass
  unedited. The first plan against a real subscription should be reviewed for exactly
  that: no change with the toggle off.
- **No new API setting.** The API accepts the gateway because the token carries `TCC.Agent`
  (`infrastructure/auth/entra.py`); adding a caller list would be a second control.
  A test asserts the API's settings gain nothing channel-shaped, and that
  `api_access_restriction` is identical on and off: default deny, `web-app-subnet` only.

## D-71 CH-07: refusals and where they live

- The enterprise profile refuses the toggle (variable validation), as the mock gateway
  does: the gateway is a public surface and the design says "public profile only for the PoC".
- The channel needs the API to validate tokens; the public profile defaults to
  `AUTH_MODE=none`. That check is a `precondition` on the root output `CHANNEL_APP_NAME`
  rather than on the module's app: `terraform test` can only expect a failure from a
  variable, output, check or root-addressable resource, and a module resource is none of
  those. The message says what to set.
- Lists (`channel_allowed_caller_app_ids`, `channel_allowed_ip_ranges`) are overlay-only:
  azd's `${NAME=default}` substitution produces strings. The four scalar variables are
  mapped, and `test_deployment_docs_contract` forced them into the handover.

## D-72 CH-07: azd and CI

- `azure.yaml` lists the `channel` service as the brief asks. **Consequence the owner must
  know:** azd resolves a service to an app by its `azd-service-name` tag, so with the channel
  OFF there is no app and a bare `azd deploy` / `azd up` reports "unable to find a resource
  tagged azd-service-name: channel". The handover and `azure.yaml` say to deploy by name
  (`azd deploy api`, `azd deploy web`) with the channel off. No azd feature to skip a service
  was found; if one exists it is a one-line change.
- `deploy.yml` triggers are untouched (still `workflow_dispatch` only, asserted). Its steps
  gained: two more outputs read, a gateway grant and a channel zip deploy, each conditional on
  the output being non-empty, so a deployment without the channel runs exactly the old steps.
- `scripts/package-app.py` is not service-aware (it zips a folder), so the channel zip is
  the same `backend/` zip; a test proves it carries `startup-channel.sh` and `channel/`.
- `startup-channel.sh` is checked out with LF (`.gitattributes` `*.sh text eol=lf`) and a test
  fails on a carriage return: a CRLF `set -e` fails on App Service.


## D-73 CH-07b: the gateway is deployed by a hook, not an azd service

- **Context.** Prompt 3 (D-72) listed a `channel` service in `azure.yaml`. azd resolves a
  service by its `azd-service-name` tag and cannot make one conditional, so with
  `enable_m365_channel = false` every default `azd up` / `azd deploy` failed. A review
  found it.
- **Choice.** `azure.yaml` services are `api` and `web` again. `scripts/deploy-channel.ps1`
  (`-WhatIf` supported) runs from a project-level `postdeploy` hook and from `deploy.yml`'s
  conditional step. It exits 0 with one quiet line unless `TCC_ENABLE_M365_CHANNEL=true`;
  otherwise it packages `backend/` with `scripts/package-app.py` and runs `az webapp deploy`
  for `CHANNEL_APP_NAME`/`AZURE_RESOURCE_GROUP` (the Terraform outputs). The gateway app no
  longer carries an `azd-service-name` tag, since azd has nothing to match it to.
- **Why.** The default command must be what it was. The hook needs the toggle in the azd
  environment as well as the Terraform variable; both are documented in the handover.
- **Edited assertions.** `test_channel_infra.py`: `test_azd_knows_the_channel_service_and_the_others_are_unchanged`
  became `test_azd_has_exactly_the_api_and_web_services_so_a_default_azd_up_is_unchanged`;
  `test_the_azd_service_name_tag_the_module_sets_matches_the_service` became
  `test_the_module_starts_the_gateway_with_its_own_script` plus a no-`channel`-tag/hook
  check. `infra/tests/channel.tftest.hcl`: the `azd-service-name == "channel"` assertion now
  asserts the tag is absent. `test_channel_deploy_hook.py` (new) runs the script against a
  stubbed `az`.
- **jsonschema.** `backend/requirements.txt` is the only requirements file and the only
  install step (`deploy.yml`, `ci.yml` use it), and already pins `jsonschema`. The channel
  zip is the `backend/` zip, which includes `channel/` and `startup-channel.sh` (tested).

## D-74 CH-08: a separate deployable, and what it shares by copying

- **Context.** The orchestrator is a Foundry hosted agent, not an App Service app, and must not import
  `backend/`. It still has to apply the very same numeric guard, composer, formatter, catalog and
  model adapters as the portal; a second implementation of the guard is the thing the design forbids.
- **Choice.** `scripts/vendor-orchestrator.py` copies the shared modules verbatim into
  `channel_orchestrator/app/vendor/tcc_shared/` with a SHA-256 manifest. The set is COMPUTED from a seed
  list by following imports, and the script fails if the closure leaves `application`, `domain` and
  `infrastructure.ai`, or imports a third-party package outside `httpx`/`azure` in the model-access
  adapters. 40 files today. The directory is gitignored (a generated copy would drift); `--check`
  verifies it, the script is idempotent, and `app/__init__.py` APPENDS it to `sys.path` so that in the
  backend's own test run the real packages win (a prepended copy would shadow `infrastructure`).
- **Extracted for sharing.** `application/chat_keywords.py` (the keyword table and `keyword_intents`) moved out
  of `api/chat/routing.py`, which re-exports the two names, so the portal and the channel cannot route the same
  words differently. Behaviour-preserving; no test was edited.
- **Rejected.** Hand-listed files (the AI-08 split already showed a list goes stale), and importing
  `backend/` into the container (drags the engine and FastAPI into a hosted agent).

## D-75 CH-08: how the orchestrator reaches a model

- **Context.** `ORCHESTRATOR.md` (Prompt 2B) said to call models only through `NarrationService`. That path
  wraps `AgentRuntime`, which drops a model's tool calls by design (ADR-004: agents hold no tools), and the
  orchestrator's job is to let the MODEL choose which deterministic tool runs.
- **Choice.** `ModelChain` (`app/core/models.py`) builds the shared `OpenAICompatibleChatModel` from the same
  `AI_*` settings: `gateway` as configured; `foundry` is the agent's own Foundry account over its Azure OpenAI
  v1 surface (`https://<account>.services.ai.azure.com/openai`, derived from `FOUNDRY_PROJECT_ENDPOINT`, Entra
  audience `https://cognitiveservices.azure.com`, the model from `FOUNDRY_MODEL`, defaulting to the platform's
  `AZURE_AI_MODEL_DEPLOYMENT_NAME`). `foundry_connection` is refused at start: BYOM serves prompt agents only.
  It keeps the chain's rule (fall to the next provider only when one fails, never splice two models' sentences,
  stay with one provider through a tool loop), the egress policy and the injection screen. It drops the
  budget/breaker/bulkhead/retry wrappers, which wrap `AgentRuntime`; a call has the total deadline and the chain.
- **Three modes.** `tools` (MAF `Agent` with `FunctionTool`s from the catalog and a middleware that replaces the
  model's text with the composer's), `json` (`AI_GATEWAY_SUPPORTS_TOOLS=false`), `keywords` (no model, a failed
  model, or the injection screen). The MAF bridge is `PortChatClient(FunctionInvocationLayer, BaseChatClient)`
  over `ModelChain`; verified against agent-framework-core 1.24.0.
- **Unverified live.** That the `/openai/v1` chat-completions path accepts the hosted agent's identity on a
  Foundry account is from the Azure OpenAI v1 documentation, not run (Prompt 6).

## D-76 CH-08: the hosting package, the protocol and what a reply is

- **Docs consulted 2026-11-02 and 2026-11-03.**
  https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/framework-hosted-agents ;
  https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent-code ;
  https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot ;
  https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot-virtual-network.
- **Choice.** The container implements the **Responses** protocol (2.0.0): the platform bridges Teams and
  Microsoft 365 Copilot to it. The handler uses the stable `azure-ai-agentserver-responses` 2.4.0 directly
  (`ResponsesAgentServerHost`, `TextResponse`); `agent-framework-foundry-hosting` is a pre-release (beta) on
  PyPI as of 2026-11-02 and a production build does not take a `--pre` dependency. The handler was exercised
  against the real host in-process (`/readiness`, `POST /responses`, `/whoami`).
- **Text only.** Published agents do not stream, and no card or attachment path through the hosted runtime was
  found in the documentation, so replies are Markdown. Files do not upload in Microsoft 365 Copilot. The
  composer's `cards_payload` is unused.
- **Conversation key.** `conversation_id`, else the response chain id, so state follows the person's thread.

## D-77 CH-08: who is asking

- **Choice.** `CHANNEL_IDENTITY_SOURCES` (default `original-subject,platform`; `client-headers` opt-in). The
  platform documents `x-agent-user-id` (opaque, not an object id), `x-ms-original-subject` (`oid`/`tid`/`idtype`,
  an experimental draft described as attribution, not proof) and `x-ms-user-identity` (only with end-user
  delegation). Nothing resolvable means the turn runs nothing and says so. The resolution records its source;
  `/whoami` (only with `CHANNEL_DEBUG_WHOAMI`) reports header names, and values only for identity fields.
- **Why client headers are off.** They are caller-supplied: anyone who can call the agent could claim anyone.
- **Name.** If no signal carries a display name the audit row says `(name not provided)`; the gateway requires a
  name and the object id is still recorded. Not invented.
- **Assurance.** The gateway records `channel-asserted` for every orchestrator call, whatever the source.
- **Prompt 6 must verify live**: which signal a Teams and a Copilot Chat message carry; whether Activity-to-
  Responses preserves `from.name`.

## D-78 CH-08: region and network isolation (not applied)

> **Corrected by [D-92](#d-92-ch-12b-the-hosted-agent-network-path-per-the-documentation-unproven).** The
> second fact below was wrong: the "standard agent setup" is the classic path, not the hosted-agent path.
> The text is left as written so the correction is visible.

- **Facts.** Hosted agents are supported in specific regions (West US 3 among them in the March 2026 list);
  a hosted agent in a network-isolated project needs the "standard agent setup" (a bring-your-own-VNet agent
  subnet and a capability host). `infra/modules/foundry` is a basic account with a private endpoint and public
  network access off, so a hosted agent there cannot reach the gateway or the model until that setup exists.
- **Not done, deliberately.** No Terraform changes in this work package. It is recorded as an infrastructure
  gap for the sandbox decision (Prompt 6, spike S3), with the choice of region left to the owner.

## D-79 CH-08: no container registry; Python 3.13

- **Choice.** The recommended deployment is the **source-code (zip) path** (`codeConfiguration`, runtime
  `python_3_13`, `remote_build`): it needs no registry and Terraform adds none, so `infra/` is untouched by
  this work package. A `Dockerfile` (python:3.13-slim, uid 10001, port 8088, `PYTHONNOUSERSITE=1`) is kept for
  the container path and a local build. The hosted runtime supports `python_3_13` and `python_3_14`, not the
  backend's 3.12, so the orchestrator targets 3.13; the vendored modules are version-neutral.
- **Verified.** The image's stages up to the `pip` step build and the later stages were checked without it
  (non-root, Python 3.13, vendored manifest present). `pip install` inside the build could not complete in this
  environment (TLS interception on the egress), so the image was not built end to end; the requirements were
  dry-run resolved on the host. Private-network source deployments need outbound access to
  `mcr.microsoft.com` and `*.login.microsoft.com`.
- **azd.** `channel_orchestrator/azure.yaml` follows the documented `azure.ai.agent` schema; it has not been run
  against a live `azd` (Prompt 6).

## D-80 CH-08: the runner's rules

- **The model chooses a tool; code chooses everything else.** Client: resolved by the platform's own
  `client_resolve` and written over any `client_id` the model passes. Year: the reader's words, else the
  conversation's, else a question; a year the model names counts only if the reader said it; a write never
  inherits a year. Method: the reader's; eligibility runs under BOTH certified methods when none is named
  (`method=both` on the tool reads pay-period only, so two runs, each labelled "Min-Max method" / "Pay Period
  method", facts namespaced `client_eligibility_min_max` / `_pay_period`). Budget: `CHANNEL_MAX_TOOL_CALLS`.
- **One named client selects it.** Teams has no page selection, so when the reader names exactly one client the
  portal rule's "a different client is in scope: ask" is not applied; two clients named, or none and nothing
  recoverable, still ask, with the candidates numbered and a bare number selecting one.
- **The model's schema.** `client_id` and the year are not offered or required (the runner supplies or asks);
  extra properties are tolerated at the door and judged against the catalog's strict schema by the runner.
  `employee_drill` is not offered to a model (a record token is never in its view).
- **What a model sees of a result** is the fact paths, never values; a prepare's confirmation token is stripped.

## D-81 CH-08: confirming a change

- Exact words (`confirm`, `yes, apply`, `cancel`), the same person and conversation, within
  `CHANNEL_CONFIRM_TTL_SECONDS` (300). Any other message drops the pending change. The pending change is cleared
  before the commit is sent with a fresh idempotency key and a commit is never retried; a lost answer is reported
  as unknown. Commit tools are not model tools; names and the single call site are pinned by
  `test_orch_structure.py`. Proved against the real stack in `test_orch_e2e.py`.

## D-82 CH-08: narration audit

- **`POST /channel/v1/audit/narration`** (route 9; `channel_route_inventory.json` updated). An agent caller only
  (a delegated Cowork token is 403). Body `{agent_name, agent_version, model, prompt_sha256, tool_names,
  guard_status, violations_count, output_summary}`, unknown fields refused. It writes a `channel_audit` event
  with the new `action_kind='narrate'` (`ACTION_KINDS` extended; `ChannelAuditor.audited` treats it as a read-like
  single event) and `numeric_guard` = the verdict, outcome `ok` or `rejected_by_guard`, and a `tcc_ops.agent_action_audit`
  row with `is_deterministic_path` true only when the guard passed (`AgentInvocation` gained `prompt_sha256` and
  `output_note`). The gateway may import `application.agent_audit` (stdlib + domain only; allow-listed with the reason).
- **No migration.** `action_kind` is `VARCHAR(16)` with the values named in a comment, not a CHECK; `narrate`
  fits. The comment in `0001_channel_audit.sql` is left as published (editing a published migration changes its hash).
- **Failure.** An unwritable channel event is a 503 `audit_unavailable`; the orchestrator logs it, counts it
  (`/whoami`) and sends the answer anyway. The report carries a hash of the prompt and a short note, never the
  prompt or the reply.

## D-83 CH-08: guard-rejection UX and the footer

- A rejected narration is dropped whole; the reply is the blocks and the disclaimer, a line saying the commentary
  was withheld, and the footer. The provenance footer (run, rule-pack path, trail hash, or source) is appended
  AFTER the composer from the envelopes' provenance fields verbatim: identifiers, not figures, no model touches them.
- No identity, an injection-flagged message, a model outage and a tool outage each have a plain sentence
  (`app/core/replies.py`); none carries a figure.

## D-84 CH-09: `scripts/publish-m365.ps1`

- **Source.** https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot-virtual-network and
  .../publish-copilot (consulted 2026-11-03). Payload shapes (bot properties, the Teams channel, the PATCH, the publish
  body, `authorization_schemes` as `[{"type": ...}]`) are the documented ones; none has been run against a live service.
- **Tokens: `az rest --resource https://ai.azure.com`, not `az account get-access-token`.** The brief names the latter;
  `az rest` asks az for the same token itself, so the script never reads, holds or prints one (nothing to leak, nothing to
  redact) and every call stays one `az` invocation a fake can stand in for. Tested: no call carries an Authorization header
  or a bearer string, and every Foundry call carries the `ai.azure.com` resource.
- **Merge, never replace.** The PATCH replaces `protocol_configuration` and `authorization_schemes`, so the script reads the
  agent, carries every existing protocol and scheme, adds `activity.enable_m365_public_endpoint` and the scope's Bot Service
  scheme, and removes only the other Bot Service scheme. An endpoint with nothing configured gets `responses` + `activity`.
  It does NOT add `AzureRbac` if absent: that would grant direct-client access nobody asked for.
- **WhatIf.** Reads (provider state, tenant, the agent) run, because the merge cannot be shown without the agent; every
  request that changes something is printed with its body and not sent. `Remove-Item`/`Set-Content` on the script's own temp
  files use `-WhatIf:$false`: a `-WhatIf` that skipped them would leak files and fail.
- **Version.** A published `appVersion` cannot be republished, so a "version already exists" answer moves to the next patch
  version (up to 50 tries) and the package download uses the version that published. Each run that reaches publish therefore
  publishes a new version; the bot, channel and endpoint steps are idempotent.
- **Guards.** `Tenant` without `-ConfirmTenantPublish` stops before any call; the provider check prints the register command
  and exits 1 and the script never registers a provider; success is printed only with a `titleId`.
- **Parameters.** `-EnablePrivateNetworkRoute` is a `[bool]` as specified; under `pwsh -File` it must be passed as
  `-EnablePrivateNetworkRoute:$false` (a bare second argument is rejected), which the docs and tests use.
- **Placeholders.** Developer, privacy and terms URLs default to this repository's `SECURITY.md` and `DISCLAIMER.md`.
- **Not scripted: unpublish.** The reference has no such call; `PUBLISHING.md` says how to remove an agent by hand.
- **Request bodies go through temp files** (`--body @file`) rather than inline strings, because quoting JSON for a native
  command differs between PowerShell and cmd and a mangled body is a silent failure; the files are deleted in `finally`.
- **A second Bicep-free resource:** the bot is one ARM PUT. No Terraform was added: Bot Service is created per
  publish by the operator who holds the role, not by the platform's infrastructure code.

## D-85 CH-08b: gaps found re-reading the brief

- A re-read of the work package against the brief found items the first pass missed; all are fixed in
  `wp/CH-08b-spec-gaps`: candidates are numbered `1) Name` (was `1.`); a message that supersedes a pending
  change says so; a claim-package confirm is followed, in code, by `claim_package_link`; a turn deadline
  (`CHANNEL_TURN_TIMEOUT_SECONDS`) and plain-word mappings for 401/403/429/timeouts; one span per gateway call
  (`app/core/telemetry.py`, no payroll in attributes); `/whoami` also names the display name, channel and
  conversation, and a refused turn shows what was received when `CHANNEL_DEBUG_WHOAMI` is on; the report carries
  `conversation_id`; the golden prompts now cover every write flow and assert, for every answer, that each
  numeral is in the facts or the reader's words.
- **A what-if's size and a base year are the reader's** (found while doing the above): a `magnitude`, hire hours
  or rate the model chose is dropped, a missing size is asked for ("How many, or by how much?"), and a
  `base_year` is treated like a write's tax year (explicit only). A free identifier the model supplies (a finding
  id, a unit) is not checked here: the preview shows what will change and the person confirms it.
- **Conversation state** is an in-memory dictionary with a TTL. The runtime's session storage (`$HOME`) is a
  filesystem the platform may discard on idle and is not shared across replicas, and what is held is a
  convenience and one safety device whose loss costs a repeated question.

## D-86 Prompt 5 runs in the main checkout, on `feat/m365-channel`

- **Context.** The session began in the main checkout on `main`, which holds only the initial commit; the channel work
  is on `feat/m365-channel`, which no worktree has checked out (the earlier sessions' worktrees hold their own
  branches, all ancestors of it). The brief requires that branch.
- **Choice.** `git checkout feat/m365-channel` in the main checkout (the only untracked path was a stray `__pycache__`
  folder under `channel_orchestrator/`, which the checkout did not touch), then one `wp/CH-nn-*` branch per package.
  Nothing is pushed.
- **Why.** The brief names the branch explicitly; no other worktree is affected.

## D-87 CH-10: what was read, and how the package was validated

- **Read 3 Nov 2026:** `https://learn.microsoft.com/en-us/copilot/cowork/cowork-plugin-development` (updated 3 Nov),
  `https://learn.microsoft.com/en-us/microsoft-365/copilot/extensibility/plugin-authentication` and
  `.../plugin-authentication-oauth` (auth config, redirect URI, Teams Developer Portal fields),
  `https://microsoft.github.io/wiqd/getting-started/installation/` and `.../cli/reference/`.
- **Manifest 1.29**, URL-only connector (`mcpToolDescription` optional). 1.28 stays buildable (`manifest_version`);
  its tool file is generated from the catalog through `channel.mcp.describe`, the same code as `tools/list`.
- **`wiqd` was not installed.** Its installer is a remote script; running one unattended on a shared machine is not
  worth a validation convenience. The offline validator implements the documented rules instead (ASKILL-M001..M003,
  P001..P008, connector and companion-file rules). **`atk` 1.1.14 was already installed**: `atk package` built the
  generated tree inside a throwaway Agents Toolkit project (`m365agents.yml` with a `package` lifecycle), and the
  rendered manifest was also validated against the published 1.29 JSON schema fetched for the occasion (0 errors).
  `atk validate` and `wiqd plugin validate --mode deep` need sign-in and were not run; the setup guide says to run them.
- **Frontmatter reader.** PyYAML is not a repository dependency, so `scripts/cowork_plugin/frontmatter.py` reads the
  narrow slice skills use and rejects the rest as ASKILL-P003.
- **Neutrality.** The deny-list is read from `scripts/audit-export.py` (where it is already spelled out), not copied.

## D-88 CH-10: the gateway's MCP text gains a provenance line

- **Context.** The brief wants a briefing footer with the run id, rule-pack version and trail hash "taken from the
  envelopes". The MCP text block carried blocks, handover lines and the disclaimer, not the provenance; a client that
  shows the model only the text would leave it nothing to copy, and a model with nothing to copy writes something.
- **Choice.** `channel/render.provenance_line` adds `Provenance: run X; rule pack Y; assumptions Z; trail hash W.`
  between the body and the disclaimer, omitted when a result has none (a claims-only read has no run). The label says
  "trail hash", not "sha256", because the figure check reads the digits of a digest as numerals and the word adds one.
  The skills pass the four values as `allowed_context` when they verify the footer, so a footer with an altered digit
  still fails the check.
- **Why.** Additive; the frame the tests rely on (`VERBATIM` first, the disclaimer last) is unchanged.

## D-89 CH-10: `book_rank` returns names, not ids

- **Context.** `book_rank`'s facts carry `client_name` but no `client_id`, so W1's per-client reads need an id.
- **Choice.** The W1 skill calls `client_resolve` with the name exactly as returned, asks when it is ambiguous, and
  never picks. The facts are not changed.
- **Why.** The rows are the chat's book brief too; adding a field changes what the portal's narrator is handed and the
  equivalence tests pin it. Revisit by adding `client_id` to the brief if the extra call proves slow in the demo.

## D-90 CH-10: a preview is not read-only, so Cowork may ask twice

- **Choice.** The tool annotations stay as built: reads `readOnlyHint: true`, commits `destructiveHint: true`, a preview
  neither. Cowork treats `readOnlyHint: false` as needing confirmation, so a preview can prompt before the skill's own
  confirmation. That is one more confirmation, never one fewer, and annotation-driven prompts for non-Microsoft servers
  are still rolling out, so the skills do not depend on them. Documented in the setup guide.

## D-91 CH-10: two OAuth registrations, and `offline_access`

- **Choice.** The setup guide separates the Entra client registration (the identity Cowork presents, with the redirect
  URI `https://teams.microsoft.com/api/platform/v1.0/oAuthRedirect` and admin consent for `Channel.Access`) from the
  Teams Developer Portal registration that yields the `referenceId`. It tells the operator to restrict usage by app to
  **Any Teams app** (a specific app id makes every tool call return 404 for an MCP server, per the documentation) and
  to include `offline_access` in the scope so the token refreshes.

## D-92 CH-12b: the hosted-agent network path, per the documentation, unproven

- **Context.** D-78 said a hosted agent in a network-isolated project needs the "standard agent setup". The Foundry
  documentation read on 2 November shows that setup is the **classic** path (Cosmos DB, AI Search, Storage and a
  capability host, for threads, files and vector stores). The hosted-agent path and the networking deep dive describe a
  customer-delegated agent subnet plus private endpoints to the customer's own Storage, SQL and Key Vault, and no
  Cosmos, Search or capability host. Our agents use no threads, files or vector stores.
- **Choice.** State it as **per the documentation, unproven until spike S6**. The customer has ruled Cosmos DB out, so the
  hardened path must prove a network-injected account running hosted and prompt agents with no capability host and no
  Cosmos, or stop and escalate. D-78 and `ORCHESTRATOR.md` are corrected in place (D-78 keeps its original text under a
  correction note). The plan and the runnable checklist are `docs/architecture/HARDENING-PLAN.md` and
  `docs/m365-channel/HARDENING-SPIKE.md`.
- **Why.** An unproven claim stated as fact would have sent the hardened build towards Cosmos, which is ruled out, and
  away from the path the documentation actually describes for hosted agents.

## D-93 CH-12b: how the demo toggle is built

- **Choice.** `foundry_public_network_access` (default `false`), `foundry_allowed_ip_ranges` and `foundry_allow_any_ip`
  thread to `modules/foundry`, which sends `publicNetworkAccess` and `networkAcls` from two locals; with the toggle off
  they evaluate to exactly the block the module always sent (no `ipRules` key). The module exposes `network_settings`
  (read back from the account's own body) and `private_endpoint_id`, so the tests assert the real properties and that the
  private endpoint stays.
- **The ranges are `type = any`.** azd substitutes strings into `main.tfvars.json`, and a list variable cannot take one, so
  the input accepts a list or a comma-separated string; `infra/foundry_network.tf` normalises it. That is also why the
  range rules are `precondition`s on a `terraform_data` rather than variable validations: a validation can only read the
  raw variable. The resource has `count` 0 unless the demo posture or a range is asked for, so the default plan gains
  nothing. Enterprise and `data_classification = customer` are plain variable validations on the toggle.
- **The rules.** IPv4 CIDRs only (the account firewall takes no IPv6); a `/32` is sent as a bare address and `/31` is
  refused (the firewall supports neither form); any `/0` needs the second switch; ranges or the second switch without the
  toggle are refused, because a firewall rule that is silently ignored is worse than none. A toggle with no ranges means
  `Allow`, as the brief says; the warning names "no address restriction".
- **The warning is a `check`.** A failed `check` is a warning in the plan, so it cannot be missed and does not block the
  demo. The tests expect it. A mutation (the any-address rule made always true) was shown to fail its test.
- **Not built.** No agent subnet, ops VM, Bastion, private endpoint or registry.

## D-94 CH-12: order of the last two packages, and what the documents are built from

- **Choice.** CH-12b was built and merged **before** CH-12, although the brief lists it after. CH-12's documents link to the
  hardening plan and the spike, and a link check that fails until a later package exists is a gate that cannot pass in
  order. Nothing else about the packages changed.
- **The documents were written against the code, not the plan.** Examples: claim package tickets live in the confirmation
  store (the Warehouse when deployed), not in memory; an allow-list change takes effect at the next call and a group source
  caches for 60 seconds; `/channel/ready` does not check the Warehouse. Where the design document and the code differed,
  the documents say what the code does.
- **The demo uses only the synthetic clients in `backend/data/source/synth.py`** (Cascade Retail Partners, Northwind Care
  Systems, Ironbridge Logistics, Halloway Foods). The reference client's codename is not used: its payroll is real,
  de-identified.
- **Two limits found by the end-to-end tests are documented as limits, not fixed** (D-89 and the value-matching guard): the
  figure guard compares values, and `client_resolve` asks even for one exact name. Both are in KNOWN-LIMITATIONS and the
  demo script tells the presenter what the resolver will do.

## D-95 CH-13: integration branch, Python, resource group

- **Context.** `feat/m365-channel` is checked out in the owner's main checkout, so this prompt ran in a linked worktree
  on a session branch that started at the initial public commit.
- **Choice.** The session branch was fast-forwarded to the tip of `feat/m365-channel` (no history rewritten, nothing
  lost) and treated as the integration branch; `wp/CH-13-live-deploy` is cut from it. The fast-forward of
  `feat/m365-channel` itself is left to the owner. Python 3.12 is not installed here; the `.venv` uses 3.14 (the
  backend suite and all scripts ran on it; the deployed apps run 3.12 and the hosted agent 3.13).
- **The resource group is created by Terraform, tagged through the `tags` variable**, not pre-created with `az`: the
  provider declares the group and an existing one must be imported first. Tags are `purpose=m365-channel-poc` and
  `owner=<operator>`.

## D-96 CH-13: three things changed in code because the live run needed them

- **Easy Auth on the public profile (locals.tf).** The public profile with `auth_mode = entra` (which the channel
  needs) left the web app without Easy Auth, so the BFF forwarded no token and the portal could not call the API. It is now
  enabled for that combination **only when `web_client_id` is given**; every other combination is unchanged (two tests).
- **`postprovision` never runs the synthetic load against a brought Lakehouse.** `load_fabric --synthetic-only`
  overwrites every table it writes and drops the reference client. The step runs only when Terraform created the
  Lakehouse (`TCC_FABRIC_CREATED=true`). This is a data-loss guard on the owner's workspace, not a convenience.
- **The API reads `CHANNEL_WRITER_SOURCE` and the group id (main.tf).** It enforces the writer entitlement itself. The
  existing test that said the API gets no channel setting was narrowed to exactly these two settings, and only with the
  channel on. Also: `channel_debug_whoami` (default off) so the `channel_ping` diagnostic is a Terraform setting, and the
  mock model gateway listens on port 8000 (the platform's probe), with its one test updated.

## D-97 CH-13: the Fabric target was reused, and what was and was not touched

- **Reused, not created:** the existing workspace, lakehouse and warehouse (ids verified against the Fabric API before
  any write; the guard passed). The warehouse already held the v2.0 schema, so only pending migrations 0001 and 0002 ran;
  the destructive bootstrap never did. The T-SQL grants and the idempotent seed ran; the seed wrote nothing.
- **Workspace roles added, both for this deployment's own identities:** the API identity (Terraform, `Contributor`) and
  the gateway identity (`Viewer`, added through the Fabric API: it connects, and its object-level `INSERT, SELECT` on
  `tcc_ops.channel_audit` is what writes the audit). Nothing else on the workspace was changed. The shared capacity was
  checked (Active) and not touched.
- **Data check, read-only:** column names, row counts and the shape of a few values were inspected before any write; no
  personal names, emails or phone numbers, and the tax-identifier and address columns hold placeholder business values.
  Nothing was copied into logs or notes. Classification `synthetic` stands.

## D-98 CH-13: the Foundry firewall is open to any address in the demo

- **Context.** The brief asked for the data plane to be reachable from the operator's address and nowhere else. The
  hosted agent's own runtime calls the project (storage, history) from addresses nobody can list, and with the firewall
  narrowed to one address those calls were refused (403), so the agent could not answer at all.
- **Choice.** `TCC_FOUNDRY_ALLOWED_IP_RANGES` was emptied: public, Entra-only, local keys off, synthetic data. This is the
  setting the repo's own demo toggle provides; nothing new was added. It is documented in KNOWN-LIMITATIONS and must be
  closed (OPERATIONS.md, "Turning the demo posture off") before any real data.
- **What it did not fix:** the agent's call to the account's model endpoint still fails at connect. The orchestrator
  degrades by design to the engine's own answer without commentary. Left open as M-01 (resolved in D-101).

## D-99 CH-13: how the agent was deployed and published

- `azd ai agent` needed a different `azure.yaml` shape than the one written offline (`entryPoint` is a string; the
  project, protocols and Bot Service scheme are declared); the file was rewritten from what the tool itself generates.
  It also created the Azure Bot resource, which `publish-m365.ps1` then reused. The script's default developer name was
  38 characters; the platform's cap is 32, so the default is now `Tax Credit Copilot (PoC)`.
- Scope was `Shared`. `Tenant` was never used. The agent's identity holds `Channel.Invoke` on the gateway and the
  Foundry User role on the account; the client-headers identity source was switched on only to prove the agent reaches the
  gateway (spike S3) and switched off again before publishing.
- Files `azd ai agent` generates carry the bot id; they are gitignored and were removed from the one unmerged commit that
  first included them.

## D-100 CH-14: the silent Teams chat: `activity` declared as a container protocol

- **Symptom.** Teams showed `/whoami` as delivered and nothing came back, twice (13:05 and 13:34 PST). Bot Service
  metrics showed HTTP 200 only, so Teams to Bot Service to the agent endpoint was accepted.
- **Root cause, from the container's own log** (session of the 13:34 message, agent version 13): `POST /activity/messages` ...
  `404`. `channel_orchestrator/azure.yaml` declared `activity` under the **container** `protocols:`, and the orchestrator
  serves the Responses protocol only (`app/main.py`). A container that declares `activity` is sent Teams messages
  as Activities at `/activity/messages`, which nothing serves. The sibling project that works in Teams found the same
  thing ("declaring `activity` as a container protocol had made the platform post Teams messages to `/activity/messages`,
  which nothing serves", its go-no-go Run 35) and rolled back to the **Responses bridge**: `activity` declared only on the
  endpoint, where the platform converts an Activity into a Responses call for a Responses-only container.
- **Fix.** `activity` removed from the container's `protocols:`; `agentEndpoint.protocols` stays `[responses, activity]`;
  `agentEndpoint.authorizationSchemes` is `Entra` and `BotServiceRbac` (the working agent's pair; the spelling is azd's).
  Verified by `GET /agents/<name>` after **every** deploy and after the re-publish (the evidence is
  [evidence/model-access-2026-11-03.md](evidence/model-access-2026-11-03.md), "agent definition"): `definition.protocol_versions` is
  `responses` only; `agent_endpoint.protocols` is `activity, responses`; `protocol_configuration.activity.enable_m365_public_endpoint`
  is `true`; schemes `Entra, BotServiceRbac`. The agent was re-published at scope Shared; the package manifest is 1.0.2.
- **What was not shown.** A direct Activity sent as the operator to the Activity Protocol URL was accepted (HTTP 202, version
  resolved to the latest) but the hosted-agent session list does not show the session it created, so the request could not be
  watched arriving. Web Chat is unavailable: the bot's public network access is `Disabled` (the publish script's setting). The
  proof is therefore the next real Teams message: see "Retry in Teams" in DEMO-SCRIPT.

## D-101 CH-14: M-01 (model access from the hosted agent): root cause and fix

- **Naming.** Prompt 6 called this S6, which `HARDENING-SPIKE.md` already uses for the hardened-network spike. The live issue is **M-01**.
- **Root cause.** `/netcheck` (new, gated by `CHANNEL_DEBUG_WHOAMI`) run in the container: `<account>.services.ai.azure.com` and
  `<account>.cognitiveservices.azure.com` did not resolve ("Temporary failure in name resolution"), while `<account>.openai.azure.com`
  resolved to a public address, accepted TCP and TLS and answered an unauthenticated request with 401. The documented sample's own call
  (`AIProjectClient.get_openai_client().responses`, probed by `/modelprobe`) failed the same way, at the same DNS step, because it uses
  the project's `services.ai.azure.com` host. It was never a firewall, a role or a timeout: from the workstation all three names resolve to
  the same address. Why the hosted runtime's resolver refuses two of the account's names and not the third is not known (the account has
  private endpoints and private DNS zones for all three); the fix does not depend on it.
- **Fix.** The `foundry` provider's base is `https://<account>.openai.azure.com/openai` (v1 chat completions, Entra token for
  `https://cognitiveservices.azure.com`). The same account, token and deployment. A non-public-cloud host keeps its own.
  Connect timeout unchanged at 5 s: the failure was DNS, not slow connects.
- **Roles** (each an Azure RBAC assignment inside `rg-tcc-poc-channel`, built-in, at the account): the agent's instance identity
  holds **Foundry User** (granted in Prompt 6, inherited by the project) and now also **Cognitive Services User**
  (`a97b65f3-24c7-4388-baec-2e87135dc908`), which the working sibling agent's publish script grants as well. The identity is read from
  `GET /agents/<name>` `instance_identity`; it did not change across the versions deployed here.
- **Two more findings once the model answered.** (1) The model wrote `{{book_rank.clients.0.identified_usd|money}}`, dropping the `facts.`
  the narrator prompt requires; the composer rightly refused it and withheld the narration (live audit: `rejected_by_guard`, "5 figure(s)
  not in the tool facts": the digits of the unresolved path). Every `fact_paths` entry the model is shown now carries the exact `placeholder`
  (`app/core/placeholders.py`); the composer, the guard and the platform's narrator prompt are untouched. (2) The model chose `book_rank` for a
  one-client question and the engine's figures for the *first ranked client* were narrated as the asked-about client's: figures exact, attribution
  wrong, which no value-matching guard can see. The planner prompt now says when to use the client's tools and when the whole book.
- **Mock gateway in the chain.** The orchestrator's chain is `foundry` only and must stay so: the mock admits only the integration subnet,
  which the hosted runtime is not in. Stated plainly in `AI-GATEWAY.md` and `ORCHESTRATOR.md`: the hosted orchestrator can use a customer gateway only
  if that gateway is reachable from the hosted runtime's network.
- **A test rule changed, narrowly:** `test_orch_structure.py` allows `modelprobe.py` to import `azure` (it lazy-imports the project client); `azure-ai-projects` is
  pinned in the orchestrator's requirements at the backend's version and `test_orch_requirements.py` keeps the two in step.

## D-102 CH-14: `x-agent-user-id` is a default identity source

- **Evidence.** The same sibling project found that under `BotServiceRbac` the platform refuses an activity without a tenant and a caller object
  id and names the person with `x-agent-user-id`, not the activity's `aadObjectId`. Documented as "a per-user partition key, not a credential",
  so it can be opaque. `/whoami` now reports its *shape* (a GUID, or opaque with a length, and whether it equals another oid signal) and shows it only
  when it is a GUID. Live, for the operator's own call: **GUID, 36 characters, equal to the operator's object id**, with no client headers sent.
- **Choice.** `agent-user-id` joins the default `CHANNEL_IDENTITY_SOURCES` (`original-subject,platform,agent-user-id`), last, and only a GUID counts: an opaque
  value is no signal and the next source is tried, never a refusal. It names no tenant, so the deployment's own is recorded; assurance stays
  `channel-asserted`. A direct, authenticated caller now resolves as themselves. What a *Teams* message carries is still to be confirmed by `/whoami` in Teams.

## D-103 CH-14: the live checks use the mock's fixed test credentials, supplied at command time

- The brief says secret-based gateway modes use Key Vault references only. No real secret exists here: the mock's `api_key` and `oauth`
  credentials are fixed, documented, non-secret test strings. They were given only in the environment of the command that ran the check
  (never in an app setting, a file or the repository), so the Key Vault toggle was not enabled. Entra mode needs a real token; the operator's own,
  short-lived, was written to a temporary folder for the run and deleted after. Flipping the mock's `MOCK_AUTH` is a Terraform-managed app setting:
  it was set back to `entra` at the end and the plan re-checked.

## D-104 CH-15e: one Graph client, refresh-and-retry-once, bounded by a cool-down

- **Context.** After `GroupMember.Read.All` was granted, the API's group check stayed denied for about a day: the identity had asked Graph for a token before the grant and the platform kept it. CH-15a (display names) needs the same Graph plumbing.
- **Choice.** `infrastructure/auth/graph_client.py` holds `GraphClient` (bearer, one request, **one** retry) and `GraphTokenProvider` (a callable over `DefaultAzureCredential` with `invalidate()`). A 401, or a 403 whose body says `Authorization_RequestDenied` / insufficient privileges, invalidates the token and retries once. Invalidation passes `claims` to `get_token`, which makes azure-identity/MSAL skip their cache (for a managed identity, MSAL also asks the platform endpoint for a fresh token); a credential that rejects `claims` is rebuilt and asked plainly. A 60-second cool-down on `invalidate()` stops a permanently missing role from forcing a token fetch on every check. `EntraGroupEntitlement` builds a `GraphClient` per call from its two public attributes (the existing tests replace them after construction), so no existing test changed. Fail-closed is unchanged: a refusal that survives the retry, any other status, bad JSON or a timeout is "not a writer". The display-name adapter reuses `GraphClient.request` and `GraphTokenProvider`.
- **Not verified.** Whether the App Service managed-identity endpoint honours the cache bypass is only confirmable live; recorded in KNOWN-LIMITATIONS and handed to the live redeploy.
- **Rejected.** Retrying every non-2xx (a 500 or 429 is not a stale token), and a retry loop (one attempt, as the brief says).

## D-105 CH-15e: the channel's `client_resolve` settles one exact name

- **Context.** With no client selected the resolver always asked, even for one exact full name, so each Teams or Cowork conversation paid an extra turn and the skills had to confirm and call again.
- **Choice.** In `application/capabilities/client.py`, when not `strict`, a resolution that would clarify is promoted to the one client when the text names exactly one client (full name or exact alias, whole word, case-insensitive), whatever `current_client_id` says; a full name beats a first-word alias that other clients share (the full name is removed and the remainder must name nobody else). `facts.resolved` is added. "Their" with a current client already resolved; without one it still asks. `chat_scope.resolve_referent` and `strict=True` are untouched, so the portal chat keeps its rule (a page selection can contradict the sentence; a channel has no page). The orchestrator's earlier one-name workaround stays for a gateway that predates `resolved`.
- **One existing test edited.** `tests/channel/test_workflows.py::resolve` asserted "with nothing selected the resolver always asks", i.e. the limitation this item removes; it now asserts `resolved` on the first call. No other existing test changed; the equivalence test with the chat resolver still holds for its cases.
- **Also.** `client_resolve` was a legacy standards offender (complexity 12, 41 lines); splitting its facts and blocks out took it under both limits and the baseline tightened (two entries removed, none added).

## D-106 CH-15e: the debug switch, the startup warning and the cleanup page

- **Context.** `CHANNEL_DEBUG_WHOAMI` already defaulted to false in `azure.yaml`, the Terraform variable and both settings loaders; nothing pinned it and nothing said so when it was on.
- **Choice.** Both processes log a WARNING at startup when it is on (gateway `create_app`, orchestrator `build_orchestrator`; neither message carries an identifier), and tests pin every default. `DEMO-CLEANUP.md` lists the five switch-offs in order. Only `TCC_FOUNDRY_PUBLIC_NETWORK_ACCESS`, `TCC_FOUNDRY_ALLOWED_IP_RANGES`, `TCC_CHANNEL_WRITER_SOURCE`, `TCC_CHANNEL_WRITER_GROUP_ID` and the orchestrator's own azd values are mapped in `infra/main.tfvars.json`; `channel_debug_whoami`, `foundry_allow_any_ip`, `channel_allowed_caller_app_ids` and `enable_mock_ai_gateway` are not, so for those the page gives the exact overlay line (`infra/m365-poc.auto.tfvars`) and `azd provision`, not an `azd env set` that would do nothing. Mapping them would make a demo setting a per-environment default and could fight the overlay, so `main.tfvars.json` was left alone.
- **Typed errors (item 3).** `claim_transition_prepare` typed errors (409 `not_calculated`, 404 `claim_not_found`, 422 `rejected`) are now orchestrator goldens asserting the plain-words text and no status code, error code or confirm prompt. No code change was needed.

## D-107 CH-15a: display names from Graph, in the gateway, off by default

- **Context.** Teams carries an object id and no name, so audit rows read "(name not provided)" and a write was attributed to a GUID. The gateway identity can be granted Graph `User.ReadBasic.All`.
- **Choice.** Port `application/display_names.py` (`DisplayNameResolver`, `ResolvedPerson`, `needs_resolution`; standard library only) and adapter `infrastructure/auth/graph_people.py` over the CH-15e `GraphClient` and `GraphTokenProvider` (no second Graph client): `GET /users/{oid}?$select=displayName,userPrincipalName`, a 2 s timeout, a 24 h cache for an answer and 5 min for none, bounded (2,048, least recently used out), thread-safe and single-flight per object id, fail-soft (any failure is `None`; the warning carries the oid and the exception type only). The OID is checked as a GUID before it reaches a URL. A name is cut to 256 characters because the API refuses a longer acting-user field.
- **Where it applies.** `channel/people.py` (`CallerPeople.enrich`) runs for an **agent** caller whose name is missing or the placeholder, in `run_tool`, `audit_narration` (so the narration rows name the person too) and the MCP `tools/call`; a delegated (Cowork) caller never reaches it. It runs in a worker thread, so a slow Graph cannot stall the event loop. The channel's own UPN, if one was ever asserted, outranks the directory's; the name is replaced only when it was missing or the placeholder. The API already prefers the UPN as the author (`ActingUser.actor`), so no API change was needed.
- **Composition.** Wired in `application/channel_wiring.py` (`get_/set_display_name_resolver`), which `application/wiring.py` re-exports, not in `wiring.py` itself: the gateway must not import the engine (`test_gw_architecture`), and `channel_wiring` is the gateway's composition. `build_services` takes no new argument; a test injects through `set_display_name_resolver`. The gateway architecture test's allow-list gained `application.display_names` (one reason stated), and `test_channel_infra`'s env-name scan now also reads `_flag(...)` so a new flag cannot dodge the documentation test.
- **One deliberate tension.** The brief says "no retries on the request path" and also "reuse the stale-token fix". The only retry is `GraphClient`'s once-after-a-401/403-`Authorization_RequestDenied` refresh, bounded by its 60 s cool-down, so a missing role costs one extra call a minute at most and the negative cache then absorbs five minutes of requests; there is no other retry.
- **Configuration.** `CHANNEL_RESOLVE_DISPLAY_NAMES` (default false in code); Terraform `channel_resolve_display_names` (default false) emits the setting only when true, so the default plan is unchanged; azd value `TCC_CHANNEL_RESOLVE_DISPLAY_NAMES` is mapped in `infra/main.tfvars.json` with a `false` default (D-106's reason for leaving the debug switch unmapped, a demo toggle that could fight the overlay, does not apply: this is a stable per-environment capability the brief asks to be an azd value).
- **Admin action.** `assign-channel-roles.ps1 -GrantUserReadBasic` gives only `User.ReadBasic.All`, to the gateway identity only, idempotently; it needs `-GatewayIdentityPrincipalId` and, when the caller may not grant, prints the exact command and exits 2 like the other roles. SECURITY.md records why that role and nothing broader.
- **Privacy.** A name and UPN reach only the audit columns, the API's acting-user header and the author of a write; tests assert they are absent from logs and request summaries.
- **Not verified.** Anything live (the role, Graph, the token refresh on the platform).

## D-108 CH-15b: the agent icon is SVG in the repo and PNG only as build output

- **Context.** One icon is wanted for the Teams / Copilot listing and the Cowork plugin. The export audit forbids committed rasters, and the Cowork build used to draw a placeholder (a ring and a dot) from first principles.
- **Choice.** The two SVGs live in `channels/branding/`; `scripts/render-icons.py` (logic in `scripts/branding_icons/`) renders `color-192.png` and `outline-32.png` into the gitignored `dist/branding/`. Renderer order: `cairosvg`, then Playwright Chromium. On this Windows machine the Cairo DLL is absent (`no library called "libcairo-2"`), so Chromium (an existing frontend-tooling dependency) is what ran; both are pinned in `scripts/requirements-icons.txt`, dev-only and absent from `backend/requirements.txt`. The tests assert dimensions, an alpha channel, transparent colour-icon corners, and a white-only outline using a stdlib PNG reader (`branding_icons/png.py`), so they do not depend on which renderer ran; they skip with the reason only when no renderer exists.
- **Publish.** An explicit icon path must be valid (an error otherwise); an unset one is used when the rendered file exists; `''` means none. Validation (signature, size, RGBA for the outline) happens before any request so a bad icon cannot spend a version number. The body printer replaces icon fields with their length. `-DeveloperName` gets `ValidateLength(1,32)`; the default (24 characters) was already within it. Existing publish tests pass `''` for both so a rendered `dist/branding` cannot change them.
- **Cowork.** Placeholder drawing is deleted rather than kept as a fallback: shipping a different icon silently would be worse than stopping (`TCC-I001`). Renderer output is not guaranteed byte-identical across Chromium versions, so determinism is "same icons in, same zip out", and the PNG hashes go in the build manifest beside the zip, never in a tracked file. The `accent_color` default moved from the old blue to the icon's mid-gradient `#2A4FC2`. The line-ending test needed `crlf.mkdir()` because removing `assets/` changed the traversal order it relied on (no assertion changed).

## D-109 CH-15c: narration quality, a hedging guard, and descriptions that separate the book from one client

- **Context.** Live (3 Nov) the narration of a whole-book question was clumsy ("their position 1 and the reason given: On the line"), a model called an exact figure "rounded", dropped the `facts.` prefix, and occasionally planned the whole-book tool for a one-client question.
- **Narrator prompt (v2).** `channel_narrator.md`: senior-colleague voice (answer first, then the reason, one to four sentences), the engine's reason labels verbatim by placeholder, no rank prose, no hedging word, copy the `placeholder` character for character, and six worked examples (book, brief, both methods, trend, at-risk, refusal) with no digit in them except a list index inside a fact path. That index (`clients.0.name`) is addressing, not a figure, so `test_its_instructions_carry_no_digit_to_copy` was narrowed to ignore a digit between two dots; every other digit is still refused. The manifest records version 2 beside version 1. `test_orch_e2e` pinned the audit's `agent_version` as `7+prompt1`; it is `7+prompt2` now (the pin exists to notice exactly this). A new test composes every example reply through the real composer, so the prompt cannot teach a shape the composer withholds.
- **Hedging guard.** `application/composer_hedging.py` (standard library; a `composer_*` sibling so it is vendored and passes the composer's import allow-list unedited). Strict and structural: a qualifier (about, around, roughly, approximately, nearly, almost, rounded, circa, ballpark, `~`, and the phrases up to, close to, or so, more or less, give or take, just over and similar) within three tokens, either side, of a figure rejects the narration, so "not rounded" is rejected too. A placeholder is a figure by construction: the check runs on the narration with placeholders masked (the same masked text the digit gate reads), which is equivalent to checking after substitution without having to guess how a formatter prints. "estimate" is deliberately not a qualifier: the platform itself labels an open year's run-rate an estimate. A rejection is a `Violation` of kind `approximation` with a fixed code and never the words, and it degrades exactly like a bad digit (blocks and disclaimer, a line saying the commentary was withheld). Known limit: a hedge four or more tokens away is not caught, and rank prose built from a placeholder (`position`) is accepted by the composer; the prompt forbids both and the eval flags the second.
- **Planner.** Client resolution was already code (`ToolRunner.ensure_client` runs `client_resolve` before any client tool and overwrites the model's client id); the failure was the model's choice of tool. So the repair is in the words: every client tool's catalog description now begins "ONE client (needs a client)", `book_rank` says "WHOLE BOOK only" and "Never use it for a question about one client", and the planner and JSON-plan prompts state the test (a named client, "them", "their", "this client") and who resolves the client. These descriptions are shared with the Cowork MCP tool list, which is a benefit (Cowork's model has the same trap), and no test pinned the old wording. A code-level refusal of `book_rank` for a client question was considered and rejected: it needs the client resolved before the model chooses, which changes every golden's gateway sequence and would refuse a legitimate "who should we call" asked after a client was discussed.
- **Goldens and tests.** `golden/planning.json` (ten cases: whole-book without a client resolve, a named-client brief, a "their" follow-up on the same client, a book question after a client, a what-if, an at-risk question, keyword mode never ranking the book, and three narration-style cases) plus `test_orch_planning.py` (description and prompt wording). The keyword table sends "Give me a brief on X" to `eligibility`, not `situation`; that is the shared table's behaviour and is recorded as a live-only eval row rather than tuned here.
- **Evals.** `routing.jsonl` gains `forbidden` (a capability that is wrong even beside the right one) and eight offline rows plus two live-only; `narration.jsonl` gains rows with a `narration` (placeholders), `brief` (facts), `must_contain` and `forbidden` patterns, judged through the real composer, with default forbidden wording (hedges, rank prose); six pass rows and eight reject rows, `by: composer` where the composer itself must drop it. The offline thresholds stay 1.0; live narration rows with a `narration` are left out of the live run (the live narrator evaluation of this prompt is unbuilt).
- **Not verified.** How a live model follows the new prompt, and whether it stops choosing `book_rank` for a client question. That needs the redeploy and a live run (`scripts/live-ai-checks.py`).

## D-110 CH-15d: the portal chat emits `evidence`, built from the envelope, by a tap and not by rewriting the pipelines

- **Context.** The Ask workspace draws typed evidence, but `/api/chat` emitted none, so the right pane showed only "Show on page" links. Every portal pipeline calls a capability, keeps `.facts` for the narrator and drops the envelope. Three of them (`_pipeline_eligibility`, `_pipeline_portfolio`, `_pipeline_simulate`) and `_dispatch` are already over the size and complexity baseline, so adding lines to them would have worsened the ratchet.
- **Choice: tap, wrap, no new lines in the long functions.** A pipeline passes the capability result through `tap(result)` (`api/chat/evidence_tap.py`), which notes it in a per-request ContextVar and returns it unchanged; `_run_intent` now wraps the pipeline in `with_evidence`, which emits one `evidence` event ahead of the next frame the pipeline yields. The change inside the pipelines is `x(...).facts` to `tap(x(...)).facts`, so no function grew. The sink is cleared with `set(None)` and not `reset(token)`: an async generator may be closed in another context. A request that never sets it (the REST endpoints calling `_book_brief`, the page summary) makes `tap` a no-op.
- **Choice: `tool` is the chat intent.** The contract says `tool` is "a capability from the `plan` event", and two intents (`multi_state`, `discovery`) share one tool, so the item carries the intent and a fixed tab title per intent. Ids are `ev-<intent>-<n>`: a later turn's answer replaces the earlier tab of the same intent, which keeps the pane from growing a tab per question (the contract's re-sent-id rule).
- **Choice: reshape, never reformat.** A heading titles the block after it; a table's header row becomes `columns`; every cell passes through as the envelope's own string; no `align`, no `kpis` (inferring either would be the platform guessing). `warnings` become `Note` callouts (`tone: partial`) because "the claimed side is an unverified assertion" must reach the reader; `provenance.assumption_set_id` and `source` have no slot in the contract and are not sent. Facts are top-level scalars as strings; a bool or null is left out.
- **Choice: sensitive rows.** `sensitive` (from the catalog) or an unknown tool withholds a table unless `principal.authenticated`; the table becomes a text block that keeps the count and the item's facts are emptied. A new ContextVar `_AUTHENTICATED` (default False) is set in `chat()` beside `_ACTOR`; under `AUTH_MODE=none` the principal is `ANONYMOUS`, so rows are withheld there, which is the "when in doubt" side. No portal-reachable capability renders an employee row today (D-08: at-risk blocks are counts, and `employee_drill` / `findings_list` have no portal intent), so the rule is a guard and the tests use synthetic rows. The model is never handed `blocks`, so it never sees rows in either case (a test asserts the narrator's prompts).
- **Choice: `confirmation` stays inert.** The portal chat has no write flow. Said in the contract's new Status section.
- **The real shape differs from the fixtures in four ways, and the frontend is unchanged.** `tool` is the intent (the fixtures also use intent names); headings become block titles; no capability emits `kpis` (the fixtures do, and the component still draws them); `provenance` is often absent (a claims-only read has no run). The golden file `frontend/src/lib/askBackendShape.json` holds two real items; the backend test compares to it and `AskWorkspace.backend.test.jsx` feeds it through the real `streamChat` reader and the pane, so a change to either side fails both suites.
- **Tooling.** `frontend/tools/mock_api.py` now answers `POST /api/chat` itself with a stream in the backend's framing built from the golden file (previously it forwarded to a backend that cannot boot without Fabric and would have streamed the scripted stub, which emits no evidence); `check_a11y.py` scans the workspace for both the dev fixture and this real shape and fails if the real shape renders no evidence tab.
- **Not changed.** No route (the inventory is untouched), no existing SSE event or field, the parity pins, the narrator prompts.

## D-111 CH-16a: the semantic model is data with decisions in it, and the ratchet does not see `application/data/`

- **Context.** Prompt 9 gives the agent governed data access. The model must say what can be queried, what a row is, what is sensitive, and which tool is authoritative, and must break the build when the schema moves without a decision.
- **Choice: Python data modules, not JSON.** Typed, validated at import (a dangling join, a blocked column with an operator or a non-identifier name raises), no file I/O in the application layer, packaged with the code. A small `Cols` vocabulary carries the defaults so an exception is visible.
- **Choice: sensitivity describes the RAW value.** A dataset is `employee_level` when a row is a person or a person-period (4 of 11). Whether a *query* returns person-level rows is a property of the spec (CH-16b `classify`): any selected `employee_level` column, any identifier, or no measure on an employee-level dataset. An aggregate over `employee_level` columns is not itself employee level.
- **Choice: employee ids are `blocked`, the token is the handle.** `employee_id` (tokenised), `client_employee_id` (lakehouse) and `triggered_by` (staff UPN) are modelled as `blocked` so they are a decision, never an omission. The lakehouse holds no record token (it is derived per programme and tax year), so source payroll rows are anonymous.
- **Choice: currency is part of the dataset.** Gold reads pin the live run (`LIVE_RUN`, as the portal's readers do through the manifest) or `is_current`; `run_manifest` and the source tables have none. Without this a query would mix superseded and current figures.
- **Choice: no `tax_year` on the source payroll.** A tax year follows the client's fiscal window; the source has dates only. It offers `pay_year`/`pay_month`, described as calendar values and "not the tax year", as derived columns with a T-SQL and a SQLite form.
- **Choice: three declared fixed joins, all many-to-one and all LEFT**, on the lakehouse payroll (`location`, `worksite`, `pay_code_info`), so a join can never multiply or drop base rows. No Gold join: a Gold worksite id cannot be joined to a lakehouse name in one statement; the catalog's distinct-values tool resolves the name first.
- **Choice: exclusions carry reasons.** 19 Warehouse and 7 source tables are on `model_excluded.py` (operational, audit, global registries, no client key, employee-level audit rows deferred). The drift test refuses a table on both lists.
- **Choice: the doc is generated** (`model_doc.py`), and a test compares it byte for byte.
- **Found.** `tools/code_standards/baseline.py` skips any path with a `data/` part (meant for the synthetic generators), which would exempt `application/data/`. Not changed (it would move the baseline); `tests/test_data_access_standards.py` measures the package directly with no baseline.
- **Not changed.** The parity pins, the route inventory, any existing test.

## D-112 CH-16b: a specification has no field SQL could go in, the statement carries a marker not a client id, and a few small choices

- **Context.** The builder must make "no model writes SQL, every value bound, client scope first" structural, not a convention, and `application/data/` is stdlib-only, so it cannot import `tenant_sql` from infrastructure.
- **Choice: the builder emits the `{tenant}` marker; the executor binds it.** `build_sql` returns `(sql, params)` with `{tenant:t}` as the first term of every WHERE and `{tenant:alias@AccountId}` as the first term of every join's ON (and `{tenant:m}` inside the live-run subquery); `params` excludes the client. CH-16c runs it through `TenantScopedQuery(plan.client_id)`, which refuses a statement whose marker is not first. Tests bind every generated statement through the real helper.
- **Narrow change to `tenant_sql.py`.** The marker grew an optional `@Column` from the closed set `{client_id, AccountId}`, because the lakehouse keys on `AccountId`. The name is interpolated, hence a closed set. Backwards compatible; existing tests unedited; module held at 250 lines.
- **Choice: no field for SQL, and unknown names are never echoed.** The spec is a closed JSON object (`additionalProperties: false`), `from_dict` refuses unknown keys, and an error message names a field, never the caller's value or an unknown column name. Equality-style text values are screened for SQL on their NFKC form and for control/format characters; `contains` on a declared free-text dimension skips the keyword screen (as Prompt 9 says) but still refuses control characters, is length-capped, lowercased on both sides and LIKE-escaped (`\ % _ [`).
- **Choice: the measure alias is the one validated, not whitelisted, identifier** (`^[a-z][a-z0-9_]{0,39}$`, quoted). Everything else interpolated is model text or a configured schema name checked as an identifier. The row limit is an integer literal (`TOP (n)` / `LIMIT n`), capped at 500; binding it was rejected because Fabric's support for a parameterised `TOP` is unverified and the integer is validated twice.
- **Choice: one extra row is fetched** (`TRUNCATION_PROBE = 1`) so CH-16c can report "capped" without a second COUNT. The executor drops the extra row.
- **Choice: method is never chosen silently.** A dataset with a method column returns it first in every result and groups by it; `method` defaults to `both` (no predicate), `min_max`/`pay_period` pin it. A dataset without one refuses a `method`.
- **Choice: currency is applied by the builder.** `is_current = 1`, or `run_id = (live run subquery)` mirroring `gold_reader._stmt_latest_run` (success, not superseded, completed, newest first), both bound and tenant-scoped. A test fails if the manifest columns it names leave the DDL.
- **Choice: aggregates over a measure are the only way to use one.** A measure cannot be grouped by (as Prompt 9 says), so a distribution is a min/avg/max/count by a dimension. Selecting a raw measure beside aggregates is refused (`group_by_measure`). Integer `AVG` is widened to `DECIMAL(19,4)` in T-SQL (it would otherwise truncate); a flag is summed as `CAST(.. AS INT)`.
- **Choice: audience is a property of the query.** `result_audience(plan)` is `user` if any selected column is `employee_level` (a record token, a raw pay figure) or an employee-level dataset is read without an aggregate; otherwise `both`. `employee_level_labels(plan)` names the result columns CH-16d must keep out of facts.
- **Known gaps left for later WPs.** Small groups (an aggregate over one person) still reach the model; the lanes, not the model, are the control, and the doc says so. `tax_years` outside what a client holds is enforced only when the caller passes `known_years` (CH-16c reads it from the client's scope). T-SQL is verified by string and shape tests, not executed: no T-SQL engine runs offline.
- **Not changed.** The parity pins, the route inventory, any existing test, the architecture test.

## D-113 CH-16c: execution is an application port with three adapters, limits refuse rather than queue, and provenance hashes structure only

- **Context.** CH-16b produces `BuiltQuery(sql, params, plan)` with a `{tenant}` marker. Something must run it read-only on the Warehouse, the lakehouse endpoint or SQLite, bound to one client, within time, row and rate limits, and describe what it returned.
- **Choice: the port takes `client_id` beside the statement.** `DataQueryExecutor.execute(sql, params, *, client_id, timeout_s, max_rows) -> Rows` (the prompt's signature plus `client_id`): the scope is bound by `TenantScopedQuery` inside the adapter, the only place allowed to touch a cursor, and the statement carries a marker, never an id. `Rows(columns, rows, truncated)`; the adapters fetch `max_rows + 1` and drop the probe row.
- **Choice: one T-SQL core, two connections.** `TsqlDataQueryExecutor` (`warehouse_data_query.py`) serves the Warehouse and, over `LakehouseSqlConnection`, the lakehouse endpoint. `LakehouseSqlConnection` subclasses `FabricWarehouseConnection` (same managed identity and token) with its own pool, because the Warehouse pool is process-wide and unkeyed: borrowing from it would hand a lakehouse link to a Gold read. Settings follow the Warehouse pattern with defaults the repo already has: `LAKEHOUSE_SQL_SERVER` (default `WAREHOUSE_SERVER`), `LAKEHOUSE_SQL_DATABASE` (default `FABRIC_LAKEHOUSE`).
- **Choice: `DATA_QUERY_SOURCE_ENABLED` (default false in code) gates the lakehouse source datasets only.** The Gold and ops datasets are not behind it (they exist wherever Gold does); the prompt's wording ("lakehouse ... feature-flag") was read that way. A disabled source is `data_source_disabled`, an unconfigured one `data_source_unavailable`; there is never a fallback to another store.
- **Choice: read-only guard.** The statement must start with `SELECT` and contain no `;`, and also no comment marker (`--`, `/*`): every value is bound, so a legitimate statement has no reason to. A test proves the guard accepts every statement the builder can emit (11 datasets x 25 specs x 2 dialects).
- **Choice: limits refuse, never queue.** `DATA_QUERY_TIMEOUT_SECONDS` (20; pyodbc query timeout set on the borrowed connection and reset to 0 before it returns to the pool; SQLite uses the progress handler) -> typed `query_timeout`, never partial rows, and the connection is discarded (which also cancels the statement). `DATA_QUERY_MAX_ROWS` (500) can only lower a specification's limit. `DATA_QUERY_RATE_PER_MINUTE` (30) per person via the gateway's token bucket and `DATA_QUERY_MAX_CONCURRENCY` (4) via a bulkhead that refuses after 0.25s (`query_budget_exceeded` with `retry_after_s`, `query_busy`). A specification that fails validation costs no budget. All per process.
- **Narrow change: the token bucket moved.** `channel/limiter.py` -> `application/rate_limit.py` (the API-process data layer cannot import `channel`, which depends on `application`); `channel.limiter` re-exports it, so no gateway import or test changed except the gateway's allow-list in `tests/channel/test_gw_architecture.py`, which gained `application.rate_limit` with its reason (standard library only).
- **Narrow change: the tenant architecture rule names the adapters.** `tests/test_architecture.py::_tenant_scoped_modules` also includes `lakehouse_data_query.py` and `sqlite_data_query.py` (the Warehouse one matches `warehouse_*.py` already); `tests/test_data_query_architecture.py` adds mutation checks and asserts none can use `tenant_exempt`. `open_attached` lives in `sqlite_data_source.py`, because the rule caught its `ATTACH` as a direct `execute`.
- **Choice: provenance hashes structure, never values.** `statement_sha256` is over the marker-form statement; `params_sha256` over the parameter TYPES in order (plus `param_count`). A filter value is shown only on a `public_aggregate` column; otherwise `<redacted>`. `source_line` is `Source: <source> <schema>.<table>`; `notes` say what a block must state (capped, the server cap, the method, the live run, current rows only).
- **Choice: the live run is read after the data, uncached, through the validated builder over `run_manifest`.** Only `LIVE_RUN` datasets carry `run` (run id, rule pack, both assumption-set ids); `IS_CURRENT` datasets state "current rows only" and claim no run, because their rows are not guaranteed to come from one. A rerun landing between the two reads could make the provenance name the previous run; stated in the module docstring. `as_of` is the run's completion time (`as_of_basis=run_completed_at`) or the query time (`query_time`).
- **Choice: `tax_years` outside a client's data are not wired.** `DataQueryService(years_for=...)` forwards `known_years` to validation, but nothing passes it: the client's years come from a payroll scan that is too heavy to run per data query. An out-of-range year returns no rows, which is honest. CH-16d may pass a cheap source.
- **Choice: SQLite local population.** The adapter takes a connection factory; tests populate it from `tests/data_fixture.py`, and a local run points `DATA_QUERY_SQLITE_DIR` at `<schema>.db` files. Running the engine into SQLite is not built: there is no SQLite Gold writer and the Warehouse writer is T-SQL.
- **Choice: composition in `application/data_wiring.py`,** not `wiring.py` (already over its ratchet baseline; the gateway must not load it). `get_data_query_service()` / `set_data_query_service()`.
- **Not changed.** Parity pins, route inventory, Terraform (the `DATA_QUERY_*` and `LAKEHOUSE_SQL_*` mapping and the lakehouse grants wait for CH-16f; `ENV-VARS.md` rows added now), the code-standards baseline, `tenant_sql.py`.

## D-114 CH-16d: the data tools are three capabilities with a lane on the envelope, and Copilot Cowork is refused employee rows unless the caller is a writer

- **Context.** CH-16a-c built a governed way to query data. The channel needs it as tools (API registry, gateway catalog, MCP list), with the privacy design enforced on the contract rather than by convention, and with a defined answer for Cowork, whose model reads whatever text a tool returns.
- **Choice: the three tools are ordinary capabilities.** `data_catalog`, `data_query`, `data_distinct_values` (`application/capabilities/data_*.py`), registered in `registry.py`, catalogued in `catalog_data.py` (vendored; `catalog.py` splices it in), read-only, `needs_principal`. **No route was added**: `POST /api/capabilities/{tool}` is generic, so the route inventory and every route count are unchanged. The MCP list, `tools/list` annotations (`readOnlyHint`, `idempotentHint`) and the Cowork package validator all derive from the catalog, so they needed no change beyond the connector description in `manifest.template.json`.
- **Choice: `data_query`'s schema is flat (the specification's own fields), its function takes `**query`.** A flat schema keeps `client_id` where the API's entitlement check, the gateway's audit and the orchestrator's client override already look. A parameter per field would be eleven arguments (limit: seven), and a nested `query` object would have needed all three of those places taught a new path to the client. `QuerySpec.from_dict` refuses an unknown key, so the loose signature accepts nothing more. One existing test (`test_every_schema_property_is_a_parameter_of_its_function`) was narrowed to say `data_query` is the named `**`-function; nothing else in it changed.
- **Choice: the schema is written out in the catalog and a test holds it equal to `query_spec_schema(default_model())`.** A vendored catalog module may import only the standard library and its siblings, and the specification lives with the semantic model. The test failed on first run (dataset order), which is the drift check working. `catalog_data.py` and `lanes.py` joined `_VENDORED_CAPABILITY_MODULES` and the vendoring seeds.
- **Choice: the lanes are on the envelope.** `Block.audience` (`both` default, omitted from the wire when `both`, so every existing envelope is byte-identical) and `ToolResult.user_only_facts` (top-level fact keys; omitted when empty). `capabilities/lanes.py` is the one projection a model-facing caller reads: `model_facts` drops the named keys (and `rows` if `facts.audience` says `user` but nothing was named, and caps a `rows` list at 50 for a model), `model_blocks` drops `user` blocks, and any audience word other than `both` is read as `user` (fail closed). The orchestrator's `ToolRun.model_facts` and `compose.model_facts_of` use it; the narrator brief, the tool answer handed to MAF and the JSON-mode narration all take the projection. The composer still gets the full facts and blocks, because the reply is the person's.
- **Choice: a `lookup` tag is the declared exception.** The orchestrator shows a model the NAMES of facts, never values (unchanged). A model cannot write a valid query without reading the catalog or the values of a category, so `data_catalog` and `data_distinct_values` carry `catalog.LOOKUP` and their facts (still through the projection) are handed to the model as `result`, with numeric fact paths only. The catalog holds no row value; a distinct-values call refuses any column whose values describe people (employee-level, identifier, blocked) with `column_not_listable`. Their blocks are left out of a reply when another tool answered, and shown when they are the answer.
- **Choice: Cowork refuses an employee-level RESULT unless the caller is a writer.** The prompt says "employee_level datasets"; read as results, because an aggregate over an employee-level dataset (count of people by location) carries no person and is the question most worth asking. A query is refused when `result_audience(plan)` is `user`: a selected employee-level column, or raw rows of an employee-level dataset. The API checks before anything runs (`DataQueryService.audience_of` validates only: no budget spent, nothing read; the channel comes from the acting user's `channel == "cowork"`, the writer check is the platform's own entitlement), and the gateway checks again on the way back (`channel/lane_guard.py`) so a result that still carries a person-only lane never reaches a non-writer's Cowork text, never enters the fact ledger and is audited `refused`. Code `employee_level_not_available`, HTTP 403, text shared from `lanes.py`. Reasoning in ADR-009 decision 8.
- **Choice: client scope is never free text.** `client_id` is validated by the same `ClientAuthorizer` as every tool (`client_ids(args)` finds it at the top level), the orchestrator overwrites whatever the model passed with the resolved client (`CLIENT_PLACEHOLDER`), and a data tool's `tax_years` is the reader's: a year the model named that the reader did not say (and the conversation is not on) is replaced by the years they did say, or dropped.
- **Choice: the audit line is built by the semantic model.** `AuditCall.summary` replaces `args` in the human-readable summary only (the hash is still over the whole request). `application/data/audit_summary.py` writes dataset, select, group-by, measures as `agg(column)`, years, method, limit and each filter as `column op`, with the value only for a `public_aggregate` column of the named dataset; an employee-level, unknown or join column is `<redacted>`, and a name that is not a plain identifier is `<invalid>`. The gateway imports it (allow-list entry with its reason). `is_deterministic_path` stays true; `run_id` comes from the result's provenance. A data result has no trail, so `trail_sha256` stays empty rather than carrying the statement hash under a name that says "trail".
- **Choice: the table shows 50 rows.** Facts keep up to 500. A channel message with five hundred rows is not delivered, so the block shows the first 50 and says how many it cut. A table that is not the whole result is stated, never implied.
- **Choice: no small-group suppression.** CH-16b flagged that a small aggregate group is close to a person's own figure. Suppressing it would make an aggregate differ from the data, which this product does not do; the person is entitled to the figure, and a model is never shown a value in Teams. Recorded in KNOWN-LIMITATIONS ("Data queries") with what would close it.
- **Existing tests edited (four, narrowly).** `test_capabilities_envelope.py` (the `**query` function, above); `test_architecture.py` (the two new vendored modules); `channel/test_gw_architecture.py` (two allow-list entries with reasons); the orchestrator harness answers the data tools with the real capabilities over SQLite, and `golden/data.json` adds four cases. No assertion about existing behaviour changed.
- **Not changed.** Parity pins, the route inventory, Terraform, the code-standards baseline, the CH-16c service. The planner prompt, narrator examples, skills' "go deeper" step, the 25 goldens and the equivalence tests are CH-16e; docs, ENV-VARS, the Terraform mapping and grants are CH-16f.

## D-115 CH-16e: the agent is taught the data tools in the words it reads, JSON mode reads a lookup before it plans, and the generic query is held equal to the fixed tools

- **Context.** CH-16d gave the agent three data tools. A model uses a tool well only if its description, the planner's instructions and the narrator's examples say when to use it and how to talk about what it returns; and two ways of answering one question (a fixed tool and a generic query) are only safe if they agree.
- **Choice: the decision rule is in the planner prompt, the JSON-plan prompt and the descriptions.** Fixed engine tools first for credit, eligibility, trend, at-risk, what-if; `data_catalog` then `data_query` for a descriptive or comparative question about payroll or enriched data; a "why" question takes the fixed tool first and the data second; `data_distinct_values` turns a name the reader gave into the value the data holds before a filter; never an invented column (a catalog with none for the question means "the data has nothing for it"); every measure named with `as` so the answer can refer to a result column; another client or several is not a data question. `data_query` now begins "(needs a client)" and `data_catalog` says "Needs no client". `test_orch_data_planning.py` pins the words in both prompt forms and in the MAF tool list and JSON catalogue.
- **Choice: JSON mode plans twice, once, and only after lookups.** A plan made only of lookup tools (`data_catalog`, `data_distinct_values`) cannot name a column it has not read, and JSON mode has no tool loop. The planner now runs the lookups, appends their model-visible `result` (the same lane projection tool mode hands back) as one more user message, and asks again, once. A plan that already holds a query, or holds no lookup, is unchanged; a third planning call never happens. This is the smallest change that makes the prompt's "read the catalog" rule satisfiable in the fallback mode; tool mode is untouched.
- **Choice: narrator prompt version 3.** Rules for data results (describe the table and the grouping, never why or "unusual"; "first" only when an order was asked for; say a result was capped and give the limit by placeholder; say plainly when no rows matched or the data has no such column; never describe rows that went to the person alone; the engine's figure is the authority) and six worked examples (a descriptive aggregate, a comparison between methods, a capped result, a catalog miss, employee-level rows, a "why" answered engine-first). Every example reply is composed through the real composer by `test_channel_narrator_prompt.py`. Existing assertions edited, narrowly: the version (2 -> 3) and that the manifest records every version; the example count (4-6 -> 4-12) and the topic list; the e2e agent-version pin now reads the prompt's own version instead of a literal. The manifest was refreshed with `prompt-manifest.py --refresh` after the bump.
- **Choice: a catalog search with no match says so.** The empty table and a generic "pass dataset=<name>" hint read as "try again" and invite a guessed column. The note now says the data has nothing for it and not to guess. The search text is not echoed (it is the model's string and would put unvouched characters in a note).
- **Choice: the failure sentence no longer doubles its full stop.** Several typed refusals end in "." and the orchestrator appended another.
- **Choice: the Cowork skills gain an optional step, not a new skill.** `tcc-client-review-pack` step 8 "Go deeper" (steps 9-12 renumbered, nothing referenced them by number), `references/data-questions.md` (a table of ten useful questions with the fixed tool that stays authoritative), a data section in the shared rules skill that leaves the verbatim and `verify_figures` rules untouched, data error rows in the error table. The validator gained the dataset names and the data error codes as known non-tool names (so `employee_eligibility` is not mistaken for a mis-spelt `employee_*` tool); a test holds every name the table teaches to the semantic model, so a skill cannot teach a column the catalog does not list.
- **Choice: the goldens and evals answer different questions and both are offline.** `golden/data_use.json` (29 conversations) plays a scripted model through the shipped pipeline, composer and numeric guard over the real data capabilities on SQLite and asserts the gateway tool sequence, the arguments the platform settled, the wording, and (new `model_never_sees`) that no prompt carried a person-level value; the runner's existing check proves every numeral in an answer is in the facts or the reader's words. `tests/ai_evals` gains a `data_routing` suite (34 recorded plans run through the real catalog, validator and fixture: sequence, forbidden tools, typed refusal code, lane, cap flag, catalog miss) at offline threshold 1.0, and 15 `nar-data-*` narration rows through the composer. Neither can say what a live model will plan or write; both say what the platform does with it, and tests prove each can fail. `data_routing` has no live threshold: nothing in this repo can run it live yet, and a threshold nobody exercises is a claim.
- **Choice: the equivalence tests run the REAL engine.** The prompt allowed a fallback ("build it via the Gold writers on the synthetic run"). It was not needed: `RunClientCalculationCommand` replays the synthetic payroll, the real `GoldWriter` writes it to SQLite (its statements, its supersession, its manifest stamp; only the T-SQL section-9 validation is skipped), the real `GoldReader` reads it back (only `TOP` and `OFFSET ... FETCH` are translated to `LIMIT`), and the data service reads the same connection. Compared, exactly: eligible and evaluated counts per method and year (against `client_trend` and the population of `client_eligibility`), the annual average (against `client_eligibility`), annual credit per tax year (against `client_trend`) and per unit-year and its headcount (against the units grid read), lifetime tranches (against the installment read), headcount per month overall and per unit (against `headcount_series` and `month_summaries`), and the `onezero_matrix` month sums against `unit_month_summary`, which the model's engine note claims are equal. **No mismatch was found, so no model or builder change was needed.** One honest limit: there is no fixed capability that returns a monthly headcount, so the monthly series is compared to the fixed READER the eligibility and progress views use, not to a tool.
- **Choice: SQLite stores money as a float in this fixture.** The engine's money is whole dollars, so values are exact and the tests compare as Decimals; the deployed Warehouse stores DECIMAL.
- **Not changed.** Parity pins, the route inventory, Terraform, the code-standards baseline, the engine. `DATA-ACCESS.md`, `SECURITY.md`, ENV-VARS rows beyond CH-16c's, the Terraform mapping and the lakehouse grants remain CH-16f.

## D-116 CH-16f: the data settings are optional and emitted only when set, the lakehouse grant is object-level SELECT from the model, and the Fabric data agent stays off

- **Context.** CH-16c/d/e documented the data-query settings but left their Terraform mapping, the lakehouse-endpoint grants and the Fabric Data Agent evaluation to CH-16f.
- **Choice: settings follow the AI-03 pattern.** `data_query_source_enabled` (bool, default false) emits `DATA_QUERY_SOURCE_ENABLED=true` only when true; the four limits and the two lakehouse endpoint settings are strings, empty meaning unset, validated by regex to the ranges the code clamps to (a bad value fails the plan rather than being silently clamped). A default plan is unchanged (asserted: `api_data_query_settings` is empty), and the gateway module is given none. azd values are `TCC_DATA_QUERY_*` and `TCC_LAKEHOUSE_SQL_*`; the flag defaults to `false`.
- **Choice: the lakehouse grant is `GRANT SELECT ON OBJECT::<SOURCE_SCHEMA>.<table>` for exactly the lakehouse datasets of the semantic model, for the API identity only.** Object level, not schema, so a source table nobody modelled is not readable; the table list is read from the model so a new lakehouse dataset and its grant cannot drift (a test compares them). No write, role, `DENY` or schema grant. The script refuses the gateway identity, and the endpoint must be on the same host as the guarded Warehouse (one host per Fabric workspace), else exit 3. postprovision runs it only when `TCC_DATA_QUERY_SOURCE_ENABLED=true`, after the schema grants.
- **Choice: no new workspace role.** The API identity's existing role stays; the explicit `SELECT` makes the read independent of it. Whether the role alone suffices is a live question (CH-17).
- **Choice: the Fabric Data Agent is off, with written conditions for a sandbox-only exploratory lane** (DATA-ACCESS §9): no per-user identity passthrough on this path (service identity, our client predicate is application-level), a model writes the query (against *tools calculate* and the numeric guard, and no lanes), the NL-to-SQL model is not ours to choose, the audit line and the capacity budget do not apply, and the product is preview with a documented tool deprecation. Claims are from Microsoft documentation of 3 November 2026 and flagged to be re-read.
- **Choice: read-only is stated honestly as code-enforced.** The API identity also writes the Warehouse, so the data query is read-only by construction in code, not by a database principal; a separate read-only identity is listed as the unbuilt defence in depth (SECURITY, KNOWN-LIMITATIONS).
- **Changed narrowly.** Nothing existing was weakened: `DEPLOYMENT-HANDOVER.md` gained the azd values the existing contract test demands. No parity pin, route, baseline entry or architecture rule changed.

## D-117 CH-17 (part C1): a distinct-values limit counts values, and the model payload leaves a names-only trace

- **Context.** The live run compared `data_distinct_values` with a direct SQL count: 50 worksites against 101. A dataset holding both statutory readings lists each value once per reading and the limit counted rows.
- **Choice: fetch twice the limit for a method-dependent dataset, merge, cut at the limit, report truncation from the merged list.** The semantic model was right and is unchanged. The tool still says it was cut and never lists a person-level column.
- **Choice: the orchestrator logs one names-and-counts line per tool answer** (`user_lane`, user blocks and fact keys withheld, the keys of the answer, `rows_in_answer`), so a live run can show without reading a row that the person's lane did not reach a model. It takes effect at the next orchestrator deployment.
- **Not done live, on purpose.** The non-writer refusals (they need a second person's delegated token; changing the allow-list or the group is outside a verification part) and a forced statement timeout (it needs load). Both are proven offline.

## D-118 CH-17 (part C2): the narration may never say "rounded", a repeated call is answered once, the model's capacity is raised, and the data questions are taught what they cannot do

- **Context.** Ten live questions through the hosted agent (Responses, the operator's identity) found: a narration that said "Rounded to the nearest thousand" with no figure beside the word (it passed the three-token hedging window); the same eligibility call run twice and shown twice; a what-if that asked for the size the reader had given; location, month and "weekly hours" questions routed to client-wide tools or to a mislabelled average; the framework's stop message shown as the first line of a reply; and `429` answers from a model deployment of 20 thousand tokens a minute.
- **Choice: a rounding word anywhere in a narration is a violation.** `composer_hedging.states_rounding` (`rounded`, `rounding`, `round`, `approximate`, `approximately`, `approximated`, `approx`). The narrator prompt already said never to say a figure is rounded, even to deny it; the structural check now holds that line. A rejected narration costs the reader nothing (the engine's answer shows without commentary).
- **Choice: a repeated identical tool call returns the first answer.** Same name, same arguments, no second run, no second table. A different call is untouched. The turn's budget still counts both.
- **Choice: the framework's stop message is never narration, and the budget is 8.** A data question is a catalog read plus one or two queries; 6 was too tight. The setting stays `CHANNEL_MAX_TOOL_CALLS` (1 to 20).
- **Choice: planner rules, not new tools.** A question narrowed to a location is a data question; name an average of `hours` per pay period, never weekly; a query takes six measures, so twelve months go in two; filter a location only with a code the reader gave; the what-if takes the named location and the number said. The tool set, the numeric guard and the lanes are unchanged.
- **Choice: narrator prompt version 4.** Do not restate the question's claim as a finding (a difference or overlap the table does not hold); when asked to round or estimate, say the platform gives every figure exactly as computed; do not repeat a count the table states. The whole-book example lost its repeated count.
- **Choice: the model capacity goes from 20 to 100 (thousand tokens a minute) through the overlay value `foundry_capacity`.** A GlobalStandard deployment's capacity is a quota ceiling with no idle cost; the change was one in place update, the next preview showed none, and the agent invariants held. Raising it was not named in the stage prompt; it is recorded here and in the private notes with the one-line revert.
- **Honest outcome.** Eight of ten questions are answered well; one is an honest non-answer and one is partly answered with its narration correctly withheld. They are recorded as limitations, not hidden: the planner is a small model and the two weak spots are the twelve-month series and a per-location average.
- **Not changed.** The numeric guard, the lanes, the data capabilities, the statute, every pinned figure, the route inventory.

## D-119 RM-01: small groups are left out and counted, never altered; K is a floor of 2 with a default of 5; a writer is exempt

- **Context.** CH-16d decided against minimum-group-size suppression because hiding a group "would break exactness". The remediation brief asks for it: an average over one worksite employee is that employee's figure, and over Cowork the text a tool returns is what the model reads.
- **Choice: reconcile by reporting, not altering.** A group below K is **omitted**, never merged into an "other" bucket (an average, a distinct count or a min/max of a merged group is not computable from the groups' own results) and never rounded. Every figure shown is exact, and the number of groups omitted is exact too (`facts.small_groups.suppressed_groups`, a note, the provenance). CH-16d's objection was to silent alteration; this is neither silent nor an alteration.
- **Choice: the size is people, counted in the same statement.** Each employee-level dataset declares a `person_key` (the tokenised employee id; the payroll source's employee key), a hidden `COUNT(DISTINCT key) + MAX(CASE WHEN key IS NULL ...)` column rides in the statement (a row with no key counts as an unknown person, so a null key cannot make a group look empty) and the service strips it. One statement, so the tenant predicate is still first and no second query runs. `require_person_keys` fails the service build if an employee-level dataset lacks one.
- **Choice: applies to aggregates over employee-level datasets only.** Raw rows are the person's lane (never a model's; Cowork refuses them to a non-writer) and are not suppressed. Datasets that are not employee-level (`unit_month_summary`, `unit_year_master`, the credit and ops datasets, `location`, `pay_code`) are not suppressed: their grain is already a worksite or a year and no person key exists. This is the answer for the "both" lane: only the employee-level datasets need the rule.
- **Choice: an ungrouped aggregate is one group, a grouping of singletons is refused.** An average over a filter that isolates two people is withheld like any small group; a group-by whose every group is one person fails with `groups_are_individuals` (422). Filters, derived columns and the method column shrink groups inside the same statement, so they are covered by construction.
- **Choice: K is `DATA_MIN_GROUP_SIZE`, default 5, clamped to a floor of 2.** `QueryLimits` refuses to be built below 2 and the setting reads a lower value as 2, never as off. Not mapped in Terraform: it is a privacy floor, so the code default is the deployed value.
- **Choice: a writer is exempt, in every channel.** The writer entitlement is the platform's own bar for seeing and changing a client's employee data, and the API's client check ran before the capability. This build has no per-client ownership, so "a writer viewing their own client" is a writer on an authorised client. An unknown or anonymous caller is suppressed.
- **Choice: `data_distinct_values` obeys the rule.** A value held by fewer than K people is not listed; a free-text dimension such as a job title would otherwise name a single person through its row count.
- **Honest limits.** Not a defence against differencing; when the row limit cuts a result the omitted-group count covers only the groups fetched; the omitted count is itself a small disclosure. All in KNOWN-LIMITATIONS.
- **Tests.** `test_data_small_groups.py` (35, over a database with groups of 6, 5, 3, 1 and 1 people), three architecture tests in `test_data_query_architecture.py` (every capability that runs a query states who is exempt; only the service applies the rule; every statement that counts people passes the read-only guard and runs). The shared fixture runs at K=2 (it holds two people per client); the rule itself is never weakened.

## D-120 RM-02: only a positively first-party channel is handed employee rows, the API checks for itself, and an agent's claimed channel is bound to its app id

- **Context.** The Cowork rule asked "is this Cowork?" (`channel == "cowork"`). A caller whose channel was missing, unknown or `api-test`, or a person's own token sent straight to the API (no acting-user header, so no channel at all), was therefore not Cowork and was handed employee rows. And an agent's `X-Channel` was checked only against an enum, so any registered caller could claim Teams.
- **Choice: the test is positive and lives in one place.** `ActingUser.is_first_party` is true only for `teams` or `m365-copilot` with a `channel-asserted` assurance (`domain/channel_trust.FIRST_PARTY_CHANNELS`); the API's `data_access.is_first_party` additionally requires an agent principal. Everything else is Cowork-like and refused employee rows unless a writer. `is_cowork` keeps its name and now means "not positively first-party". An AST test fails if any code compares a channel to `"cowork"` again.
- **Choice: the API does not rely on the gateway.** The pre-run check in `data_query` stays (nothing is read for a refused caller), and `invoke` now runs `refuse_user_lane` on every finished result, so a capability that forgot the pre-run check, or one added later, cannot hand a person-only lane to a Cowork-like caller. The gateway's `lane_guard` is the third copy, now positive as well. A person's own token is Cowork-like at the API, so a non-writer calling the API directly gets aggregates only.
- **Choice: an agent's channel is bound to its registered app id with `CHANNEL_CALLER_CHANNELS`.** `<app id>=<channel>|<channel>` over the two first-party channels only (an agent can never be bound to `cowork` or `api-test`; a bad entry fails startup). With any entry set the registry is authoritative: a caller it does not list, including a role holder, asserts nothing (`403 channel_not_allowed`), as does a token with no app id. With none set, every registered caller keeps the enum-level trust it had and the gateway warns at startup. That default is deliberate: the setting cannot be mapped in Terraform in this work package (infrastructure was not in scope, and the live overlay is not ours to edit), and failing every role-authorised orchestrator on the next deploy would take Teams down. The residual is said in KNOWN-LIMITATIONS, with the one-line closer (set the setting).
- **Choice: no channel an agent can claim is added.** An agent claiming `cowork`, `api-test` or an unknown channel is a 400 as before; a person's token is `cowork` whatever headers it carries.
- **Tests.** `test_cowork_fails_closed.py` (31: a person's token straight to the API, a forged channel header on it, an agent with no, `cowork`, `api-test`, unknown or delegated-assurance channel, writer and non-writer, the `invoke` wall, and an AST test that nothing compares a channel to `"cowork"`) and `channel/test_gw_channel_binding.py` (the binding, the spoof, no-registry behaviour, the lane guard per channel, the start-up warning). Three existing tests changed on purpose: the portal-user row now expects a refusal for a non-writer, the HTTP catalogue test compares with the caller shape it actually is, and the shared refusal message names "any client other than Teams or Microsoft 365 Copilot Chat".
- **Not changed.** The writer rule, the lanes, the small-group rule, the route inventory, Terraform, the numeric guard.

## D-121 RM-03: authentication is the default, `none` is a stated local opt-in, and a failed audit write always raises an alert

- **Context.** `AUTH_MODE` defaulted to `none`, so an environment that forgot the setting served every route to anybody; the startup check only refused `none` with customer data. Separately, a failed audit write was logged where it was caught and nowhere a person looks: the closing channel event, the narrator's agent-action row and the narration report each swallowed or surfaced it differently, and nothing a log alert could key on existed.
- **Choice: `AUTH_MODE` defaults to `entra`; `none` needs `ENVIRONMENT=local` SET.** `application/auth_policy.py` is the one reader (an architecture test fails if another module names `AUTH_MODE`; `channel/config.py`, which refuses `none` outright, is the stated exception). An unset `ENVIRONMENT` still means "local" for store defaults, which suits a clone and is not permission to skip sign-in, so `explicit_local_dev` reads the raw value. Startup fails in every other environment, with a message that says how to opt in. The hint is on the tenant error, because that is what an environment that said nothing now meets first.
- **Choice: one second route to `none`, for the deployed synthetic demo.** The Terraform public profile is a deployed (`ENVIRONMENT=azure`) demo over synthetic data with `AUTH_MODE=none`; refusing it would make the profile un-deployable. `ALLOW_ANONYMOUS_SYNTHETIC=1` together with `DATA_CLASSIFICATION=synthetic` permits it, `infra/main.tf` sets the flag exactly when `auth_mode = "none"`, and the customer classification never honours it (D26 is unchanged). This is the one place the brief's "fails in any environment that is not explicitly local" is relaxed; the alternative was a public profile that cannot start. Entra deployments (the live one, `AUTH_MODE=entra`) are untouched.
- **Choice: the suite opts in explicitly.** `tests/conftest.py` sets `ENVIRONMENT=local` and `AUTH_MODE=none`, the same way it pins `DATA_SOURCE=csv`; nothing was weakened. The frontend stand-in (`frontend/tools/mock_api.py`) never imports the backend, so it is unaffected; a real backend started for it needs the same two variables (documented in `.env.example`, RUNBOOK §10, ENV-VARS).
- **Choice: one alert for an audit-write failure.** `application/audit_alert.py`: an ERROR on the logger `tcc.audit_alert`, message `audit_write_failed source=… operation=… error_type=… fatal=…`, plus a per-source counter (`failure_counts`). It carries no payload and no exception message (a database error can echo the row that failed). Sources: `channel_audit`, `agent_audit`, `narration`. `fatal` says whether the work was refused (an opening event that cannot be written: the call is not made, `503 audit_unavailable`, unchanged) or the answer stood (a closing event, an agent row). `ChannelAuditor._append` is the one place a channel event is written, so no path can fail without it; the narration report alerts as `narration` when its event cannot be filed and when its agent row is not recorded; the portal chat's recorder alerts as `agent_audit`; the orchestrator logs the same prefix when the gateway refuses its report.
- **Choice: user-lane reads stay fail-closed.** Unchanged behaviour, now tested end to end through the gateway: a read whose opening event cannot be written never reaches the API and no row reaches the caller.
- **Choice: each writer source denies by name.** `infrastructure/auth/writers.py`: `DenyOnFailure` wraps a source so a failure to answer is a denial and a `writer_check_failed` ERROR on `tcc.writer_check` (the source's name and the error type, no oid), counted. The allow-list (a database read that used to raise into the caller) is wired through it; `EitherEntitlement` wraps each of its sources so a broken one denies without hiding the others; the Entra group source and the gateway's own check use the same event. A broken source can no longer look like an ordinary "not a writer".
- **Enforced.** `tests/test_architecture_audit_alerts.py`: every broad `except` in the audit and entitlement modules raises its alert or re-raises; every audit source named at a call site is a declared one and every declared one is used; `AUTH_MODE` is read in one place; the default is written once.
- **Existing tests changed on purpose (nine, narrow).** Those that relied on an unset `AUTH_MODE` meaning `none` now set it (`test_artifacts_api`, `test_auth`'s anonymous-mode test, `test_gw_config`'s entry-point test deletes the API's `none`); the deployed-synthetic-demo environments in `test_deployment_config`, `test_ai_settings` and `test_channel_audit` carry the demo flag; `test_auth`'s parametrised startup table replaced the "none is the default" row (now a different refusal, covered in `test_auth_default.py`) with the demo-flag rows. No assertion about behaviour was loosened.
- **Not changed.** The numeric guard, the lanes, the small-group rule, the route inventory, any live resource (no deployment in this work package: the next `azd provision` adds `ALLOW_ANONYMOUS_SYNTHETIC` to a public-profile API only).
- **Unverified.** The deployed behaviour of the log alert itself (the Log Analytics query is documented in RUNBOOK §13.10, not run against a workspace).

## D-122 RM-04: a seeded abuse fuzzer over the query builder, a closed grammar for derived-column SQL, quotes are values, and four holes it found

- **Context.** The query builder's promises (no caller text in SQL, the tenant predicate first, caps) were tested with fixed hostile lists and valid generated specs. Nothing threw hostile input at every position at once, the one SQL text the model carries (a derived column's expression) was reviewed by eye, and the value screen refused names that were fine: `Bakers' Group`, `Smith' and Sons` and `Cooks' Order House` all matched the quote-and-keyword pattern, though a quote cannot alter a bound parameter.
- **Choice: a seeded, deterministic generator, not hypothesis.** It is not a dependency, and a failing seed must replay from the test id (`category:seed`). `tests/test_data_query_abuse.py` poisons identifiers, filter values, IN lists, derived-column references, limits and the payload's shape (500 seeds per category and dialect, about 3 seconds). For every query that builds and every one refused it asserts: a refusal is a typed `QueryError` and never a crash; no caller string reaches the SQL text (and every placeholder has a parameter); the `{tenant}` markers are exactly the ones the plan's tables account for, the bound WHERE starts with the client predicate, and removing or moving it makes the tenant helper refuse; the caps hold (limit, items per list, parameters per statement). Hostile values are also executed against the SQLite fixture: a quote injection matches nothing and the tables survive. A mutation (restoring `$` in the alias pattern) fails five tests, so the suite bites.
- **Found and fixed by it.**
  1. **A trailing newline passed the identifier patterns.** `^...$` also matches before a final newline, so an alias `n\n` was interpolated into the statement (`AS [n\n]`). Not an injection (it sits inside the quotes) but a caller string in SQL text, and a newline in an audit line. `IDENTIFIER`, the column reference and alias patterns, the audit summary's name pattern and the date patterns now end in `\Z`; an architecture test fails on any `^...$` pattern in `application/data`.
  2. **A list of tax years was uncapped.** `MAX_YEARS` (12) applied to the `{from, to}` form only; a list took any length (bounded only by dedupe to 101 years). A list over 12 is now `malformed_spec`.
  3. **A client id of 10^30 validated.** It would have failed at the driver, not at the scope, but a client that is not a BIGINT is not a client. `client_id` is 1 to 2^63-1.
  4. **The tenant helper accepts a statement with one marker missing.** Removing only the base table's marker from a live-run dataset's statement still binds (the manifest subquery's marker is still there). The builder always writes the base marker first, and the fuzzer checks that against every statement it builds, so nothing reaches the helper without it; the helper itself cannot know which tables a statement reads. Recorded as a limit, not changed (the tenant helper is shared by every Warehouse adapter and its contract is in `test_architecture`).
- **Choice: quotes are not screened.** `_SQL_QUOTE_TRICK` is removed from `values.py`. The second wall keeps what a bound value can still be and a legitimate value is not: statement punctuation (`;`, `--`, `/*`), a leading `select ...`, `xp_`, `@@`, and control or invisible characters. `O'Brien` already passed; `Bakers' Group`, `Smith' and Sons` and `Cooks' Order House` now do. Existing tests changed on purpose (narrow): in `test_data_validate.py` three quote-only values (`x' OR '1'='1`, `x" OR "1"="1`, `x' = '`) moved from "refused" to a new test saying they arrive as the value, verbatim, and in `test_data_capabilities.py` the "hostile filter value is refused by name" example is now `x'; DROP TABLE t; --` (the old example was quote-only); the abuse tests prove quote-only values are bound and match nothing. Values that also carry `;`, `--` or a statement keyword are still refused.
- **Choice: the derived-column expression is an allow-list enforced where the column is built.** `application/data/expression_grammar.py`: declared columns only (each dialect naming exactly `depends_on`, in its own quoting), `YEAR`, `MONTH`, `COALESCE`, `CAST ... AS INTEGER`, `strftime` with `'%Y'` and `'%Y%m'`, integers of up to four digits, `+`, `*`, parentheses, commas. `Column.__post_init__` calls it, so a model with any other expression cannot be constructed (20 refusal cases: subselect, `;`, comments, another function, a literal, an undeclared column, the wrong dialect's quoting, a wide cast, unbalanced parentheses, fullwidth letters, an empty string). Widening it is a change to that file and its test.
- **Not changed.** The numeric guard, the lanes, the small-group rule, the route inventory, the tenant helper, any capability's behaviour.

## D-123 RM-05: a narration may not point into the person's lane; the data tools have no door past the guard; coverage for both

- **Context.** The lanes keep employee-level rows from a model (ADR-009): the narrator's brief names only `model_facts`. The numeric guard already rejects any typed digit in a narration, so a model cannot type a wage. What was not pinned, and was open: the orchestrator composes against the reader's FULL facts (the person's reply shows the rows and is verified against them), and a placeholder only had to name a path that exists there. A narration `{{facts.data_query.rows.0.total_wages}}` therefore rendered a figure only the person's lane holds. No model saw the value (the platform renders it, and the reader is the person the rows belong to), but the narrator had been handed a path outside its view and the claim "figures from the user lane are not allowed context for the narrator" was true of typed digits only.
- **Choice: close it in the orchestrator, leave the composer alone.** `compose_reply` (the one caller of `compose`, now an architecture test) first asks `paths_outside_model_view`: placeholder paths that exist in the reader's facts but not in `model_facts_of` (the person's lane, and rows past `MODEL_ROW_LIMIT`). If any, the narration is dropped whole, the platform's blocks and the disclaimer are shown (the person's rows included, verified as before), and the guard verdict is `rejected` with one violation whose reason is a fixed code (`narration named a fact outside the model's view`), never the path. The vendored composer, the guard and the formatter are untouched; goldens pass unchanged. It takes effect at the next orchestrator deployment (RM-16 is not done in this work package).
- **Tests.** `tests/channel_orchestrator/test_orch_numeric_lanes.py` (33, through the whole turn on the real data capabilities): the wages exist only in the lane; the allowed numerals never hold them; a typed wage is rejected and the table still shows; a placeholder into the lane is rejected (four paths); `row_count` and an aggregate's rows still render; rows past the cut are not a target; for `data_catalog`, `data_distinct_values` and `data_query` a figure the tool did not return is rejected, one it did return is rejected if typed and rendered if named, an invented path is rejected, and the tool's facts are the guard's facts; the composer is reached only through `compose_reply`; every data tool is an ordinary read the model may name. `tests/test_numeric_guard_lanes.py` (14) pins the same rule at `lanes`, `FactIndex`, the guard and `AllowedContext` with no orchestrator. `tests/channel/test_gw_numeric_lanes.py` (14) pins the gateway side: each data tool's facts are recorded so `verify_figures` passes a figure and rejects it with a digit changed; a conversation that was told nothing verifies nothing; a Cowork caller refused employee rows never has them in the ledger, so a figure only those rows held is "not told"; a writer who was handed the rows may verify against them (what a person was handed is what their conversation was told); the ledger forgets no data tool and only tools that exist. A mutation (the new check patched out) fails six tests.
- **Honest limit.** The gateway ledger records a first-party caller's full facts, user lane included, because it is what that person was handed. `verify_figures` is not offered to a model (it is gateway-local), so no model can use that to learn a row; if it ever were, the ledger would need the same projection.
- **Not changed.** The numeric guard and the verbatim composer, the lanes, the narrator prompt, any capability, the route inventory, the portal chat path (which still does not validate prose; see the copilot instructions).

## D-124 RM-06: MAF is the orchestration layer except where a guarantee needs code; the hosting package stays out; the write path and review pack are Workflows

- **Context.** The orchestrator used MAF only for a tool loop. RM-06 asked, with evidence from the installed packages, what MAF now provides and which hand-rolled parts must stay. The evidence, the hand-rolled inventory (every component, a verdict, an Outcome column the later packages fill in) and the go/no-go table are in [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md). No production code changed.
- **Choice: verdicts.** RM-07 (generated `FunctionTool`s from the catalog), RM-08 (tool rules as `FunctionMiddleware`), RM-10a (the `Agent` is the planner), RM-10b (write path as a `Workflow` with `request_info`), RM-10c (client review pack as a `Workflow`) and RM-11 (agent as code, scoped to `azure.yaml` and one publish list) are **GO**. RM-09 is **GO, conditional**: MAF's `OpenAIChatClient` / `OpenAIChatCompletionClient` against the account's OpenAI host, because `FoundryChatClient` has no endpoint override and targets the project host that did not resolve from the hosted runtime (D-101); `ModelChain` stays only for a multi-provider or customer-gateway chain. RM-14 is **GO as a time-boxed spike**: in `mcp` 2.3.0 the request's headers reach the handler (stateless and stateful), which removes D-65's stated blocker, but the SDK does not bind a session to its user. RM-12 is **NO-GO**.
- **Choice: hosting stays out (supersedes nothing in D-76, extends it).** `agent-framework-foundry-hosting` has only pre-release builds (newest `1.0.0b261030`; it needs core `>=1.24.0`, so versions are compatible), has no Activity handler (nor do the `azure-ai-agentserver` packages), and per-request identity into an `Agent`'s tools under hosting is not shown to work. Teams does not need the container to serve `activity`: the platform converts an Activity into a Responses call for a Responses-only container, and a container that declares it is sent `/activity/messages` (D-100). `azure.yaml` is unchanged; the host stays behind the `app/main.py` seam and the architecture rule confining `azure.ai.agentserver` to it stays.
- **Choice: confirmation is a Workflow, not MAF tool approval.** Approval is a structured reply to a tool call the model made; Teams sends text, and approval would put `*_commit` in the model's tool set. A `Workflow` (prepare, `request_info`, `@response_handler`, commit) paused and resumed on a freshly built graph from a checkpoint in the spike; the reply is produced by the exact-word, same-person, in-time gate in our code, and the token stays in memory.
- **Choice: what stays code (KEEP), with reasons in the inventory.** Identity extraction and refusal, the exact-word gate, the gateway REST client (commit fields), the verbatim composer and numeric guard, lane projection, the per-replica TTL state map, the degraded json and keywords paths, the multi-provider failover, the gateway pipeline, ledger, auth and lane guard, debug diagnostics.
- **Gaps recorded** (REMEDIATION-FINDINGS.md F-01 to F-08): no GA hosting or Activity host; no endpoint override on `FoundryChatClient`; function middleware cannot see an unregistered tool name (refused commit attempts are recorded in a `ChatMiddleware`); a mapping schema is validated shallowly (keep `jsonschema`); no failover chat client; no approval path for a free-text channel; the catalog lacks reader-owned-argument and model-offered metadata and `channel_ping` and `mcp.describe` sit outside it.
- **Verification.** Run in process, not on the live service: `FunctionTool` from the real `client_eligibility` spec reproduces name, description and schema; an `Agent` with a scripted client ran a middleware that overwrote the model's `client_id` while the body received the person from `function_invocation_kwargs`; the Workflow pause and resume; the MCP SDK per-request header read. The newest hosting package and the `azure-ai-agentserver` wheels were downloaded to a folder outside the repo and read, not installed; no requirements file or `.venv` changed.
- **Not changed.** Any code, test, requirements file, `azure.yaml`, the numeric guard, the composer, the lanes, the narrator prompt, the route inventory.

## D-125 RM-07: the catalog says which arguments the reader owns and what a model may name; one factory generates the MAF tools; nothing else defines a tool

- **Context.** The catalog owned names, descriptions and schemas, but the orchestrator kept its own list of reader-owned arguments (`CLIENT_PLACEHOLDER`, `YEAR_KEYS`, `SCENARIO_NUMBERS`), its own list of tools a model may not name (`_NOT_FOR_MODELS`), a hand-written `function_tools` that built each `FunctionTool`, and the gateway defined `channel_ping` by hand while the MCP facade edited descriptions in `describe()`. Four places could drift from the catalog without a test noticing (F-07).
- **Choice: metadata as data on `CapabilitySpec`.** `reader_owned: tuple[ReaderOwned(name, kind), ...]`, derived from the schema when not given (`owned_arguments`; the argument-name vocabulary is written once, in `catalog_types`). Kinds: `client`, `year`, `explicit_year` (a write's year and a base year: only a year the reader wrote), `years`, `method`, `method_both` (an unnamed method means every certified method; set on `client_eligibility` only, as before), `size` and `scenario` (a what-if's numbers). Tags `code-only` (`client_resolve`, `employee_drill`) and `debug` say who may name a tool; `catalog.model_offered()` is the one filter (commits, plumbing, gateway-local, code-only and debug tools never reach a model). `CERTIFIED_METHODS`, `TAX_YEAR` and `CLIENT_RESOLVER` replace literals in the orchestrator. `to_dict()` is unchanged, so the REST capability list and the portal see nothing new.
- **Choice: `channel_view` owns the presentation.** `model_schema(spec)` is the schema a model is shown (the client removed, nothing the reader owns required, extra properties tolerated and judged by the strict schema afterwards); `channel_description` and `behaviour_hints` are what the MCP facade's `describe()` wrote by hand (`PREVIEW_SENTENCE` moved here; `channel.mcp` re-exports it). `model_schema` equals the projection the orchestrator used to build, for every tool (a test keeps the old function as an oracle). `channel_ping` is `catalog.CHANNEL_PING` in `catalog.DIAGNOSTICS`, outside `CATALOG` (the API has no capability behind it and the portal and REST lists must not show it); `catalog.offered_for_channel(debug=)` is the gateway's list and `channel.tools.PING_SPEC` remains an alias.
- **Choice: one factory, bodies that only forward.** `app/core/maf_catalog_tools.py`: `catalog_tool(spec, body)` builds a `FunctionTool` from the catalog's name, description and `model_schema` with `result_parser=SKIP_PARSING`; the default body `forward_to_gateway` reads the turn from `FunctionInvocationContext.kwargs` (`function_invocation_kwargs`, the mechanism the spike proved) and forwards through the gateway as the acting person. Tools are built once and carry no turn. Until RM-08 moves the rules into middleware, `function_tools(runner)` routes the body through the turn's `ToolRunner.run` (which still enforces them), so no guarantee was out of force at the RM-07 merge. The argument rules in `ToolRunner` are catalog-driven now (`spec.owned(...)`, `reader_arguments.ReaderWords`), with identical behaviour.
- **Choice: the MAF layer is the `maf_*` modules.** `test_orch_structure.py` allowed `agent_framework` in `maf_agent.py` alone; with a second and third MAF module that became "only modules named `maf_*`". Narrow edit to two assertions (the allow-list and the set check), no assertion loosened beyond that. `test_architecture.py`'s list of vendored capability siblings gained `channel_view`.
- **Enforced.** `tests/test_architecture_catalog_only.py` (55 cases, with scanners that take source text so tests prove they bite): no `FunctionTool`, `CapabilitySpec` or `ToolSpec` with a literal outside the factory and the catalog, no tool-making decorator, no dict shaped like a tool definition with a literal name or description, no inline JSON schema, no string that repeats or edits a catalog description or channel sentence, and a catalog tool name written as a literal only in four listed files with a reason each (`ledger.py`, `pipeline.py`, `downloads.py`, `writes.py`); the list fails if an entry goes stale. Scanned: `channel_orchestrator/app` (not the vendored copy) and `backend/channel` (which holds the MCP facade).
- **Not changed.** What a model sees (descriptions and schemas are byte-identical, checked against the old projection), the goldens, the workflow, write and audit tests (no edits), the numeric guard, the composer, the lanes, the route inventory, the REST capability contract.

## D-126 RM-08: the tool rules are MAF function middleware inside the model's loop; `ToolRunner` is the turn's state; the degraded modes reach the same middleware

- **Context.** `ToolRunner` held every rule (budget, refusal, client, year, method, schema, repeat cache, both-methods, fact capture, token strip) and the framework only carried a closure to it. The rules ran outside the loop, the degraded modes called them directly, and `PortChatClient` recorded unregistered names by hand.
- **Choice: the rules are `FunctionMiddleware`, stateless, in this order.** `Budget` → `RefuseUnlisted` → `ClientFromReader` → `YearAndMethodFromReader` → `SchemaCheck` → `CallAndCapture` (`maf_tool_rules.py`, `maf_tool_call.py`). Each reads the turn from `function_invocation_kwargs` (the agent's `additional_function_arguments`) and either lets the call go on or answers it with the stable code and sentence the model always read. The model-visible text is byte-identical: the orchestrator goldens, workflow, write, audit, resilience, identity and numeric-lane tests pass with **no edit**. A question back (no client, no year, no size) answers that call with `needs_*` and does not terminate the loop (MAF's `MiddlewareTermination` would end the model's turn, which changes the transcript).
- **Choice: the commit refusal is two layers, because the framework answers an unregistered name before any function middleware (F-03).** `RecordUnregisteredCalls` is chat middleware (a `ChatMiddlewareLayer` was added to `PortChatClient`; `on_unknown` is removed) and records each name the model asks for that is not a registered tool, the framework still answering "not found"; nothing is registered to refuse a commit, because a stub would put a commit in the model's set. `RefuseUnlisted` is the same rule in function middleware, in the brief's position after the budget, as defence in depth. In the json and keyword modes the refusal runs before any rule (the unchanged `test_orch_runner` asserts a refused name is recorded even when the budget is spent), so the brief's "budget, then refusal" order holds for registered tools and the observable behaviour for the rest is the earlier one.
- **Choice: the degraded modes run the same middleware, through a one-shot agent.** `FunctionMiddlewarePipeline` is not public (F-09), so `ToolRunner.run` (json and keywords) sends the named tool through `maf_tool_run.run_through_the_rules`: an `Agent` whose chat client (`OneCall`) asks for exactly that call, with the same generated tool and the same middleware, and the model-visible answer is read back from the tool result. No rule is written twice. Tradeoff: an `Agent` is built per degraded call.
- **Choice: both-methods stays a policy, in the call stage.** `CallAndCapture` calls `call_next()` once per `catalog.CERTIFIED_METHODS` when the settled method is `both` (the framework allows a second `call_next()` with changed arguments), labelling each run, counting the second call against the budget and skipping it when spent. It fires for any tool whose settled method is `both`, as the runner did.
- **Choice: argument rules are catalog-driven.** `reader_arguments.ReaderWords` holds the pure functions of the reader's words; no argument name appears in a rule (`spec.owned(...)`), and `maf_tool_call` finds the method argument and the conversation's year argument from the catalog (`method_argument`, `catalog.TAX_YEAR`).
- **Choice: `ToolRunner` remains, as the turn.** The unchanged tests construct it and call `run`, and the pipeline, the planner, the audit and the composer read its ledger (`runs`, `problems`, `refused`, `clarify`, `pending`). It went from 249 to 121 lines: state, the one gateway call (`forward`, inside the span the resilience tests pin), the resolver call, `hold`, `refuse`, and `run` for the degraded modes. `__deepcopy__` returns the object itself, because the framework deep-copies an agent's default function arguments (F-10) and a copy would split the budget and the ledger.
- **Choice: the span stays.** MAF emits its own `execute_tool` span when instrumentation is on, but the contract the resilience tests pin (`tcc.tool.<tool>` and six allowed attributes) also covers the resolver and the keyword mode, which have no framework span. Recorded as KEPT with that reason.
- **Existing tests edited (one, narrowly).** `test_orch_catalog_tools.py` (added in RM-07) built `PortChatClient(..., on_unknown=...)`; the argument is gone. No test from before RM-07 was edited in this work package.
- **Enforced.** `tests/channel_orchestrator/test_orch_tool_rules.py` (14): the rules fire from the framework in the stated order inside a real `Agent` loop; each is stateless and built once; the budget refuses a call over it before the gateway; a commit and an invented name are recorded and nothing is called; the model's `client_id` is overwritten; a missing year is a question back; a year the reader did not say is replaced and the method defaults to both runs; the schema check records and stops; a prepared change's token stays on the turn and never in what the model reads; the degraded modes run the same middleware (a patched `Budget` is seen); a refused name is recorded even with the budget spent; `ToolRunner` holds none of the rule methods and `tools.py` does not touch `jsonschema`. Two mutations (the recorder or the rules left out of `build_agent`) fail 2 and 7 of them.
- **Not changed.** What a model sees, the numeric guard, the verbatim composer, the lanes, the narrator brief (names, not values), the confirmation flow and `writes.py`, the gateway, the catalog, the route inventory.

## D-127 RM-09: the foundry provider is served by MAF's own OpenAI chat client on the account's OpenAI host; a chain that names a gateway keeps `ModelChain`

- **Context.** RM-06 found that the framework's `FoundryChatClient` has no endpoint override and reaches the model on the project host (`<account>.services.ai.azure.com`), which the hosted runtime could not resolve (D-101), while `<account>.openai.azure.com` resolves and answers with the same account, token and deployment. So the framework's Foundry client could not be used as is, and the orchestrator sent every model call through `PortChatClient` over `ModelChain` over the shared `OpenAICompatibleChatModel`, a bridge of ours for a job the framework does.
- **Choice: the framework's `OpenAIChatCompletionClient`, not `FoundryChatClient` and not the Responses client.** Both OpenAI clients accept a `base_url` and a token-provider `credential` (verified in the installed `agent-framework-openai` 1.18.0: `load_openai_service_settings` builds an `AsyncOpenAI` on that URL, with the provider as its bearer source, and the model name as the `model` field). The chat-completions client sends exactly what the shared adapter sent: `POST https://<account>.openai.azure.com/openai/v1/chat/completions`, the deployment name as `model`, `tools` and `tool_choice: auto`, `Authorization: Bearer <Entra token for https://cognitiveservices.azure.com>`. The Responses client would change the tool wire against a service that has not seen it from this runtime, so it is a later, deliberate step and not part of this package. `FoundryChatClient` stays unused until `/modelprobe` shows the project host resolves from the hosted runtime.
- **Choice: one interface, one small factory, one rule.** `app/core/model_access.py`: `ModelAccess` is what the planner reads (`configured`, `tools_available`, `screen`, `complete`); `ModelChain` implements it and so does `FoundryModelAccess`, an SDK-free description (base URL, deployment, egress policy, deadline, optional token provider). `select_model_access(settings)` reads `AI_PROVIDER_CHAIN` (the narrator role's chain): **exactly `foundry` is served by the framework's client; any chain that names `gateway`, alone or with `foundry` before or after it, is served by `ModelChain` through `PortChatClient`** (the framework has no failover client, F-05, and the customer's gateway has its own dialect, authentication and egress policy). `maf_agent.chat_client_for` builds the client for whichever object it is given and refuses an unknown one. A foundry-only chain with no `FOUNDRY_PROJECT_ENDPOINT` still fails at start. No environment variable was added.
- **Choice: what `ModelChain` did around a call is kept on the framework path as chat middleware** (`maf_foundry_client.py`), in this order: `EgressGuard` (the egress policy, so an identifier never reaches the wire, whatever the policy), `Deadline` (`AI_TOTAL_DEADLINE_SECONDS` per call; the SDK's own timeout is 600 s), `TraceModel` (fills the `ModelTrace` the narration audit reads: provider, the model the service reports, the prompt hash input). The injection screen stays a pre-model decision on the access object, because a flagged message reaches no model and so is not a chat call. `ComposeMiddleware`, the generated tools, the tool rules and `RecordUnregisteredCalls` are unchanged and still run on the same `Agent`, so the narrator's words are still replaced by the composer's verbatim output and the numeric guard is still the only way out. `ModelTrace` and the message shape moved to `maf_chat.py` (still importable from `maf_agent`); `PortChatClient` and `ModelChain` are untouched.
- **Choice: no key, one credential per process.** The credential is a token provider over `DefaultAzureCredential` (`az login` locally, the managed identity deployed), built once per process (`lru_cache`) so its token cache serves every turn, with the blocking fetch in a thread. `FoundryModelAccess` has no key field, `AZURE_OPENAI_*` and `OPENAI_*` variables are not read for authentication (a test sets them and shows the request carries the Entra token only), and an architecture test fails on `api_key=` or those variable names anywhere in `channel_orchestrator/app`.
- **Deployment consequence: the project host versus the account's OpenAI host.** The request path is unchanged from D-101's fix (same host, path, token audience), so no network, DNS or role change is needed. What is new is the client library in the zip: `requirements.txt` gains `agent-framework-openai==1.18.0` and `openai==3.39.0` (pinned to the versions the platform runs; `test_orch_requirements.py` checks both against what is installed). **RM-16 must verify live, with the debug switch on for the check and off afterwards:** (1) `/netcheck` and `/modelprobe` still show the account host resolving and the project host not (or, if the project host now resolves, record it: `FoundryChatClient` becomes possible); (2) the remote build installs the two new packages and the agent starts; (3) a tool-calling question gets a model answer on the framework path (audit `model` filled, `mode=tools`, `narration_used`), with the deployment actually in use, including a `gpt-5` family deployment (no `temperature` is sent for it); (4) a request really carries a bearer token and the instance identity still holds **Foundry User** and **Cognitive Services User** on the account; (5) behaviour when the model is slow or errors (the answer degrades to the engine's figures; the SDK retries a 429 or 5xx twice inside the per-call deadline); (6) latency against the earlier path, since one HTTP client is created per turn (a TLS handshake per turn; connection reuse within a turn).
- **Not verified here.** Nothing ran against the live service: every test is in process, with an `httpx.MockTransport` handed to the framework through the seam it builds its own HTTP client with. The body the framework sends was read from that transport, not from a capture of the real service.
- **Enforced.** `tests/channel_orchestrator/test_orch_foundry_client.py` (24): the selection for `foundry`, `gateway`, `foundry,gateway`, `gateway,foundry` and a narrator-role override; the missing endpoint; the host derivation (project host to account host, a non-public-cloud host kept, a non-https endpoint refused) and the built client's base URL and deployment; a full turn through the real `Agent` (tools called, composer speaks, narration audit carries the service's model, a model sentence with an invented figure rejected); the wire (URL, model, tools without a commit and without `client_id`, no turn state leaking into the body, `temperature` only where accepted); authentication by token provider only and no key; the credential built once; an employee identifier, an injection attempt, a slow model and a refused request each degrade to the engine's own answer; the trace. `test_orch_structure.py` gains: the framework's OpenAI client is built in `maf_foundry_client.py` alone, `FoundryModelAccess` in `model_access.py` alone, `PortChatClient` in `maf_agent.py` alone, `select_model_access` called from `wiring.py` alone, no `FoundryChatClient`, no key, and no SDK in `model_access.py`, `models.py` or `maf_chat.py`.
- **Existing tests edited (narrowly).** `test_orch_structure.py`: the import allow-list gives `agent_framework_openai` and `azure` to `maf_foundry_client.py` only, and the assertion that only the MAF layer imports the framework also counts `agent_framework_openai`. No golden, workflow, write, audit, identity, resilience or numeric-lane test was edited; all pass unchanged on the `ModelChain` path they use.
- **Not changed.** The numeric guard, the composer, the lanes, the narrator brief, the tool rules, the catalog, the gateway, `AI_PROVIDER_CHAIN`'s meaning for the API and the portal, the route inventory.

## D-128 RM-12: hosting stays as it is behind the `main.py` seam; the seam and the Teams-silencing protocol rule are tests now

- **Context.** RM-06 left RM-12 as NO-GO: `agent-framework-foundry-hosting` is pre-release only and has no Activity handler. The brief said to adopt it if it served Responses and Activity, and otherwise to keep the current host and keep the seam provable.
- **Choice: no-go, re-checked.** On 2026-11-04 `pip index versions agent-framework-foundry-hosting` still lists 29 releases, every one an alpha or beta (newest `1.0.0b261030`), and a plain `pip install` finds no matching distribution. The orchestrator does not install it, does not use `--pre`, and keeps `app/main.py` on the stable `azure-ai-agentserver-responses` pin. Nothing about the host, `azure.yaml`, the requirements or the runtime changed in this package.
- **Choice: the seam is enforced, not described.** New `tests/channel_orchestrator/test_orch_hosting_seam.py`: only `channel_orchestrator/app/main.py` imports a hosting package (`azure.ai.agentserver*`, `agent_framework_foundry_hosting`), checked across the orchestrator, the backend and `scripts/` (the older rule covered only `app/`); the zip-root `main.py` imports only `app.main`; `app/main.py` registers one Responses handler, reaches the orchestrator only through `app.host` and `app.wiring`, stays at or under 60 lines and does not touch the agent framework; the agent framework is imported by `app/core/maf_*.py` only (the root file is now covered too); the beta hosting package is in no requirements file; the stable Responses host is pinned; `azure.yaml`'s `entryPoint` and the Dockerfile's `CMD` start the same file. A swap to the hosting package is therefore one file plus a deliberate edit of the test's `SEAM`.
- **Choice: a guard for the Teams-silencing regression (D-100).** The same file reads `channel_orchestrator/azure.yaml` and fails unless the container's `protocols:` is exactly `responses` and the agent endpoint's `protocols:` contains both `activity` and `responses`. `activity` on the container makes the platform post Teams messages to `/activity/messages`, which the container does not serve; Teams then goes silent with no error. The reader is an indentation walker (this repository's tests carry no YAML dependency) and five crafted inputs (activity added to the container, replacing `responses`, an unknown protocol added, `activity` or `responses` missing from the endpoint) each fail it, a missing block fails rather than passes, and the known-good shape passes.
- **Re-check conditions** are in [MAF-ALIGNMENT.md, "Hosting: go / no-go and when to re-check"](MAF-ALIGNMENT.md#hosting-go--no-go-and-when-to-re-check): GA with a core range that admits our pin; Activity settled (a handler, or the Responses-only container with endpoint-level `activity` confirmed as the supported path); per-request identity shown to reach `app/host.py` and the tools; the Foundry-backed stores acceptable or off with the confirmation token still in memory (D-81); then the seam test, `azure.yaml` unchanged, the suite and goldens, `check_all.py`, and a live Teams round trip with the previous agent version recorded for rollback.
- **Not verified.** Nothing ran against the live service. The claim that Teams works without the container serving `activity` rests on D-100's live evidence, not on anything run here.
- **Not changed.** Any production code, `azure.yaml`, requirements, the Dockerfile, the numeric guard, the composer, the lanes, the route inventory. No existing test was edited.

## D-129 RM-10a: the Agent is the planner; json and keywords are one small degraded path; one compose path, one brief, one trace

- **Context.** `planner.py` held three planners in one class (the MAF Agent, a JSON-plan mode, a keyword mode) and repeated work between them: the reply was composed in two places (the Agent's output closure and `TurnPipeline._answer`), the narrator's brief was built in two (`maf_tool_call.capture` for the Agent's tool replies, `_narrate` for the JSON mode), and the model trace was written by hand in four.
- **Choice: the Agent is the planner for an open question; the other two are a documented degraded path behind `DegradedPlanner`.** `app/core/degraded.py`: `DegradedPlanner` is a `Protocol` of `mode` and `async plan(runner, planned)`; `JsonPlanner` (a provider without tool calling: the model names tools as JSON and writes one narration call) and `KeywordPlanner` (no model, a flagged message, or a failed model layer: the platform's keyword table picks the tools, nothing narrates) implement it. `Planner` (`planner.py`, now only the dispatch and the Agent path) takes the two as an injectable mapping, so a test can hand it fakes. Both still run their tools through `ToolRunner.run`, which is the Agent's own middleware (D-126). They are for "no tool-calling model is reachable" and not a place to add capability.
- **Choice: one compose path.** `planned.Planned` (moved from `planner.py`, still importable from it) owns `composed_for(runner)`: the verbatim composer and the numeric guard over the turn's results and the narration, computed once and invalidated by a new narration (`narrate`). The Agent's output middleware, the degraded planners and `TurnPipeline._answer` all use it; `compose_reply` is called from `planned.py` and from the commit path (`writes.py`) only, which a test asserts. The hosts a link may name travel on `Planned` from the `Planner` that `wiring.py` builds from `AI_OUTPUT_ALLOWED_HOSTS`; the pipeline no longer reads them a second time (the two were the same value in production and in every test, since the default is empty).
- **Choice: one narrator brief and one trace.** `compose.narration_brief(question, runs, fenced=)` is what a model is told of results (names with placeholders, never a value). `maf_tool_call.capture` uses it per tool reply and `JsonPlanner` once for its narration call (`fenced=True`: the question travels in that brief). `ModelTrace.sent/took` replace the four hand-written appends, in `PortChatClient`, the JSON planner's two calls and (through its own prompt text) the framework path.
- **Existing tests.** None edited. The orchestrator suite (437) and the whole backend suite pass; the goldens (`fallback.json`, `planning.json`, `guard.json`, the data cases) are unchanged and exercise every mode.
- **Enforced.** `tests/channel_orchestrator/test_orch_degraded_planner.py` (15): the interface is `mode` and `plan` only; the Agent plans when a tool-calling model is reachable and neither degraded planner is asked; each degraded planner is chosen by its condition (no tool calling, no model, a flagged message); a failure before any tool ran falls to the keywords and says so, one after tools ran keeps what they returned; the real planners are the default; the JSON plan reader; one composition and its invalidation; `compose_reply`, `narrator_brief` and the trace's `prompt_parts` are touched from one place each.
- **Not changed.** What a model sees, the tools, the rules, the guard, the composer, the lanes, the confirmation flow, the gateway, the catalog, the route inventory. Nothing verified on the live service.

## D-130 RM-10b: the write path is a MAF Workflow (prepare, the framework's request step, commit); the checkpoint is in memory

- **Context.** The confirmation flow was hand-written: `ToolRunner.hold` kept the prepared change and its token, `ConversationState.pending` carried it to the next turn, and `commit_pending` (in `writes.py`) cleared it, checked the expiry and sent the commit. The guarantees were right and the shape was ours. MAF has the primitive for "pause, wait for a person, resume" (`WorkflowBuilder`, `Executor`, `request_info`, `@response_handler`, checkpoints), proved on core 1.24.0 in the RM-06 spike.
- **Choice: a three-executor graph, built fresh on every run** (`maf_write_steps.py`, `maf_write_flow.py`): `Prepare` (asks the gateway for the preview as the acting person, writes nothing) → `AwaitConfirmation` (`request_info`; the workflow goes idle) → `Commit` (one commit, once). The start input is `PrepareRequest` and nothing else (`Workflow.input_types`), `Commit` accepts only `Approved`, a message only `AwaitConfirmation`'s response handler creates, and that handler creates it only for a `Confirmation(True)` that arrives before the expiry (the pipeline's clock, as before). A cancel is `Confirmation(False)` (the workflow ends with the cancelled outcome); "any other message" is the framework's `cancel_pending_requests`. The graph has no model, no tool and no figure.
- **Choice: the model reaches only Prepare.** A `*_prepare` tool's body is `prepare_body` (`maf_catalog_tools.body_for` picks it by the catalog's `write_prepare` kind; every other tool still forwards). It starts the workflow, which pauses on the preview; the preview's gateway reply goes back to the tool loop untouched, so what the model is told, the fact ledger and the composed preview are unchanged. The paused workflow is left on `ToolRunner.flow`; `TurnPipeline` keeps it as `ConversationState.write` (`state.PausedWrite`: the checkpoint storage, checkpoint id and request id) for the same person and conversation. A commit is still not in the model's tool set, and now cannot be reached by starting the workflow either.
- **Choice: the exact-word gate stays ours and is the only producer of the reply.** `writes.parse_command` is unchanged. `TurnPipeline` calls `commit_pending` (now `maf_write_flow.commit_pending`; the structure test that it is called from `turn.py` only passes unedited), `cancel_pending` and `drop_pending`. Each clears the state first, as before, rebuilds the graph and resumes it from the checkpoint with the person's identity of THIS turn. `writes.send_commit` (the old body of `commit_pending`: the commit, a fresh idempotency key, the package link, the composed text) is called by the commit executor and by nothing else.
- **Choice: the framework's checkpoint, in memory only.** The graph is rebuilt per run and resumes from an `InMemoryCheckpointStorage` held for that one paused write. The checkpoint contains the single-use token, so it must not be on a disk or in a store another replica reads (D-81: the filesystem may be discarded, replicas are interchangeable). `FileCheckpointStorage` and the hosting package's Foundry-backed stores were therefore not used, and `StateStore` (a TTL map, keyed by person and conversation) stays as the registry. A restart loses a pending confirmation exactly as before: it cannot be confirmed, the person asks again. The workflow's message types are registered with `register_checkpoint_type` because the framework's checkpoint decoder allows only registered types.
- **Choice: a fault is never a held preview, a silent cancel or a retry.** A framework error while preparing returns a `write_flow_failed` error (the person is told the preview could not be held; no confirmation hint). An error while confirming says the outcome is unknown and that nothing will be retried (the commit may have been sent), the same sentence a lost commit answer has always had. An error while dropping or cancelling is logged and changes nothing, because a preview writes nothing. In every case the state is already cleared, so a later `confirm` finds nothing.
- **The token checks are unchanged and not duplicated.** The gateway and the API still check the person, the tool, the arguments, the expiry and the single use, the writer policy and the audit trail; the orchestrator sends exactly the previewed arguments and the issued token (a test compares the prepare and commit calls), with a fresh idempotency key, as the person who confirmed.
- **Existing tests.** None edited. The write, workflow, audit, identity and resilience goldens and tests pass on the workflow (the orchestrator suite is 456 before the new file, all green), including `test_orch_structure.py::test_the_commit_path_is_one_module_called_from_one_place` (the commit name is built in `writes.py` only; `commit_pending` is called from `turn.py` only).
- **Enforced.** `tests/channel_orchestrator/test_orch_write_flow.py` (21): the graph and its two edges; the one start input; `Approved` cannot start it; the prepare step refuses a commit tool and a read; the modules import only workflow primitives; a prepare pauses in an in-memory checkpoint and sends nothing but the preview; the confirmation resumes on a different graph object and sends one commit with the previewed arguments, the token and the confirming person's headers; somebody else's `confirm` finds nothing and leaves the owner's preview; the boundary of the expiry; every refusal the gateway can give a commit is reported and not retried; cancel ends the workflow; any other message cancels the framework's pending request and says so; a framework fault while dropping, confirming or preparing; a refused preview never pauses; a model naming a commit is refused. A mutation that removes the expiry check fails two tests (one golden, one new).
- **Unverified.** Nothing ran against the live service. The in-memory checkpoint's behaviour across a real replica restart is the old behaviour by construction (nothing survives), not by a test.

## D-131 RM-10c: the client review pack is a second MAF Workflow, reached by the orchestrator's routing; no catalog composite

- **Context.** The Cowork skill `tcc-client-review-pack` and the portal describe a multi-step job: resolve the client, read the position, check, present. Cowork runs it from the model's side (the skill is a procedure for the host model). In Teams and Copilot Chat nothing ran it: a reader had to ask for each part, and an Agent chooses its own tools, which is the wrong pattern for a sequence that is always the same.
- **Choice: a Workflow, because the sequence is fixed.** `maf_review_pack.py`: `WorkflowBuilder` over one `add_chain`: `ResolveClient` (the client by code, or a question back) → one `Capability` executor per tool (`client_situation`, `client_eligibility`, `client_trend`, `client_at_risk`, `client_discovery`, named through the catalog's chat-intent table, never as a literal) → `Check` (something must have answered) → `Compose` (the reply from the engine's blocks through `Planned.composed_for`: the verbatim composer and the numeric guard, no narration). No model takes part: the pack never calls one, whatever is configured, and its audit is the gateway's row per call (the narration report is skipped, as in the keyword mode).
- **Choice: each step is a call through the SAME rules and the SAME tools.** A `Capability` runs `ToolRunner.run(tool, {})`, which is the generated FunctionTool inside the function middleware (budget, client, year and method, schema, call and fact ledger), exactly what an Agent's loop and the degraded planners use; so the arguments the gateway sees are the ones an Agent's call for the same words would have produced (a test compares them), eligibility runs under both certified methods with distinct labels, and the figures are the gateway's envelopes, untouched. **No executor computes**: they move a marker, stop the sequence when the reader must say something or nothing answered, and compose. The AST test in D-132 proves it.
- **Choice: reached by routing, not by a tool.** `review_pack.wants_review_pack` (the reader asks for it by name: "review pack", "client review", "credit review", "client briefing") makes `TurnPipeline._answer` run the Workflow instead of the planner. The alternative the brief offers, exposing it to the Agent as a catalog tool or as a server-side composite capability in `application/capabilities`, was **not** taken: (1) a composite would have to merge several envelopes (blocks, per-method labels, provenance, the fact ledger's one-entry-per-call rule) into one new envelope shape, a change to the contract every surface and the parity run depends on, to save one routing rule; (2) Cowork already runs the pack from its skill, and a tool that duplicated it would change the MCP tool list, the Cowork package and the conformance run; (3) a pack that a model may choose to run is the Agent doing a fixed sequence, which is the pattern the rule of the run forbids. If a surface other than the orchestrator ever needs the pack server-side, the composite is the home, and this Workflow becomes its test oracle. Not decided for the owner; recorded here.
- **Choice: the pack has its own tool budget.** `review_pack.CALL_LIMIT` (every step once, and eligibility's second certified method) is the runner's budget for a pack turn, whatever `CHANNEL_MAX_TOOL_CALLS` says: the budget exists to bound a model's loop, and the sequence has no loop. A smaller operator ceiling would otherwise drop steps silently.
- **Choice: what the pack leaves out, and why (RM-10e).** (a) **A what-if** needs a worksite and a size; the size is the reader's and the worksite comes from their words or an earlier result, which takes a model, and a step that chose either in code would invent it. (b) **The data deeper** (`data_catalog`, `data_query`) is open Q&A. (c) **Findings, claim moves and the package** are the person's decisions, one confirmation each; they go through the write Workflow when the person asks, never inside a read. (d) **The walkthrough** is long and one question away. The reply ends with one fixed sentence (`replies.REVIEW_PACK_NEXT`, no figure) saying so. None of this weakens a guarantee; it is the boundary between the two patterns. Recorded in REMEDIATION-FINDINGS.md (F-14).
- **Choice: asking back.** A pack with no year stops after the first step that needs one and asks "Which tax year do you mean?"; if the next message is only a year, it resumes the pack (`state.question` holds the pack request for one turn). An ambiguous client is asked for with numbered candidates and the number resumes the pack, through the existing path. The resume is limited to a pack request, so no other question's behaviour changed.
- **Existing tests.** None edited; the orchestrator goldens and the whole suite are unchanged by this package.
- **Enforced.** `tests/channel_orchestrator/test_orch_review_pack.py` (27): the phrases that ask for it and the ordinary questions that do not (including "brief me", "walk me through"); the steps are catalog read tools and the budget is exactly the sequence's; the pack runs every step in order through the gateway, with no model asked and the engine's figures verbatim; the reply passes the numeric guard against the runs' own facts; the gateway sees the arguments an Agent's call would have produced; a configured model is not asked; the budget holds against a ceiling of one; nothing is prepared or committed; a missing year is asked for and a bare year resumes it; an ambiguous client is asked for and the number resumes it; a bare year is not taken from a message that is not answering a pack; a failed step is reported and the others answer; nothing answering stops at the check with no figure; the graph is one chain with no branch.
- **Unverified.** Nothing ran against the live service. The sentence a reader sees (`REVIEW_PACK_NEXT`) and the length of five tools' blocks in one Teams message are not checked against Teams' message limits.

## D-132 RM-10d: where each MAF pattern is allowed is a test; so is "no executor or tool body computes a figure"

- **Context.** After RM-10a to RM-10c the orchestrator uses the framework three ways (an Agent, two Workflows, generated tool bodies), and the rule of the run is that each has one job and that no figure is produced by anything but a capability. Nothing stopped a fourth use, a model inside a workflow, a loose sequence of tool calls or arithmetic in an executor.
- **Choice: the rules are over the source, with a registry per rule.** `tests/test_architecture_patterns.py` reads `channel_orchestrator/app` with `ast` and states: an **Agent** is built only in `maf_agent.py` (the planner, for open Q&A) and `maf_tool_run.py` (the framework's only way to run function middleware, F-09), and `build_agent` is called from the planner alone; a **Workflow** is built only in the two registered modules (`maf_write_flow.py`: a confirmation; `maf_review_pack.py`: a fixed sequence), `Executor` subclasses and the workflow primitives (`Executor`, `WorkflowBuilder`, `WorkflowContext`, `handler`, `response_handler`) appear only in the registered workflow modules, a workflow module imports no model, planner, degraded planner, chat client or prompt, and no open-question module imports a workflow (a workflow is started by the pipeline, or by the generated prepare tool's body); each **entry point** (`run_review_pack`, `commit_pending`, `cancel_pending`, `drop_pending`, `prepare_write`, `build_agent`) is called only from where it is allowed; the **commit chain** is built only by the step before it (`Approved` by the request step's response handler, `Commit` by the graph builder, `PrepareRequest` and `Confirmation` by the write flow, `send_commit` by the commit executor), which answers F-16; and **no sequence of tool calls** (two in one function, or one in a loop) stands outside an executor, the Agent or a named degraded planner. Each registry entry carries its reason, and a stale entry fails.
- **Choice: the figure detector is strict and its allowance is three named statements.** For the MAF layer (every `maf_*` module but `maf_chat.py`, whose loop limits are counts of model iterations) and for the tool bodies elsewhere (`ToolRunner.forward` and `_timed`, `writes.send_commit` and `_package_link`), the test fails on arithmetic (`+ - * / // % **`, augmented or not, unless both operands are int literals or one is text or a container), negation, `round`, `sum`, `min`, `max`, `abs`, `divmod`, `pow`, `float`, `Decimal`, `format`, `.format`, `%` formatting, an f-string format spec, and an import of `math`, `statistics`, `decimal`, `fractions`, `numpy` or `locale`. Text and container operands are exempt because `+` and `*` on them are concatenation, not arithmetic. It does not try to follow data flow: it forbids the operation, so it cannot be argued around with a variable name. The allowance is keyed by (file, function, statement): the budget's two call counters and a label suffix (`n + 1`), each an integer that is not a figure. The expiry (`clock() + window`) was the one real arithmetic in an executor; it moved to `ToolRunner.deadline()` and the executor calls it, so the write executors hold none. Discovery fails the build if a new module defines an executor or function middleware or builds a tool and is not in scope, so a new executor cannot start unscanned.
- **Proved, not assumed.** The detector is tested on eighteen seeded violations (multiplying an envelope value, adding, rounding, summing, a maximum, dividing, a power, negation, a running total, a conditional total, `float`, `Decimal`, an f-string spec, `.format`, `%`, `format`, two maths imports) and ten pieces of ordinary code it must leave alone; a violation is injected into the real `Prepare` executor's source and into the real `ToolRunner.forward` and is found with the function named; the sequence detector is proved on four seeded sequences and three clean shapes. Real mutations were tried on the tree and each failed the suite: a `round(float(...))` in the commit executor, a planner import in the review pack, and two tool runs in `turn.py`.
- **Existing tests.** None edited. One new production seam: `ToolRunner.deadline()` (used by `hold` and handed to the write context); `WriteContext` takes `deadline` instead of `ttl_seconds`. My own RM-10b test was adjusted for that argument.
- **Not covered, on purpose.** The detector scans the orchestrator's executors and tool bodies; the gateway's MCP facade and REST adapters are covered by the catalog-only rule and the parity run (RM-13), not by this one. A model could still be told a figure by an instruction; that is the narrator brief's names-not-values rule and the numeric guard, unchanged.

## D-133 RM-11: the orchestrator's definition is `azure.yaml` (no manifest file); the specialist prompt agents are declared in one list

- **Context.** The brief asks for the orchestrator's definition to be declarative and reviewable, "the azd ai agent manifest" included, and for the specialist Foundry prompt agents to be published from one list. Twelve agent modules each declared a name, a prompt call, a model role and a temperature, and the roster was a hand-kept import list in `factory.py`.
- **Choice: no `agent.manifest.yaml`, because the extension no longer takes one.** Microsoft Learn (*azure.yaml reference for hosted agents* and *agent.yaml schema reference*, both read 2026-11-04, updated 2026-10-29) says `azure.yaml` is the single configuration for a hosted-agent project, that `agent.manifest.yaml` and `agent.yaml` are legacy, and that `azd ai agent init` rejects the manifest wrapper. `channel_orchestrator/azure.yaml` already had the documented shape, so the work is to make that file the stated definition and to hold it to the reference with a test. Added to it: a header saying so, `description`, and `requiredVersions.extensions.azure.ai.agents: ">=1.0.0-beta.20"` (the documented minimum; the file's header records beta.23 as the version it was written against). Not changed: the `protocols` shape (container `responses` only, endpoint `responses` + `activity`; D-100, guarded by `test_orch_hosting_seam.py`), the string `entryPoint` the reference shows, the env list, the resources.
- **Choice: the list is JSON, `backend/agents/agents.json`.** The repository's backend carries no YAML dependency (and its tests avoid one), JSON is stdlib, and a reviewer reads it as a table. Per agent: `module`, `name`, `prompt`, `role`, `temperature`, `tools`. `agents/roster.py` loads and validates it on first use (cached): format 1, exactly those fields, a real role, a temperature that is null or 0 to 2 (and not a boolean), `tools` empty, unique module, name and prompt, every prompt file either an agent's or listed under `excluded_prompts` with a reason (today none is excluded). A malformed list raises on import, not at the first publish.
- **Choice: "model" in the list is a ROLE.** The model an agent runs on is the setting `AI_MODEL_<ROLE>` (per provider, then role-wide, then Foundry's default). Declaring a deployment name in the list would make the repository name a deployment, would be wrong for the other providers in the chain, and would add a field `AgentSpec` and the catalog do not have. So a model change stays a setting. If a per-agent pin is wanted, it is an `AgentSpec` field and a catalog change, not a list-only edit.
- **Choice: the modules stay, for the profile.** Each `agents/<module>.py` still holds the display profile the Agents page shows (tab label, responsibility, inputs, outputs, tools prose); that is page content, not publishing. Its `SPEC` is `build_spec("<module>", AGENT_PROFILE)` and `NAME` and `INSTRUCTIONS` come from it, so the existing tests (which read `NAME`, `INSTRUCTIONS`, `AGENT_PROFILE`, `SPEC` and `list_agent_modules()`) pass unedited. `factory.list_agent_modules()` now follows the list's order instead of an import list.
- **Publishing is unchanged.** `foundry_publish`, `FoundryAgentCatalog` and `ai_wiring` were not edited. A hash over every spec's name, instructions, role, temperature and profile is identical before and after the change.
- **Enforced.** `tests/test_agent_roster.py` (38 cases with the architecture file: each fault refused, specs equal the declarations, one version per agent, no tool attached, an identical definition reused, a changed prompt publishes a new version of that agent only, a stray prompt file is refused) and `tests/test_architecture_agent_roster.py` (no agent module declares a name, prompt, role or temperature or imports what only the roster may; only `roster.py` builds an `AgentSpec` or loads a prompt; the publisher is fed from the roster alone; every prompt file is referenced or excluded; seeded violations are found; a real mutation, a `ModelRole` import in a module, failed the suite and was reverted). `tests/channel_orchestrator/test_orch_agent_definition.py` (20) holds `azure.yaml` to the documented reference.
- **Findings.** F-17: `FOUNDRY_MODEL` in `env` sits under a prefix the documentation reserves (it worked live; named as the one known exception in the test; decide at RM-16). F-18: `definitions_match` ignores the temperature, so a temperature edit alone publishes nothing.
- **Existing tests.** None edited. No live publish; `azd` was not run, so the two added `azure.yaml` fields are documented but not deploy-tested.
