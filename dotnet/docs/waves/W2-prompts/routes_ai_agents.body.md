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
