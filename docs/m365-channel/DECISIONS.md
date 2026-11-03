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
