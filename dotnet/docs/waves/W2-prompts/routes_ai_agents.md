# Chat, summary and capabilities routes; prompt agents and their publishing

Session `routes_ai_agents` of wave `W2`. You run unattended: nobody will answer questions, so do not ask any.
Worktree: `C:\Projects\GitHub\tcc-dotnet-w2-ai` (branch `dotnet/w2-routes_ai_agents`, created from `dotnet/integration`).

---

## Pre-approved decisions (policy)

The owner decided these in advance. Follow them without asking. If something needs a decision that is not covered here, choose the reading closest to the documented design and the Python behaviour, record it in STATUS.json under `needs_human`, and continue.

- **parity**: Equivalent behaviour, not bug-for-bug. The target is the designed functionality and the contract a client depends on: the same routes and methods, authentication and authorisation, request and response fields and their types, the meaning of each status code, money as a decimal string with its scale, and the same calculated figures for the same valid input. Do not reproduce defects, accidents of Python, FastAPI or Pydantic, or artefacts of the recording harness (plain-text error bodies, key order, number lexemes such as 5.0 versus 5, byte-level headers and wording, HEAD and trailing-slash quirks, reflected CORS headers). Never write code whose only purpose is to reproduce a defect or a framework artefact. Where the Python behaviour is a bug or an accident, implement what the design, the ADRs, the docs or sound engineering intend, and record it in dotnet/docs/improvements/<session>.json (see improvements_register). If the same issue turns up naturally in the .NET code, that is acceptable; note it as a finding.
- **parity_tiers**: The replay runs in semantic mode (values equal; key order and number lexeme free). Tier A (certified-figure routes and every gateway tool result): the values must be equal, and a changed figure is never an improvement. Tier B (everything else with a JSON body): values equal. Tier C (error responses): keep the error shape family (a JSON body with `detail`, as the clients read it) and the right status; the message text is free. Tier D (zip and xlsx container bytes, timing, model output): out of scope. Anything else that differs from a recording for a good reason goes in the improvements register, not into reproduction code.
- **python_oddities**: Fix defects instead of reproducing them. F-2 to F-6 (plain-text 500s): return the JSON error family with the correct status, a 4xx where the cause is a client error, and never a stack trace. F-8 (duplicate claims): handle duplicates as the claims design intends (idempotent or a 409), and record which. F-14 to F-16 (inconsistent writer checks): apply the writer check consistently to every route that writes. F-1 (a GET that never returns because magnitude is unbounded): bound it and refuse out-of-range values with a 422. F-17 and every other entry in contract/FINDINGS.md: apply the same principle; read the finding first. Exception: if fixing something would change a calculated figure, a stored value or an authorisation outcome for a valid request, keep the Python result, and list it under needs_human as a fix candidate for the owner.
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

Implement the four `ai` HTTP operations and the prompt-agent roster/publication contract. Application features belong in `dotnet\src\TaxCredit.Application\Features\Ai`, endpoints in `dotnet\src\TaxCredit.Api\Endpoints\Ai`, tests in `dotnet\tests\TaxCredit.Api.Tests\Ai`, and agent infrastructure in `dotnet\src\TaxCredit.Infrastructure.Ai\Agents`. The four operations are `GET /api/capabilities`, `POST /api/capabilities/{tool}`, `POST /api/chat` and `POST /api/summary`.

Correct the brief's count using captured evidence: there are 12 prompt Markdown files, 12 roster agents and 12 captured publication requests. `manifest.json` is metadata, not a thirteenth prompt. Keep the captured roster and prompt versions rather than creating an extra agent to satisfy the brief. This task implements API capabilities and deterministic scripted stream behavior, not the W3 gateway or hosted orchestrator.

## Preflight

Read `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`, `dotnet\docs\COMPOSITION-REPORT.md`, `dotnet\docs\HOST-ARCHITECTURE.md`, `dotnet\docs\DOMAIN-SLICE-REPORT.md`, `dotnet\docs\port-map.md` and relevant `dotnet\docs\findings.md` entries. Then read `contract\CONTRACT-REPORT.md` sections 4-5, `contract\COVERAGE.md`, auth/normalisation documentation, `contract\recordings\p1_artifacts_ai.jsonl`, `contract\recordings\agents.json`, the agent inventory and production roster/manifest sources.

Inspect `backend\agents\agents.json`, `roster.py`, `_prompts.py`, `factory.py`, all 12 prompt Markdown files and `prompts\manifest.json`; trace the actual provider publishing function used by the capture. The current channel-narrator prompt is manifest version 4, while older hashes remain history. Captured requests use `agents.create_version`, `PromptAgentDefinition`, a `tcc-` name prefix and `contract-model`; temperatures vary by agent. Do not infer the publishing payload solely from display profiles.

Reconcile W1 adapters with current code: `AddTaxCreditAi` supplies guards, router/resilience, budgets, unframed events and offline degradation, not endpoints, capabilities, prompt agents or a production publishing/invocation factory. Shared host composition now registers the real graph; configured Foundry without a factory is explicitly unavailable. Register owned services through pre-build feature modules and exact endpoint groups, leaving shared startup and the existing adapters intact.

Verify the numeric-guard prerequisite rather than assuming it exists: W1's prompt-injection/egress guards are different from ADR-008's numeral-integrity check. The current .NET safety folder has those provider guards, but no demonstrated numeral guard. Trace `backend\application\numeric\guard.py` and its sibling types/extract/context/facts modules plus capability formatting. Any missing guard work needed by these routes belongs in this feature's Application code, not in unowned W1 safety files or a speculative Domain rewrite.

## Stage 1: lock prompt and fake-publication fidelity

Create the roster/prompt loading and publication abstraction under the allocated Agents folder. Preserve roster order, names, model roles, temperatures, empty tools and exact current instruction text. Load or package resources in a way that works with the existing project/resource arrangement; do not silently depend on the planner's absolute machine paths. The original Python prompt/roster files remain the read-only reference, and any .NET copies/resources stay within Agents.

Use `contract\recordings\agents.json` as the publication oracle. For all 12 agents compare call name, agent name, definition type, resolved model, supported/omitted temperature, instruction character count and SHA-256, extra keyword list, and returned published name/version/id projection. Roles must resolve through supplied model configuration, not hardcoded deployment names. The contract model is fake test configuration, not a runtime model choice.

Test prompt-manifest validation with a changed prompt and a stale/current hash mismatch. Read `_prompts.py` to preserve the intended text/newline normalization and version-selection semantics rather than hashing differently normalized text until the digest happens to pass. Use `test_agent_roster.py`, `test_agent_modules.py`, the existing manifest-check specifications and the captured fake-client results.

Use an injected recording client to capture publication requests. This establishes request construction and mapping without requiring a new SDK dependency in a shared package file. Report any installed-SDK invocation gap separately from a verified request DTO/fake-client seam.

Checkable result: the 12 current prompts validate against their manifest, a mutation is refused, and 12 fake publication requests match the captured request fields/hashes without contacting a model or service.

## Stage 2: implement capabilities and settle cross-feature prerequisites

Trace `backend\api\capabilities.py` and `backend\application\capabilities` catalogue/invoke/envelope/format and tool implementations. Implement the catalogue's offered-versus-declared distinction and invocation boundary, not just the few tools with direct API success recordings. Preserve tool names, argument schemas, default arguments, client targeting, confirmation/idempotency fields, result envelopes, evidence/trail data and controlled errors. Declared/unbuilt/debug-disabled tools must retain their intended refusal rather than disappear or pretend to run.

Cases in `contract\recordings\p1_artifacts_ai.jsonl` include `capabilities.list`, `capabilities.unknown-tool`, `capabilities.book-rank`, `capabilities.book-rank-bad-arg`, `capabilities.client-situation`, `capabilities.client-situation-missing-arg`, `capabilities.client-eligibility`, `capabilities.args-not-object`, `capabilities.idempotency-key-too-long` and `capabilities.debug-tool`. Add focused evidence for catalogue operations not exercised there using `test_capabilities_api.py`, `test_capabilities_envelope.py`, `test_capabilities_equivalence.py`, `test_capabilities_program_code.py`, `test_capabilities_missing_targets.py` and data-capability tests.

Dispatch tools to application/domain calculations and W1 repositories, not to an API calling itself over HTTP. Preserve caller/client authorization and commit idempotency semantics; a timeout response must not imply a commit cannot later land. Governed data queries use `IGoldDataQueryPort` and its existing bounds/authorization, not arbitrary SQL. Raw employee data must not be sent into narration context.

The ReadsCalc portfolio/discovery work and Claims/Drafts application services are being written in parallel and are absent from this base. First map each offered capability and page-brief/chat dependency to an existing W1 port/certified helper or a concrete missing sibling service. Use existing callable behavior where available, expose a narrow feature-owned invocation seam, and test required external collaborators with realistic contract-backed fakes. Do not claim a fake collaborator proves ordinary-host invocation. Document exact unresolved production bindings for integration instead of copying sibling calculation logic, mapping their endpoints or returning recorded fixture answers.

Checkable result: catalogue and locally satisfiable capability calls work on the ordinary host; every remaining tool dependency is identified by name, required contract and owner. Invalid arguments, disabled tools and unauthorized targets have the recorded envelope/status family.

## Stage 3: implement scripted chat/summary and numeric checking

Implement deterministic chat routing/history and page-brief assembly from trusted application facts. Read production `agents\page_summary.py`, `tools\page_brief.py`, `portfolio_brief.py`, `brief_format.py` and chat routing to understand which summary fields and fallback text are generated by tools, not by the model. Include portfolio, client, unit and employee scope with the same required client/token/month checks.

Use the existing unframed W1 event/provider abstractions and the API `EventStream` transport helper. Chat frames include ordered `status`, `agent_start`, `token` and `done`; summary uses `brief`, `fallback` or `token`, `check`, then `done`, with `error`/`done` where recorded. Derive exact sequences and event payloads per case from recordings; the family description is not a universal sequence for every refusal. Both operations stream, despite the old exemplar claiming summary alone does.

Cover `p1_artifacts_ai:chat.ask`, `chat.ask-client`, `chat.history`, `chat.empty-message`, `chat.bad-history`, `summary.portfolio`, `summary.client`, `summary.unit`, `summary.employee`, `summary.bad-page`, `summary.client-without-client`, `summary.short-token` and `summary.bad-month`. Use `test_chat_routing.py`, `test_page_summary.py`, `test_unavailable_rows.py`, `test_numeric_guard.py`, `test_numeric_guard_lanes.py` and relevant capability equivalence tests for unrecorded application paths.

Complete the needed numeric guard from production `application\numeric`: raw model numerals and final substituted facts have different checks; exact facts, user-supplied context, dates/years, structural markers, percentages, abbreviations and non-ASCII numeric evasion are not interchangeable. Exercise a one-digit perturbation, an unsupported abbreviation, a fabricated date, a permitted reader year and a non-ASCII digit. Reuse existing exact numeric primitives where appropriate; this guard does not estimate or repair a changed figure.

Checkable result: scripted responses are assembled from real trusted facts, recorded ordered events and payloads match, and numeral-integrity refusals are demonstrated independently of injection/egress guards.

## Stage 4: verify streaming lifetime and composed behavior

Exercise the endpoints over a real local HTTP stream as well as in-process tests. Confirm `event: name\ndata: JSON\n\n` framing, per-frame flushing, no-cache and buffering-disabled headers, Unicode/JSON encoding and a single terminal sequence. Cancel before the first event and midstream, and exercise an upstream scripted failure so disposal releases budgets/scopes and does not emit a second terminal event. Reuse W1's no-retry-after-visible-output and request-scoped degradation behavior rather than adding an endpoint-level retry loop.

Run complete relevant replay scenarios with fresh absolute diagnostics and ordinary feature discovery. `p1_artifacts_ai` starts by capturing a unit/employee token and findings from other groups, then creates/downloads a package. A missing ReadsCalc/Claims handler can prevent later AI cases from being reached; report that setup dependency explicitly and retain direct endpoint evidence instead of synthesizing IDs or editing the scenarios.

Write `dotnet\docs\ROUTES-AI-REPORT.md` describing all four routes, catalogue/dispatch completeness, numeric-guard status, the 12-agent hash/publication matrix, event-case evidence and unresolved production feature bindings. Distinguish verified scripted/fake-client behavior from an installed production Foundry transport. W1b explicitly leaves production invocation unavailable without its factory; fake publication evidence is not proof of a deployed agent or a live model.

Checkable result: normal host discovery supplies the new routes, local deterministic paths and stream lifecycle are exercised, every captured publication is accounted for, and any unsatisfied sibling dependency is visible as a concrete integration item.

## Traps to expect

- `CONTRACT-REPORT` sections 4-5 make SSE event ordering/framing part of the observable contract. Serializing an async sequence as JSON or buffering it to request completion is not the recorded stream.
- W1's `IModelGuard` addresses injection/egress; the numeral guard addresses factual integrity. The two cannot substitute for each other, and a bare chat model's tool events do not authorize execution.
- Prompt/manifest hashes and instruction counts are not container-byte exceptions. `channel_narrator` has current version 4; preserve its history without publishing old instructions.
- Agent roster `ClientSituationAgent` and `ReportingAgent` use temperature 0.3; rules ingestion uses 0.1. The default 0.2 is not correct for every agent.
- Tool facts and fallback wording may depend on deferred portfolio/page-brief work. A prompt agent cannot invent those missing facts. Preserve null/unavailable distinctions and calculate outside narration.
- Source fingerprint markers are not Delta versions; governed monetary AVG and the M-01/first-program/fiscal/zero-worksite boundaries remain inherited. Narration cannot reconcile or reinterpret their figures.
- Shared project/package files and the existing AI safety/provider implementations are not part of Agents ownership. Use current references and injected publishing contracts; report a concrete wiring/dependency gap instead of expanding those files.

## Evidence this plan is based on

- `dotnet\docs\SOURCES-AUTH-AI-REPORT.md`: W1 guards/router/budgets/events and scripted degradation; prompt agents, HTTP framing, numeric integration and SDK publication were not verified.
- `dotnet\docs\COMPOSITION-REPORT.md` and `dotnet\docs\HOST-ARCHITECTURE.md`: real AI graph, offline provider, explicit unavailable Foundry factory and pre-build feature discovery.
- `dotnet\docs\DOMAIN-SLICE-REPORT.md` and `dotnet\docs\port-map.md`: already-certified calculations versus deferred portfolio/discovery and agent/page-brief work.
- `contract\CONTRACT-REPORT.md`, `contract\COVERAGE.md` and `contract\recordings\p1_artifacts_ai.jsonl`: four-operation HTTP surface, both streaming routes, scripted cases and setup dependencies.
- `contract\recordings\agents.json`, `backend\agents\agents.json` and `backend\agents\prompts\manifest.json`: 12 agents/prompts/requests, exact instruction hashes and current channel-narrator version.
- `backend\application\numeric\guard.py` and sibling modules: numeral-integrity semantics missing from the demonstrated W1 guard prerequisite.
- `parity\export_gold_payload.py` and existing calculation evidence: trusted figures originate in tools, not prompt-generated arithmetic.

---

## Gates (checked by the conductor after you finish, mechanically)

- `no_halt`: no HALT.md in the worktree
- `commits_present`: at least one commit on your branch
- `clean_tree`: everything committed
- `not_pushed`: the branch is not on any remote
- `owned_paths`: every changed file is inside your owned paths
- `status_json`: the STATUS.json finish file exists and parses
- `report_present`: the report files named below exist
- `dotnet_build`: `dotnet build -warnaserror` passes on the whole solution
- `dotnet_format`: `dotnet format --verify-no-changes` passes
- `tests_fast`: all tests not tagged `heavy` pass
- `replay`: the contract replay (semantic mode) meets the thresholds for your route groups; failures covered by your improvements register entries are shown separately and are capped
- report required: `dotnet/docs/ROUTES-AI-REPORT.md`
- replay thresholds: ai >= 95%

If a gate fails you will be resumed with its output and asked to fix it. Run the same checks yourself before you finish.

---

## Rules (fixed by the conductor; they cannot be changed by the task)

- **Work only in `C:\Projects\GitHub\tcc-dotnet-w2-ai`** (branch `dotnet/w2-routes_ai_agents`). Do not edit the main checkout or any other worktree.
- **Never push, never open a pull request, never change a remote.** Pushing is also blocked mechanically; do not try to work around it. Commit locally in small, sensible commits with the trailer `Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>`.
- **You may create or modify only:** `dotnet/src/TaxCredit.Application/Features/Ai/**`, `dotnet/src/TaxCredit.Api/Endpoints/Ai/**`, `dotnet/tests/TaxCredit.Api.Tests/Ai/**`, `dotnet/src/TaxCredit.Infrastructure.Ai/Agents/**`, `dotnet/docs/**`. The last entry, `dotnet/docs/**`, is always yours for reports, logs, status files and the improvements register; it never needs an exception. Any other change fails a gate. Never edit existing product files (`backend/`, `frontend/`, `infra/`, `scripts/`, `channel_orchestrator/`, `docs/`, `.github/`) unless they are inside your owned paths.
- **The reference is the Python product on CPython 3.12** (`C:\Projects\py312-oracle\.venv\Scripts\python.exe`): it shows what the system is meant to do, but it is not a specification to copy defect for defect. Build the designed functionality and the contract clients depend on; do not reproduce defects or framework accidents. Never change the Python code. Record each deliberate difference in `dotnet/docs/improvements/routes_ai_agents.json` as the policy describes, and record Python oddities in `STATUS.json` under `findings`. A changed calculated figure is never an improvement. Never loosen a comparison, delete a test or weaken a threshold to make something pass.
- **Nobody can answer questions.** Use the policy decisions above. When a decision is missing, take the reading closest to the documented design and the Python behaviour, record it under `needs_human` in `STATUS.json`, and keep going.
- **Customer-neutral:** no customer names, tenant or server names, identifiers, tokens or secrets in any file, log or report. Synthetic data only.
- **Tests:** tag long-running tests `[Trait("Category", "heavy")]`; the fast gate excludes them. Keep the fast gate quick.
- **Shared files:** put package versions only inside your marked section of `Directory.Packages.props` if your session has one; never add a package another section already declares. Register your services and endpoints from your own project (an `AddXxx` extension or endpoint-group class); do not edit another session's files.
- **Keep a running log** of decisions, findings and gate results in `dotnet/docs/routes_ai_agents-log.md`.
- **Budget:** you have a limited time and credit budget. Finish each stage with its checks green before polishing, and finish the whole task rather than perfecting one part.

---

## Hard stops (fixed by the conductor)

Write `dotnet/docs/HALT-routes_ai_agents.md` (what happened, what you tried, what a human must decide), commit it, and end the run if any of these happens:

1. A push, a remote change, a change outside your owned paths, or a destructive command outside your worktree would be needed.
2. A secret, token, tenant or server name, customer identifier or private data would be written to a file.
3. Equivalent behaviour for the designed functionality cannot be reached after three honest attempts on the same item (this is a valid, important result: report it, do not hide it).
4. The Python oracle environment is not CPython 3.12, or imports the wrong checkout, and configuration cannot fix it.

---

## Finish (fixed by the conductor)

When the task is done, or you are stopping at a hard stop, write `dotnet/docs/status/routes_ai_agents.json` in your worktree and commit it. It is machine-read; it must be valid JSON with this shape:

```json
{
  "session": "routes_ai_agents",
  "branch": "dotnet/w2-routes_ai_agents",
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
