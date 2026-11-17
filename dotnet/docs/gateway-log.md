# Gateway implementation log

## Preflight

- Read the complete W3 assignment, convergence/AI/composition/persistence/source
  reports, Python channel trust/pipeline/transports, findings and ADR-008.
- The inherited convergence projection is not a fresh conductor execution.
  Gateway starts with an empty executable, not an implemented service.
- CPython 3.12.13 imports this worktree's backend. Development uses SDK 10.0.404.
- Direct NuGet TLS is unavailable on this machine; the configured Microsoft
  package-feed proxy works. No machine/source configuration was changed.
- Selected official ModelContextProtocol 1.0.0 (Apache-2.0, stable net10.0).
  Installed/resolved dependency evidence and actual protocol tests follow.
- Production bridges are implemented independently from the channel transport;
  Domain and Infrastructure remain dependencies, not alternative engines.

## G1: SDK and executable

- Installed official ModelContextProtocol 1.0.0 and Core 1.0.0, Apache-2.0,
  stable net10.0 assets. Existing Microsoft.Extensions pins remain unchanged.
- Actual SDK server and client initialize/list/call pass over HTTP. The
  transport adapter preserves channel sessions and JSON errors, not an SDK
  fork. SDK logging advertisement is a truthful registered framework default.
- Shared API startup/middleware is separate from route mapping. Ordinary
  gateway composition needs no upstream process.
- The executable has its own conductor marker launch target. Actual no-marker
  and explicit-opt-out launches both return control 404s and anonymous 401s.

## G2: production bindings

- Added all remaining read bridges and all eight owning-command prepare/commit
  pairs, with 33 application/API tests. Ordinary API and gateway register them.
- Pure previews allocate no business identities and mutate no business state.
  Existing durable person/tool/argument-bound confirmations and result recovery
  remain authoritative; injected ID/secret sources make real consumers testable.
- Package tickets are durable, hashed, expiring, person-bound and atomically
  consumed. New-scope/concurrent redemption and actual authorized byte reads
  pass. Capability package results are projected without changing API metadata.
- Native hidden-person/distinct suppression remains a named refusal when the
  infrastructure cannot prove it; unavailable datasets are not fake successes.

## G3/G4: trust and transport

- RS256 and strict claim-shape validation, separate app/delegated authority,
  acting-person validation and explicit principal push/restore are shared by
  REST/MCP execution. Origin precedes MCP identity; parsing preserves source
  ordering. Restoring that ordering also removed a genuine correlation offset.
- Forced internal Entra mode and strict writer entitlement for previews prevent
  portal-local anonymous/optional-writer settings from weakening channel access.
- Required read opening audits precede dispatch; closing failures log safely
  without masking accepted results. Recognizable write-envelope refusals now
  audit before dispatch too, covered by five final HTTP regressions.
- All catalogue schemas/descriptions, protocol versions and session lifecycle
  run through the real host. Person budgets, reset and env refresh are covered.

## G5: numeric integrity, narration and downloads

- Trusted bounded eight-hour ledger is isolated by person/conversation and
  cleared by reset. Verification never takes caller-supplied replacement facts.
- Composer validates/masks placeholders, checks raw words, renders through the
  inherited formatter and checks the final reply independently. Hedging and
  unsafe prose patterns also fail closed. No numeric engine was re-ported.
- Agent narration audit keeps safe codes/counts/hash, not submitted rejected
  prose. Download authentication precedes single-use spend and bytes are read
  as the ticket owner. Unknown/replayed ticket 502/410 semantics remain intact.

## G6: final evidence and decisions

- Strict whole-solution build: zero warnings/errors. Whole-solution format
  verification passed. **1,114 fast tests pass**, zero failures/skips:
  103 gateway, 365 API, 16 architecture, 18 Domain, 167 AI, 147 auth,
  129 persistence, 108 sources and 61 parity. No fast case exceeds 20 seconds.
- Four CPython policy diagnostic regressions pass. The oracle is 3.12.13.
  No live service or heavy suite was exercised.
- All 255 G1/G1L exchanges replayed against the actual no-profile executable:
  528 raw failing fields and raw 0/255 because every case has Vary. Separate
  policy diagnostic: **233/255**, 11 fully waived cases, 56 unresolved fields
  in 22 cases, no numerical waiver. The replay requirement is board-only.
- All nine API scenarios replayed: 1,514 exchanges / 2,325 raw failures.
  Two post-change executions have identical ordered failure lists in all nine.
  See the report for separate HTTP/control and historical-conductor denominators.
- Exact remaining cases/paths are committed in replay-gateway-policy.json.
  SDK logging, consistent error shape, safe lane markers, known correlation
  preservation and boolean display spelling have narrow improvement entries.
- Source person-lane omissions conflict with the designed Cowork restriction;
  prefer the fail-closed application lane and explicitly ask the owner to
  reconcile the valid-request policy. Missing facts are not waived.
- Later IDs differ because claim previews avoid throwaway production IDs;
  no dummy ID draws or identifier waivers were introduced.
- Cross-replica/different-confirmation idempotency reservation is not proved by
  the persistence port. M-01, first-program pricing, weak source fingerprint,
  native AVG/worksite/leap-day and live byte behavior remain owner boundaries.
- All proof processes were stopped. Only assigned paths changed; no remote
  operation or push was performed. Final status identifies the tested code
  commit; the following documentation commit records its report and status.

## Conductor build-gate correction (16 November 2026)

- Reproduced the exact root-selected SDK 11.0.100 failure with
  `dotnet build .\dotnet\TaxCredit.slnx -warnaserror`: the API project reference
  supplied `_framework/Microsoft.NET.Sdk.BlazorWeb.HotReload#[.{fingerprint}]!.lib.module.js`
  without a matching gateway static-asset endpoint.
- Set `StaticWebAssetsEnabled=false` only in the JSON-only gateway project.
  It serves no UI/static assets; API composition, executable launch targets,
  net10.0, SDK pins and all endpoint contracts remain unchanged.
- Root SDK 11 strict build passes, then the pinned SDK 10.0.404 strict build
  passes, then a root SDK 11 nonincremental whole-solution build passes.
  Each reports zero warnings/errors. Root whole-solution format verification
  also passes.
- The initial parallel fast-test/format run hit the inherited AI resilience
  test's 100 ms healthy-stream timeout. The complete unchanged fast suite
  passed with projects serialized (`-m:1 -nr:false`): **1,114 passed,
  zero failed/skipped**. Evidence: `artifacts\gateway-build-fix-fast-serial`.
  No tests, filters or timing thresholds changed.
- Reran the actual root/no-profile/no-build gateway and API executables with
  the conductor marker and isolated hermetic stores. Both health probes
  returned 200. All **255 gateway** and **1,514 API** exchanges executed.
  All twelve scenarios' complete ordered failure lists exactly match the
  original delivery: **528 gateway** and **2,325 API** raw fields.
- Gateway policy diagnostic remains **233/255**, 11 fully waived cases and
  56 unresolved fields in 22 cases; no numerical waiver. The board-only replay
  gate is exercised, not represented as full parity. Evidence:
  `artifacts\gateway-build-fix-replay` and
  `artifacts\gateway-build-fix-api-replay`.
- Both proof hosts were stopped. Fix commit: `3b3fae2`; the status/report commit
  follows it. No live systems, remote operations or out-of-scope edits.
