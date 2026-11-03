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
