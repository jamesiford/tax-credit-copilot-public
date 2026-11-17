# routes_claims implementation log

## Preflight

- Branch `dotnet/w2-routes_claims`, initially clean. Only the allocated feature,
  endpoint, test and .NET documentation paths will change. No push or live service.
- Oracle verified: CPython 3.12.13; `application` imports this worktree's backend.
- Read the W1 domain, persistence, sources/auth/AI and W1b composition reports,
  schema provisioning, host architecture, route registry, contract findings,
  coverage, auth contract and contract report sections 4-5.
- The registry assigns exactly 24 operations to this feature. Ordinary production
  feature discovery is the registration seam; shared project files stay unchanged.
- Existing `ClientAssessment` already implements selected/all-year sweeps and
  status-preserving refresh. `QcResolutions` is certified but deliberately absent
  from the run writer (CAP-10). Neither is to be reimplemented.
- Packages use the live five-sheet stored-result builder, not the sealed exporter.
  The current Python service uses a fresh generation segment. Recorded F-5 is an
  older immutable-path collision; repeat creation will remain immutable and have
  an explicit request-boundary outcome.
- No dependencies added. First prototype uses BCL ZIP/XML; package XML/member
  compatibility, not Excel appearance, is the acceptance criterion.
- Native `tcc_ops.finding_audit` remains an unapplied operator prerequisite.

## Stage 1

- BCL ZIP/XML implementation passed both real-host package tests (17.8 seconds
  combined on the warm run). Every one of the 13 uncompressed members matched
  the recorded name, order, size and SHA-256, including dates/styles/properties.
- Workbook scans reject employee-id, record-token and tax-id column leakage.
  Only explicit stored-result allowlists reach sheets.
- Fresh generations use the full injected UUID. Truncating its prefix collided
  under deterministic IDs and could also reduce production entropy. Bytes are
  published before metadata. Repeats return 201, supersede only live metadata,
  and preserve earlier bytes. Wrong-client downloads are audited as denied.
- XML line endings are normalized to LF independently of the checkout OS.
  Text remains inline text, including formula-like input.
- Whole-solution warning-as-error build passed. No package/project changes.

## Stage 2 progress

- Claim commands use the certified domain lifecycle, readings and money; direct
  identical assertions return 409, while transitions and assessment refreshes
  append history. Coverage, situation and portfolio read stored claims only.
- Assessment delegates the complete sweep to `ClientAssessment`, normalizing
  only initial identities/time through host seams and attaching fiscal metadata.
- Preserved the named valid-request F-14 assessment exception (`Policy.Open`);
  other new command policies are Writer.
- P2 seed import exceeds the fast-test budget. The P2 integration test is
  heavy; its earlier bounded 60-second run was aborted during the P2 integration
  test. The exact blocking call was not established; it is not a behavior result.
  P1 remains the focused fast integration gate.

## Stage 3 and composed verification

- Findings list/resolve/reopen/history use real persistence. Focused integration
  proves visible decisions, append/supersession, immutable resolve/reopen audit,
  assign validation, and client isolation without applying annotations to runs.
- The ingestion-QC application contract is a separate lookup namespace with
  client/year-scoped certified snapshots; its command goes through the mediator.
  A test proves a fresh scope and reset; no ReadsCalc or writer file was changed.
- Rules use the existing registry, captured ingestion and PackValidator.
  Practitioner decisions persist through the lookup store. Captured refresh,
  NEEDS_KEY proposals and apply's 404/422/503 distinctions are exercised without
  live retrieval. The named F-14 reader verification exception remains Open.
- Channel audit uses real metadata storage and repository filters; a test proves
  pending/completed collapse, time bounds and limits. Person-only access remains
  enforced by the host and handler.
- Added artifact missing/corrupt-byte tests and a formula-like attribution test.
  Registered failures are audited, corrupt bytes never stream, and literal text
  never becomes a formula. Successful creation has an API-relative Location.
- Added a small three-year assessment test with real claim persistence. A sweep
  records all years; targeted refresh retains the proposed decision and prior-year
  base without mutating another year/program. This test passes in 3 seconds.
- Fixed typed-dictionary wire normalization, which the first replay exposed as an
  array of key/value pairs for package row counts. The package test now checks the
  actual JSON object shape in addition to the uncompressed members.
- No packages were added. Openpyxl-derived static OOXML assets carry their MIT
  copyright/license in `openpyxl-assets-LICENSE.txt`.

## Hard stop

- Whole-solution fast run: 4 failures, 718 passes, 722 total. Seven non-API
  projects pass. Three framework failures reproduce on a focused rerun; the
  fourth was the feature claim test's 30-second timeout under parallel load,
  which passes in isolation.
- Two shared framework tests explicitly require the newly assigned `/api/rules`
  operation to remain 501. A third bypasses feature-module registration while
  validating auto-discovered feature handlers. These are not silently waived.
- `HALT-routes_claims.md` records hard stop 1. No shared tests/composition files
  were changed and no further feature implementation was attempted after the
  conflict was established.
- Replay diagnostics retain raw differences, including sibling 501s and their
  downstream deterministic-ID effects. No comparison or threshold was loosened.
  The report distinguishes focused proof from incomplete semantic acceptance.
- All seven complete relevant scenarios finished on fresh, OS-assigned local
  ports and separate stores: 397 group-classified cases, 156 raw passes, 241
  failures (39.29%). The P2 scenario completed; its earlier integration-test
  timeout is not evidence that P2 endpoints cannot answer. No adjusted score is
  claimed. The diagnostic runner now exits nonzero for a red raw board.
- Final whole-solution build: passed, zero warnings/errors. Final whole-solution
  format verification: passed, after explicitly sorting four import blocks
  (the project formatter had left those diagnostics untouched).
- All ten focused feature tests passed together in 49 seconds. The QC reset
  test reached 23 seconds under concurrent verification load and is now heavy.
  No product behavior changed after that passing test run.
- Removed only the inspected synthetic probe/replay state directories; retained
  complete raw scenario diagnostics and reproducible probe/replay scripts.
- No local replay host remains. An attempted reuse of port 5187 encountered a
  sibling worktree's listener, so that attempt was stopped without terminating
  the sibling process; final scenario evidence exclusively uses OS-assigned
  ports and separate state. Initial multi-scenario reset failures were not
  repaired or claimed as passing; fresh-per-scenario hosting avoided that
  unverified shared-control issue.

## Conductor retry: scoped mediator and repeatable reset

- Re-read the complete task and reproduced the requested gates without changing
  shared files or other worktrees. API fast checks reproduced the three
  framework failures. The full loaded run also reproduced the claim-history
  test's artificial 30-second timeout (68 seconds including setup/cleanup).
- Reproduced the exact no-report reset failure on an exclusively owned ordinary
  host: health 200, two resets 200, real package creation 201, reset 500, and
  unchanged `contract.replay --reset-url` exit 1 without a report.
- Root cause: `AddApplication` registers a singleton mediator whose provider is
  the root. Resolving a package handler pins its scoped artifact-byte lease at
  that root; `ArtifactGenerations.Reset` then cannot drain its users.
- Registered the existing mediator as scoped in `AddClaimsArtifactsRules`.
  This uses ordinary feature registration, not a second startup graph, temporary
  provider, service-location fallback or edited shared host. Handler scopes and
  byte leases now end with the request.
- Added a same-host create/download/reset/publish/download/reset regression.
  The standalone diagnostic script proves both before/after outcomes. Reset
  now returns 200 after publication; conductor-style replay writes its report.
  It still exits 1 for real semantic differences, which are not waived.
- Classified the measured slow claim-history test as heavy and removed its
  artificial timeout, retaining all history/conflict/isolation assertions.
  Fixed the heavy P2 test's invalid attempt to set HttpClient.Timeout after
  its first request, and added a reset-success assertion. The P2 test now passes.
- All 12 feature tests pass together (two minutes, including P2 at 112 seconds).
  Final full fast check: 720 tests, 717 pass, three framework failures.
  Whole-solution warning-as-error build and format verification pass.
- Re-ran all seven complete scenarios: still 156/397 owned cases, 39.29% raw.
  Fresh raw evidence is under `revision-replay`; no comparator, recording,
  threshold or waiver policy changed. Removed only that runner's inspected
  temporary synthetic `state` subtree after its owned hosts exited.
- Implementation commit: `2cd6769`. Shared-test/composition work still requires
  edits outside the fixed allocation. The mandatory HALT remains; this retry
  repairs reset and feature-test defects but does not claim task acceptance.

## Second conductor retry: rejected improvement scope

- The supplied gate rejected IMP-routes_claims-4 for covering an artifact-ID
  mismatch. It described formula safety but matched the entire package-create
  response. Narrowed it to the actual downloaded Provenance XML member and
  narrowed the integrity entry to status. Neither entry now matches the real
  artifact-ID discrepancy. IDs and calculated values are not waived.
- Committed the register correction as `3054859`; no product code, test
  assertion, recording, comparator or threshold changed.
- Reran build, format and all fast tests. Build/format pass; fast results remain
  717 pass, three shared framework failures, 720 total.
- Reran all twelve full scenarios against exclusively owned ordinary hosts.
  All raw reports exist: 1,769 exchanges and 7,702 failing fields across groups.
  Exact method/template ownership gives 98/316 raw passing owned cases (31.01%),
  without waivers. The supplied conductor reported 80/316 adjusted (25.3%).
  These are different runs/engines; neither is a passing acceptance result.
- The legacy wrapper's 397 route-shape cases are explicitly not the conductor
  denominator. Gateway-only scenarios produce its no-owned-group diagnostic
  after their unchanged replay reports are written; they were not skipped.
- Shared assertions/composition remain outside the task's fixed allocation.
  The mandatory HALT remains rather than manufacturing a 501, hiding handlers,
  removing tests or treating a request to retry as unrestricted ownership.
- Removed only the inspected retry2 runner's temporary synthetic state subtree
  after all its owned hosts exited. No shared process or worktree was changed.

## Third conductor retry: stop repeated unchanged failures

- Read the task file in full again and re-read both shared 501 assertions.
  Ownership and hard stops are unchanged; no shared test edit is authorized.
- Inspected the newly rejected `IMP-sources_auth_ai-2`: it is a broad entry
  about atomic byte publication in the other feature's register. It cannot
  legitimately cover an artifact-ID mismatch. No waiver or ID workaround was
  added, and that register was not changed to conceal the discrepancy.
- Recorded the latest supplied conductor result: 78/316 adjusted (24.7%),
  seven waived, and the same three framework failures. The earlier local
  results remain historical evidence, not freshly claimed runs.
- No product changes or redundant full-suite/replay runs on this retry.
  Hard stop 3 now independently ends repeated attempts on the unchanged
  ownership blocker. Updated finish JSON and reports only, retaining HALT.
