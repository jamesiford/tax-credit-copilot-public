# Hosted orchestrator on Microsoft Agent Framework (.NET)

Session `orchestrator` of wave `W3`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-w3-orchestrator` (branch `dotnet/w3-orchestrator`, created from `dotnet/integration`).

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

Implement `TaxCredit.Orchestrator`, replacing the Python hosted orchestrator with Microsoft Agent Framework for .NET and the actual Foundry Responses hosting package. Preserve deterministic planning, argument settling, identity, guarded reply composition and confirmation workflows. Model behavior is specified by scripted tests, not by comparing live generated prose.

Own Orchestrator project/tests and its marked `dotnet\Directory.Packages.props` section. Add missing pins; previews are acceptable for the named framework/hosting dependencies. Use Application/ServiceDefaults references instead of vendoring. Gateway runs in parallel and owns missing capability bindings: use its existing REST contract, not uncreated sibling types or edits to its Application/API paths.

## Preflight

Read `contract\docs\ORCHESTRATOR-SPEC.md`, `contract\inventory\orchestrator.json`, `contract\recordings\orchestrator.json` and `contract\orchestrator_capture.py`. There are 25 model tools, not gateway's 36. Map the 313 pytest guarantees to .NET tests; layout/vendoring/deployment checks need equivalent architecture evidence, not copied Python folders.

The 39 records are keyword.00-.24, conversation.00-.05, identity.nobody, six host answers and host.conversation-key. Keyword rigs are fresh; conversations share state and capture the last two cumulative calls, not per-turn deltas. Resolve/yes/yes does not demonstrate prepare/commit, nor `keyword.10` successful simulation. Prove confirmation using scripted write-flow/e2e cases.

Read `dotnet\docs\ROUTES-CONVERGENCE-REPORT.md`: 978 passing fast tests and repaired shared setup supersede isolated historical HALTs. `ROUTES-AI-REPORT.md` supplies guards/envelopes, not every capability, a production Foundry factory or W3 composer/ledger. `CanonicalCapabilityReads` handles two bridge reads; Gateway owns completing the rest.

Trace `channel_orchestrator\app\main.py`, `host.py`, `wiring.py` and `core\turn.py` through planners, identity, client, argument rules, composer and `maf_*`. Only `main.py` imports hosting: one text handler; SDK-provided Responses transport/readiness/shutdown, default port 8088. No Bot Activity, SSE or cards.

Run from `dotnet` for SDK 10.0.404, not root SDK 11, and establish the baseline. Oracle: `C:\Projects\py312-oracle\.venv\Scripts\python.exe`, importing this checkout. Use the certified foundation in `dotnet\docs\DOMAIN-SLICE-REPORT.md`, `port-map.md` and `parity\README.md`.

## Stage O1: settle framework and Responses hosting feasibility first

Verify official .NET Agent Framework/Foundry Responses package IDs, versions, maturity, licences and net10.0 support from current docs/APIs; add pins/references. Do not guess C# names from `azure.ai.agentserver.responses` or substitute custom ASP.NET hosting/planning for the required SDKs.

Resolve the complete graph: W1 hit NU1605 from newer Azure dependencies against DI 10.0.0. Reuse shared declarations without editing the gateway section. Record incompatible transitive requirements precisely; a missing pin is not a blocker.

Build the smallest actual framework tool loop and real Responses handler with injected scripted model/gateway transports. Test one input-text turn, request/context mapping, readiness, cancellation and graceful disposal. Keep SDK-specific adapters thin enough for deterministic logic to run without starting a host. Definitions/tools may be singletons only if they contain no turn/person/conversation state.

The recordings cover `answer`/context, not raw Responses HTTP. Add package-backed local wire tests, not lookalike DTOs. Document actual SDK gaps precisely while completing independent deterministic work.

Checkable result: packages build together; the official host invokes the handler and the framework calls a tool. Separate actual SDK, fake and deployment evidence.

## Stage O2: person, conversation and gateway boundary

Implement source identity precedence from platform original-subject and allowed header signals, normalize the specified identifiers and carry the opaque platform ID only as context, never as trusted identity. Missing or invalid person identity produces the recorded refusal with no gateway or model call. Do not supply a default client/person to make degraded mode work.

Conversation key selection preserves explicit conversation, response-chain and source fallback semantics. Key all mutable reader selection, framework checkpoints, trace and pending workflow state by verified person and conversation. A reused response chain must not share state between people. Exercise `host.subject`, `host.no-signal`, `host.conversation-key` and `identity.nobody`, then the identity/spec tests covering case, conflicting signals and absent context.

Implement an injectable REST client with service authentication and verified reader assertions, not arbitrary inbound credential forwarding. Distinguish gateway `X-Acting-*` from API `X-TCC-Acting-User`. Preserve conversation/correlation/idempotency through calls and audit; bound requests, support cancellation and sanitize failures.

The fake gateway must implement authorization, errors, confirmations and envelopes faithfully, not return success for every call. Retain both model-visible facts and person-only blocks/paths in the client response object so projection occurs deliberately at the model boundary. An unavailable upstream remains an explicit dependency failure, not an empty numeric answer.

`/whoami`, `/netcheck` and `/modelprobe` are debug-gated text commands, not public HTTP diagnostic routes. Default debug is off; enabled startup warns. Match `host.whoami-off`, `.whoami-on`, `.whoami-on-no-signal`, `.whoami-case` and `test_orch_debug_posture.py`, keeping credentials and private headers out of output. Network/model diagnostics must be injectable/local in tests.

Checkable result: two people can share singleton definitions/client infrastructure without sharing identity, selected client, workflow or ledger association; anonymous/debug-off behavior performs no unauthorized calls.

## Stage O3: catalogue tools and one settling pipeline

Project exactly the 25 model-facing tools from the canonical existing catalogue with its descriptions/schemas, preserving the model projection's exclusion of commits, resolver and internal plumbing. Treat `contract\inventory\orchestrator.json` and `test_orch_catalog_tools.py` as comparison evidence. Build definitions once; their bodies take per-invocation context and forward through the common runner without doing calculations or hiding errors.

Use framework middleware/adapters for one common execution path shared by framework, JSON and keyword planning. Follow the production runner's order for budget accounting, whitelist/refusal, client resolution, reader-argument settling, clarification, schema validation and execution. Do not independently reimplement these decisions inside each generated tool closure.

Port reader-selected client/year/state/program/method precedence and follow-ups from `test_orch_tool_rules.py` and `test_orch_runner.py`. A model cannot replace the reader's year/client or invent simulation inputs. Resolve a named client once, retain only permitted conversation selection, distinguish ambiguity/no match, and ask before any unsafe/defaulted call. Method selection must preserve explicit Pay Period versus both-method requests, not silently choose another calculation.

Read budgets count attempts, including refused calls where the source does; a model cannot evade limits with unknown tools or repeated errors. Cover ordered split questions, several tools in a turn, exhausted budget, malformed arguments, safe refusal and repeated resolver use. Keep the framework's actual tool call trace in the common audit path, and ensure the final reply is composed once from the turn's own results.

Checkable result: all three planners share settling/refusal behavior; definitions retain no caller state.

## Stage O4: degraded planners and all deterministic records

Implement both production degraded planners: no model uses keywords; a model without tool calling uses JSON planning; a reachable tool-calling model uses the actual framework agent. A prompt rejected by the injection screen reaches no model. Failure before tools falls back to keyword planning with the source notice; failure after tools retains returned evidence and discards failed narration rather than replaying a mutation.

Compare all 39 records by ID: text, mode, calls/arguments, model-called flag and host outputs. Mirror rig boundaries/cumulative slicing. Include empty, ambiguous, out-of-range, follow-up, data, compound and unsafe questions.

In particular verify `keyword.06` versus `.07` for both/Pay Period selection, `.10` for the actual recorded what-if behavior, `.13` for absent referent, `.19` for injection and `conversation.03`-.05 for what they truly did. Recorded refusal or clarification is not permission to fabricate a successful write, nor a substitute for the scripted confirmation tests.

Use `test_orch_data_planning.py` to cover catalogue-then-query order, at most one lookup-driven replan, no replan if a query already exists, malformed plans and tool budgets. Port the deterministic review-pack behavior from `test_orch_review_pack.py`: named invocation, its own read-only step budget, missing-year and ambiguous-client follow-ups, continued partial results and no figures if every step fails.

Checkable result: 39 named comparisons plus scripted tests cover capture gaps; explain source/spec discrepancies.

## Stage O5: guarded composition and model/person numeric lanes

Use Application's capability envelopes, `CapabilityResult.ModelFacts()`, `NumericGuard`, fact indexing and formatting, not vendored backend modules. Preserve unknown-audience fail-closed behavior and person-only path filtering. Person rows and employee identifiers remain available only to the authorized reader; a model sees the permitted structural/count/name projection, never those row values in facts, blocks, warnings, traces or exceptions.

Build the model brief once for every planner/narrator path. Trusted numeric values are represented by allowed fact paths/format placeholders; models do not calculate or directly write the platform's figures. Validate placeholder paths and formats, including known path components containing digits, before masking them for raw numeral checking. `NumericGuard.CheckRaw` does not perform that masking itself.

Compose in source order: validate blocks/trusted facts, check raw model-authored text with valid placeholders masked, substitute trusted formatting, check the finished answer independently, then apply the defined fallback/output policy. Reject model-authored numerals even if equal to a fact; handle unbound paths, invalid formats, unsupported numbers, Unicode digit evasion, percentages, dates, years, abbreviations and hedging. A failing narration is dropped as a whole; trusted deterministic blocks remain only if independently valid. Never use model prose to fill a missing trusted value.

Preserve method/tool labels; omit lookup-only blocks if another tool answered, but keep a genuine catalogue answer. Append trusted source/provenance footer at the production composition point without asking the model to rewrite identifiers. Audit allowed verdict/rule codes and the verified person/conversation through gateway narration audit, not rejected prose or person-only fact paths.

`test_orch_data_lanes.py`, `test_orch_numeric_lanes.py`, `test_orch_exactness.py`, `test_orch_placeholders.py`, `test_parity_figures.py` and `test_parity_conformance.py` define the boundaries. Assert every model request's projection, not just final rendered text. The page-summary guard deliberately has weaker precision semantics and portal chat is numerically unchecked; neither is an ADR-008 substitute.

Knowledge is disabled by default. When enabled it is separately fenced reference material, never additional trusted numeric facts or placeholder authority. `test_orch_knowledge.py` covers failed retrieval, passage bounds, citation placement and removing reference blocks when narration degrades. No live retrieval is necessary to prove those rules.

Checkable result: a scripted narrator's invented digit, copied person row or invalid placeholder is detected; retained finished replies pass the guard on their own and match deterministic golden composition where recorded.

## Stage O6: framework checkpointed prepare, pause and confirm

Implement the change workflow using the framework's actual checkpoint/resume/state facilities. The prepare tool is model-visible; commit is not. Pending state records only the allowed canonical command, verified person/conversation, preview, expiry, confirmation/idempotency metadata and workflow status. It is not a second mutable state machine alongside an independent framework workflow.

Prepare calls the gateway and displays its trusted before/after preview. The confirmation token is withheld from both the model and reader. A subsequent explicit yes/confirm resumes the matching checkpoint; no, cancellation, a different request and expired state follow the specified source transitions. Clarification while a change is pending must not silently commit or transfer it.

Bind pending state to person/conversation. A different person's confirmation reaches no commit and cannot consume the owner's preview. Check expiry at the exact source boundary using an injected clock. Serialize competing confirmation attempts so at most one commit is attempted. Repeated yes after successful commit does not write again; replay/expired/conflicting gateway outcomes remain visible.

Commit timeout/fault is an unknown outcome: do not automatically retry, restore a confirmable preview or report a fabricated success. Reuse the original idempotency identity for permitted result recovery rather than generating a new command. Framework cancellation and checkpoint failure must leave an explicit safe outcome, not a silent fallback to a fresh write.

Use `test_orch_write_flow.py` and `test_orch_e2e.py` equivalents through the actual framework workflow and a faithful gateway fake: successful prepare/confirm, cancellation, wrong person, expiry, repeated yes, concurrent confirms, reader refusal at preview and timeout after dispatch. Assert gateway call order, one mutation, token exclusion from all model/reader text, and audit records for both steps. The six deterministic conversation records alone do not prove this.

Checkable result: a pause/resume turn crosses real framework state boundaries with one authorized commit, while wrong-person, expired, cancelled or uncertain workflows cannot execute another mutation.

## Stage O7: model adapters, actual Responses wire proof and handoff

Follow `test_orch_maf.py`, `test_orch_foundry_client.py`, `test_orch_models.py` and `test_orch_resilience.py` for model access description, role-specific chains, framework client selection, token-provider auth, endpoint/deployment mapping, unsupported sampling parameters, timeout and fallback. Keep W1 guard/budget/retry/egress responsibilities in their existing adapters where accessible, not in duplicated per-tool code.

Use injected local transports to assert actual SDK outbound request shapes. In a Foundry-only chain the framework's own client performs the real loop; chains that name other configured providers retain their intended routing. A configured-but-unavailable provider is not replaced by a secretly defaulted client, and model-generated text is not returned directly as the finished response.

Exercise a real local request through the installed Responses package, its handler context, shared turn pipeline and scripted collaborators. Assert request/response framing, input-text extraction, complete guarded text, verified identity/conversation propagation, readiness, cancellation and debug-off behavior. Test definitions and runtime configuration without treating the existing Python deployment manifest as a .NET deployment or adding W4 infrastructure work.

Map all `ORCHESTRATOR-SPEC.md` groups to tests. Replace folder/vendor checks with reference/isolation assertions; separate W4 metadata from executable configuration. Capture coverage, scripted guarantees, actual SDK wire proof and deployment are separate claims.

Write `dotnet\docs\ORCHESTRATOR-REPORT.md`: package/licence/maturity proof, architecture/references, 39-record results, specification traceability, workflow/failure semantics and gateway integration contract. Name unverified features. W2's twelve fake-client publications are definition evidence, not this orchestrator's deployment.

Checkable result: the executable serves a guarded Responses turn through the installed package; tests and handoff identify upstream/deployment limits.

## Traps to expect

- Gateway catalogue, model catalogue and API capability catalogue are different projections; internal redemption and commit plumbing must not become model-callable.
- Captured shared-conversation call lists are cumulative tails; success-shaped questions and recorder comments are not successful-write evidence. Raw Responses HTTP frames were not captured.
- A framework label on a bespoke loop/pending dictionary is not SDK orchestration/checkpoint proof.
- Shared singleton definitions must not close over person/conversation state. Model fallback after a tool call must never repeat an accepted mutation.
- Missing, null, empty, zero and unavailable are different contracts. Money strings retain scale; invariant culture, certified Python numeric helpers and field-specific dates matter when rendering facts.
- Existing `NumericGuard.CheckRaw` needs caller-side validated-placeholder masking; page-summary checking and portal chat are weaker paths. Final-output checks alone do not prove models never received person-only data.
- Existing source count/max fingerprints are not snapshots; native monetary AVG, strict leap-day handling, zero-worksite projection, M-01 ingestion precedence and first-program pricing remain inherited limits. Orchestration cannot reinterpret those figures.
- Target-framework compatibility alone does not establish transitive compatibility or host API availability.

## Evidence this plan is based on

- `contract\CONTRACT-REPORT.md` and `inventory\orchestrator.json`: 25 model tools, 39 deterministic records, host versus model scope.
- `contract\orchestrator_capture.py` and `recordings\orchestrator.json`: fresh/shared rigs, cumulative call tails, actual keyword/refusal behavior and host identity outputs.
- `contract\docs\ORCHESTRATOR-SPEC.md`: the 313 named test functions governing framework tools, identity, planning, lanes, placeholders, workflow, models and host seams.
- `dotnet\docs\ROUTES-CONVERGENCE-REPORT.md`: current merged baseline and repaired historical host/source defects, without gateway-completeness proof.
- `dotnet\docs\ROUTES-AI-REPORT.md`: canonical envelopes, reusable guard semantics, absent W3 composer/ledger and missing production invocation/bridge limits.
- `dotnet\docs\HOST-ARCHITECTURE.md`, `COMPOSITION-REPORT.md`, `PERSISTENCE-REPORT.md` and `SOURCES-AUTH-AI-REPORT.md`: trust/lifetime seams, durable confirmations, dependency compatibility and provider limitations.
- `dotnet\docs\DOMAIN-SLICE-REPORT.md`, `findings.md`, `port-map.md`, `PLATFORM-RISKS.md` and `parity\README.md`: certified inward calculations, numeric/fiscal traps and limits of native/live proof.

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
- report required: `dotnet/docs/ORCHESTRATOR-REPORT.md`

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-w3-orchestrator`** (branch `dotnet/w3-orchestrator`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/src/TaxCredit.Orchestrator/**`, `dotnet/tests/TaxCredit.Orchestrator.Tests/**`, `dotnet/Directory.Packages.props`, `dotnet/docs/**`. The last entry, `dotnet/docs/**`, is always yours for reports, logs, status files and the improvements register; it never needs an exception. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/orchestrator.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/orchestrator-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-orchestrator.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/orchestrator.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "orchestrator",
  "branch": "dotnet/w3-orchestrator",
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
