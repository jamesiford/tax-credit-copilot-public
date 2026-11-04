# Remediation findings

Customer-neutral. The run's summary comes first (what was fixed, what was deliberately not done, residual risks, and the decisions only the
owner can take); below it are the findings, appended per work package, that need an owner or a framework feature. Status per work package
is in [REMEDIATION-STATUS.md](REMEDIATION-STATUS.md), the reasoning in [DECISIONS.md](DECISIONS.md) (the build log), and the one document that
explains what the run produced is [ONE-ANSWER-EVERYWHERE.md](../architecture/ONE-ANSWER-EVERYWHERE.md).

## Summary

Written at the RM-22 merge, after RM-25. `main` is untouched at `029b9ad2d2c002c09167375748120c7a8af3bc03`; nothing is pushed. **Test evidence
as of this writing:** the last **full** backend run was RM-20: 6,166 passed / 136 skipped / 1 xfailed (baseline 4,957 / 136 / 1). RM-21 to RM-25
ran only the fast gate by the owner's instruction (architecture and code-standards tests, the tests that read what changed, and
`pytest tests --collect-only`: 6,338 collected, 0 errors at RM-25). The full backend and frontend suites and `check_all.py` run once at the end of
the run, by the orchestrating session; **they have not run on the RM-21 to RM-25 tip**.

### What was fixed, by tier

**Tier 1, security (offline, all merged).**
- RM-01 small-group suppression: aggregates over employee rows leave out groups smaller than K (default 5, floor 2), say how many were left out, and refuse an all-singleton group-by; a writer is exempt (D-119).
- RM-02 Cowork fails closed: only a positively first-party channel gets employee rows; the API refuses for itself, so a token sent straight to the API no longer skips the check; an agent's claimed channel is bound to its registered app id (D-120).
- RM-03 authentication is the default; `none` is a stated local opt-in; a failed audit write always raises an alert and never passes silently (D-121).
- RM-04 a seeded abuse fuzzer over the query builder, a closed grammar for derived columns, apostrophes in names work; it found four holes and they were fixed (D-122).
- RM-05 a narration cannot point into the person's lane, and the data tools have no door past the numeric guard (D-123).

**Tier 2, the Microsoft Agent Framework as the orchestration layer (offline; one live redeploy).**
- RM-06 the alignment spike and the hand-rolled inventory (47 rows) with a verdict per component (D-124).
- RM-07 every model-facing tool is generated from the catalog; nothing else defines one (D-125).
- RM-08 the tool rules (budget, commit refusal, client, year and method, schema, capture) are function middleware inside the model's loop (D-126).
- RM-09 a foundry-only provider chain is served by the framework's own chat client; a chain that names a gateway keeps the custom client (D-127).
- RM-10a the Agent is the planner; JSON and keyword modes are one small degraded path (D-129). RM-10b the write path is a Workflow (prepare, request, commit; D-130). RM-10c the client review pack is a second Workflow (D-131). RM-10d where each pattern is allowed, and that no executor or tool body computes a figure, are tests (D-132). RM-10e nothing was done by weakening a guarantee.
- RM-11 agent as code: `azure.yaml` is the orchestrator's definition, and the twelve specialist prompt agents are declared in one list (D-133).
- RM-12 hosting: **NO-GO**, the host stays behind the `main.py` seam; the seam and the protocol rule are tests (D-128).
- RM-13 parity and conformance: 19 questions across five doors, 102 answers compared, identical (D-135). One adapter bug found and fixed.
- RM-14 the MCP facade is kept, proved standard by the SDK's own client and an 89-test conformance suite; four gaps in it fixed (D-136).
- RM-15 the knowledge tier is a port, a fake and a context provider, off by default; a cited passage is never a figure (D-134, ADR-010).
- RM-16 API, gateway and the orchestrator (agent version 21) deployed; invariants 13 of 13 before and after; **live verification not finished** (below) (D-137, D-138).

**Tier 3, layering, SOLID, DRY (offline, behaviour-preserving).**
- RM-17 the composition root is `backend/bootstrap/`; `application` imports nothing from `infrastructure`, and the inner rings import no framework or SDK (D-139).
- RM-18 routers send requests through the mediator and import no adapter; the one `api` allow-list entry is gone (D-140).
- RM-19 a `GoldReadPort`, and `gold_reader.py` (1,821 lines) became a package of 16 modules with identical reads (D-141).
- RM-20 `backend/config.py` is the only reader of the process environment (D-142).
- RM-21 small wins: dispatch tables in the renderer, `numeric`, `composer` and `knowledge` packages, an ADR-009 note on the fixed pipeline (D-143).

**Tier 4, structure and docs.**
- RM-22 (this package) docs: a "Start here" and an index of every docs folder, ADR-006 and ADR-001's successor in the index, stale UI briefs and dated evidence archived, the build log named as such with an index of the durable decisions, the hand-rolled inventory completed, [ONE-ANSWER-EVERYWHERE.md](../architecture/ONE-ANSWER-EVERYWHERE.md) and this summary (D-147).
- RM-23 executable code left `docs/` for `scripts/` (D-144). RM-24 `scripts/README.md` indexes every script (D-145). RM-25 folder maps for `channel_orchestrator/` and `backend/`, `variables.tf` in numbered sections (D-146).

### Deliberately not done, and why

| Not done | Why | Finding |
| --- | --- | --- |
| Anything under `frontend/` | The UI work is being split onto its own branch. Issues found are recorded, not fixed | the run's rule |
| Renaming `backend/tools` to `devtools` | It is not developer tooling: it holds the statutory math and the calculation trail, imported by 103 files; a rename would call the audit boundary a dev folder | F-42 |
| Splitting `domain/calculation/onezero.py` and `domain/claims.py` | The private reference fixtures are absent here, so the certified 10,236 / 539 / 656 gate could not run, and the import cycle is the fault a split hides | F-38 |
| The MAF hosting package | Pre-release only (`1.0.0b261030`) with no Activity handler; Teams works through the Responses bridge | F-01, D-128 |
| Replacing the MCP facade with the SDK | The SDK serves a second person on the first person's session and answers an unauthenticated call with HTTP 200; the binding is code either way | F-08, D-136 |
| The Foundry IQ adapter, the corpus, any Search resource | Designed, not built; needs owner decisions and provisioning | F-20, F-21, ADR-010 |
| Moving the Gold-read, forecast and other routers behind queries | Out of the brief's list and the Gold ones would move twice; pinned so they only shrink | F-35 |
| `application` still imports `tools`, `data` and `config`; adapters fall back to `get_settings()` | Larger than a package and not a behaviour change | F-36, F-41 |
| One typed settings object for the orchestrator and the AI, knowledge and gateway parsers | The orchestrator vendors its parsers and cannot import the backend's config | F-40 |
| Grouping `chat_*`, `output_policy` and the audit modules; moving `synth.py` out of the shipped package; docstrings on about 300 port members | The same mechanical change with vendoring and allow-list updates; postprovision needs `synth.py` | F-43, F-44, F-45 |
| A what-if, data or write step in the review pack | A step that chose a worksite or a size in code would invent it; a model inside a fixed sequence would make it open-ended | F-14 |
| A durable write checkpoint | A pending confirmation does not survive a restart (as before); the single-use token must not be persisted | F-15, D-130 |
| Running the composer over the portal's prose | The portal's narration still streams unchecked (the known limit in ADR-008) | F-23 |
| A portal what-if, `explain` and `eligibility` on the catalog tool | Needs a product decision on how a city in a sentence becomes a worksite | F-22 |
| Resuming the shared Fabric capacity | A shared resource outside this run's guards | F-30 |

### Residual risks

- **Nothing the run changed in the orchestrator has been exercised end to end on the live service.** The ten live questions, the prepared write, the review pack and the smoke's data steps did not run because the Warehouse was unavailable (the capacity was suspended). Agent invariants (13 of 13) and the framework client's reach of the model host were verified (F-32). The framework path, the Workflows and the middleware are proven in process only.
- **`CHANNEL_CALLER_CHANNELS` is unset in the live gateway,** so an agent's claimed channel is trusted at the enum level for every registered caller (F-34, D-120).
- **The Origin default for `/mcp` is unverified against the real Cowork client** (F-27); a wrong default would refuse its connection, and the setting and RUNBOOK say how to add one origin.
- **The portal's narration is not checked.** Anything shown to a customer must render from the evidence pane and the canonical values, not the stream (F-23).
- **The parity proof ran on the synthetic payroll in a SQLite stand-in,** not on the Warehouse; the hosted handler, a real model in the Agent loop and Cowork's own client were not driven (F-26).
- **Infrastructure drift**: five in-place changes (plan SKU, `always_on`) that the run did not cause and did not apply (F-31); `always_on` off makes the first request after idle slow.
- **Unverified deploys**: the `azure.yaml` fields RM-11 added were not deploy-tested (`azd` was not run for them); the RM-03 alert query was not run against a workspace; the two additive Warehouse migrations were read, not run on a fresh Warehouse; `FOUNDRY_MODEL` sits under a name the extension's documentation reserves (F-17).
- **When the Warehouse is down, every orchestrator reply says the audit is unavailable,** including for a read whose tool call had already failed (F-33): correct for a write, arguably too strict for a read.
- **The release gates are pending**: the full backend and frontend suites and `check_all.py` have not run on the final tip (the orchestrating session runs them once).

### The owner's decisions

1. **MAF hosting package, go or no-go.** NO-GO today. Re-check when the package is generally available, serves `activity`, passes the acting person into a workflow, and leaves `azure.yaml` and the endpoint protocols unchanged; the conditions are in [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md) ("Hosting: go / no-go and when to re-check"). Nothing to do until then.
2. **MCP SDK or the facade.** Recommendation: keep the facade (D-136). Revisit if the SDK gains a hook to bind a session to an authenticated principal, or if a client we must serve speaks only the 2026-07-28 protocol (F-28).
3. **Knowledge tier provisioning.** Whether to build the Foundry IQ source at all, the corpus and who approves it, whether a reader-visible quote may contain figures from the statute text, and the latency inside a Teams turn (F-21). The provisioning steps are in [KNOWLEDGE-AND-IQ.md](../architecture/KNOWLEDGE-AND-IQ.md) section 7; nothing was created.
4. **The branch split.** Which of `feat/m365-channel`'s work goes to `main`, and as how many branches; see FINAL-STATE.md ("Planned branch split") and PUSH-CHECKLIST.md. Nothing is pushed and `main` has not moved.
5. **`CHANNEL_CALLER_CHANNELS`.** Supply the agent's app id and the channels it may assert, and set it (value shape and the order of checks are in D-137), or accept enum-level trust (F-34).
6. **The App Service plan SKU and `always_on` drift.** Decide whether the live plan was scaled down on purpose (then follow it in the overlay) or the overlay is right (then `azd provision` restores it) (F-31).
7. **The QC-exception and employee-annotation commands (F-37).** Whether a non-writer person may resolve a QC exception or annotate an employee at all. Today any signed-in user can, and the annotation is in memory only; making them `Policy.WRITER` changes who may call a route.
8. **The Origin header for Cowork.** Confirm on the first live Cowork connection whether the client sends one; if it does, set `CHANNEL_MCP_ALLOWED_ORIGINS` (F-27).
9. **Resume the shared Fabric capacity and run the pending live checks (F-30).** Resume the capacity, then run the checklist in [evidence/live-remediation-2026-11-04.md](evidence/live-remediation-2026-11-04.md) ("How to finish"): the invariants, the live smoke, the twelve questions including a review pack and a prepared, uncommitted write, and the RM-09 points 3, 5 and 6. If anything regresses, pin agent version 20.
10. **Smaller questions the findings raise:** whether the stored `decided_by` should be one representation everywhere (F-24); whether to rename `FOUNDRY_MODEL` (F-17); whether `definitions_match` should include the temperature (F-18); whether the Warehouse-down wording should change (F-33).

## RM-06: Microsoft Agent Framework alignment spike

Source and evidence: [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md); decision [D-124](DECISIONS.md). Framework versions: core 1.24.0, foundry 1.16.0, openai 1.18.0, hosting `1.0.0b261030`, `mcp` 2.3.0.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-01 | Framework | `agent-framework-foundry-hosting` has only alpha and beta releases and no Activity protocol handler (nor do `azure-ai-agentserver-core/-responses/-invocations`) | A GA hosting package; an Activity host | RM-12 is NO-GO: keep the host behind `app/main.py`. Teams works through the Responses bridge (D-100). Revisit at GA |
| F-02 | Framework | `FoundryChatClient` calls `project_client.get_openai_client()` and exposes no `base_url`; from the hosted runtime the project host did not resolve and the account's OpenAI host did (D-101) | An endpoint override on `FoundryChatClient` | RM-09: use `OpenAIChatClient` or `OpenAIChatCompletionClient` with the account host; try `FoundryChatClient` only if `/modelprobe` shows the project host resolves |
| F-03 | Framework | Function middleware never sees a call to a tool that is not registered (`_tools.py` answers "not found" first) | A middleware hook for unknown calls | RM-08: record a refused tool name (including a `*_commit`) in a `ChatMiddleware`; never register a refusing stub, which would put a commit in the model's set |
| F-04 | Framework | A mapping `input_model` is validated only for top-level `required`, `additionalProperties: false`, `enum` and primitive `type` | Full JSON-schema validation | Keep `jsonschema` against the catalog schema in a middleware step |
| F-05 | Framework | No multi-provider failover chat client | A failover client | Keep `ModelChain` for a multi-provider or customer-gateway chain only (RM-09) |
| F-06 | Framework | MAF tool approval needs a structured reply; Teams and Copilot Chat send text | An approval path for a free-text channel | Confirmation is a Workflow `request_info` whose reply our exact-word gate produces (RM-10b). **Done (RM-10b, D-130)** |
| F-07 | Repository | The catalog does not say which arguments the reader owns (`client_id`, year keys, what-if sizes) or which tools a model may name; the orchestrator hard-codes both (`CLIENT_PLACEHOLDER`, `YEAR_KEYS`, `SCENARIO_NUMBERS`, `_NOT_FOR_MODELS`). `channel/tools.py` defines `channel_ping` by hand outside the catalog, and `channel/mcp.py` `describe()` edits descriptions of prepare and commit tools | Catalog metadata; a stated rule for the description edits | RM-07 adds the metadata and an architecture test with a named allow-list; RM-13's conformance test states the allowed description delta. **Done in RM-07 (D-125):** `CapabilitySpec.reader_owned`, `code-only`/`debug` tags, `catalog.model_schema`, `catalog.channel_description`/`behaviour_hints` and `catalog.CHANNEL_PING` replace every hand-written copy; the allowed description delta is exactly `channel_description` (a prepare tool carries `PREVIEW_SENTENCE`, a commit tool `COMMIT_SENTENCE`; the MAF tools carry the catalog's own description unchanged) |
| F-08 | Repository | D-65's blocker for the MCP SDK (handlers run away from the request that carries the token) no longer holds in `mcp` 2.3.0: `ServerRequestContext.request` carries the request's headers in stateless and stateful mode. The SDK does not bind a session to its user | A session-owner check in the SDK | **Resolved by RM-14 (D-136): the facade is kept.** The spike confirmed the finding, measured the consequences (one conversation id for two people; HTTP 200 for an unauthenticated call) and the facade is now held to the specification by a conformance suite and the SDK's own client |

## RM-08: tool rules as MAF middleware

Source: [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md) (Outcome cells R1-R11, H7), decision [D-126](DECISIONS.md). Nothing here weakens a guarantee; two framework limits were met and worked around.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-09 | Framework | `FunctionMiddlewarePipeline`, the object that runs function middleware, is not exported by `agent_framework` (only from the private `agent_framework._middleware`). Nothing public runs a function-middleware chain outside an `Agent` loop | A public way to invoke a tool through middleware without a model | The json and keyword modes (no tool-calling model) send each named tool through a one-shot `Agent` whose chat client asks for exactly that call (`maf_tool_run.OneCall`), so the same middleware runs and no private import is made. If the pipeline becomes public, `OneCall` can go |
| F-10 | Framework | The framework deep-copies an agent's `default_options`, including `additional_function_arguments`, so a per-turn object placed there is copied (here it holds an HTTP client and locks) | A way to mark a default as shared rather than copied | `ToolRunner.__deepcopy__` returns itself (a turn is an identity, and a copy would split the budget and the ledger). A per-run `function_invocation_kwargs` is not copied; the default is used so an `Agent` built per turn needs no argument at each `run` |
| F-11 | Framework | `ChatMiddleware` reaches a custom chat client only if the client's bases include `ChatMiddlewareLayer` (the built-in clients do; `PortChatClient` did not) | Documented in `ChatMiddlewareLayer`'s docstring only | `PortChatClient(FunctionInvocationLayer, ChatMiddlewareLayer, BaseChatClient)`; a test fails if the recorder is not wired |

## RM-09: the foundry provider on MAF's chat client

Source: [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md) (P4, P6, G8, F-02, F-05), decision [D-127](DECISIONS.md). Nothing here weakens a guarantee.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-12 | Framework | `OpenAIChatCompletionClient` takes no timeout, retry count or HTTP client; those can be set only by handing it a ready `AsyncOpenAI` (`async_client`), which needs the `openai` SDK imported in our code. The SDK defaults are a 600 s read timeout and two automatic retries | Client-level `timeout` and `max_retries` parameters | A `Deadline` chat middleware bounds each call at `AI_TOTAL_DEADLINE_SECONDS`, so the SDK's retries happen inside it; the SDK stays unimported in our code |
| F-13 | Live check owed | The framework path was verified in process only. Whether the account's OpenAI host answers the framework's request (including a `gpt-5` family deployment), whether the remote build installs `agent-framework-openai` and `openai`, and the per-turn client creation cost are unmeasured | A live run | RM-16 checklist in D-127 |

## RM-10: planner collapse and MAF Workflows

Source: [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md) (P1-P3, T1-T4, T7), decisions [D-129](DECISIONS.md) to [D-132](DECISIONS.md). RM-10e: nothing was done by weakening a guarantee; the parts below were left as they were, or bounded, and why.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-14 | Design boundary | The review pack (RM-10c) has no what-if step and no data step. A what-if needs a worksite and a size read from the reader's words or an earlier result; a step that chose either in code would invent it, and a model is needed to read them. The data questions are open Q&A. Findings, claim moves and the package are decisions, one confirmation each | Not a framework gap. MAF can put an agent inside a Workflow, but a model call inside a fixed sequence would make the sequence open-ended again and put a model next to the figures | The pack ends with one fixed sentence pointing the reader at the Agent for a what-if, a data question or the walkthrough, and at the write Workflow for changes. Revisit if a reader asks for a what-if with a named worksite inside the pack |
| F-15 | Framework | A workflow checkpoint is a pickle whose decoder allows only registered application types (`register_checkpoint_type`), and the only stores are in-memory, on disk and (with the hosting package) Foundry-backed. There is no ephemeral store scoped to one person's conversation that survives a restart and keeps a secret out of other replicas | A per-conversation secret store, or a way to checkpoint a workflow without its messages' secrets | The write Workflow uses `InMemoryCheckpointStorage` (one per paused write), so a restart loses a pending confirmation as the old path did; the single-use token is never persisted (D-130). If hosting reaches GA and the owner wants confirmations to survive a restart, the checkpoint would have to carry a reference, not the token |
| F-16 | Framework | A message type cannot be restricted to the executors allowed to create it: the framework routes by type, so any executor in a graph could send an `Approved` to `Commit`. Here only `AwaitConfirmation` does, by construction | A way to declare who may send a message type | An AST test (D-132) fails if `Approved` is constructed anywhere but `AwaitConfirmation`, if `Commit` is built outside the graph builder, or if `send_commit` is called from anywhere but the commit executor |

## RM-11: agent as code

Source: [ORCHESTRATOR.md](ORCHESTRATOR.md) (Agent as code), decision [D-133](DECISIONS.md). Nothing here weakens a guarantee.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-17 | Documentation vs live | `azure.yaml` declares `FOUNDRY_MODEL` under `env:`. The extension's reference reserves the `FOUNDRY_` and `AGENT_` prefixes ("don't define or override them in `env`"). It worked on the live service (CH-14), so the platform evidently reserves exact names rather than the prefix, but the documentation does not promise that | A live check that the name is not shadowed or stripped; a rename (for example `ORCH_MODEL`) would need `app/wiring.py`, ENV-VARS.md and the live agent changed together | Left as is. `test_orch_agent_definition.py` names it as the one known exception and fails if another reserved name is added. Decide at RM-16 whether to rename |
| F-18 | Existing behaviour | `foundry_publish.definitions_match` compares only the model and the instructions, so a change to an agent's `temperature` in `agents.json` does not publish a new version (the old version keeps its temperature) | Include the temperature in the comparison, which changes publishing behaviour and so was out of scope for RM-11 | Documented in ORCHESTRATOR.md. Until changed, a temperature edit needs a prompt version bump (which changes the instructions) or an `AI_AGENT_VERSION_PINS` move |

## RM-15: knowledge tier (design and port)

Source: [KNOWLEDGE-AND-IQ.md](../architecture/KNOWLEDGE-AND-IQ.md), [ADR-010](../architecture/ADR-010-knowledge-tier.md), decision [D-134](DECISIONS.md). Nothing here weakens a guarantee.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-19 | Existing property | The numeric guard's fact index reads numerals out of *prose* in a fact (a passage placed among the facts would make its figures acceptable). The guard trusts its facts | Nothing missing: it is by design that the engine's facts are the figures | The knowledge tier's rule is structural, not a property of the guard: an import allow-list, no fact or ledger name, a provider that may only add instructions, a registry of importers and one ledger writer, all architecture-tested (D-134). `test_the_guard_trusts_its_facts_…` states the hazard in the suite |
| F-20 | Framework | The framework's Azure AI Search context provider is in `agent-framework-azure-ai-search`, which has only beta releases (newest `1.0.0b261030`, 2026-11-04); the Learn class reference is dated 2025-12-08. Not installed, code not read | A GA package, and a check that it keeps citations where a turn can print them | A thin `ContextProvider` of ours over a `KnowledgePort`; the stable `azure-search-documents` 12.0.0 has `KnowledgeBaseRetrievalClient` for REST `2026-04-01` for the adapter. Revisit at GA |
| F-21 | Owner decision / live check | Whether a reader-visible quote may contain figures that appear in the statute text (labelled as quoted, not computed); the corpus, its approver and refresh; latency of a knowledge call inside the Teams turn; per-tier limits, prices, regions and which knowledge source kinds are GA | Owner decisions and a live run; nothing was run | Listed in ADR-010 ("Open decisions") and KNOWLEDGE-AND-IQ.md section 7; the tier stays off until they are answered |

## RM-13: parity and conformance

Source: `backend/tests/channel_orchestrator/parity_*.py`, `test_parity_figures.py`, `test_parity_conformance.py`, `backend/tests/test_architecture_adapters.py`; decision [D-135](DECISIONS.md). One adapter bug was found and fixed (the portal's discovery totals); the rest are named gaps.

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-22 | Rule gap, by design | Four portal chat intents do not run the catalog tool the rest of the system runs. `simulate` is the straight-line prototype (`simulate_headcount`: a city and a headcount over the configured default payroll, `warnings` say it is not scoped to a client), not the catalog's worksite what-if; `explain` re-narrates a trail cached by an earlier answer; `eligibility` reads Pay Period only (D-05); `discovery` and `multi_state` scan the configured default tenant, not the page's client (D-06). The parity cases for the last two pass only because the synthetic default tenant is the reference client | A portal what-if that takes the page's client and a worksite, which needs a product decision on how a city in a sentence becomes a worksite, and an `explain` that reads a client-year | Declared in `parity_cases.py` (`portal_na` with the reason) and asserted (`every case the portal cannot answer must say why`). The figures the portal shows are the capability's; the question it asks is not always the one the other doors ask |
| F-23 | Known limit, restated | The portal's narration is not composed or checked: its prose still streams unvalidated (ADR-008). The parity run proves what the portal SHOWS (the evidence pane) and what its narrators are TOLD (every number in a brief is a capability fact), not what a model then writes | Running the composer and the numeric guard over the portal stream | Unchanged. Anything shown to a customer must render from the evidence pane, not from the stream |
| F-24 | Inconsistency, not a figure | A preview names the person it would be recorded under (`set by`, `decided_by`) the way each door's credential names them: a user principal name from a person's own token, an object id from the orchestrator's headers. The same person is `pat@example.com` in Cowork and an object id in Teams | A display name or UPN resolved for the orchestrator path (`CHANNEL_RESOLVE_DISPLAY_NAMES` exists and is off by default) | Declared as volatile in `parity_compare.py` with this reason. Whether the stored `decided_by` should be one representation everywhere is an owner decision |
| F-25 | Declared lane difference | `data_catalog` says one more thing to a caller that is not positively Teams or Copilot Chat (the channel note about employee-level rows) | Nothing | `LANE_NOTES` in `parity_compare.py`; two doors of one lane agree exactly |
| F-26 | Not driven in process | The Foundry-hosted Responses and Activity host (only `TurnPipeline` is driven, not `app/main.py`'s handler); a real model inside the Agent loop; Copilot Cowork's own client (RM-14 drives the SDK's client instead); the Fabric warehouse (SQLite stands in: money stored as a float, the reader's `TOP` and `OFFSET ... FETCH` translated, the writer's post-write validation skipped) | A live run on the deployed stack (RM-16) | Recorded here and in the module docstrings; the fixture states its two differences from the deployed path |

## RM-14: MCP facade decision

Source: `backend/tests/channel/test_gw_mcp_conformance.py`, `backend/tests/test_architecture_mcp_facade.py`, [MAF-ALIGNMENT.md](MAF-ALIGNMENT.md) section 5, decision [D-136](DECISIONS.md).

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-27 | Unverified, owner action possible | Origin validation is new. The default, `CHANNEL_MCP_ALLOWED_ORIGINS` empty, refuses any `/mcp` request that carries an `Origin` header (403 `origin_not_allowed`, before the token is read). An MCP client is not a browser and sends none, but whether the real Cowork client does was not and cannot be checked offline | A live Cowork request log, or a first connection after the next deployment | The setting, ENV-VARS.md, RUNBOOK.md section 13.1 and COWORK-SETUP.md say how to add exactly one origin. Nothing is deployed in this run, so no live connector is affected yet |
| F-28 | Protocol, future | The SDK's newest protocol is 2026-07-28 (stateless, `_meta`-keyed, `server/discover`). The facade speaks 2025-11-25, 2025-06-18 and 2025-03-26, answers any newer `protocolVersion` with 2025-11-25 and 404/400s a `server/discover`; the SDK client's `auto` mode falls back to `initialize` against it (tested). A client that speaks only 2026-07-28 would not connect | Nothing yet: no known client does | Re-check condition recorded in MAF-ALIGNMENT.md section 5 |
| F-29 | Repository | `mcp` was installed in the development environment by hand and listed in no requirements file, so a CI run (`pip install -r requirements.txt`) would not have had the SDK the conformance test needs | The SDK brings `httpx2`, `sse-starlette`, `mcp-types` (and `pywin32` on Windows), which D-65 kept out of the deployed image | New `backend/requirements-test.txt` (`mcp==2.3.0`), installed by `ci.yml` after `requirements.txt`; the deployment packages install `requirements.txt` only. `test_architecture_mcp_facade.py` keeps the SDK out of every runtime requirements file |

## RM-16: live redeploy

Source: [evidence/live-remediation-2026-11-04.md](evidence/live-remediation-2026-11-04.md), decisions [D-137](DECISIONS.md) and [D-138](DECISIONS.md).

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-30 | Operations, owner action | The shared Fabric capacity (F2) is suspended every night (08:36 UTC on 4 November, 08:37 on 3 November, by a scheduled caller outside this repository) and was still suspended 90 minutes into the working day. While it is suspended every data path answers `503` and so does the audit, which gates every orchestrator reply; `/api/health` and the gateway's health stay 200. The live verification of RM-16 could not run | Someone resuming the capacity before a demo or a live run; or a documented window | Not resumed from here (guards, OPERATIONS.md). Owner resumes it; the run's checklist is in the evidence file. Added to OPERATIONS.md (failure signature) and KNOWN-LIMITATIONS |
| F-31 | Drift, owner decision | `azd provision --preview` shows 5 in-place changes that this run did not cause: the plan SKU `P1v2` live against `P1v3` in the overlay and `always_on` off live against on in Terraform for web, API, gateway and mock gateway. Nothing destructive | Whether the plan was scaled down on purpose (cost) and the overlay should follow, or the overlay is right and a `provision` should restore it | Not applied (D-137). `always_on` off on a P1 plan means the first request after idle is slow (the API's cold start is minutes), which matters for a demo |
| F-32 | Live check done | D-127 points 1, 2 and 4, and F-17, hold on the live service: the project host does not resolve and the account's OpenAI host does, the remote build installed the two new packages, the framework's client reaches `https://<account>.openai.azure.com/openai/v1/chat/completions` with a token (200), `FOUNDRY_MODEL` is not shadowed. Point 3 (the audit's `model` and `mode` fields), 5 (slow or failing model) and 6 (latency against the old path), and a `gpt-5` family deployment, are not verified | A run with the Warehouse up; a second model deployment | The checklist in the evidence file; no `gpt-5` deployment exists in this environment, so that case stays offline-only |
| F-33 | Design observation | With the Warehouse down the orchestrator replies "I couldn't answer that: the audit trail is unavailable; nothing was done." to every question, including ones the engine could not have been asked about (the audit is the gate, `narration` is reported at the end of the turn), and the RM-03 alert line fired once per turn. That is correct for a write and arguably too strict for a read that already failed | Whether a read whose tool call failed should say "the platform is unavailable" rather than blame the audit | Not changed (the refusal is the fail-closed rule, D-121 and D-123). The wording is a candidate for a small follow-up once the owner has seen it |
| F-34 | Owner action | `CHANNEL_CALLER_CHANNELS` is unset in the live gateway, so the channel an agent asserts is trusted at the enum level for every registered caller (the gateway warns at startup). The residual in D-120 stands | The agent's app id from the private notes, an owner decision, and `azd provision` or an app-setting change | D-137 gives the exact value shape and the order of checks |

## RM-18: routers through the mediator

Decision [D-140](DECISIONS.md).

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-35 | Deferred, layering | The routers outside the eight RM-18 names still hold route logic: `api/trend.py` (Gold reads in `v2_client_units`, `v2_client_unit_detail`, `v2_employee_detail`, `_with_lever`), `api/forecast.py` (3 functions), `api/retroactive.py`, `api/simulate.py`, `api/rules.py`, `api/summary.py` (2) and `api/eligibility.py` (1 line over). They are 17 named functions over the 40-line standard and pinned in `tests/test_architecture_routers.py::LONG_FUNCTIONS`, which fails on a new one and on a stale one. `forecast`, `retroactive`, `rules`, `rules_ingestion`, `simulate`, `summary`, `trend` and `workspace` also still import `tools`, `data` or `config` (pinned in `STATUTORY_IMPORT_ALLOWANCE`, which may not widen) | Queries for those routes, one per file, as RM-18 did for One/Zero; the Gold reads belong with the `GoldReader` port of RM-19 (the port now exists: `application/gold_read_port.py`, D-141) | Not done: out of the brief's list, and the Gold routes would be moved twice. Pinned so they only shrink. Each removal tightens the baseline |
| F-36 | Deferred, layering | `application` imports `tools` (about 30 sites), `data` and `config` directly, and `application/services.py` is a service locator. The brief's rule for the application ring is `infrastructure`, `fastapi` and the SDKs (D-139); the statutory math lives in `tools` | Constructor injection for handlers; deciding whether `tools/credit_math` and friends are domain or a service ring | Not changed. Both are larger than this package and neither changes behaviour |
| F-37 | Design observation | The two person-only writes moved behind the mediator (`ResolveQcExceptionCommand`, `ReviewEmployeeCommand`) declare no policy; the entitlement is the edge's `AGENT_FORBIDDEN_WRITES` plus signed-in access, as before | Whether a non-writer person should be able to resolve a QC exception or annotate an employee at all; today any signed-in user can, and the annotation is in memory only | Not changed (making them `Policy.WRITER` would change who may call a route). They are named open in `_OPEN_COMMANDS` with that reason; an owner decision |
| F-38 | Deferred, structure | `domain/calculation/onezero.py` (1,295 lines, two certified methods of about 240 lines each and `preprocess`) and `domain/claims.py` (666 lines, a 335-line `ProgramClaim`) are still single modules. `onezero.py` ends in re-exports from three siblings that import its private helpers back | A split with the private reference fixtures present, so the certified 10,236 / 539 / 656 gate runs; the two methods need cutting inside the function to get under the limit; `ProgramClaim` needs cutting across a class | Not done in RM-19 (D-141): only the synthetic gate (81 / 51 / 49) can run here, and the import cycle is the kind of fault a split can hide. Still on the CODE-STANDARDS backlog |
| F-39 | Design observation | `unit_drill` (11 keyword parameters, 77 lines) and `eligibility_population` (12, 58) stay over the standards in `gold_reader/`, and the port carries their optional parameters as `Unpack` TypedDicts to stay within seven arguments | Parameter objects for the two reads (a drill request and an eligibility query), which changes the callers and the capability layer | Not changed: it would alter call sites and the live-only tests. Two renamed baseline entries each; they may only shrink |
| F-40 | Design observation | `Settings` (RM-20) types the variables that were read directly (runtime, observability, data source, warehouse, stores, web search), but the AI, knowledge, gateway, sign-in/deployment and data-query settings are still parsed by their own mapping-taking modules, fed `get_settings().environ`. | One shared, vendored settings module that the orchestrator and the backend both import, so every section is parsed in one place | Not done in RM-20 (D-142): the orchestrator vendors the AI and knowledge parsers and cannot import `backend/config`, and moving them changes the vendoring closure and the orchestrator's own `app/core/settings.py`. The orchestrator was left as it is: it already parses a mapping and reads the environment only in `app/main.py`, `app/host.py` and `app/wiring.py` |
| F-41 | Deferred, layering | Adapters fall back to `get_settings()` when a value is not passed (`FabricWarehouseConnection`, the SQLite stores, the Blob and local artifact stores, `FabricLakehouseReader`), and `application` modules (`warmup`, `invoke`, `deployment`, `auth_policy`, `run_client_calculation`) import `config` directly. Nothing reads `os`, but the dependency on a process-wide accessor is still there (F-36 covers the same direction for `tools`) | Constructor injection from `bootstrap` for every adapter and a settings Protocol in `application` | Not done: many tests build adapters with no arguments and rely on the environment. `bootstrap/artifact_wiring.py` now passes its values explicitly; the rest follow when those tests are migrated |

## RM-21: small wins

Decision [D-143](DECISIONS.md).

| Id | Kind | Finding | What is missing or open | Handling |
| --- | --- | --- | --- | --- |
| F-42 | Deliberately not done, structure | `backend/tools` was not renamed `devtools`. It is not dev tooling: it holds the statutory math and the calculation trail (`credit_math`, `trail`, `unit_trend`, `fabric_source`, the grid filter), imported by 103 files (197 import lines, 27 of them in `application`), by 20 string or patch targets in tests, by `.gitleaks.toml`, `.github/copilot-instructions.md`, the architecture tests' layer lists and 110 files that mention the path. A rename would call the audit boundary a dev folder and could only be proven by the full suite, which this run defers to its end. | If wanted, split `tools/` by what it is: the deterministic compute into `domain` or `application`, the genuine developer scripts (`verify_*`, `backfill_gold`, `purge_test_claims`) into `devtools/`. That is a design change, not a rename | Owner decision; not scheduled |
| F-43 | Deferred, structure | Only three groups in `application/` were made packages (`numeric`, `composer`, `knowledge`). `chat_scope` / `chat_keywords`, `output_policy` and the `*_audit` / `*_alert` modules are still loose: they are vendored seeds (`chat_*`, `output_policy`) or imported by the gateway's allow-list by exact module name, and the brief's `ai_*` group has no cohesive set beyond `application/ai/` and `knowledge`. | Moving them is the same mechanical change, with `scripts/vendor-orchestrator.py` seeds and `test_gw_architecture.py` entries to update | Not scheduled |
| F-44 | Design observation | `data/source/synth.py` (920 lines, a code-standards baseline entry) could not move out of the shipped package: the public profile's postprovision runs `python -m data.source.load_fabric --synthetic-only`, which imports it. Its boundary is enforced instead (`test_architecture_fixtures.py`: no runtime module imports it, and importing `data.source` does not load it). | Splitting the file by client would shrink it; moving the loader and the fixture together under a `fixtures/` package would need `postprovision.ps1` and the deployment docs to change | Not scheduled |
| F-45 | Design observation | About 300 public functions and methods in `application/`, `channel/` and `channel_orchestrator/app` still have no docstring. Most are one-line port members (`ports.py`, `gold_read_port.py`, `source_ports.py`), the `services.get_*` accessors and middleware `process` methods, where the name and the type say everything. Sixteen helpers whose why was not obvious from the name were documented. | Add a why-docstring when a helper is next touched | Not scheduled |