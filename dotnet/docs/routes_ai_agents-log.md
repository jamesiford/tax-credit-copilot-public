# routes_ai_agents session log

## Preflight

- Worktree and branch verified clean: `dotnet/w2-routes_ai_agents`.
- Approved oracle reports CPython 3.12.13. No live services are authorized or contacted.
- Read the task, composition/host/domain reports, port map, contract sections 4-5,
  coverage, authentication and normalization contracts and the AI recordings.
- Work is restricted to the feature's five allocated path roots. No package is added.
- Prompt publication and numeral-integrity ports are independent bounded workstreams.
  Capability dispatch owns its own subfolder; stream/page assembly and API composition
  remain in the main workstream.

## Decisions and integration boundaries

- Keep all twelve captured agents; `manifest.json` is not an agent.
- Existing W1 injection/egress guards do not implement numeral integrity.
- Python's unconfigured chat emits fixed synthetic figures unrelated to the selected
  scope. Do not copy that defect: offline chat must render actual capability facts
  or a named unavailable dependency. Record this deliberate difference separately.
- Python's client summary invokes a router with a FastAPI `Query` default and
  reports a SQL binding error. Call the inward page source instead.
- Employee summaries remain deterministic/person-facing; employee identifiers,
  raw rows and near-miss person-level lines must not enter model context.
- Portfolio/discovery, page-drill shaping and write operations owned by sibling
  features require explicit inward seams, not endpoint self-calls or canned facts.

## Implementation evidence

- The packaged prompt bundle is independent of the working directory. All twelve
  bodies/counts/current hashes were compared with the Python capture on 3.12.13.
  The channel narrator retains manifest version 4 and its historical hashes.
- The publication client is an injected request/response seam; no installed
  Foundry publication or invocation transport is claimed.
- Page briefs cover all four scopes, recorded verdicts and supplied hours levers.
  Stored client-grid facts use the existing Gold port without an engine replay.
- Owned feature discovery maps chat and summary to mediator handlers and the
  existing flushing SSE transport. Initial source failures and synchronous or
  asynchronous provider failures are explicit, sanitized outcomes.
- Focused tests cover compound chat, clarification, malformed history, summary
  fallback/check events, privacy lanes, cancellation before output, real-socket
  flushing/disconnect cleanup, and W1 reservation/span cleanup after visible
  upstream failure without a retry or provider hop.
- Initial concurrent compilation exposed unfinished capability files and parent
  numeric/helper signature errors. Parent signature errors were corrected.
  Whole-solution gates are deferred until the independent files are coherent;
  no passing build/test gate was claimed at that intermediate point.

## Composed verification and corrections

- All twelve publication DTOs/prompts and strict versus page-precision numeric
  lanes passed focused tests. The page checker retains Python's binary64
  `1e-9` boundary, rather than introducing a decimal-only tolerance change.
- Corrected W1 dictionary serialization at the capability boundary and retained
  the application fixture book label. The complete captured situation envelope,
  not only its headline facts, now matches through ordinary host discovery.
- Real-socket tests found root-captured scoped collaborators through the shared
  singleton mediator. A keyed request-scoped instance of the existing mediator
  fixes completion/disconnect disposal without changing the shared pipeline.
- Whole-solution validation additionally caught optional handlers discovered
  without their feature services and direct adapter imports in an endpoint
  module. Explicit feature-local mediator forwarding adapters and an
  infrastructure-owned DI extension address both composition constraints.
- A verification run was interrupted by Windows DLL locks from this session's
  replay host. The host was stopped before rebuilding; no unrelated process was
  terminated. Later checks run without a concurrently loaded API binary.

## Semantic replay

- Ran all 36 exchanges of the unchanged `p1_artifacts_ai` scenario through an
  ordinary hermetic host using CPython 3.12.13 and absolute diagnostic paths.
- Initial raw AI board: 5/23 passing, 21.74%; 18 failing. The scenario has 192
  differences and 6 tolerated differences in total, including missing sibling
  setup endpoints. The required 95% gate is not claimed.
- Missing book/eligibility and portfolio/unit/employee projections are explicit
  503 or streamed dependency refusals. No IDs, fixture success bodies or altered
  scenario steps were substituted to get past missing ReadsCalc/Claims setup.
- Remaining differences include the intentionally removed fixed offline demo,
  the repaired client-summary router-default defect, validation English/context
  metadata and SSE charset spelling. Improvements are documented individually.
- The existing board wrapper reports raw results with zero waivers; the
  improvements register has not been treated as a passing replay result.

## Final measured gates

- Whole-solution `dotnet build -warnaserror -m:1 -nr:false`: passed with zero
  warnings and errors, targeting net10.0 with SDK 10.0.404.
- Whole-solution `dotnet test --filter 'Category!=heavy'`: 1,025 passed,
  zero failures/skips. API includes 213 owned AI cases out of 279.
- After the final infrastructure-owned prompt registration change, rebuilt the
  whole solution and reran all 279 API tests successfully. Whole-solution
  `dotnet format --verify-no-changes` passed on the final source.
- Replayed the complete scenario again against the final compiled ordinary
  host using fresh `dotnet\artifacts\ai-replay-final` diagnostics. It reproduced
  the initial 5/23 AI result, 192 differences, 6 tolerated differences and
  36 completed exchanges. No replay threshold is claimed.
- Both temporary replay hosts were stopped. No live external system, push,
  remote change or out-of-ownership product edit was used.
- Finish reports distinguish verified local/fake behavior from missing sibling
  production bindings and the unavailable production Foundry factory.

## Conductor follow-up: CA2026

- The conductor's newer analyzer flagged the undisposed document in
  `StreamEndpointTests.Parse`. The parser now uses an explicit `using` scope
  and returns a cloned element before disposing the document. Stream payloads,
  parsing assertions and the net10.0 target are unchanged.
- Re-ran exact whole-solution `dotnet build -warnaserror`,
  `dotnet format --verify-no-changes` and
  `dotnet test --filter 'Category!=heavy'` from `dotnet`: all pass,
  with zero build warnings/errors and 1,025 passing tests, no failures/skips.
- Also ran `dotnet build dotnet\TaxCredit.slnx -warnaserror` from the worktree
  root, where SDK 11.0.100 supplies the newer analyzer. It passes with zero
  warnings/errors; the project's pinned SDK is still 10.0.404 and all targets
  remain net10.0. No suppression or shared configuration change was needed.
- Re-ran the unchanged complete semantic scenario against a fresh ordinary
  host. `dotnet\artifacts\ai-ca2026-replay\board.json` and its `diagnostics`
  directory report the same 36 exchanges, 192 differences, six tolerated and
  5/23 AI cases passing (21.74%). The existing sibling integration blocker and
  unclaimed replay gate are unchanged. The temporary host was stopped.

## Conductor follow-up: excessive improvements coverage

- Read the conductor's full raw/adjusted boards rather than inferring success
  from the local single-scenario wrapper. The conductor completed 1,769
  exchanges and reported AI 24/27 after coverage (88.9%), with 16/27 cases
  waiver-dependent (59.3%); both thresholds fail.
- Traced each owned-register match. The summary privacy entry incorrectly
  matched missing portfolio/unit/employee services; the chat demo entry also
  matched unrelated history/header differences. This coverage was not proof
  of implemented behavior and is removed.
- Retained only the offline-demo and repaired-client-summary defect entries,
  constrained by route, case family, event category and event path. Verified
  against every conductor failure that these scopes can match only the three
  intended case/event families, never other page scopes, capability results,
  validation or headers.
- Removed inactive/general privacy/explanation/error waivers and withdrew
  incidental header/validation waivers pending a concrete policy decision.
  Production behavior remains unchanged; removed coverage exposes failures,
  rather than manufacturing a passing percentage.
- Added DEC-AI-1/2/3 under finish-status `needs_human`: resolve the explicit
  framework-artifact prohibition versus the case-waiver cap; confirm the
  designed offline/read contracts; integrate the missing canonical sibling
  projections. No decision is assumed and no replay gate is claimed.
- Re-ran whole-solution build (zero warnings/errors), formatting and all
  1,025 non-heavy tests successfully. No source behavior changed in this
  follow-up.
- Ran every unchanged scenario through a fresh ordinary host: twelve
  scenarios, 1,769 exchanges, 9,472 raw field differences, six tolerated.
  The owned AI scenario still has 192 differences. Exact four-route
  method/path selection yields 8/27 raw AI cases passing; the existing
  wrapper includes four other method/slash cases and reports 11/31.
- Against these fresh diagnostics, the retained register scopes can touch
  only three AI cases (at most 11.1% of the conductor denominator). Their
  header differences remain failures; this upper bound is not an adjusted
  acceptance claim. All missing service results remain unwaived.
- Diagnostics are under `dotnet\artifacts\ai-waiver-review`. The temporary
  host was stopped. The report and finish status preserve the unresolved
  policy/integration decisions rather than suggesting replay is green.

## Conductor follow-up: 48.1% AI replay and mandatory stop

- Read the task again in full and inspected the latest raw/adjusted conductor
  evidence: 13/27 AI passing (48.1%), 5/27 waiver-dependent (18.5%),
  1,769 exchanges, 8,868 failing fields and 737 covered fields.
- Confirmed no new canonical sibling implementation is available: the
  Application feature folders remain Ai, Framework and WorkspaceSealed.
  The current owned failures remain missing capability/page services,
  prohibited framework artifacts, or the already documented Python defects.
- The conductor's five waiver-dependent AI cases include W1 register matches.
  The feature's two retained event-only entries were not widened, and no
  other session's register was modified.
- Re-ran `dotnet build -warnaserror`, `dotnet format --verify-no-changes`
  and `dotnet test --filter 'Category!=heavy'`: all pass, zero build
  warnings/errors, 1,025 tests passed, no failures or skips.
- Verified CPython 3.12.13 and replayed all twelve unchanged scenarios through
  a fresh ordinary host after its health endpoint returned 200. Result:
  1,769 exchanges, 9,472 raw differences, six tolerated; exact four-operation
  AI selection 8/27 passing. The unchanged wrapper reports 11/31 because of
  its four additional method/slash cases, without improvements adjustment.
  The owned scenario remains 36 exchanges and 192 differences.
- Diagnostics are ignored under `dotnet\artifacts\ai-hard-stop-replay`.
  The owned host was stopped. No live external system was contacted.
- Recorded `HALT-routes_ai_agents.md` under hard stop 1: implementing absent
  sibling services needs unowned changes; copying their algorithms or changing
  fixed acceptance policy is not an authorized alternative. This deliberately
  withdraws `no_halt` as well as leaving `replay` unclaimed. Product code,
  calculated figures, comparators, scenarios and register coverage are unchanged.
