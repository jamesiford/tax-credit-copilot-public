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

## D-84 CH-08b: gaps found re-reading the brief

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
