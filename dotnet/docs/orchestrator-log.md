# W3 orchestrator running log

## Preflight

- Read the complete conductor task, specification, inventory, 39 recordings and capture harness.
- Clean branch `dotnet/w3-orchestrator`; changes restricted to owned paths; no live services permitted.
- SDK 10.0.404; baseline warning-as-error build passed. Baseline fast suite:
  1,078 passed (332 API, 16 architecture, 18 domain, 167 AI, 147 auth,
  108 sources, 129 persistence, 61 parity); gateway/orchestrator initially have no tests.
- CPython 3.12.13 imports `contract` from this checkout when run from the root.
  An initial probe after changing cwd to `dotnet` failed to import `contract`;
  root cwd fixes the configuration, not an oracle defect.
- Current convergence report supersedes historical route HALTs. Domain slice
  remains certified; no engine code is being re-ported.

## O1 package feasibility

- Official Azure SDK README and NuGet metadata identify
  `Azure.AI.AgentServer.Responses` 1.0.0-beta.9, with Core beta.30.
  Both explicitly target net10.0; Responses uses `ResponseHandler`,
  `CreateResponse`, `ResponseContext`, `TextResponse`, not guessed Python names.
- Microsoft Agent Framework `Microsoft.Agents.AI` and `.Workflows` 1.28.0
  are stable, MIT, with a net10.0 asset. Responses is preview, MIT.
  `Microsoft.Extensions.AI.OpenAI` 10.11.0 supplies the official chat adapter.
- Verified installed signed package nuspec metadata as well as current official
  documentation. Direct NuGet HTTPS from PowerShell/curl fails TLS handshake;
  packages are already present in the machine cache. Restore/build will verify
  the complete graph rather than treating network access as SDK availability.
- Framework 1.28.0 requires DI/DI.Abstractions >=10.0.13; the shared pins are
  10.0.0. Reuse those declarations through `PackageVersion Update` in the
  owned orchestrator section. No gateway section edits or duplicate Includes.
- Sources: https://www.nuget.org/packages/Azure.AI.AgentServer.Responses/1.0.0-beta.9
  and https://www.nuget.org/packages/Microsoft.Agents.AI/1.28.0 ;
  https://learn.microsoft.com/azure/foundry/how-to/develop/framework-hosted-agents .

## Implementation and integration

- Installed package APIs, not Python-shaped facsimiles: `ChatClientAgent` with
  function middleware, `FunctionInvokingChatClient`, workflow request ports and
  checkpoint resume, and the Responses SDK's `ResponseHandler`/`TextResponse`.
- Production `Program` now validates configuration, composes the REST gateway
  and model adapters, and runs the official host. Default port is 8088.
  No custom Responses transport, Bot Activity transport, cards or streaming
  unverified prose was added.
- Exactly 25 shared catalogue definitions are built once. The common runner
  owns attempt budgets, whitelist, reader settlement, resolver-once, schema
  refusal, method expansion, deduplication, capture and safe model projection.
  Keyword, JSON and actual framework planning all enter that middleware.
- Verified person/conversation leases serialize selection and confirmation.
  Source precedence, identity refusal, debug-off posture, service bearer auth,
  `X-Acting-*`, correlation and idempotency are separately exercised.
- Composition uses Application envelopes, fact indexing, formatting and
  `NumericGuard`; valid placeholder masking precedes raw-numeral checking.
  Final bodies are independently checked. Person-only rows and confirmation
  tokens never become narrator authority. Provenance/reference text is
  separately labelled, not falsely described as guarded numeric body.
- Framework checkpoints own pending commands. Confirm resumes a fresh graph;
  concurrent/repeated confirmations cannot repeat a mutation. Unknown commits
  remain non-confirmable; unrelated reads remain usable. Package commit
  success survives a failed/cancelled post-commit link read.
- Runtime knowledge uses the source `KNOWLEDGE_ENABLED`, `KNOWLEDGE_PROVIDER`
  and `KNOWLEDGE_TOP` names. The only enabled built-in provider is explicitly
  synthetic `fake`; `foundry-iq` is explicitly not implemented.
- Official OpenAI 2.14.0 is a stable MIT dependency. Its token-policy
  constructor is experimental (`OPENAI001`); the suppression is scoped to
  that constructor. The production factory uses an explicit endpoint and
  Entra policy, never ambient API-key discovery. The default credential is
  process-lazy. `Azure.Identity` is assembly-aliased because Azure.Core 1.63.0
  also exposes the type name; no shared foundation code was changed.
- W1 still owns provider chains, egress, budgets, retry, breaker, bulkhead and
  deadlines. Text-only providers are skipped for tool requests, not removed
  from JSON/text chains. SDK retries are disabled to avoid duplicate retry
  owners. Configured-but-missing clients fail rather than defaulting.

## Corrections made during validation

- Corrected new test assumptions, not source contracts: global `data_catalog`
  precedes client resolution; SDK explicit conversation/response-chain keys
  outrank header fallbacks; an ordinary bare-year question uses the existing
  eligibility fallback rather than necessarily producing help.
- Parent command parsing now preserves the source's trailing `.`/`!`
  confirmation grammar. Bare `yes` is still not confirmation.
- Diagnostic total budgets use monotonic elapsed time and remaining-time
  clamps, including uncooperative probes and delayed timer callbacks.
- The cancellation-during-package-link regression uses an explicit read-start
  signal instead of a wall-clock race. Known commit success is retained even
  if framework cancellation wins while fetching its link.
- No pinned figures, recordings, comparison thresholds or Python tests changed.

## Final validation

From `dotnet`, using SDK 10.0.404:

1. `dotnet build -warnaserror --nologo -v quiet`: passed, zero warnings/errors.
2. `dotnet format --verify-no-changes --no-restore --verbosity quiet`: passed.
3. `dotnet test --no-build --filter 'Category!=heavy' --nologo -v quiet`:
   **1,509 passed**, zero failures/skips. Orchestrator: **431** cases.
   The unchanged foundation contributes the other **1,078**.
4. All **39** named deterministic source records pass, including exact text,
   semantic debug JSON, arguments, modes, model-called flags and cumulative
   conversation call tails.
5. Complete named index: **313 / 313**, 32 groups; **156 E, 103 P, 15 U,
   39 X**. This is not a claim of 313 equivalent executable .NET tests.

All orchestrator cases run below the heavy-test threshold. No live Foundry,
Fabric, Entra, customer endpoint, DNS probe or model generation was used.
The installed SDK wire proofs use local/injected transports. Deployment and
the complete multi-surface/golden matrices remain explicitly unverified.

## Conductor gate repair

- The conductor reported CA2026 at `WriteWorkflowTests.cs(287,63)` for
  `JsonDocument.Parse(body).RootElement.Clone()`: the temporary document was
  never disposed. The test now clones from an explicitly scoped `using`
  document, keeping the reply independent of the disposed owner. No assertion,
  production behavior, target framework or analyzer configuration changed.
- Re-ran whole-solution warning-as-error build, formatting verification and
  all fast tests from `dotnet` with SDK 10.0.404: passed, zero build
  warnings/errors and **1,509 tests passed**, zero failures/skips.
- Also ran those same solution gates from the repository root with installed
  SDK 11.0.100, where the additional analyzer is active: all passed, including
  **431 orchestrator cases** and the **39 deterministic records**. Projects
  still target net10.0; no .NET 11 API or feature was introduced.
- Repair commit: `b602404`. Status and this log are recorded in its descendant.
  Existing O5 integration and deployment limits remain unchanged.
